"""One auto-generated sentence combining weather, precipitation, air
quality/wildfire, commute, today's agenda, and household status —
instead of reading five separate tiles and mentally combining them
yourself. Only shown during MORNING_WINDOW.

Deliberately built from many distinct phrasings per condition (not one
template with values plugged in) so it reads as actually written about
today, not a form letter — see the *_LINES lists below. Which variant
gets picked is stable for the whole day (seeded by the date + a salt
per category, not re-randomized every rerun), so it doesn't visibly
change every 5 seconds, but still varies day to day even when the
underlying numbers land in the same bucket twice in a row.

Global, not page-local (like commute_reminder.render_leave_headline) —
the whole point is catching you during the actual morning routine,
regardless of which of the 10 rotating pages happens to be up.
"""

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from astral import LocationInfo
from astral.sun import sun

import calendar_client
import commute_client
import commute_reminder
import ec_alerts
import ec_radar
import fuel_price_client
import market_yf_client
import waste_schedule
import wildfire_client
from config import AQI_SHOW_THRESHOLD, COMMUTE_DESTINATION, TIMEZONE, WEATHER_LAT, WEATHER_LON
from scenery import condition_category

MORNING_WINDOW_START_HOUR = 5
MORNING_WINDOW_END_HOUR = 10

# Was 3 — widened so a morning that's genuinely eventful (an active
# alert AND rain closing in AND a packed calendar) can actually say all
# of it, instead of silently dropping whichever lost the priority sort.
MAX_CLAUSES = 5

# Duplicated from weather_client rather than imported — same convention
# as this app's other small per-module geo/time math (see ec_radar.py's
# own haversine/bearing helpers): this only needs day length, not a full
# weather fetch, so it's cheaper and more self-contained to compute it
# locally than to widen weather_client's return contract for one caller.
_LOCATION = LocationInfo(latitude=WEATHER_LAT, longitude=WEATHER_LON, timezone=TIMEZONE)

GREETINGS = ["", "", "", "Morning — ", "Good morning. ", "Rise and shine — ", "Here's the rundown: "]

HEAT_LINES = [
    "it's already {temp}°C — bracing for a scorcher, high near {high}°C",
    "{temp}°C and climbing, today's shaping up to be a hot one up to {high}°C",
    "heat's on early, {temp}°C now and headed for {high}°C by afternoon",
    "{temp}°C already — today's going to be a sweaty one, {high}°C expected",
]
WARM_LINES = [
    "warm start at {temp}°C, climbing to {high}°C — good day to be outside",
    "{temp}°C this morning, {high}°C expected, proper shorts weather",
    "a warm one on tap, {temp}°C now on the way to {high}°C",
    "{temp}°C out already, nice and warm, topping out near {high}°C",
]
MILD_LINES = [
    "a comfortable {temp}°C to start the day",
    "{temp}°C out there, pretty pleasant, high of {high}°C expected",
    "mild morning, {temp}°C, nothing to complain about",
    "{temp}°C right now, easy weather, {high}°C by afternoon",
]
COOL_LINES = [
    "cooler start, {temp}°C — worth a jacket on your way out",
    "{temp}°C this morning, a bit brisk before it warms to {high}°C",
    "chilly-ish, {temp}°C now, {high}°C by afternoon",
    "{temp}°C out, cool enough for a light layer",
]
COLD_LINES = [
    "it's {temp}°C — bundle up before you head out",
    "{temp}°C this morning, proper cold, high only {high}°C",
    "cold one, {temp}°C now, dress for it",
    "{temp}°C out there, winter's not messing around today",
]

