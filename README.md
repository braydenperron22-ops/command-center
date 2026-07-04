# Brayden's Command Center

Always-on personal dashboard: date/time, weather, calendar agenda, email highlights, and a task/reminder list.

## Running it

```
pip install -r requirements.txt
streamlit run app.py
```

Leave the browser tab open on the always-on laptop/monitor. It auto-refreshes every 60 seconds.

## How data gets in

Tasks/reminders are added directly in the app UI and stored in `data/tasks.json`.

Weather, calendar, and email data come from `data/state.json`, which is written by a
**scheduled Claude task** (not this app) running every 30 minutes. That task:

1. Fetches weather for Corbeil, Ontario (lat 46.3667, lon -79.1667) from the
   Open-Meteo API (no key required):
   `https://api.open-meteo.com/v1/forecast?latitude=46.3667&longitude=-79.1667&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min&timezone=America/Toronto`
2. Fetches today's/upcoming Google Calendar events via the connected calendar MCP tool.
3. Fetches unread/important Gmail messages via the connected Gmail MCP tool.
4. Writes the result to `data/state.json` in this shape:

```json
{
  "last_synced": "2026-07-04T13:00:00",
  "weather": {
    "temp_now": 24,
    "condition_now": "Partly cloudy",
    "temp_high": 27,
    "temp_low": 16
  },
  "calendar_events": [
    {"time": "2:00 PM", "title": "Dentist appointment"}
  ],
  "email_highlights": [
    {"from": "Air Canada", "subject": "Your flight is confirmed"}
  ]
}
```

This app never calls those APIs/MCP tools itself — it only reads the JSON file the
scheduled task maintains. If `state.json` is missing or stale (>2x the sync interval),
the dashboard shows a warning instead of guessing.
