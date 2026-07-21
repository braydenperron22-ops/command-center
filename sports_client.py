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
# MLB's own static logo CDN, keyed by team id — no API call, confirmed
# live this returns a real SVG for every team id tried, not just 141.
_MLB_LOGO_URL = "https://www.mlbstatic.com/team-logos/{team_id}.svg"


def _mlb_logo_url(team_id: int) -> str:
    return _MLB_LOGO_URL.format(team_id=team_id)


NHL_SCHEDULE_URL = "https://api-web.nhle.com/v1/club-schedule-season/{team}/now"
NHL_STANDINGS_URL = "https://api-web.nhle.com/v1/standings/now"
NHL_TEAM_ABBR = "MTL"  # Montreal Canadiens
NHL_DIVISION_ABBREV = "A"  # Atlantic
NHL_DIVISION_NAME = "Atlantic"
# gameType 1 is preseason — same reasoning as MLB's "S" exclusion above.
NHL_SEASON_GAME_TYPES = {2, 3}
# Same idea as MLB above — the standings endpoint happens to return this
# same URL shape per team (confirmed live), so it's built directly here
# rather than needing a standings lookup just to find a logo. "_light"
# is the version meant to read on a dark background, which is this
# whole app's theme.
_NHL_LOGO_URL = "https://assets.nhle.com/logos/nhl/svg/{abbrev}_light.svg"


def _nhl_logo_url(abbrev: str) -> str:
    return _NHL_LOGO_URL.format(abbrev=abbrev)

SEASON_WINDOW_DAYS = 10  # no games at all in this wide a window either side of now => offseason
GAME_CACHE_TTL_SECONDS = 5 * 60  # frequent enough to catch a live score changing
STANDINGS_CACHE_TTL_SECONDS = 30 * 60  # standings only move once a game finishes, not worth polling harder
# A live game's own count/base-runners/period-clock genuinely can change
# every few seconds — polled far tighter than the 5-minute schedule
# cache above, which only needs to catch state flipping to/from "live".
LIVE_DETAIL_CACHE_TTL_SECONDS = 30

MLB_LINESCORE_URL = "https://statsapi.mlb.com/api/v1/game/{game_id}/linescore"
NHL_BOXSCORE_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"

_last_good_mlb_games: list[dict] | None = None
_last_good_mlb_standings: list[dict] | None = None
_last_good_mlb_wildcard: dict | None = None
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
    fetch_throttle.wait_turn()
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


