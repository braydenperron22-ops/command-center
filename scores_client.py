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

import data_health
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
    data_health.record_success("scoreboard")

    games = [g for g in (_normalize_game(e) for e in raw) if g is not None]
    games.sort(key=lambda g: g["start_time"] or datetime.max)
    _last_good_games[league_key] = games
    return games


# Session request (jumbotron Featured board): win probability and a
# real "Top Performers" grid with headshots across BOTH teams. Neither
# exists on the native MLB/NHL APIs sports_client.py otherwise uses for
# the Featured board — ESPN's own scoreboard/summary payload is where
# this data actually lives (it's also exactly where the original
# static mockup pulled it from, which is why that version had this so
# easily). Cross-referenced by team abbreviation against today's
# already-fetched ESPN scoreboard rather than a separate team-schedule
# lookup — same data this module's own fetch_games() already pulls.
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/summary"


def find_espn_competition(league_key: str, away_name: str, home_name: str, today: datetime | None = None) -> dict | None:
    """{"event_id", "competition", "sport", "league"} for today's ESPN
    game matching these two teams' full display names, or None if
    nothing matches (ESPN simply not carrying this game) — every
    caller of this treats None as "skip this feature," never a hard
    failure. Matched by name rather than abbreviation: MLB Stats API's
    own schedule payload doesn't carry team abbreviations at all
    (confirmed live), while both it and the NHL API already hand back
    full names (game["opponent"], sports_client.MLB_TEAM_NAME/
    NHL_TEAM_NAME) that line up exactly with ESPN's own displayName
    (confirmed live for tonight's real matchup)."""
    league = next((entry for entry in LEAGUES if entry["key"] == league_key), None)
    if league is None:
        return None
    today = today or datetime.now(ZoneInfo(TIMEZONE))
    try:
        raw = _fetch_scoreboard_raw(league["sport"], league["league"], today.strftime("%Y%m%d"))
    except Exception:
        return None
    wanted = {away_name.lower(), home_name.lower()}
    for event in raw:
        competition = (event.get("competitions") or [{}])[0]
        names = {(c.get("team", {}).get("displayName") or "").lower() for c in competition.get("competitors", [])}
        if wanted <= names:
            return {"event_id": event.get("id"), "competition": competition, "sport": league["sport"], "league": league["league"]}
    return None


@st.cache_data(ttl=GAME_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_summary_raw(sport: str, league: str, event_id: str) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(SUMMARY_URL.format(sport=sport, league=league), params={"event": event_id}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def win_probability(match: dict) -> float | None:
    """Home team's live win probability (0-100) — only populates once
    ESPN's own model has enough of the game to compute one (confirmed
    live: null pregame), so None is the normal, expected pregame state,
    not a failure."""
    try:
        summary = _fetch_summary_raw(match["sport"], match["league"], match["event_id"])
    except Exception:
        return None
    wp = summary.get("winprobability") or []
    if not wp:
        return None
    pct = wp[-1].get("homeWinPercentage")
    return pct * 100 if pct is not None else None


def leaders_with_headshots(match: dict, max_items: int = 8) -> list[dict]:
    """Every real statistical leader across BOTH teams in this game —
    {"cat", "who", "stat", "hshot"} — same shape and purpose as the
    original static mockup's own leadersFrom(): a per-game "Top
    Performers" grid with real headshot photos, ported because the
    data (and the photos) turned out to already be one ESPN call away,
    not because the mockup's own click-through drawer/live JS came with
    it (see sports_alerts.py's own docstring for what was deliberately
    left out and why). Skips ESPN's own composite "Rating" category —
    not a real single stat, same reasoning as this module's own
    _game_leader. [] once the game is far enough along that ESPN stops
    returning leaders (never happens in practice, but no different a
    result to callers than "no leaders yet")."""
    competition = match["competition"]
    out = []
    for competitor in competition.get("competitors", []):
        abbr = competitor.get("team", {}).get("abbreviation", "")
        for category in competitor.get("leaders") or []:
            leaders = category.get("leaders") or []
            if not leaders or "rating" in (category.get("name") or "").lower():
                continue
            l0 = leaders[0]
            athlete = l0.get("athlete") or {}
            hshot = athlete.get("headshot")
            if isinstance(hshot, dict):
                hshot = hshot.get("href")
            who = athlete.get("shortName") or athlete.get("displayName") or ""
            stat = l0.get("displayValue") or ""
            if not who or not stat:
                continue
            out.append(
                {
                    "cat": category.get("abbreviation") or category.get("shortDisplayName") or category.get("name") or "",
                    "who": f"{who} · {abbr}",
                    "stat": stat,
                    "hshot": hshot,
                }
            )
    return out[:max_items]
