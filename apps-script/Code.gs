/**
 * Brayden's Command Center — serverless sync engine.
 *
 * Runs entirely in Google's cloud on a time-driven trigger (no laptop needed).
 * Fetches weather/commute/markets/calendar, writes the result as JSON into
 * Script Properties, and serves it via doGet() as a Web App endpoint that
 * the Streamlit dashboard polls.
 */

// ---- Config ----
const HOME_LAT = 46.2423683;
const HOME_LON = -79.2526926;
const DEST_LAT = 46.3204083;
const DEST_LON = -79.4397409;
const DEST_LABEL = "103 Laurentian Ave, North Bay";
const NTFY_TOPIC = "brayden-command-center-6513";

function runSync() {
  const health = loadHealth();
  const state = {
    last_synced: Utilities.formatDate(new Date(), "America/Toronto", "yyyy-MM-dd'T'HH:mm:ss"),
    weather: null,
    calendar_events: [],
    commute: null,
    alerts: [],
    indices: [],
  };

  const weather = withHealth(health, "weather", fetchWeather);
  if (weather) state.weather = weather;

  const calendarEvents = withHealth(health, "calendar", () => fetchCalendarEvents(weather));
  if (calendarEvents) state.calendar_events = calendarEvents;

  const commute = withHealth(health, "traffic", fetchCommute);
  if (commute) {
    state.commute = { minutes: commute.minutes, destination: DEST_LABEL };
    if (commute.minutes > 30) {
      state.alerts.push({ severity: "red", message: `Commute to North Bay is running ${commute.minutes} min today — you'll be late leaving 30 min ahead.${commute.incidentNote || ""}` });
    } else if (commute.minutes > 25) {
      state.alerts.push({ severity: "yellow", message: `Commute to North Bay is running ${commute.minutes} min today — cutting it close with your usual 30 min buffer.${commute.incidentNote || ""}` });
    }
  }

  const weatherAlert = withHealth(health, "weather_alerts", fetchWeatherStatement);
  if (weatherAlert) state.alerts.push(weatherAlert);

  const indices = withHealth(health, "markets", fetchMarketIndices);
  if (indices) state.indices = indices;

  if (state.weather) {
    delete state.weather._hourly; // internal-only field, don't leak it to the dashboard
  }

  const redAlerts = state.alerts.filter((a) => a.severity === "red");
  redAlerts.forEach((a) => pushNotification(a.message));

  saveHealth(health);
  PropertiesService.getScriptProperties().setProperty("state", JSON.stringify(state));
}

function doGet(e) {
  const state = PropertiesService.getScriptProperties().getProperty("state");
  return ContentService.createTextOutput(state || "{}").setMimeType(ContentService.MimeType.JSON);
}

// ---- Sync health (retry-once, notify-once-then-throttle) ----

function loadHealth() {
  const raw = PropertiesService.getScriptProperties().getProperty("health");
  return raw ? JSON.parse(raw) : {};
}

function saveHealth(health) {
  PropertiesService.getScriptProperties().setProperty("health", JSON.stringify(health));
}

function withHealth(health, key, fn) {
  const prev = health[key] || { status: "ok", last_pinged: null };
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const result = fn();
      health[key] = { status: "ok", last_pinged: null };
      return result;
    } catch (err) {
      if (attempt === 1) {
        const now = new Date().getTime();
        const shouldPing = prev.status === "ok" || !prev.last_pinged || (now - prev.last_pinged) > 24 * 60 * 60 * 1000;
        if (shouldPing) {
          pushNotification(`Command Center: ${key} sync failed — ${err.message}`);
          health[key] = { status: "failing", last_pinged: now };
        } else {
          health[key] = prev;
        }
        return null;
      }
    }
  }
  return null;
}

function pushNotification(message) {
  try {
    UrlFetchApp.fetch(`https://ntfy.sh/${NTFY_TOPIC}`, {
      method: "post",
      payload: message,
      muteHttpExceptions: true,
    });
  } catch (e) {
    // Best-effort — don't let a notification failure break the sync.
  }
}

// ---- Weather ----

function fetchWeather() {
  const url = `https://api.open-meteo.com/v1/forecast?latitude=${HOME_LAT}&longitude=${HOME_LON}` +
    `&current=temperature_2m,weather_code,is_day&hourly=precipitation_probability,weather_code,temperature_2m` +
    `&daily=temperature_2m_max,temperature_2m_min&timezone=America/Toronto&forecast_days=4`;
  const data = JSON.parse(UrlFetchApp.fetch(url).getContentText());
  const code = data.current.weather_code;
  const result = {
    temp_now: Math.round(data.current.temperature_2m),
    condition_now: conditionLabel(code),
    temp_high: Math.round(data.daily.temperature_2m_max[0]),
    temp_low: Math.round(data.daily.temperature_2m_min[0]),
    code: code,
    is_day: data.current.is_day === 1,
    _hourly: data.hourly, // internal use for weather-at-event, stripped before writing
  };

  const nowHour = new Date().getHours();
  const probs = data.hourly.precipitation_probability.slice(nowHour, nowHour + 4);
  if (probs.length && probs[0] < 40) {
    for (let i = 1; i < probs.length; i++) {
      if (probs[i] >= 50) {
        result.precip_soon = `Rain likely in ~${i}h`;
        break;
      }
    }
  }
  return result;
}

