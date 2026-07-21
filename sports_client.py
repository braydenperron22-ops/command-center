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

import data_health
import fetch_throttle
from config import TIMEZONE

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_STANDINGS_URL = "https://statsapi.mlb.com/api/v1/standings"
MLB_TEAM_ID = 141  # Toronto Blue Jays
# Full display name, not an abbreviation — MLB Stats API's own schedule
# payload doesn't carry team abbreviations at all (confirmed live,
# both sides come back None), but ESPN's own scoreboard competitor
# names match this exactly, which is what scores_client.
# find_espn_competition actually matches on.
MLB_TEAM_NAME = "Toronto Blue Jays"
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
NHL_TEAM_NAME = "Montreal Canadiens"  # see MLB_TEAM_NAME's own comment above for why this exists
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
# MLB's own schedule endpoint needs an explicit date range (unlike
# NHL's club-schedule-season/now, which already returns the whole
# season regardless) — this is how far back that range reaches, wide
# enough to comfortably contain RECENT_FORM_GAMES completed games even
# across an All-Star break or a run of postponements, still within the
# same single schedule fetch _pick_current_game already needed.
MLB_FORM_LOOKBACK_DAYS = 30
GAME_CACHE_TTL_SECONDS = 5 * 60  # frequent enough to catch a live score changing
STANDINGS_CACHE_TTL_SECONDS = 30 * 60  # standings only move once a game finishes, not worth polling harder
# A live game's own count/base-runners/period-clock genuinely can change
# every few seconds — polled far tighter than the 5-minute schedule
# cache above, which only needs to catch state flipping to/from "live".
LIVE_DETAIL_CACHE_TTL_SECONDS = 30

MLB_LINESCORE_URL = "https://statsapi.mlb.com/api/v1/game/{game_id}/linescore"
NHL_BOXSCORE_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"
# Per-period goals for the jumbotron's linescore table. The NHL's own
# landing/boxscore payloads don't carry one (confirmed live: landing's
# `summary` has only scoring/penalties/threeStars, and boxscore has no
# linescore key at all) — right-rail is where it actually lives.
NHL_RIGHT_RAIL_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/right-rail"

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
    start = (now - timedelta(days=MLB_FORM_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    end = (now + timedelta(days=SEASON_WINDOW_DAYS)).strftime("%Y-%m-%d")
    try:
        result = _fetch_mlb_games_raw(start, end)
    except Exception:
        return _last_good_mlb_games
    _last_good_mlb_games = result
    data_health.record_success("sports_schedule")
    return result


@st.cache_data(ttl=STANDINGS_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_mlb_standings_raw_all() -> list[dict]:
    """Every MLB division, both leagues, one request (the standings
    endpoint's own comma-separated leagueId) — the Jays' own AL East
    view below and fetch_all_mlb_standings()'s full-league rotation
    (session request: "rotate between all divisions and all leagues...
    a full deep dive") both filter from this single shared call rather
    than hitting the endpoint once per division."""
    fetch_throttle.wait_turn()
    resp = requests.get(MLB_STANDINGS_URL, params={"leagueId": "103,104", "standingsTypes": "regularSeason"}, timeout=10)
    resp.raise_for_status()
    return resp.json().get("records", [])


def _fetch_mlb_standings_raw() -> list[dict]:
    for record in _fetch_mlb_standings_raw_all():
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


RECENT_FORM_GAMES = 10


def _recent_form(games: list[dict], now: datetime) -> list[str]:
    """Outcome ("W"/"L") of the last RECENT_FORM_GAMES completed games,
    oldest first (reads left-to-right as a timeline, most recent on the
    right) — from the same full-season schedule already fetched to
    find the current game (see _pick_current_game), so this costs
    nothing extra."""
    finals = sorted(
        (g for g in games if g["state"] == "final" and g["start_time"] <= now), key=lambda g: g["start_time"]
    )
    return ["W" if g["team_score"] > g["opp_score"] else "L" for g in finals[-RECENT_FORM_GAMES:]]


def fetch_jays() -> dict | None:
    """{"game": {...}|None, "standings": [{"rank","team","wins","losses","logo",
    "extra","is_team"}, ...], "division_name", "wildcard": {"games_back",
    "rank"}|None, "team_logo", "recent_form": ["W"/"L", ...]} — None
    entirely if the Jays haven't played a regular/postseason game
    within SEASON_WINDOW_DAYS of now (the actual offseason, not just a
    rest day). "game", when not None, also carries its own
    "opponent_logo"."""
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
            "logo": _mlb_logo_url(t["team"]["id"]),
        }
        for t in _fetch_mlb_standings()
    ]
    return {
        "game": game,
        "standings": standings,
        "division_name": MLB_DIVISION_NAME,
        "wildcard": _fetch_mlb_wildcard(),
        "team_logo": _mlb_logo_url(MLB_TEAM_ID),
        "recent_form": _recent_form(normalized, now),
    }


# division.id -> full name — the standings endpoint itself returns null
# for "division.name" on every record (confirmed live), so this is
# filled in by hand; MLB's division ids are static league structure, not
# something that changes season to season. Order here is AL then NL,
# East/Central/West within each, purely for a sensible rotation order.
MLB_DIVISION_NAMES = {201: "AL East", 202: "AL Central", 200: "AL West", 204: "NL East", 205: "NL Central", 203: "NL West"}
MLB_DIVISION_ORDER = [201, 202, 200, 204, 205, 203]


def fetch_all_mlb_standings() -> list[dict]:
    """[{"league": "MLB", "division_name", "rows": [...]}, ...] for every
    MLB division — session request: "rotate between all divisions and
    all leagues... a full deep dive on sports." Same row shape as
    fetch_jays()'s own "standings" list, so existing rendering needs no
    changes. [] only if the standings request itself fails outright —
    unlike fetch_jays()/fetch_habs(), not gated on that team's own
    season being active, since this isn't about one team."""
    try:
        records = _fetch_mlb_standings_raw_all()
    except Exception:
        return []
    by_id = {r["division"]["id"]: r for r in records}
    out = []
    for div_id in MLB_DIVISION_ORDER:
        record = by_id.get(div_id)
        if not record:
            continue
        rows = [
            {
                "rank": int(t["divisionRank"]),
                "team": t["team"]["name"],
                "wins": t["leagueRecord"]["wins"],
                "losses": t["leagueRecord"]["losses"],
                "extra": t.get("gamesBack", "-"),
                "is_team": t["team"]["id"] == MLB_TEAM_ID,
                "logo": _mlb_logo_url(t["team"]["id"]),
            }
            for t in sorted(record["teamRecords"], key=lambda t: int(t["divisionRank"]))
        ]
        out.append({"league": "MLB", "division_name": MLB_DIVISION_NAMES[div_id], "rows": rows})
    return out


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
    data_health.record_success("sports_schedule")
    return result


@st.cache_data(ttl=STANDINGS_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_nhl_standings_raw_all() -> list[dict]:
    """Every NHL team, all four divisions, one request — the Habs' own
    Atlantic view, the wildcard calc, and fetch_all_nhl_standings()'s
    full-league rotation all filter from this single shared call rather
    than hitting the endpoint separately for each."""
    fetch_throttle.wait_turn()
    resp = requests.get(NHL_STANDINGS_URL, timeout=10, allow_redirects=True)
    resp.raise_for_status()
    return resp.json().get("standings", [])


def _fetch_nhl_standings_raw() -> list[dict]:
    teams = [t for t in _fetch_nhl_standings_raw_all() if t["divisionAbbrev"] == NHL_DIVISION_ABBREV]
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
    conference = [t for t in _fetch_nhl_standings_raw_all() if t["conferenceAbbrev"] == NHL_CONFERENCE_ABBREV]
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
            "logo": _nhl_logo_url(t["teamAbbrev"]["default"]),
        }
        for t in _fetch_nhl_standings()
    ]
    return {
        "game": game,
        "standings": standings,
        "division_name": NHL_DIVISION_NAME,
        "wildcard": _fetch_nhl_wildcard(),
        "team_logo": _nhl_logo_url(NHL_TEAM_ABBR),
        "recent_form": _recent_form(normalized, now),
    }


