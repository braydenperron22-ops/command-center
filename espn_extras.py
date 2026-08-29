"""Session request: "smart jumbotron / pregame warm-up mode" — a
pregame show for the jumbotron's 3 tracked teams (Jays/Habs/Saints),
with real storylines like a broadcast pregame show has ("player X just
got called up and is making their debut," "team Y has scored the most
in the league over its last 10 games"). Three ESPN endpoints not used
anywhere else in this app, confirmed live against real Jays/Habs/Saints
data while planning this: team transactions (call-ups/trades/waivers —
the exact kind of storyline that inspired this whole feature), team-
filtered news, and league-wide statistical leaders.

Kept in its own module rather than folded into scores_client.py
(general ESPN scoreboard-wide utilities already used by game_blurb.py)
since these three each need their own real amount of parsing/pagination/
$ref-resolution logic, not just one more thin accessor.

Same conventions every other ESPN call in this app already follows
(scores_client.py/sports_client.py/ufc_client.py): plain requests.get
through fetch_throttle.wait_turn(), st.cache_data on the raw fetch,
try/except-and-return-empty on any failure — no new error-handling
philosophy, and never invents a fact that isn't really in the response
(this app's rule everywhere else, most recently morning_briefing.py's
own hero-badge audit)."""

import datetime as _dt

import requests
import streamlit as st

import fetch_throttle

TRANSACTIONS_URL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/transactions"
NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/news"
CORE_API_BASE = "https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}"

TRANSACTIONS_CACHE_TTL_SECONDS = 30 * 60  # dated prose entries, doesn't need to be fresher than this
NEWS_CACHE_TTL_SECONDS = 30 * 60
# League leaders move slowly (a full game's worth of stats, once a
# day at most) — cached far longer than this app's usual live-data
# TTLs, and each entry costs its own resolve GET (see _resolve_ref_
# cached below), so there's a real cost to polling this often too.
LEADERS_CACHE_TTL_SECONDS = 6 * 60 * 60