RADAR_RAIN_LINES = [
    "radar's picking up rain heading your way, could hit in about {eta} min",
    "rain's closing in on the radar, roughly {eta} minutes out",
    "heads up, rain looks to be moving in, ETA around {eta} minutes",
]
RADAR_SNOW_LINES = [
    "radar's picking up snow heading your way, could hit in about {eta} min",
    "snow's closing in on the radar, roughly {eta} minutes out",
    "heads up, snow looks to be moving in, ETA around {eta} minutes",
]
ARRIVED_RAIN_LINES = [
    "rain's here now, radar's got it clearing in about {eta} min",
    "it's raining now, should clear up in roughly {eta} minutes",
]
ARRIVED_SNOW_LINES = [
    "snow's here now, radar's got it clearing in about {eta} min",
    "it's snowing now, should clear up in roughly {eta} minutes",
]
FORECAST_RAIN_LINES = [
    "rain's in the forecast today, {chance}% chance around {time} — grab an umbrella on your way out",
    "looks like rain later, {chance}% chance near {time}",
    "{chance}% chance of rain today, expected around {time}",
]
FORECAST_SNOW_LINES = [
    "snow's in the forecast today, {chance}% chance around {time} — plan accordingly",
    "looks like snow later, {chance}% chance near {time}",
    "{chance}% chance of snow today, expected around {time}",
]
CLEAR_SKY_LINES = [
    "skies look clear for now",
    "no rain in the forecast, small mercies",
    "dry morning ahead, nothing on the radar",
]

WILDFIRE_LINES = [
    "air quality's rough today ({aqi}) — looks like smoke from a wildfire about {distance:.0f}km out",
    "hazy out, {aqi} AQI, likely wildfire smoke drifting in from roughly {distance:.0f}km away",
    "air's not great this morning ({aqi}), wildfire smoke nearby, closest fire about {distance:.0f}km off",
]
AQI_ONLY_LINES = [
    "air quality's elevated today ({aqi}) — maybe skip the outdoor workout",
    "AQI's sitting at {aqi}, a bit rough for being outside long",
]

COMMUTE_BAD_LINES = [
    "commute's rough this morning, {delay} extra minutes{reason}",
    "roads are backed up, {delay} min of delay heading to {destination}{reason}",
    "give yourself extra time, {delay} minutes of traffic on the way to {destination}{reason}",
]
COMMUTE_MINOR_LINES = [
    "a few extra minutes on the roads today, {duration} min total to {destination}",
    "light traffic, {delay} min slower than usual heading to {destination}",
]
COMMUTE_CLEAR_LINES = [
    "roads are clear, {duration} min to {destination} like normal",
    "smooth drive in today, {duration} minutes to {destination}",
    "no delays on the way to {destination}, {duration} min as usual",
]

AGENDA_BUSY_LINES = [
    "packed day, {count} things on the calendar, starting with {first_event} at {time}",
    "busy one today, {count} on the books, kicking off with {first_event} at {time}",
]
AGENDA_LIGHT_LINES = [
    "just {first_event} at {time} on the calendar today",
    "light schedule, {first_event} at {time} is the main thing today",
]
AGENDA_EMPTY_LINES = [
    "calendar's wide open today",
    "nothing on the agenda, a rare quiet one",
    "no events today, a blank slate",
]

GARBAGE_LINES = [
    "bins go out tonight, it's {kind} day",
    "don't forget: {kind} day today",
]
GAS_ECO_LINES = [
    "gas ticked up to {price:.1f}¢, might hold off on filling up if you can",
    "prices are up ({price:.1f}¢/L), eco mode's worth it today",
]

ALERT_LINES = [
    "heads up: {title}",
    "worth knowing this morning — {title}",
    "one to watch: {title}",
]

MARKET_UP_LINES = [
    "markets are green so far, S&P +{pct}%",
    "S&P's up {pct}% this morning",
    "green start for the market, up {pct}%",
]
MARKET_DOWN_LINES = [
    "markets are red this morning, S&P -{pct}%",
    "S&P's down {pct}% so far",
    "a rough start for the market, off {pct}%",
]
MARKET_FLAT_LINES = [
    "markets are flat this morning",
    "S&P's roughly unchanged so far",
]

# Deliberately the lowest-priority clause of all of them (see its
# priority=1 below) — it's always available (every day has a sunrise and
# sunset), so without a low priority it would crowd out genuinely
# time-sensitive info on a busy morning. It's here for the quieter days,
# to tie the daily routine to the bigger, slower cycle behind it.
DAYLIGHT_GAINING_LINES = [
    "days are stretching out — {delta} more minutes of daylight than yesterday, sunset at {sunset}",
    "gaining daylight now, {delta} minutes more than yesterday",
    "the days keep growing, {delta} extra minutes of light today",
]
DAYLIGHT_LOSING_LINES = [
    "days are shrinking — {delta} fewer minutes of daylight than yesterday, sunset at {sunset}",
    "losing daylight now, {delta} minutes less than yesterday",
    "the days are contracting, {delta} fewer minutes of light today",
]