NHL_DIVISION_ORDER = ["A", "M", "C", "P"]  # Atlantic, Metropolitan, Central, Pacific


def fetch_all_nhl_standings() -> list[dict]:
    """[{"league": "NHL", "division_name", "rows": [...]}, ...] for every
    NHL division — same session request and same row shape as
    fetch_all_mlb_standings() above. Not gated on the Habs' own season
    being active (unlike fetch_habs()): the standings/now endpoint keeps
    returning the completed season's final table through the summer
    (confirmed live), which is still real, useful "how did the season
    end" content for an offseason deep dive rather than nothing at all.
    [] only if the standings request itself fails outright."""
    try:
        teams = _fetch_nhl_standings_raw_all()
    except Exception:
        return []
    by_div: dict[str, list[dict]] = {}
    for t in teams:
        by_div.setdefault(t["divisionAbbrev"], []).append(t)
    out = []
    for abbrev in NHL_DIVISION_ORDER:
        group = by_div.get(abbrev)
        if not group:
            continue
        group.sort(key=lambda t: t["divisionSequence"])
        rows = [
            {
                "rank": t["divisionSequence"],
                "team": t["teamName"]["default"],
                "wins": t["wins"],
                "losses": t["losses"],
                "extra": f"{t['otLosses']} OTL",
                "is_team": t["teamAbbrev"]["default"] == NHL_TEAM_ABBR,
                "logo": _nhl_logo_url(t["teamAbbrev"]["default"]),
            }
            for t in group
        ]
        out.append({"league": "NHL", "division_name": group[0].get("divisionName") or abbrev, "rows": rows})
    return out


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