# Division rank alone reads as "hopeless" for a team buried in a strong
# division even when it's genuinely alive in the Wild Card race (e.g.
# 12 games back in the AL East but only 2.5 back for a Wild Card spot,
# confirmed live) — same free endpoint as the division standings above,
# just a different standingsTypes value, one extra request only ever
# hit once per STANDINGS_CACHE_TTL_SECONDS.
@st.cache_data(ttl=STANDINGS_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_mlb_wildcard_raw() -> dict | None:
    fetch_throttle.wait_turn()
    resp = requests.get(MLB_STANDINGS_URL, params={"leagueId": 103, "standingsTypes": "wildCard"}, timeout=10)
    resp.raise_for_status()
    for record in resp.json().get("records", []):
        for t in record.get("teamRecords", []):
            if t["team"]["id"] == MLB_TEAM_ID:
                return {"value": t.get("wildCardGamesBack"), "rank": t.get("wildCardRank"), "unit": "GB"}
    return None


def _fetch_mlb_wildcard() -> dict | None:
    global _last_good_mlb_wildcard
    try:
        result = _fetch_mlb_wildcard_raw()
    except Exception:
        return _last_good_mlb_wildcard
    if result:
        _last_good_mlb_wildcard = result
    return result or _last_good_mlb_wildcard


def _normalize_mlb_game(g: dict) -> dict:
    away, home = g["teams"]["away"], g["teams"]["home"]
    is_home = home["team"]["id"] == MLB_TEAM_ID
    us, opp = (home, away) if is_home else (away, home)
    state = {"Preview": "upcoming", "Live": "live", "Final": "final"}.get(
        g["status"]["abstractGameState"], "upcoming"
    )
    return {
        "game_id": g["gamePk"],
        "opponent": opp["team"]["name"],
        "opponent_logo": _mlb_logo_url(opp["team"]["id"]),
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
        "game_id": g["id"],
        "opponent": opponent,
        "opponent_logo": _nhl_logo_url(opp["abbrev"]),
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
    "extra","is_team"}, ...], "division_name", "wildcard": {"games_back",
    "rank"}|None, "team_logo"} — None entirely if the Jays haven't played
    a regular/postseason game within SEASON_WINDOW_DAYS of now (the
    actual offseason, not just a rest day). "game", when not None, also
    carries its own "opponent_logo"."""
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
    return {
        "game": game,
        "standings": standings,
        "division_name": MLB_DIVISION_NAME,
        "wildcard": _fetch_mlb_wildcard(),
        "team_logo": _mlb_logo_url(MLB_TEAM_ID),
    }


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


NHL_CONFERENCE_ABBREV = "E"  # Eastern


@st.cache_data(ttl=STANDINGS_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_nhl_wildcard_raw() -> dict | None:
    """Division rank alone reads as "buried" for a team outside its
    division's own top 3 even when it's genuinely alive for one of the
    conference's 2 Wild Card berths — same standings endpoint as the
    division table above, just unfiltered by division so the whole
    conference is visible. Unlike MLB's endpoint, the NHL one exposes a
    wildcardSequence but no ready-made "points back" number, so the Wild
    Card pool (every team not already in its own division's real top 3)
    is built and ranked by points here directly. None whenever MTL
    already holds a real Atlantic top-3 spot — Wild Card context isn't
    relevant to a team that doesn't need it."""
    fetch_throttle.wait_turn()
    resp = requests.get(NHL_STANDINGS_URL, timeout=10, allow_redirects=True)
    resp.raise_for_status()
    conference = [t for t in resp.json().get("standings", []) if t["conferenceAbbrev"] == NHL_CONFERENCE_ABBREV]
    mtl = next((t for t in conference if t["teamAbbrev"]["default"] == NHL_TEAM_ABBR), None)
    if mtl is None or mtl["divisionSequence"] <= 3:
        return None

    pool = sorted((t for t in conference if t["divisionSequence"] > 3), key=lambda t: -t["points"])
    rank = next(i for i, t in enumerate(pool) if t["teamAbbrev"]["default"] == NHL_TEAM_ABBR) + 1
    # Points behind whoever holds the pool's 2nd (last) Wild Card spot —
    # 0 or negative means MTL holds a spot itself, by that many points.
    cutoff_points = pool[1]["points"]
    points_back = cutoff_points - mtl["points"]
    return {"value": points_back, "rank": rank, "unit": "PTS"}


def _fetch_nhl_wildcard() -> dict | None:
    try:
        return _fetch_nhl_wildcard_raw()
    except Exception:
        return None


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
    return {
        "game": game,
        "standings": standings,
        "division_name": NHL_DIVISION_NAME,
        "wildcard": _fetch_nhl_wildcard(),
        "team_logo": _nhl_logo_url(NHL_TEAM_ABBR),
    }


# --- Live in-game detail (session request: "during a game the sports
# page turns into a full comprehensive scoreboard") -------------------
# Both leagues' own free live-game endpoints, separate from the
# schedule/standings ones above — only ever fetched for a game already
# known to be "live" (see _pick_current_game), so this cost is never
# paid for an upcoming/final game.


@st.cache_data(ttl=LIVE_DETAIL_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_mlb_linescore_raw(game_id: int) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(MLB_LINESCORE_URL.format(game_id=game_id), timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_mlb_live_detail(game_id: int) -> dict | None:
    """{"inning_state" ("Top"/"Bottom"/"Middle"/"End"), "current_inning",
    "balls", "strikes", "outs", "batter", "pitcher", "bases":
    {"first","second","third": bool}} — the live situation only (the
    score itself already comes from the compact game dict everywhere
    this is used). None on any fetch failure (no last-good fallback: a
    stale pitch count/base state would be actively misleading rather
    than just old, unlike a season schedule that barely changes)."""
    try:
        data = _fetch_mlb_linescore_raw(game_id)
    except Exception:
        return None

    offense = data.get("offense", {})
    defense = data.get("defense", {})
    return {
        "inning_state": data.get("inningState"),
        "current_inning": data.get("currentInning"),
        "balls": data.get("balls"),
        "strikes": data.get("strikes"),
        "outs": data.get("outs"),
        "batter": (offense.get("batter") or {}).get("fullName"),
        "pitcher": (defense.get("pitcher") or {}).get("fullName"),
        "bases": {"first": "first" in offense, "second": "second" in offense, "third": "third" in offense},
    }


def _nhl_period_label(period_descriptor: dict) -> str:
    period_type = period_descriptor.get("periodType")
    if period_type in ("OT", "SO"):
        return period_type
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(period_descriptor.get("number"), f"{period_descriptor.get('number')}th")


@st.cache_data(ttl=LIVE_DETAIL_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_nhl_boxscore_raw(game_id: int) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(NHL_BOXSCORE_URL.format(game_id=game_id), timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_nhl_live_detail(game_id: int) -> dict | None:
    """{"period_label", "clock", "in_intermission"} — the live situation
    only (the score itself already comes from the compact game dict
    everywhere this is used). None on any fetch failure, same reasoning
    as fetch_mlb_live_detail."""
    try:
        box = _fetch_nhl_boxscore_raw(game_id)
    except Exception:
        return None

    clock = box.get("clock", {})
    return {
        "period_label": _nhl_period_label(box.get("periodDescriptor", {})),
        "clock": clock.get("timeRemaining"),
        "in_intermission": clock.get("inIntermission", False),
    }