def _pick(options: list[str], now: datetime, salt: str) -> str:
    rng = random.Random(f"{now.date().isoformat()}-{salt}")
    return rng.choice(options)


def _weather_clause(now: datetime, weather: dict) -> tuple[int, str] | None:
    temp = weather.get("temp_c")
    high = weather.get("forecast_high_c")
    if temp is None:
        return None
    high_text = f"{high:.0f}" if high is not None else f"{temp:.0f}"
    fmt = {"temp": f"{temp:.0f}", "high": high_text}
    if temp >= 30:
        lines = HEAT_LINES
    elif temp >= 22:
        lines = WARM_LINES
    elif temp >= 12:
        lines = MILD_LINES
    elif temp >= 0:
        lines = COOL_LINES
    else:
        lines = COLD_LINES
    return 3, _pick(lines, now, "weather").format(**fmt)


def _precip_clause(now: datetime, weather: dict, category: str) -> tuple[int, str] | None:
    status = ec_radar.precip_status("snow" if category == "snow" else "rain")
    if status is not None and status["minutes"] is not None:
        is_snow = category == "snow"
        if status["state"] == "arrived":
            lines = ARRIVED_SNOW_LINES if is_snow else ARRIVED_RAIN_LINES
        else:
            lines = RADAR_SNOW_LINES if is_snow else RADAR_RAIN_LINES
        return 8, _pick(lines, now, "precip").format(eta=status["minutes"])

    rain_at = weather.get("rain_at")
    chance = weather.get("precip_chance")
    if rain_at is not None and chance is not None:
        is_snow = weather.get("precip_kind") == "snow"
        lines = FORECAST_SNOW_LINES if is_snow else FORECAST_RAIN_LINES
        time_text = rain_at.strftime("%I:%M %p").lstrip("0")
        return 7, _pick(lines, now, "precip").format(chance=chance, time=time_text)

    return 1, _pick(CLEAR_SKY_LINES, now, "precip")


def _air_clause(now: datetime, air_quality: dict | None) -> tuple[int, str] | None:
    aqi = air_quality.get("us_aqi") if air_quality else None
    if aqi is None or aqi <= AQI_SHOW_THRESHOLD:
        return None
    wildfire = wildfire_client.nearest_wildfire()
    if wildfire is not None:
        text = _pick(WILDFIRE_LINES, now, "air").format(aqi=round(aqi), distance=wildfire["distance_km"])
        return 8, text
    return 5, _pick(AQI_ONLY_LINES, now, "air").format(aqi=round(aqi))


def _commute_clause(now: datetime) -> tuple[int, str] | None:
    destination = commute_reminder.todays_destination(now)
    using_default = destination is COMMUTE_DESTINATION
    data = commute_client.route(None if using_default else destination)
    if not data:
        return None
    duration = round(data["duration_seconds"] / 60)
    delay = round(data["delay_seconds"] / 60)
    dest_label = destination["label"]
    if delay >= 10:
        reason = f", mostly {data['incident']}" if data.get("incident") else ""
        text = _pick(COMMUTE_BAD_LINES, now, "commute").format(
            delay=delay, destination=dest_label, reason=reason
        )
        return 6, text
    if delay >= 1:
        text = _pick(COMMUTE_MINOR_LINES, now, "commute").format(delay=delay, duration=duration, destination=dest_label)
        return 4, text
    text = _pick(COMMUTE_CLEAR_LINES, now, "commute").format(duration=duration, destination=dest_label)
    return 2, text


