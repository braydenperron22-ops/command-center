"""The dashboard's own data, exposed to the LLM as named, structured,
READ-ONLY tools — session's own explicit hard requirement: "Do NOT
simply give the LLM the entire Streamlit webpage/HTML... I want the
existing dashboard's underlying data/functions exposed to the AI as
structured tools/functions wherever practical." Every tool here is a
thin wrapper around an already-existing, already-proven dashboard
function (weather_client, commute_reminder, calendar_client, ...) —
this file adds no new data-fetching logic of its own, only the
tool-schema + safe-serialization layer around functions that already
work. See voice/config.py's own comment for why the repo root gets put
on sys.path before these sibling imports.

Security posture (explicit session requirement): every tool below is
read-only. There is no tool here that changes dashboard state, device
state, or anything else — see this project's own architecture writeup
for why that's a hard line, not just a starting point. A future
write/action tool (lights, TV, dashboard settings) needs its own
explicit, separate permission model; it does not get added here just
because the plumbing would make it easy.

Every tool function catches its own exceptions and returns a plain
{"error": "..."} dict rather than raising — a dashboard API being down
must degrade to "the assistant can't answer that right now," never to
crashing the whole voice pipeline (same "must never take a page down"
rule every dashboard client module already follows)."""

import html
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

# Import for its side effect only (puts the repo root on sys.path) —
# this module must not depend on some OTHER voice/ module having been
# imported first to make the sibling imports below resolve. Real bug
# caught in review: this file originally had no `voice.config` import
# at all, so `import calendar_client` etc. only worked when something
# else (orchestrator.py) happened to import voice.config earlier in
# the same process — a plain `from voice import tools` in isolation
# would have raised ModuleNotFoundError.
from voice import config as _voice_config  # noqa: F401

import calendar_client
import commute_reminder
import ec_aqhi
import ec_alerts
import road_conditions_511
import sports_client
import weather_alerts_bar
import weather_client
from config import TIMEZONE

# Sports teams this dashboard actually tracks (see sports_client.py) —
# not a general "any team" lookup, since fetch_* only exists for these.
_SPORTS_FETCHERS = {
    "habs": sports_client.fetch_habs,
    "canadiens": sports_client.fetch_habs,
    "jays": sports_client.fetch_jays,
    "blue jays": sports_client.fetch_jays,
    "saints": sports_client.fetch_saints,
}


def _now() -> datetime:
    """Naive local-time `now`, TIMEZONE-pinned — the same convention
    every dashboard module that takes a `now` argument already expects
    (see commute_reminder.commute_status, calendar_client.todays_events,
    etc.), not the AI's own notion of "now" (a local LLM has no
    reliable clock of its own to draw on)."""
    return datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)


def _jsonable(value):
    """Recursively converts datetimes to plain ISO strings so a tool's
    raw dashboard-shaped return value (which routinely carries real
    `datetime` objects — see calendar_client.todays_events, weather_
    client.fetch_weather) can go straight through json.dumps for the
    LLM without a bespoke serializer per tool."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _safe(fn, *args, **kwargs) -> dict:
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - a tool must never raise into the LLM loop
        return {"error": f"{fn.__name__} failed: {exc}"}
    if result is None:
        return {"error": "no data currently available"}
    return _jsonable(result) if isinstance(result, dict) else {"result": _jsonable(result)}


def get_weather(when: str = "now") -> dict:
    """Current conditions, or tomorrow's forecast high/low, from the
    same Open-Meteo/Environment-Canada blend the dashboard's own
    Weather page uses (weather_client.py) — no API key, real live data,
    never fabricated."""
    weather = weather_client.fetch_weather()
    if weather is None:
        return {"error": "weather data is not currently available"}
    out = _jsonable(weather)
    if when == "tomorrow":
        daily = weather_client.daily_forecast()
        if daily:
            out["tomorrow"] = _jsonable(daily[1] if len(daily) > 1 else daily[0])
    return out


def get_commute_status() -> dict:
    """Live route, congestion, and (when a real shift is active) the
    computed leave-by time for the user's actual commute — commute_
    reminder.commute_status(), TomTom-backed, real traffic. This is the
    single tool that answers "should I leave for work" — the LLM must
    call this rather than ever guessing a travel time or a leave-by
    time on its own."""
    return _safe(commute_reminder.commute_status, _now())


def get_schedule(day: str = "today") -> dict:
    """The user's real calendar events (shifts, appointments) for
    "today" or "tomorrow", merged across every configured ICS calendar
    — calendar_client.todays_events(). Empty list is a genuine "nothing
    scheduled," not a fetch failure (see that function's own
    docstring)."""
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return {"error": "no calendars configured"}
    target = _now().date() + (timedelta(days=1) if day == "tomorrow" else timedelta(days=0))
    return {"day": day, "events": _safe(calendar_client.todays_events, calendars, target).get("result", [])}


def get_air_quality() -> dict:
    """Real North Bay AQHI reading (Environment Canada), not modeled —
    ec_aqhi.fetch_aqhi()."""
    return _safe(ec_aqhi.fetch_aqhi)


def get_weather_alerts() -> dict:
    """Any currently-active Environment Canada weather alert for this
    region (warnings/watches/advisories/statements) plus its severity
    tier — ec_alerts.fetch_alerts() + weather_alerts_bar.current_
    severity(). Empty/"none" is a genuine all-clear, not missing data."""
    alerts = _safe(ec_alerts.fetch_alerts)
    severity = weather_alerts_bar.current_severity()
    type_label = weather_alerts_bar.current_type_label()
    return {"alerts": alerts.get("result", alerts), "severity": severity or "none", "type": type_label}


def get_road_conditions() -> dict:
    """Real, currently-active road closures/construction/incidents
    along the user's actual commute routes — road_conditions_511.
    road_issues_near_commute(), Ontario 511-backed."""
    return _safe(road_conditions_511.road_issues_near_commute, _now())


def get_sports(team: str) -> dict:
    """Live/last game state and standings for one of the teams this
    dashboard actually tracks — Montreal Canadiens (habs), Toronto
    Blue Jays (jays), New Orleans Saints (saints) — sports_client.py,
    NHL/MLB/NFL-backed. None (a plain "no data") is the honest answer
    outside that team's season, not an error."""
    key = team.strip().lower()
    fetcher = _SPORTS_FETCHERS.get(key)
    if fetcher is None:
        return {"error": f"unknown team {team!r}; this dashboard only tracks Habs, Jays, and Saints"}
    return _safe(fetcher)