@st.cache_data(ttl=TRANSACTIONS_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_transactions_raw(sport: str, league: str, team_id: int) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(
        TRANSACTIONS_URL.format(sport=sport, league=league),
        params={"team": team_id, "limit": 50},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_transactions(sport: str, league: str, team_id: int, days: int = 10) -> list[dict]:
    """Real, dated transactions for this team — [{"date", "description"}],
    newest first, trimmed to the last `days` days. Confirmed live
    (2026-08-29): recalls, trades, waivers, IL moves, signings, all as
    real prose ESPN itself writes ("Recalled RHP CJ Van Eyk from
    Buffalo (IL)... Designated RHP Simeon Woods Richardson for
    assignment"), not something this app has to construct from raw
    fields. `?team=` genuinely filters (confirmed live by diffing
    against a second team's id — only genuine league-wide items like
    farm-system rankings overlap). [] on any fetch failure or if
    genuinely nothing's happened in the window."""
    try:
        data = _fetch_transactions_raw(sport, league, team_id)
    except Exception:
        return []
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    out = []
    for t in data.get("transactions") or []:
        date_str = t.get("date")
        desc = t.get("description")
        if not date_str or not desc:
            continue
        try:
            when = _dt.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when < cutoff:
            continue
        out.append({"date": when, "description": desc})
    return sorted(out, key=lambda t: t["date"], reverse=True)


@st.cache_data(ttl=NEWS_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_news_raw(sport: str, league: str, team_id: int) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(NEWS_URL.format(sport=sport, league=league), params={"team": team_id}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_team_news(sport: str, league: str, team_id: int, max_items: int = 5) -> list[dict]:
    """Real team-filtered headlines — [{"headline", "description"}], up
    to max_items. Distinct from scores_client.fetch_summary()'s own
    "news" key, which is ESPN's generic league-wide feed (confirmed
    live: unfiltered, almost never mentions our own team). This one
    genuinely filters (confirmed live by diffing against a second
    team's id) — though NHL's own pool is thin right now, off-season,
    and ESPN backfills with general league content when a team
    genuinely has nothing fresh of its own. Same graceful degradation
    as everywhere else in this app, not an error — the caller (and the
    AI prompt built from this) should treat a generic-sounding headline
    as weaker material, not force it into a storyline."""
    try:
        data = _fetch_news_raw(sport, league, team_id)
    except Exception:
        return []
    out = []
    for a in (data.get("articles") or [])[:max_items]:
        headline = a.get("headline")
        if not headline:
            continue
        out.append({"headline": headline, "description": a.get("description") or ""})
    return out


@st.cache_data(ttl=LEADERS_CACHE_TTL_SECONDS, show_spinner=False)
def _resolve_ref_cached(ref_url: str) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(ref_url, timeout=10)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=LEADERS_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_season_types_raw(sport: str, league: str, year: int) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(f"{CORE_API_BASE.format(sport=sport, league=league)}/seasons/{year}/types", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _current_season_type(sport: str, league: str, year: int) -> int:
    """Which season "type" (ESPN's own convention: 1=preseason,
    2=regular, 3=postseason) is actually active right now, picked by
    real date rather than hardcoded — confirmed live this matters: a
    hardcoded type=2 (regular season) 404s for NFL's own leaders
    endpoint right now (2026-08-29, still preseason: "No stats found").
    Falls back to 2 on any lookup failure — the common case for most of
    a season."""
    try:
        items = _fetch_season_types_raw(sport, league, year).get("items") or []
        now = _dt.datetime.now(_dt.timezone.utc)
        for ref in items:
            detail = _resolve_ref_cached(ref["$ref"])
            start = _dt.datetime.fromisoformat(detail["startDate"].replace("Z", "+00:00"))
            end = _dt.datetime.fromisoformat(detail["endDate"].replace("Z", "+00:00"))
            if start <= now <= end:
                return detail["type"]
    except Exception:
        pass
    return 2


@st.cache_data(ttl=LEADERS_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_leaders_raw(sport: str, league: str, year: int, season_type: int) -> dict:
    fetch_throttle.wait_turn()
    url = f"{CORE_API_BASE.format(sport=sport, league=league)}/seasons/{year}/types/{season_type}/leaders"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_league_leaders(
    sport: str, league: str, categories: list[str], year: int | None = None, top_n: int = 5
) -> dict[str, list[dict]]:
    """Real league-wide statistical leaders, resolved to real names —
    {category: [{"name", "team_abbr", "value", "display"}]}, ordered
    same as ESPN's own list (already rank order). Confirmed live: MLB
    home runs (Kyle Schwarber 40, Matt Olson 37...), NHL points
    (Connor McDavid 138...), NFL passing yards. Each ESPN leader entry
    is a $ref needing its own resolve GET — capped to top_n per
    category to bound the real request count, and the whole result is
    cached (LEADERS_CACHE_TTL_SECONDS) since this genuinely doesn't
    move fast. {} for any category ESPN doesn't have data for right
    now (a real, common case — see _current_season_type's own
    docstring on the NFL-preseason "No stats found" case) or on an
    outright fetch failure — never invented."""
    year = year or _dt.datetime.now().year
    season_type = _current_season_type(sport, league, year)
    try:
        data = _fetch_leaders_raw(sport, league, year, season_type)
    except Exception:
        return {}
    by_name = {c.get("name"): c for c in data.get("categories") or []}
    out: dict[str, list[dict]] = {}
    for cat in categories:
        category = by_name.get(cat)
        if not category:
            continue
        entries = []
        for leader in (category.get("leaders") or [])[:top_n]:
            athlete_ref = (leader.get("athlete") or {}).get("$ref")
            team_ref = (leader.get("team") or {}).get("$ref")
            if not athlete_ref:
                continue
            try:
                athlete = _resolve_ref_cached(athlete_ref)
                team = _resolve_ref_cached(team_ref) if team_ref else {}
            except Exception:
                continue
            name = athlete.get("shortName") or athlete.get("displayName")
            if not name:
                continue
            entries.append(
                {
                    "name": name,
                    "team_abbr": team.get("abbreviation", ""),
                    "value": leader.get("value"),
                    "display": leader.get("displayValue"),
                }
            )
        if entries:
            out[cat] = entries
    return out