def _agenda_clause(now: datetime) -> tuple[int, str] | None:
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return None
    events = [e for e in calendar_client.todays_events(calendars, now.date()) if not e["all_day"]]
    if not events:
        return 1, _pick(AGENDA_EMPTY_LINES, now, "agenda")
    events.sort(key=lambda e: e["start"])
    first = events[0]
    time_text = first["start"].strftime("%I:%M %p").lstrip("0")
    if len(events) >= 3:
        text = _pick(AGENDA_BUSY_LINES, now, "agenda").format(
            count=len(events), first_event=first["summary"], time=time_text
        )
        return 5, text
    text = _pick(AGENDA_LIGHT_LINES, now, "agenda").format(first_event=first["summary"], time=time_text)
    return 3, text


def _household_clause(now: datetime) -> tuple[int, str] | None:
    pickup = waste_schedule.next_pickup(now.date())
    if pickup["days_until"] == 0:
        return 4, _pick(GARBAGE_LINES, now, "household").format(kind=pickup["kind"].lower())
    gas = fuel_price_client.eco_mode_status()
    if gas and gas["eco_recommended"]:
        return 2, _pick(GAS_ECO_LINES, now, "household").format(price=gas["price"])
    return None


def _alert_clause(now: datetime) -> tuple[int, str] | None:
    alerts = ec_alerts.fetch_alerts()
    if not alerts:
        return None
    text = _pick(ALERT_LINES, now, "alert").format(title=alerts[0]["title"])
    return 10, text


def _markets_clause(now: datetime) -> tuple[int, str] | None:
    status = market_yf_client.market_status(now)
    if status == "weekend":
        return None
    symbol = market_yf_client.primary_symbol(status)
    quote = market_yf_client.quote_for(symbol)
    if not quote or quote["intraday"] is None:
        return None
    pct = quote["intraday"]
    fmt = {"pct": f"{abs(pct):.1f}"}
    if pct >= 0.15:
        lines = MARKET_UP_LINES
    elif pct <= -0.15:
        lines = MARKET_DOWN_LINES
    else:
        lines = MARKET_FLAT_LINES
    return 3, _pick(lines, now, "markets").format(**fmt)


def _day_length_minutes(day) -> float:
    s = sun(_LOCATION.observer, date=day, tzinfo=ZoneInfo(TIMEZONE))
    return (s["sunset"] - s["sunrise"]).total_seconds() / 60


def _daylight_clause(now: datetime, weather: dict) -> tuple[int, str] | None:
    sunset = weather.get("sunset")
    if sunset is None:
        return None
    try:
        today_len = _day_length_minutes(now.date())
        yesterday_len = _day_length_minutes(now.date() - timedelta(days=1))
    except Exception:
        return None
    delta = round(today_len - yesterday_len)
    if delta == 0:
        return None
    fmt = {"delta": abs(delta), "sunset": sunset.strftime("%I:%M %p").lstrip("0")}
    lines = DAYLIGHT_GAINING_LINES if delta > 0 else DAYLIGHT_LOSING_LINES
    return 1, _pick(lines, now, "daylight").format(**fmt)


def render(now: datetime, weather: dict | None, air_quality: dict | None) -> None:
    if not (MORNING_WINDOW_START_HOUR <= now.hour < MORNING_WINDOW_END_HOUR):
        return
    if not weather:
        return

    category = condition_category(weather["weather_code"])
    clauses = []
    for fn, args in (
        (_alert_clause, (now,)),
        (_weather_clause, (now, weather)),
        (_precip_clause, (now, weather, category)),
        (_air_clause, (now, air_quality)),
        (_commute_clause, (now,)),
        (_agenda_clause, (now,)),
        (_household_clause, (now,)),
        (_markets_clause, (now,)),
        (_daylight_clause, (now, weather)),
    ):
        try:
            result = fn(*args)
        except Exception:
            result = None
        if result is not None:
            clauses.append(result)

    if not clauses:
        return
    clauses.sort(key=lambda c: c[0], reverse=True)
    picked = [text for _, text in clauses[:MAX_CLAUSES]]
    sentence = "; ".join(picked)
    sentence = sentence[0].upper() + sentence[1:] + "."
    greeting = _pick(GREETINGS, now, "greeting")

    st.markdown(f'<div class="morning-briefing">{greeting}{sentence}</div>', unsafe_allow_html=True)
