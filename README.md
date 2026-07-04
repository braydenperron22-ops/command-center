# Brayden's Command Center

Always-on personal dashboard: date/time, weather, calendar agenda, email highlights,
commute/ETA tracking, and a task/reminder list.

## Running it

```
pip install -r requirements.txt
streamlit run app.py
```

Leave the browser tab open on the always-on laptop/monitor. It auto-refreshes every
15 seconds (fast enough for the "leave now" countdown and page rotation to feel live).

## How data gets in

Tasks/reminders are added directly in the app UI (stored in `data/tasks.json`), but
the scheduled sync also appends tasks automatically from actionable email (see below).

The look is built on [theme.py](theme.py) (typography, hidden Streamlit chrome, glass
card styling), [scenery.py](scenery.py) (soft ambient gradient + particles reacting to
weather), and [icons.py](icons.py) (minimal line-art weather icons) — deliberately
understated rather than a busy dashboard.

## Page rotation

To avoid cramming everything onto one screen, the content area below the hero rotates
between two views on a 60-second cycle (`config.ROTATION_CYCLE_SECONDS` /
`ROTATION_EXTRAS_SECONDS`): 45s on the main view (Today/Upcoming agenda, Needs a Look,
Tasks & Reminders), 15s on an "extras" view (3-day outlook, Deliveries). The hero
(clock, weather, commute) and any alert/leave-now banners stay visible the whole time.

## "Leave now" banner

If any calendar event's computed `leave_by` time is within 15 minutes (or up to 20 min
past), a banner appears above the agenda: yellow while there's still time, red once
it's within 5 minutes or past due.

## The scheduled sync

Weather, calendar, email, traffic, and alerts all come from `data/state.json`, written
by a **scheduled Claude task** (`command-center-sync`, not this app) running every 20
minutes. Each run:

1. **Weather** — Open-Meteo (no key), home = Ouellette Road, Corbeil (lat 46.2423683,
   lon -79.2526926). Also computes a rain/snow nowcast (`precip_soon`, e.g. "Rain
   likely in ~45 min") from hourly precipitation probability, and a 3-day outlook.
2. **Calendar** — lists events for the next 7 days via the connected Calendar MCP.
   Events with a `location` get `eta_minutes`/`leave_by` computed via Nominatim
   (geocoding) + OSRM (driving time from home).
3. **Email** — scans the last 14 days of inbox (**not just unread** — Brayden is
   forgetful, so already-opened-but-unactioned mail counts too), filtered to genuine
   necessities (personal/security alerts, real people needing a response). Skips
   anything already handled (a linked task marked done).
4. **Auto-creates things from email**: concrete appointments become Google Calendar
   events (duplicate-checked first); other actionable items (bills, forms, RSVPs)
   become tasks in `tasks.json` with a `source_email_id` so they're never duplicated
   and stop resurfacing once marked done.
5. **Deliveries** — shipping/tracking emails still in transit surface on the extras
   page.
6. **Commute** — live Corbeil → 103 Laurentian Ave (North Bay) drive time (OSRM) plus
   real incident data on that specific stretch (511 Ontario API). Over 25 min = yellow
   alert, over 30 min = red (Brayden leaves 30 min before things).
7. **Weather statements** — live Environment Canada alerts page (not web search, which
   surfaces stale articles that look current).
8. **News** — breaking financial/national/local news, only when genuinely current.

### Self-healing sync

Each external source (Gmail, Calendar, weather, traffic, weather alerts) is tracked in
`data/sync_health.json`. On failure the task retries once silently. If still failing:
a first-time failure sends one push notification (via `PushNotification`) so Brayden
knows something needs manual attention (e.g. reconnecting Gmail); a *known*, ongoing
failure stays silent and only re-pings once every 24h, rather than every 20 minutes.
Recovery is silent — no "it's fixed" notification, it just resumes working.

### state.json shape

```json
{
  "last_synced": "2026-07-04T13:00:00",
  "weather": {
    "temp_now": 24, "condition_now": "Partly cloudy", "temp_high": 27, "temp_low": 16,
    "code": 2, "is_day": true, "precip_soon": "Rain likely in ~45 min"
  },
  "calendar_events": [
    {"date": "2026-07-06", "time": "2:00 PM", "title": "Dentist appointment", "eta_minutes": 22, "leave_by": "1:33 PM"}
  ],
  "email_highlights": [{"from": "Air Canada", "subject": "Your flight is confirmed"}],
  "commute": {"minutes": 24, "destination": "103 Laurentian Ave, North Bay"},
  "alerts": [{"severity": "red", "message": "Severe thunderstorm warning with tornado risk this afternoon near North Bay."}],
  "outlook": [{"day": "Mon", "condition": "Rain", "high": 21, "low": 14}],
  "deliveries": [{"label": "Amazon — phone case", "eta": "Arriving today"}]
}
```

`weather.code`/`weather.is_day` drive the animated background scene in
[scenery.py](scenery.py). `alerts` renders as a stacked, color-coded banner
([alerts.py](alerts.py)), sorted red > yellow > neutral.

This app never calls those APIs/MCP tools itself — it only reads the JSON files the
scheduled task maintains. If `state.json` is missing or stale (>2x the sync interval),
the dashboard shows a warning instead of guessing.