def fetch_mlb_linescore(game_id: int) -> dict | None:
    """Inning-by-inning runs plus R/H/E totals for the jumbotron's
    linescore table — {"columns": [{"label", "away", "home"}, ...],
    "totals": {"away": {"runs","hits","errors"}, "home": {...}},
    "away_is_team", ...}. None on any fetch failure (a half-drawn
    linescore is worse than none). Reuses the same cached raw linescore
    call fetch_mlb_live_detail already makes, so this costs no extra
    request."""
    try:
        data = _fetch_mlb_linescore_raw(game_id)
    except Exception:
        return None
    innings = data.get("innings") or []
    if not innings:
        return None
    columns = [
        {
            "label": str(inning.get("num", "")),
            "away": (inning.get("away") or {}).get("runs"),
            "home": (inning.get("home") or {}).get("runs"),
        }
        for inning in innings
    ]
    teams = data.get("teams") or {}
    totals = {
        side: {
            "runs": (teams.get(side) or {}).get("runs"),
            "hits": (teams.get(side) or {}).get("hits"),
            "errors": (teams.get(side) or {}).get("errors"),
        }
        for side in ("away", "home")
    }
    return {"columns": columns, "totals": totals, "extra_labels": ("R", "H", "E")}


@st.cache_data(ttl=LIVE_DETAIL_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_nhl_right_rail_raw(game_id: int) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(NHL_RIGHT_RAIL_URL.format(game_id=game_id), timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_nhl_linescore(game_id: int) -> dict | None:
    """Same shape as fetch_mlb_linescore, per period instead of per
    inning, with only a goals total (no hits/errors equivalent) — see
    NHL_RIGHT_RAIL_URL's own comment for why this endpoint and not the
    boxscore/landing ones."""
    try:
        data = _fetch_nhl_right_rail_raw(game_id)
    except Exception:
        return None
    linescore = data.get("linescore") or {}
    by_period = linescore.get("byPeriod") or []
    if not by_period:
        return None
    columns = [
        {
            "label": _nhl_period_label(period.get("periodDescriptor") or {}),
            "away": period.get("away"),
            "home": period.get("home"),
        }
        for period in by_period
    ]
    totals_raw = linescore.get("totals") or {}
    totals = {side: {"runs": totals_raw.get(side)} for side in ("away", "home")}
    return {"columns": columns, "totals": totals, "extra_labels": ("T",)}


# Session request (jumbotron pregame board): venue, real game-day
# weather, and probable starters. MLB's own live-feed endpoint carries
# all three under gameData — the same endpoint sports_alerts.py already
# polls for scoring plays, just gameData instead of liveData, and on a
# much slower cache (this context is settled hours before first pitch,
# no need to poll it every 15s). Defined here rather than imported from
# sports_alerts.py to avoid a circular import (sports_alerts already
# imports this module for team logos).
MLB_LIVE_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_id}/feed/live"
PREGAME_CACHE_TTL_SECONDS = 5 * 60


@st.cache_data(ttl=PREGAME_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_mlb_gamedata_raw(game_id: int) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(MLB_LIVE_FEED_URL.format(game_id=game_id), timeout=15)
    resp.raise_for_status()
    return resp.json().get("gameData", {})


def fetch_mlb_pregame_extra(game_id: int) -> dict | None:
    """{"venue", "weather_line", "away_pitcher", "home_pitcher"}. The
    weather line is MLB's own condition text as-is ("Roof Closed, 72°F"
    for a dome, "Clear, 72°F, 15 mph Out To CF" outdoors) — confirmed
    live a domed stadium's own weather.condition already says so, no
    separate indoor/roof flag needed on top of it. None on any fetch
    failure — this is pregame color, not worth a fallback."""
    try:
        gd = _fetch_mlb_gamedata_raw(game_id)
    except Exception:
        return None
    venue = (gd.get("venue") or {}).get("name")
    weather = gd.get("weather") or {}
    weather_line = None
    if weather.get("condition"):
        parts = [weather["condition"]]
        if weather.get("temp"):
            parts.append(f'{weather["temp"]}°F')
        if weather.get("wind") and "none" not in weather["wind"].lower():
            parts.append(weather["wind"])
        weather_line = ", ".join(parts)
    probables = gd.get("probablePitchers") or {}
    return {
        "venue": venue,
        "weather_line": weather_line,
        "away_pitcher": (probables.get("away") or {}).get("fullName"),
        "home_pitcher": (probables.get("home") or {}).get("fullName"),
    }


NHL_LANDING_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/landing"


@st.cache_data(ttl=PREGAME_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_nhl_landing_raw(game_id: int) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(NHL_LANDING_URL.format(game_id=game_id), timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_nhl_venue(game_id: int) -> str | None:
    """Arena name only — NHL has no MLB-style probable-goalie field or
    outdoor weather to show alongside it (every rink is indoor).
    Separate from fetch_nhl_linescore's own right-rail fetch — that
    endpoint's gameInfo has referees/scratches, not the venue."""
    try:
        data = _fetch_nhl_landing_raw(game_id)
    except Exception:
        return None
    return (data.get("venue") or {}).get("default")
