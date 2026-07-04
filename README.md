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

The look is built on [theme.py](theme.py) (typography, hidden Streamlit chrome, glass
card styling), [scenery.py](scenery.py) (soft ambient gradient + particles reacting to
weather), and [icons.py](icons.py) (minimal line-art weather icons) — deliberately
understated rather than a busy dashboard.

Weather, calendar, and email data come from `data/state.json`, which is written by a
**scheduled Claude task** (not this app) running every 20 minutes. That task:

1. Fetches weather for Corbeil, Ontario (lat 46.3667, lon -79.1667) from the
   Open-Meteo API (no key required):
   `https://api.open-meteo.com/v1/forecast?latitude=46.3667&longitude=-79.1667&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min&timezone=America/Toronto`
2. Fetches today's/upcoming Google Calendar events via the connected calendar MCP tool.
3. Fetches unread Gmail messages via the connected Gmail MCP tool, filtered down to
   only ones that (a) are addressed to Brayden personally (not bulk/cc'd/newsletter)
   or (b) look like something he genuinely needs to catch up on (time-sensitive,
   from a real person, action needed) — not every unread email, just the necessities.
4. Checks for noteworthy weather statements (live Environment Canada alerts page),
   traffic on the Corbeil–North Bay Highway 17 stretch specifically (live 511 Ontario
   API), and breaking news (financial markets, national/world, local North Bay/Ontario),
   classifying each as `red` (urgent), `yellow` (moderate), or `neutral` (FYI). Weather
   and traffic use live authoritative endpoints, not web search, since search results
   can surface stale articles that look current but aren't.
5. Writes the result to `data/state.json` in this shape:

```json
{
  "last_synced": "2026-07-04T13:00:00",
  "weather": {
    "temp_now": 24,
    "condition_now": "Partly cloudy",
    "temp_high": 27,
    "temp_low": 16,
    "code": 2,
    "is_day": true
  },
  "calendar_events": [
    {"time": "2:00 PM", "title": "Dentist appointment"}
  ],
  "email_highlights": [
    {"from": "Air Canada", "subject": "Your flight is confirmed"}
  ],
  "alerts": [
    {"severity": "red", "message": "Severe thunderstorm warning with tornado risk this afternoon near North Bay."}
  ]
}
```

`weather.code` (raw WMO code) and `weather.is_day` drive the animated background
scene in [scenery.py](scenery.py) — sky gradient, sun/moon/stars, drifting clouds,
rain, or snow depending on conditions. `alerts` renders as a stacked, color-coded
banner ([alerts.py](alerts.py)) above the header, sorted red > yellow > neutral.

This app never calls those APIs/MCP tools itself — it only reads the JSON file the
scheduled task maintains. If `state.json` is missing or stale (>2x the sync interval),
the dashboard shows a warning instead of guessing.
