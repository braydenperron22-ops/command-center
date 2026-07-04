# Brayden's Command Center

Always-on personal dashboard: date/time, weather, calendar agenda (with per-event ETA
and weather-at-tee-time), email highlights, and commute tracking. Single page, no
clutter — no tasks list, no rotating secondary view.

## Running it

```
pip install -r requirements.txt
streamlit run app.py
```

Leave the browser tab open on the always-on laptop/monitor. It auto-refreshes every
15 seconds, fast enough for the "leave now" countdown to feel live.

## The look

Built on [theme.py](theme.py) (typography, hidden Streamlit chrome, glass card
styling), [scenery.py](scenery.py) (soft ambient gradient + particles reacting to
weather), and [icons.py](icons.py) (minimal line-art weather icons) — deliberately
understated rather than a busy dashboard.

## "Leave now" banner

If any calendar event's computed `leave_by` time is within 15 minutes (or up to 20 min
past), a banner appears above the agenda: yellow while there's still time, red once
it's within 5 minutes or past due. This is computed client-side by the app itself from
`leave_by`, not something the sync pushes.

## The scheduled sync

Weather, calendar, email, traffic, and alerts come from `data/state.json`, written by
a **scheduled Claude task** (`command-center-sync`, not this app) running every 15
minutes. Each run:

1. **Weather** — Open-Meteo (no key), home = Ouellette Road, Corbeil (lat 46.2423683,
   lon -79.2526926). Computes a rain/snow nowcast (`precip_soon`) from hourly
   precipitation probability.
2. **Calendar** — lists events for the next 7 days via the connected Calendar MCP.
   Events with a `location` get `eta_minutes`/`leave_by` (Nominatim geocoding + OSRM
   driving time from home). Outdoor/golf events (tee times) get a `weather_note` for
   that specific hour instead.
3. **Email** — scans the last 14 days of inbox (not just unread — Brayden is
   forgetful, so already-opened-but-unactioned mail counts too), filtered to genuine
   necessities.
4. **Auto-creates calendar events** from concrete appointments/tee-times found in
   email (duplicate-checked first). Non-appointment actionable mail (bills, forms)
   just surfaces via email_highlights — there's no separate task list.
5. **Commute** — live Corbeil → 103 Laurentian Ave (North Bay) drive time (OSRM) plus
   real incident data on that specific stretch (511 Ontario API). Over 25 min =
   yellow alert, over 30 min = red (Brayden leaves 30 min before things).
6. **Weather statements** — live Environment Canada alerts page (not web search,
   which surfaces stale articles that look current).
7. **News** — breaking financial/national/local news, only when genuinely current.
8. Any **red-severity alert** also triggers an immediate push notification (not just
   a dashboard entry) — Brayden may not be looking at the screen.

### Self-healing sync

Each external source (Gmail, Calendar, weather, traffic, weather alerts) is tracked in
`data/sync_health.json`. On failure the task retries once silently. If still failing:
a first-time failure sends one push notification; a *known*, ongoing failure stays
silent and only re-pings once every 24h rather than every run. Recovery is silent.

### state.json shape

```json
{
  "last_synced": "2026-07-04T13:00:00",
  "weather": {
    "temp_now": 24, "condition_now": "Partly cloudy", "temp_high": 27, "temp_low": 16,
    "code": 2, "is_day": true, "precip_soon": "Rain likely in ~45 min"
  },
  "calendar_events": [
    {"date": "2026-07-06", "time": "2:00 PM", "title": "Dentist appointment", "eta_minutes": 22, "leave_by": "1:33 PM"},
    {"date": "2026-07-04", "time": "6:00 PM", "title": "Tee time — Highview Golf Course", "weather_note": "22° · Clear sky"}
  ],
  "email_highlights": [{"from": "Air Canada", "subject": "Your flight is confirmed"}],
  "commute": {"minutes": 24, "destination": "103 Laurentian Ave, North Bay"},
  "alerts": [{"severity": "red", "message": "Severe thunderstorm warning with tornado risk this afternoon near North Bay."}]
}
```

`weather.code`/`weather.is_day` drive the animated background scene in
[scenery.py](scenery.py). `alerts` renders as a stacked, color-coded banner
([alerts.py](alerts.py)), sorted red > yellow > neutral.

This app never calls those APIs/MCP tools itself — it only reads the JSON file the
scheduled task maintains. If `state.json` is missing or stale (>2x the sync interval),
the dashboard shows a warning instead of guessing.
