"""Blue Jays (MLB) and Canadiens (NHL) — current/most recent game plus
full division standings, from each league's own free public API (no
key needed for either). A team's whole section is hidden while its
league is out of season — detected from that team's own schedule (no
regular- or postseason games within SEASON_WINDOW_DAYS of now means
nothing's being played), not a fixed calendar assumption, so it self
corrects around lockouts, elimination, early/late starts, etc. without
yearly upkeep.
"""

import time
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
# The live feeds above are close to real-time, but Brayden's actual TV
# broadcast runs a beat behind that — session report: "the inning over
# thing is being picked up before the live stream." Rather than just
# polling slower (which would still show the true current instant, only
# choppier), every live-situation payload is held back by this long so
# the jumbotron deliberately trails the broadcast instead of leading it.
# Broadcast lag isn't constant (cable vs. streaming, mid-game provider
# hiccups), so this is only the starting point — the jumbotron's own
# delay stepper (pages_jumbotron.render) lets it be tuned mid-game via
# st.session_state["jumbotron_live_delay_seconds"], read in _delayed
# below.
DEFAULT_LIVE_DATA_DELAY_SECONDS = 10

MLB_LINESCORE_URL = "https://statsapi.mlb.com/api/v1/game/{game_id}/linescore"
NHL_BOXSCORE_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"
_last_good_mlb_games: list[dict] | None = None
_last_good_mlb_standings: list[dict] | None = None
_last_good_mlb_wildcard: dict | None = None
_last_good_nhl_games: list[dict] | None = None
_last_good_nhl_standings: list[dict] | None = None
# {buffer_key: [(fetched_at, payload), ...]}, oldest first — backs
# _delayed() below. Plain module state like _last_good_* above rather
# than session_state: this is about trailing the real-world event by a
# fixed wall-clock amount, not anything session-specific.
_delay_buffers: dict[str, list] = {}


def _delayed(key: str, value):
    """Returns whatever `value` was for this key as of the current delay
    setting ago (st.session_state["jumbotron_live_delay_seconds"],
    DEFAULT_LIVE_DATA_DELAY_SECONDS until the jumbotron's own stepper
    changes it), buffering the fresh value in first. Falls back to
    `value` itself until the buffer's been running long enough to have
    anything older (start of a game/app) — briefly live, rather than
    blocking display entirely."""
    now = time.time()
    delay_seconds = st.session_state.get("jumbotron_live_delay_seconds", DEFAULT_LIVE_DATA_DELAY_SECONDS)
    buf = _delay_buffers.setdefault(key, [])
    buf.append((now, value))
    cutoff = now - delay_seconds
    while len(buf) > 1 and buf[1][0] <= cutoff:
        buf.pop(0)
    return buf[0][1] if buf[0][0] <= cutoff else value


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
    # MLB's own abstractGameState buckets "Warmup" under "Live" (confirmed
    # live: players on the field, broadcast underway, but first pitch
    # hasn't happened — status was {"abstractGameState": "Live",
    # "detailedState": "Warmup"} a genuine 21 minutes before start_time).
    # Treated as still upcoming so the jumbotron doesn't flip to a 0-0
    # "live" scoreboard while there's real pregame time left (session
    # report: "there's still quite some time till the game starts, and
    # it's put us into live mode... which is confusing"). NHL's own
    # equivalent pregame state ("PRE") is already mapped to "upcoming"
    # below — this is an MLB-only quirk.
    if g["status"].get("detailedState") == "Warmup":
        state = "upcoming"
    else:
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
        # Raw detailedState, MLB-only (NHL's own game dict has no
        # equivalent) — exposed so sports_alerts can fire a one-time
        # "warmups underway" toast on the Preview->Warmup transition,
        # which "state" alone can't distinguish from any other still-
        # upcoming game.
        "detail_state": g["status"].get("detailedState"),
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


def _mlb_linescore_delayed(game_id: int) -> dict:
    """_fetch_mlb_linescore_raw, run through _delayed — shared by
    fetch_mlb_live_detail and fetch_mlb_live_matchup so the inning/count
    state and the batter/pitcher on it stay in lockstep at the same
    delayed instant, rather than each drifting against its own buffer."""
    return _delayed(f"mlb_linescore_{game_id}", _fetch_mlb_linescore_raw(game_id))