function conditionLabel(code) {
  if (code === 0) return "Clear sky";
  if ([1, 2, 3].includes(code)) return "Partly cloudy";
  if ([45, 48].includes(code)) return "Fog";
  if (code >= 51 && code <= 67) return "Rain";
  if ([80, 81, 82].includes(code)) return "Rain showers";
  if (code >= 71 && code <= 77) return "Snow";
  if ([85, 86].includes(code)) return "Snow showers";
  if (code >= 95) return "Thunderstorm";
  return "Partly cloudy";
}

// ---- Calendar ----

function fetchCalendarEvents(weather) {
  const cal = CalendarApp.getDefaultCalendar();
  const now = new Date();
  const end = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
  const events = cal.getEvents(now, end);
  return events.map((ev) => {
    const start = ev.getStartTime();
    const entry = {
      date: Utilities.formatDate(start, "America/Toronto", "yyyy-MM-dd"),
      time: ev.isAllDayEvent() ? "All day" : Utilities.formatDate(start, "America/Toronto", "h:mm a"),
      title: ev.getTitle(),
    };
    const location = ev.getLocation();
    if (location) {
      const eta = computeEta(location);
      if (eta) {
        entry.eta_minutes = eta.minutes;
        const leaveBy = new Date(start.getTime() - (eta.minutes + 5) * 60000);
        entry.leave_by = Utilities.formatDate(leaveBy, "America/Toronto", "h:mm a");
      }
    }
    if (weather && /tee time|golf/i.test(entry.title)) {
      const note = weatherAtHour(weather, start);
      if (note) entry.weather_note = note;
    }
    return entry;
  });
}

function weatherAtHour(weather, when) {
  if (!weather._hourly) return null;
  const hoursFromNow = Math.round((when.getTime() - Date.now()) / 3600000);
  if (hoursFromNow < 0 || hoursFromNow >= weather._hourly.temperature_2m.length) return null;
  const temp = Math.round(weather._hourly.temperature_2m[hoursFromNow]);
  const code = weather._hourly.weather_code[hoursFromNow];
  return `${temp}° · ${conditionLabel(code)}`;
}

function computeEta(location) {
  try {
    const geo = JSON.parse(UrlFetchApp.fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(location)}&format=json&limit=1`
    ).getContentText());
    if (!geo.length) return null;
    const lat = geo[0].lat, lon = geo[0].lon;
    const route = JSON.parse(UrlFetchApp.fetch(
      `http://router.project-osrm.org/route/v1/driving/${HOME_LON},${HOME_LAT};${lon},${lat}?overview=false`
    ).getContentText());
    if (!route.routes || !route.routes.length) return null;
    return { minutes: Math.ceil(route.routes[0].duration / 60) };
  } catch (e) {
    return null;
  }
}

// ---- Traffic ----

function fetchCommute() {
  const route = JSON.parse(UrlFetchApp.fetch(
    `http://router.project-osrm.org/route/v1/driving/${HOME_LON},${HOME_LAT};${DEST_LON},${DEST_LAT}?overview=false`
  ).getContentText());
  const minutes = Math.round(route.routes[0].duration / 60);
  let incidentNote = "";
  try {
    const events = JSON.parse(UrlFetchApp.fetch("https://511on.ca/api/v2/get/event").getContentText());
    const relevant = events.filter((ev) => {
      const desc = (ev.RoadwayName || "") + " " + (ev.Description || "");
      return /hwy 17|highway 17/i.test(desc) && /north bay|corbeil|callander|astorville/i.test(desc);
    });
    if (relevant.length) incidentNote = " Live incident reported near North Bay on Hwy 17.";
  } catch (e) {
    // best-effort, ignore
  }
  return { minutes: minutes, incidentNote: incidentNote };
}

// ---- Weather statements ----

function fetchWeatherStatement() {
  const html = UrlFetchApp.fetch("https://weather.gc.ca/warnings/report_e.html?onrm119=").getContentText();
  if (/no watches or warnings/i.test(html)) return null;
  const knownTypes = ["Tornado Warning", "Severe Thunderstorm Warning", "Heat Warning", "Winter Storm Warning",
    "Freezing Rain Warning", "Wind Warning", "Special Weather Statement", "Frost Advisory"];
  for (const type of knownTypes) {
    if (html.indexOf(type) !== -1) {
      const severity = /Tornado|Severe Thunderstorm|Winter Storm/.test(type) ? "red" : "yellow";
      return { severity: severity, message: `${type} in effect for North Bay - Powassan - Mattawa.` };
    }
  }
  return null;
}

// ---- Markets ----

function fetchMarketIndices() {
  const symbols = [
    { name: "S&P 500", symbol: "%5EGSPC" },
    { name: "Nasdaq", symbol: "%5EIXIC" },
    { name: "Dow", symbol: "%5EDJI" },
    { name: "TSX", symbol: "%5EGSPTSE" },
  ];
  const results = [];
  symbols.forEach((s) => {
    try {
      const data = JSON.parse(UrlFetchApp.fetch(
        `https://query1.finance.yahoo.com/v8/finance/chart/${s.symbol}`
      ).getContentText());
      const meta = data.chart.result[0].meta;
      const price = meta.regularMarketPrice;
      const prevClose = meta.previousClose || meta.chartPreviousClose;
      const changePct = ((price - prevClose) / prevClose) * 100;
      results.push({
        name: s.name,
        price: price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        change_pct: Math.round(changePct * 100) / 100,
      });
    } catch (e) {
      // skip this index if it fails, don't fail the whole step
    }
  });
  if (!results.length) throw new Error("all market indices failed");
  return results;
}