# --- Tool schema (Ollama/OpenAI-style function-calling format) -------------
# Kept in the same file as the implementations on purpose (session
# precedent already established elsewhere in this app — e.g.
# weather_alerts_bar owning its own alert wording): the schema
# describing a tool and the code that answers it should never drift
# apart in two different files.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get real current weather conditions for the user's home, or tomorrow's forecast.",
            "parameters": {
                "type": "object",
                "properties": {
                    "when": {
                        "type": "string",
                        "enum": ["now", "tomorrow"],
                        "description": "'now' for current conditions, 'tomorrow' to also include tomorrow's forecast high/low.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_commute_status",
            "description": (
                "Get the user's real, live commute status right now: current traffic conditions, congestion, "
                "and (if a work shift is active) the computed time they need to leave by. Always call this for "
                "any question about traffic, commuting, or whether to leave for work — never guess."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule",
            "description": "Get the user's real calendar events (shifts, appointments) for today or tomorrow.",
            "parameters": {
                "type": "object",
                "properties": {"day": {"type": "string", "enum": ["today", "tomorrow"]}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_air_quality",
            "description": "Get the real current Air Quality Health Index (AQHI) reading for the user's area.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_alerts",
            "description": "Get any currently active Environment Canada weather alert (warning/watch/advisory) for the user's area.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_road_conditions",
            "description": "Get real, currently active road closures or incidents along the user's actual commute routes.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sports",
            "description": "Get the live or most recent game and standings for one of the NHL/MLB/NFL teams this dashboard tracks: the Montreal Canadiens (Habs), Toronto Blue Jays (Jays), or the New Orleans Saints.",
            "parameters": {
                "type": "object",
                "properties": {"team": {"type": "string", "enum": ["habs", "jays", "saints"]}},
                "required": ["team"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "get_weather": get_weather,
    "get_commute_status": get_commute_status,
    "get_schedule": get_schedule,
    "get_air_quality": get_air_quality,
    "get_weather_alerts": get_weather_alerts,
    "get_road_conditions": get_road_conditions,
    "get_sports": get_sports,
}


def call_tool(name: str, arguments: dict) -> str:
    """Dispatches a tool call by name to its real implementation and
    returns a JSON string ready to hand straight back to the LLM as a
    tool-result message. An unknown tool name (should never happen —
    the LLM only ever sees TOOL_SCHEMAS' own names — but a
    hallucinated/malformed tool call is exactly the kind of thing a
    voice pipeline must degrade from, not crash on) returns a plain
    error payload instead of raising."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"no such tool: {html.escape(str(name))}"})
    try:
        result = fn(**(arguments or {}))
    except Exception as exc:  # noqa: BLE001
        result = {"error": f"{name} raised: {exc}"}
    return json.dumps(result, default=str)