def fetch_mlb_live_detail(game_id: int) -> dict | None:
    """{"inning_state" ("Top"/"Bottom"/"Middle"/"End"), "current_inning",
    "balls", "strikes", "outs", "batter", "pitcher", "bases":
    {"first","second","third": bool}, "away_score", "home_score"} — the
    live situation, plus the score itself (session report: "the big
    score takes forever to update" — the compact game dict everywhere
    else this used to come from is only refreshed every
    GAME_CACHE_TTL_SECONDS (5 min, fine for a schedule, far too slow
    for a live score); this linescore endpoint is already polled every
    LIVE_DETAIL_CACHE_TTL_SECONDS (30s) for the situation fields below,
    and carries the real live score too). None on any fetch failure (no
    last-good fallback: a stale pitch count/base state — or score —
    would be actively misleading rather than just old, unlike a season
    schedule that barely changes). Held back the current live-data
    delay behind the real feed via _mlb_linescore_delayed, to trail the
    TV broadcast rather than lead it."""
    try:
        data = _mlb_linescore_delayed(game_id)
    except Exception:
        return None

    offense = data.get("offense", {})
    defense = data.get("defense", {})
    teams = data.get("teams", {})
    return {
        "inning_state": data.get("inningState"),
        "current_inning": data.get("currentInning"),
        "balls": data.get("balls"),
        "strikes": data.get("strikes"),
        "outs": data.get("outs"),
        "batter": (offense.get("batter") or {}).get("fullName"),
        "pitcher": (defense.get("pitcher") or {}).get("fullName"),
        "bases": {"first": "first" in offense, "second": "second" in offense, "third": "third" in offense},
        "away_score": (teams.get("away") or {}).get("runs"),
        "home_score": (teams.get("home") or {}).get("runs"),
    }


PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people/{player_id}"


