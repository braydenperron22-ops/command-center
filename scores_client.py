"""Today's scoreboard across MLB, NBA, NHL, and NFL — ESPN's free public
scoreboard endpoint (site.api.espn.com), no key, no rate-limit tier.
Unlike sports_client.py (which tracks the Jays/Habs specifically via
each league's own official API), this is deliberately league-wide and
team-agnostic: every game on the slate for today, not one team's
schedule. Both stay on their own data sources rather than merging, since
they answer different questions.

One shared response shape across all four leagues (ESPN's own schema is
already consistent across sports), so the scores page can render any of
them through the same template.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st

import fetch_throttle
from config import TIMEZONE

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
LEAGUES = [
    {"key": "mlb", "label": "MLB", "sport": "baseball", "league": "mlb"},
    {"key": "nba", "label": "NBA", "sport": "basketball", "league": "nba"},
    {"key": "nhl", "label": "NHL", "sport": "hockey", "league": "nhl"},
    {"key": "nfl", "label": "NFL", "sport": "football", "league": "nfl"},
]

GAME_CACHE_TTL_SECONDS = 5 * 60  # matches sports_client.py's own game-freshness cadence

_last_good_games: dict[str, list[dict]] = {}


def _to_local(iso_utc: str) -> datetime:
    return datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(ZoneInfo(TIMEZONE)).replace(tzinfo=None)


@st.cache_data(ttl=GAME_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_scoreboard_raw(sport: str, league: str, date_str: str) -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(
        SCOREBOARD_URL.format(sport=sport, league=league), params={"dates": date_str}, timeout=10
    )
    resp.raise_for_status()
    return resp.json().get("events", [])


def _team_record(competitor: dict) -> str | None:
    """Overall W-L (e.g. "52-48") — a competitor's "records" list also
    carries home/road splits, so this specifically picks the "total"
    one rather than whichever happened to be listed first."""
    records = competitor.get("records") or []
    overall = next((r for r in records if r.get("type") == "total"), None)
    return (overall or (records[0] if records else {})).get("summary")


def _game_leader(competition: dict) -> dict | None:
    """That game's standout performer — the top name in ESPN's own
    first-listed stat category (its own per-sport "headline" stat:
    Rating for MLB, passer rating for NFL, etc.) — real box-score color
    once a game's actually started, not just the final score. None
    before then (an empty "leaders" list pregame, same as an empty
    score) or if the feed didn't carry one for this game at all."""
    for category in competition.get("leaders") or []:
        leaders = category.get("leaders") or []
        if not leaders:
            continue
        athlete = leaders[0].get("athlete") or {}
        name, stat_line = athlete.get("shortName"), leaders[0].get("displayValue")
        if name and stat_line:
            return {"name": name, "stat_line": stat_line}
    return None


def _normalize_game(event: dict) -> dict | None:
    competition = event.get("competitions", [{}])[0]
    competitors = competition.get("competitors", [])
    if len(competitors) != 2:
        return None
    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not home or not away:
        return None

    status = competition.get("status", {}).get("type", {})
    state = status.get("state", "pre")  # "pre" | "in" | "post"
    return {
        "state": state,
        "status_text": status.get("shortDetail", ""),
        "start_time": _to_local(event["date"]) if event.get("date") else None,
        "home": {
            "abbr": home["team"].get("abbreviation", ""),
            "name": home["team"].get("shortDisplayName", home["team"].get("displayName", "")),
            "logo": home["team"].get("logo"),
            "score": home.get("score") if state != "pre" else None,
            "record": _team_record(home),
        },
        "away": {
            "abbr": away["team"].get("abbreviation", ""),
            "name": away["team"].get("shortDisplayName", away["team"].get("displayName", "")),
            "logo": away["team"].get("logo"),
            "score": away.get("score") if state != "pre" else None,
            "record": _team_record(away),
        },
        "leader": _game_leader(competition) if state != "pre" else None,
    }


def fetch_games(league_key: str, today: datetime | None = None) -> list[dict]:
    """Every game for `league_key` ("mlb"/"nba"/"nhl"/"nfl") on today's
    date in TIMEZONE — [] on a genuine off day (nothing scheduled, most
    likely off-season) or if the feed itself is unreachable with no
    prior good copy to fall back on yet. Sorted by start time, live/
    final games naturally first since those started earliest."""
    global _last_good_games
    league = next((entry for entry in LEAGUES if entry["key"] == league_key), None)
    if league is None:
        return []
    today = today or datetime.now(ZoneInfo(TIMEZONE))
    date_str = today.strftime("%Y%m%d")

    try:
        raw = _fetch_scoreboard_raw(league["sport"], league["league"], date_str)
    except Exception:
        return _last_good_games.get(league_key, [])

    games = [g for g in (_normalize_game(e) for e in raw) if g is not None]
    games.sort(key=lambda g: g["start_time"] or datetime.max)
    _last_good_games[league_key] = games
    return games
