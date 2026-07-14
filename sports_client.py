"""Blue Jays (MLB) and Canadiens (NHL) — current/most recent game plus
full division standings, from each league's own free public API (no
key needed for either). A team's whole section is hidden while its
league is out of season — detected from that team's own schedule (no
regular- or postseason games within SEASON_WINDOW_DAYS of now means
nothing's being played), not a fixed calendar assumption, so it self
corrects around lockouts, elimination, early/late starts, etc. without
yearly upkeep.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import streamlit as st

import fetch_throttle
from config import TIMEZONE

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_STANDINGS_URL = "https://statsapi.mlb.com/api/v1/standings"
MLB_TEAM_ID = 141  # Toronto Blue Jays
MLB_DIVISION_ID = 201  # AL East
MLB_DIVISION_NAME = "AL East"
# "S" (spring training) and "A" (all-star) intentionally excluded — those
# happening don't mean the real season is underway.
MLB_SEASON_GAME_TYPES = {"R", "F", "D", "L", "W"}

NHL_SCHEDULE_URL = "https://api-web.nhle.com/v1/club-schedule-season/{team}/now"
NHL_STANDINGS_URL = "https://api-web.nhle.com/v1/standings/now"
NHL_TEAM_ABBR = "MTL"  # Montreal Canadiens
NHL_DIVISION_ABBREV = "A"  # Atlantic
NHL_DIVISION_NAME = "Atlantic"
# gameType 1 is preseason — same reasoning as MLB's "S" exclusion above.
NHL_SEASON_GAME_TYPES = {2, 3}

SEASON_WINDOW_DAYS = 10  # no games at all in this wide a window either side of now => offseason
GAME_CACHE_TTL_SECONDS = 5 * 60  # frequent enough to catch a live score changing
STANDINGS_CACHE_TTL_SECONDS = 30 * 60  # standings only move once a game finishes, not worth polling harder

_last_good_mlb_games: list[dict] | None = None
_last_good_mlb_standings: list[dict] | None = None
_last_good_nhl_games: list[dict] | None = None
_last_good_nhl_standings: list[dict] | None = None


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _to_local(iso_utc: str) -> datetime:
    return datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(ZoneInfo(TIMEZONE)).replace(tzinfo=None)


@st.cache_data(ttl=GAME_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_mlb_games_raw(start_date: str, end_date: str) -> list[dict]:
    resp = requests.get(
        MLB_SCHEDULE_URL,
        params={"sportId": 1, "teamId": MLB_TEAM_ID, "startDate": start_date, "endDate": end_date},
        timeout=10,
    )
    resp.raise_for_status()
    games = []
    for day in resp.json().get("dates", []):
        games.extend(day.get("games", []))
    return games


def _fetch_mlb_games(now: datetime) -> list[dict] | None:
    global _last_good_mlb_games
    start = (now - timedelta(days=SEASON_WINDOW_DAYS)).strftime("%Y-%m-%d")
    end = (now + timedelta(days=SEASON_WINDOW_DAYS)).strftime("%Y-%m-%d")
    fetch_throttle.wait_turn()
    try:
        result = _fetch_mlb_games_raw(start, end)
    except Exception:
        return _last_good_mlb_games
    _last_good_mlb_games = result
    return result


@st.cache_data(ttl=STANDINGS_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_mlb_standings_raw() -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(MLB_STANDINGS_URL, params={"leagueId": 103, "standingsTypes": "regularSeason"}, timeout=10)
    resp.raise_for_status()
    for record in resp.json().get("records", []):
        if record["division"]["id"] == MLB_DIVISION_ID:
            return sorted(record["teamRecords"], key=lambda t: int(t["divisionRank"]))
    return []


def _fetch_mlb_standings() -> list[dict]:
    global _last_good_mlb_standings
    try:
        result = _fetch_mlb_standings_raw()
    except Exception:
        return _last_good_mlb_standings or []
    if result:
        _last_good_mlb_standings = result
    return result or (_last_good_mlb_standings or [])


def _normalize_mlb_game(g: dict) -> dict:
    away, home = g["teams"]["away"], g["teams"]["home"]
    is_home = home["team"]["id"] == MLB_TEAM_ID
    us, opp = (home, away) if is_home else (away, home)
    state = {"Preview": "upcoming", "Live": "live", "Final": "final"}.get(
        g["status"]["abstractGameState"], "upcoming"
    )
    return {
        "opponent": opp["team"]["name"],
        "is_home": is_home,
        "team_score": us.get("score"),
        "opp_score": opp.get("score"),
        "state": state,
        "start_time": _to_local(g["gameDate"]),
    }


def _normalize_nhl_game(g: dict) -> dict:
    is_home = g["homeTeam"]["abbrev"] == NHL_TEAM_ABBR
    us, opp = (g["homeTeam"], g["awayTeam"]) if is_home else (g["awayTeam"], g["homeTeam"])
    state = {"FUT": "upcoming", "PRE": "upcoming", "LIVE": "live", "CRIT": "live", "FINAL": "final", "OFF": "final"}.get(
        g["gameState"], "upcoming"
    )
    opponent = f"{opp['placeName']['default']} {opp['commonName']['default']}"
    return {
        "opponent": opponent,
        "is_home": is_home,
        "team_score": us.get("score"),
        "opp_score": opp.get("score"),
        "state": state,
        "start_time": _to_local(g["startTimeUTC"]),
    }


def _pick_current_game(games: list[dict], now: datetime) -> dict | None:
    """Live game first; else today's game (even if already final — the
    point right after a game ends is seeing how it went, not being
    bumped straight to next week's matchup); else the nearest upcoming
    game; else the most recent final."""
    live = [g for g in games if g["state"] == "live"]
    if live:
        return live[0]
    today = [g for g in games if g["start_time"].date() == now.date()]
    if today:
        return sorted(today, key=lambda g: g["start_time"])[0]
    upcoming = sorted(
        (g for g in games if g["state"] == "upcoming" and g["start_time"] > now), key=lambda g: g["start_time"]
    )
    if upcoming:
        return upcoming[0]
    finals = sorted(
        (g for g in games if g["state"] == "final" and g["start_time"] <= now),
        key=lambda g: g["start_time"],
        reverse=True,
    )
    return finals[0] if finals else None


def fetch_jays() -> dict | None:
    """{"game": {...}|None, "standings": [{"rank","team","wins","losses",
    "extra","is_team"}, ...], "division_name"} — None entirely if the
    Jays haven't played a regular/postseason game within
    SEASON_WINDOW_DAYS of now (the actual offseason, not just a rest
    day)."""
    now = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
    raw_games = _fetch_mlb_games(now)
    if raw_games is None:
        return None
    if not any(g.get("gameType") in MLB_SEASON_GAME_TYPES for g in raw_games):
        return None

    normalized = [_normalize_mlb_game(g) for g in raw_games if g.get("gameType") in MLB_SEASON_GAME_TYPES]
    game = _pick_current_game(normalized, now)

    standings = [
        {
            "rank": int(t["divisionRank"]),
            "team": t["team"]["name"],
            "wins": t["leagueRecord"]["wins"],
            "losses": t["leagueRecord"]["losses"],
            "extra": t.get("gamesBack", "-"),
            "is_team": t["team"]["id"] == MLB_TEAM_ID,
        }
        for t in _fetch_mlb_standings()
    ]
    return {"game": game, "standings": standings, "division_name": MLB_DIVISION_NAME}


@st.cache_data(ttl=GAME_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_nhl_games_raw() -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(NHL_SCHEDULE_URL.format(team=NHL_TEAM_ABBR), timeout=10, allow_redirects=True)
    resp.raise_for_status()
    return resp.json().get("games", [])


def _fetch_nhl_games() -> list[dict] | None:
    global _last_good_nhl_games
    try:
        result = _fetch_nhl_games_raw()
    except Exception:
        return _last_good_nhl_games
    _last_good_nhl_games = result
    return result


@st.cache_data(ttl=STANDINGS_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_nhl_standings_raw() -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(NHL_STANDINGS_URL, timeout=10, allow_redirects=True)
    resp.raise_for_status()
    teams = [t for t in resp.json().get("standings", []) if t["divisionAbbrev"] == NHL_DIVISION_ABBREV]
    return sorted(teams, key=lambda t: t["divisionSequence"])


def _fetch_nhl_standings() -> list[dict]:
    global _last_good_nhl_standings
    try:
        result = _fetch_nhl_standings_raw()
    except Exception:
        return _last_good_nhl_standings or []
    if result:
        _last_good_nhl_standings = result
    return result or (_last_good_nhl_standings or [])


def fetch_habs() -> dict | None:
    """Same shape as fetch_jays() — None entirely outside the NHL season
    (this is what makes the whole page fall back to just the Jays, or
    to a quiet placeholder, in the summer)."""
    now = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
    raw_games = _fetch_nhl_games()
    if raw_games is None:
        return None
    in_window = [
        g
        for g in raw_games
        if g.get("gameType") in NHL_SEASON_GAME_TYPES
        and abs((_to_local(g["startTimeUTC"]) - now).total_seconds()) <= SEASON_WINDOW_DAYS * 86400
    ]
    if not in_window:
        return None

    season_games = [g for g in raw_games if g.get("gameType") in NHL_SEASON_GAME_TYPES]
    normalized = [_normalize_nhl_game(g) for g in season_games]
    game = _pick_current_game(normalized, now)

    standings = [
        {
            "rank": t["divisionSequence"],
            "team": f"{t['teamName']['default']}",
            "wins": t["wins"],
            "losses": t["losses"],
            "extra": f"{t['otLosses']} OTL",
            "is_team": t["teamAbbrev"]["default"] == NHL_TEAM_ABBR,
        }
        for t in _fetch_nhl_standings()
    ]
    return {"game": game, "standings": standings, "division_name": NHL_DIVISION_NAME}