@st.cache_data(ttl=LIVE_DETAIL_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_mlb_player_raw(player_id: int, group: str) -> dict:
    """This one player's full /people payload — bio fields (name,
    number, height/weight, age, throws/bats hand, ...) plus their
    season stat splits for `group` ("hitting"/"pitching") — {} if the
    API genuinely has nothing for this id. Used via
    _fetch_mlb_player_season_stat_raw for the Current Matchup card's
    stat line."""
    fetch_throttle.wait_turn()
    resp = requests.get(PEOPLE_URL.format(player_id=player_id), params={"hydrate": f"stats(group=[{group}],type=[season])"}, timeout=10)
    resp.raise_for_status()
    people = resp.json().get("people") or []
    return people[0] if people else {}


def _fetch_mlb_player_season_stat_raw(player_id: int, group: str) -> dict:
    """This one player's own season-total stat line for `group`
    ("hitting"/"pitching") — {} if the API genuinely has none yet (a
    two-way player with no innings pitched this season, a September
    call-up, etc.), not just on a fetch failure."""
    person = _fetch_mlb_player_raw(player_id, group)
    stats = person.get("stats") or []
    if not stats:
        return {}
    splits = stats[0].get("splits") or []
    return splits[0].get("stat", {}) if splits else {}


# MLB's own headshot CDN, keyed by player id — no API call, same idea
# as _mlb_logo_url (confirmed live this returns a real photo for a
# real player id, 404s harmlessly otherwise — callers already handle a
# broken image with onerror).
_MLB_HEADSHOT_URL = (
    "https://img.mlbstatic.com/mlb-photos/image/upload/"
    "w_213,d_people:generic:headshot:silo:current.png,q_auto:best,f_auto/v1/people/{player_id}/headshot/67/current"
)


def _mlb_headshot_url(player_id: int) -> str:
    return _MLB_HEADSHOT_URL.format(player_id=player_id)


MLB_BOXSCORE_URL = "https://statsapi.mlb.com/api/v1/game/{game_id}/boxscore"


@st.cache_data(ttl=LIVE_DETAIL_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_mlb_boxscore_raw(game_id: int) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(MLB_BOXSCORE_URL.format(game_id=game_id), timeout=10)
    resp.raise_for_status()
    return resp.json()


def _mlb_game_pitching_totals(game_id: int, pitcher_id: int) -> dict:
    """This specific game's pitch count, plus how many of those were
    balls vs strikes, so far for one pitcher — {"pitches", "balls",
    "strikes"}, any of which is None if genuinely not available yet.
    Session request: "for pitchers add number of pitches below ERA,"
    then clarified to "how many of the pitches have been balls and how
    many have been strikes over the entire outing" (not the live
    at-bat's own count, which the situation strip above already
    shows). Season ERA comes from the /people stat line, but these are
    inherently per-game, only in the boxscore's own per-player stats.
    {} on any fetch failure or before this pitcher has thrown a pitch
    this game (not yet in the boxscore's player list). Delayed the same
    amount as the linescore feed, so this pitcher's count doesn't tick
    up before the pitch it reflects has aired."""
    try:
        data = _delayed(f"mlb_boxscore_{game_id}", _fetch_mlb_boxscore_raw(game_id))
    except Exception:
        return {}
    for side in ("home", "away"):
        players = ((data.get("teams") or {}).get(side) or {}).get("players") or {}
        for p in players.values():
            if (p.get("person") or {}).get("id") == pitcher_id:
                pitching = (p.get("stats") or {}).get("pitching", {})
                return {"pitches": pitching.get("numberOfPitches"), "balls": pitching.get("balls"), "strikes": pitching.get("strikes")}
    return {}


def fetch_mlb_live_matchup(game_id: int) -> dict | None:
    """{"batter": {"id", "name", "ops", "photo"}, "pitcher": {"id",
    "name", "era", "pitches", "balls", "strikes", "photo"}} for
    whoever's actually at the plate/on the mound right now — session
    request: "during the game can you make the top performers tab show
    current pitcher and batter and their stats... ideally add the
    pitcher and batter pics," later refined to "for pitchers add
    number of pitches below ERA" (briefly swapped the batter stat to
    AVG in the same request, then "keep ops, screw avg" put it right
    back) and then "how many of the pitches have been balls and how
    many have been strikes over the entire outing." Reuses the same
    cached linescore fetch_mlb_live_detail already pulls this rerun (no
    extra request for the matchup itself), one small extra request
    each for the two players' own season stat lines plus one boxscore
    request for the pitcher's game-total pitch/ball/strike counts.
    None on any fetch failure or once there's genuinely no one at the
    plate/mound to name (the linescore payload omits offense/defense
    between innings). Uses the same _mlb_linescore_delayed snapshot as
    fetch_mlb_live_detail (see its own docstring) so the matchup shown
    here never gets ahead of the situation strip above it."""
    try:
        data = _mlb_linescore_delayed(game_id)
    except Exception:
        return None
    batter = (data.get("offense") or {}).get("batter")
    pitcher = (data.get("defense") or {}).get("pitcher")
    if not batter or not pitcher:
        return None
    batter_stat = _fetch_mlb_player_season_stat_raw(batter["id"], "hitting")
    pitcher_stat = _fetch_mlb_player_season_stat_raw(pitcher["id"], "pitching")
    pitcher_totals = _mlb_game_pitching_totals(game_id, pitcher["id"])
    return {
        "batter": {"id": batter["id"], "name": batter["fullName"], "ops": batter_stat.get("ops"), "photo": _mlb_headshot_url(batter["id"])},
        "pitcher": {
            "id": pitcher["id"],
            "name": pitcher["fullName"],
            "era": pitcher_stat.get("era"),
            "pitches": pitcher_totals.get("pitches"),
            "balls": pitcher_totals.get("balls"),
            "strikes": pitcher_totals.get("strikes"),
            "photo": _mlb_headshot_url(pitcher["id"]),
        },
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
    """{"period_label", "clock", "in_intermission",
    "intermission_seconds_remaining", "away_score", "home_score"} —
    the live situation, plus the score itself (same "the big score
    takes forever to update" fix as fetch_mlb_live_detail — see its
    own docstring). "intermission_seconds_remaining" is the same
    clock.secondsRemaining the NHL's own broadcast intermission
    countdown uses — real seconds left until the next period, not an
    estimate — session request: "a timer till the game resumes again."
    None on any fetch failure, same reasoning as fetch_mlb_live_detail.
    Delayed the same amount as the MLB side, so the intermission
    countdown targets when the broadcast shows puck drop, not the true
    (slightly earlier) instant."""
    try:
        box = _delayed(f"nhl_boxscore_{game_id}", _fetch_nhl_boxscore_raw(game_id))
    except Exception:
        return None

    clock = box.get("clock", {})
    return {
        "period_label": _nhl_period_label(box.get("periodDescriptor", {})),
        "clock": clock.get("timeRemaining"),
        "in_intermission": clock.get("inIntermission", False),
        "intermission_seconds_remaining": clock.get("secondsRemaining"),
        "away_score": (box.get("awayTeam") or {}).get("score"),
        "home_score": (box.get("homeTeam") or {}).get("score"),
    }


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
