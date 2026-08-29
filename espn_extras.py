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

Session follow-up: "make sure that they're completely upstash as well
so that there's no error on rerun." Every raw fetch below is now
backed by persisted_state (Upstash, with the same local-file fallback
persisted_state.py's own docstring describes) instead of plain st.
cache_data — a process restart mid-pregame-window no longer forces a
slow cold re-fetch of transactions/news/leaders, matching the same
restart-surviving guarantee pregame_storylines.py's own AI-card cache
already has. See _persisted_fetch's own docstring for the exact shape
(mirrors groq_client.generate_periodic's time-window pattern, applied
to a plain ESPN JSON fetch instead of an AI call).

Same conventions every other ESPN call in this app already follows
(scores_client.py/sports_client.py/ufc_client.py): plain requests.get
through fetch_throttle.wait_turn(), try/except-and-return-empty on any
failure — no new error-handling philosophy, and never invents a fact
that isn't really in the response (this app's rule everywhere else,
most recently morning_briefing.py's own hero-badge audit)."""

import datetime as _dt
import time

import requests

import fetch_throttle
import persisted_state

TRANSACTIONS_URL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/transactions"
NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/news"
CORE_API_BASE = "https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}"
# Session follow-up: "deeper statistical context — Hot Streaks, Cold
# Streaks, Career-High/Career-Best Years, and Fall-Off/Regressive
# Seasons." A different ESPN host from everything above (site.web.
# api.espn.com — sports_client.py already has one precedent using this
# same host, for playoff-odds standings) — confirmed live against 3
# real players (George Springer/MLB, Kirby Dach/NHL, Zach Wilson/NFL):
# .../athletes/{id}/gamelog returns real game-by-game logs (newest
# category and newest event first within it — confirmed against
# Springer's own real box score, a 4-for-4/1-HR game matched exactly),
# and .../athletes/{id}/stats returns real season-by-season history
# INCLUDING the current in-progress season, several years back. The
# category NAME differs by sport/position (MLB: "career-batting"/
# "career-pitching"; NHL: the player's own position name, e.g.
# "center"; NFL: "passing"/"rushing"/etc.) — not hardcoded here, this
# module just reads whichever category ESPN lists first for that
# player, which is consistently their own primary stat line.
PLAYER_STATS_BASE = "https://site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/athletes/{athlete_id}"

TRANSACTIONS_CACHE_TTL_SECONDS = 30 * 60  # dated prose entries, doesn't need to be fresher than this
NEWS_CACHE_TTL_SECONDS = 30 * 60
# League leaders move slowly (a full game's worth of stats, once a
# day at most) — cached far longer than this app's usual live-data
# TTLs, and each entry costs its own resolve GET (see _resolve_ref_
# cached below), so there's a real cost to polling this often too.
LEADERS_CACHE_TTL_SECONDS = 6 * 60 * 60

# Bounded the same way game_blurb.py's own persisted cache is — plain
# dicts preserve insertion order, so dropping the oldest key on
# overflow is the same one-liner. Comfortably above the real key count
# this module ever produces (3 teams x a handful of fetch kinds, plus
# however many distinct athlete/team $refs fetch_league_leaders
# resolves) — a safety net against unbounded growth, not something
# that trims real data in normal use.
MAX_CACHED_ENTRIES = 500
_PERSIST_KEY = "espn_extras_cache"


def _load_cache() -> dict:
    raw = persisted_state.load(_PERSIST_KEY, {})
    return raw if isinstance(raw, dict) else {}


# {cache_key: {"at": epoch_seconds, "value": ...}} — module-level, same
# load-once-at-import shape game_blurb.py's own _pregame_cache/
# _postgame_cache already use.
_cache: dict[str, dict] = _load_cache()


def _persisted_fetch(cache_key: str, ttl_seconds: int, fetch_fn):
    """Same time-window cache shape groq_client.generate_periodic
    already uses for AI calls (see that function's own docstring for
    the full reasoning) — applied here to a plain ESPN JSON fetch
    instead. Checks the in-process dict first (instant, no network
    round-trip for a repeat call within one running process — these
    fetches only ever happen once per real pregame window anyway,
    gated by pregame_storylines' own per-game_id cache, but no reason
    to pay Upstash latency twice for the same value in one process's
    lifetime), then persisted_state (Upstash) as the durable layer
    underneath it — a process restart mid-window reuses whatever was
    last fetched instead of paying a slow cold re-fetch. Only persists
    on a real fetch success; a failure just raises straight through,
    same as st.cache_data's own behavior, so every caller's existing
    try/except already handles it unchanged."""
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and now - cached["at"] < ttl_seconds:
        return cached["value"]
    value = fetch_fn()
    _cache[cache_key] = {"at": now, "value": value}
    if len(_cache) > MAX_CACHED_ENTRIES:
        _cache.pop(next(iter(_cache)))
    persisted_state.save(_PERSIST_KEY, _cache)
    return value


def _fetch_transactions_raw(sport: str, league: str, team_id: int) -> dict:
    def _do():
        fetch_throttle.wait_turn()
        resp = requests.get(
            TRANSACTIONS_URL.format(sport=sport, league=league),
            params={"team": team_id, "limit": 50},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    return _persisted_fetch(f"transactions_{sport}_{league}_{team_id}", TRANSACTIONS_CACHE_TTL_SECONDS, _do)


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


def _fetch_news_raw(sport: str, league: str, team_id: int) -> dict:
    def _do():
        fetch_throttle.wait_turn()
        resp = requests.get(NEWS_URL.format(sport=sport, league=league), params={"team": team_id}, timeout=10)
        resp.raise_for_status()
        return resp.json()

    return _persisted_fetch(f"news_{sport}_{league}_{team_id}", NEWS_CACHE_TTL_SECONDS, _do)


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


def _resolve_ref_cached(ref_url: str) -> dict:
    def _do():
        fetch_throttle.wait_turn()
        resp = requests.get(ref_url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    return _persisted_fetch(f"ref_{ref_url}", LEADERS_CACHE_TTL_SECONDS, _do)


def _fetch_season_types_raw(sport: str, league: str, year: int) -> dict:
    def _do():
        fetch_throttle.wait_turn()
        resp = requests.get(f"{CORE_API_BASE.format(sport=sport, league=league)}/seasons/{year}/types", timeout=10)
        resp.raise_for_status()
        return resp.json()

    return _persisted_fetch(f"season_types_{sport}_{league}_{year}", LEADERS_CACHE_TTL_SECONDS, _do)


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


def _fetch_leaders_raw(sport: str, league: str, year: int, season_type: int) -> dict:
    def _do():
        fetch_throttle.wait_turn()
        url = f"{CORE_API_BASE.format(sport=sport, league=league)}/seasons/{year}/types/{season_type}/leaders"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    return _persisted_fetch(f"leaders_{sport}_{league}_{year}_{season_type}", LEADERS_CACHE_TTL_SECONDS, _do)


def fetch_league_leaders(
    sport: str, league: str, categories: list[str], year: int | None = None, top_n: int = 5
) -> dict[str, list[dict]]:
    """Real league-wide statistical leaders, resolved to real names —
    {category: [{"name", "id", "team_abbr", "value", "display"}]}, ordered
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
                    "id": athlete.get("id"),
                    "team_abbr": team.get("abbreviation", ""),
                    "value": leader.get("value"),
                    "display": leader.get("displayValue"),
                }
            )
        if entries:
            out[cat] = entries
    return out


GAMELOG_CACHE_TTL_SECONDS = 30 * 60  # a player's last game changes at most once a day
CAREER_STATS_CACHE_TTL_SECONDS = 12 * 60 * 60  # season-to-date totals move slowly, once a game at most

# Rate/percentage columns a gamelog's own stats array carries as a
# CUMULATIVE season-to-date value as of that game, not that game's own
# isolated number (confirmed live: George Springer's own AVG/OBP/SLG/
# OPS columns tick upward game to game, matching a running total, while
# his AB/H/HR/RBI columns matched his real single-game box score
# exactly) — summing these across a "last N games" window would
# produce a meaningless number, so recent_game_trend below skips them
# entirely rather than silently reporting something wrong. Matched by
# a simple heuristic (any label containing one of these substrings)
# since the exact label spelling drifts by sport (AVG/OBP/SLG/OPS for
# batters, ERA/CMP%/QBR/RTG for pitchers and QBs, SPCT for skaters).
_RATE_LABEL_HINTS = ("AVG", "OBP", "SLG", "OPS", "ERA", "PCT", "RTG", "QBR", "%")

# Real "more is better" marquee counting stats, checked in this order
# — career_trajectory takes whichever of these the player's own stats
# actually carry, prioritizing the first (most sport-typical) match.
# Deliberately excludes anything where a higher number isn't
# unambiguously good regardless of position (INT thrown, sacks
# allowed) or where "better" means LOWER (ERA, GAA) — those would need
# their own inverted comparison this first pass doesn't attempt yet.
_TRAJECTORY_STAT_LABELS = ["HR", "RBI", "OPS", "AVG", "SO", "W", "SV", "PTS", "G", "A", "YDS", "TD"]
# AVG/OPS (and any other rate stat that sneaks into the list above)
# compare directly rather than getting prorated by games played — a
# .300 average 50 games in is already directly comparable to a full
# season's .300, unlike a counting stat.
_TRAJECTORY_RATE_LABELS = {"AVG", "OPS", "OBP", "SLG"}
_FULL_SEASON_GAMES = {"mlb": 162, "nhl": 82, "nfl": 17}
MIN_GAMES_FOR_PACE = 8  # too early in any of the 3 seasons' own length for a "pace" to mean anything below this


def _fetch_gamelog_raw(sport: str, league: str, athlete_id) -> dict:
    def _do():
        fetch_throttle.wait_turn()
        resp = requests.get(f"{PLAYER_STATS_BASE.format(sport=sport, league=league, athlete_id=athlete_id)}/gamelog", timeout=10)
        resp.raise_for_status()
        return resp.json()

    return _persisted_fetch(f"gamelog_{sport}_{league}_{athlete_id}", GAMELOG_CACHE_TTL_SECONDS, _do)


def _fetch_career_stats_raw(sport: str, league: str, athlete_id) -> dict:
    def _do():
        fetch_throttle.wait_turn()
        resp = requests.get(f"{PLAYER_STATS_BASE.format(sport=sport, league=league, athlete_id=athlete_id)}/stats", timeout=10)
        resp.raise_for_status()
        return resp.json()

    return _persisted_fetch(f"career_stats_{sport}_{league}_{athlete_id}", CAREER_STATS_CACHE_TTL_SECONDS, _do)


def _safe_float(raw) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def recent_game_trend(sport: str, league: str, athlete_id, n_games: int = 10) -> dict | None:
    """Real last-N-games aggregate for this athlete — {"games", "stats":
    {label: value}}, summing each game's own real counting stats (see
    _RATE_LABEL_HINTS's own comment on why the cumulative rate columns
    are skipped rather than summed) and deriving a real AVG from summed
    AB/H when both are present — the one rate stat genuinely worth
    reporting for a window like this, computed honestly instead of
    read off a column that doesn't actually represent it. None on any
    fetch failure, or if this player genuinely has fewer than n_games
    played yet this season — a "last 10 games" claim backed by only 3
    real games would be misleading, not helpful, same "never show a
    stat that isn't real" rule as everywhere else in this app."""
    try:
        data = _fetch_gamelog_raw(sport, league, athlete_id)
    except Exception:
        return None
    labels = data.get("labels") or []
    season_types = data.get("seasonTypes") or []
    if not season_types or not labels:
        return None
    events = []
    for cat in season_types[0].get("categories") or []:
        events.extend(cat.get("events") or [])
    if len(events) < n_games:
        return None
    window = events[:n_games]  # confirmed live: newest event first, both across categories and within one

    sums: dict[str, float] = {}
    for ev in window:
        stats = ev.get("stats") or []
        for i, label in enumerate(labels):
            if i >= len(stats) or any(hint in label.upper() for hint in _RATE_LABEL_HINTS):
                continue
            value = _safe_float(stats[i])
            if value is not None:
                sums[label] = sums.get(label, 0) + value

    if not sums:
        return None
    stats_out: dict[str, str] = {
        label: (str(int(total)) if total == int(total) else f"{total:g}") for label, total in sums.items()
    }
    if "AB" in sums and "H" in sums and sums["AB"]:
        stats_out["AVG"] = f"{sums['H'] / sums['AB']:.3f}".lstrip("0")
    return {"games": n_games, "stats": stats_out}


def career_trajectory(sport: str, league: str, athlete_id) -> dict | None:
    """Whether this season's real pace is a genuine career year or a
    real fall-off against this player's own past seasons — {"label",
    "direction": "career_year"|"fall_off", "current_pace" (or current
    value for a rate stat), "games_played", "career_best",
    "career_best_year"}. None whenever there's nothing real to report:
    no multi-season history at all (a rookie — see MIN_GAMES_FOR_PACE's
    own comment), too early in the current season for a pace to mean
    anything, or the player's real pace simply isn't notable either
    way (most players, most seasons) — a normal season correctly
    produces nothing here, never a forced verdict."""
    try:
        data = _fetch_career_stats_raw(sport, league, athlete_id)
    except Exception:
        return None
    categories = data.get("categories") or []
    if not categories:
        return None
    labels = categories[0].get("labels") or []
    seasons = categories[0].get("statistics") or []
    if len(seasons) < 2:
        return None
    current, past = seasons[-1], seasons[:-1]

    def _val(season: dict, label: str) -> float | None:
        if label not in labels:
            return None
        idx = labels.index(label)
        stats = season.get("stats") or []
        return _safe_float(stats[idx]) if idx < len(stats) else None

    games_played = _val(current, "GP")
    if not games_played or games_played < MIN_GAMES_FOR_PACE:
        return None
    full_season = _FULL_SEASON_GAMES.get(league, 82)

    best_candidate, best_ratio_delta = None, 0.0
    for label in _TRAJECTORY_STAT_LABELS:
        current_val = _val(current, label)
        if current_val is None:
            continue
        past_vals = [(v, (s.get("season") or {}).get("year")) for s in past if (v := _val(s, label)) is not None]
        if not past_vals:
            continue
        career_best_val, career_best_year = max(past_vals, key=lambda t: t[0])
        if career_best_val <= 0:
            continue
        is_rate = label in _TRAJECTORY_RATE_LABELS
        pace = current_val if is_rate else (current_val / games_played * full_season)
        ratio = pace / career_best_val
        if ratio >= 1.05:
            direction = "career_year"
        elif ratio <= 0.7:
            direction = "fall_off"
        else:
            continue
        ratio_delta = abs(ratio - 1)
        if ratio_delta > best_ratio_delta:
            best_ratio_delta = ratio_delta
            best_candidate = {
                "label": label,
                "direction": direction,
                "current_pace": round(pace, 3) if is_rate else round(pace),
                "games_played": int(games_played),
                "career_best": career_best_val,
                "career_best_year": career_best_year,
            }
    return best_candidate


# Session follow-up: "matchup- and history-aware... season head-to-head
# records... individual batter vs pitcher or batter vs opponent team
# splits... venue/situational stats." Same site.web.api.espn.com host
# as gamelog/stats above — .../athletes/{id}/splits, confirmed live
# for a real MLB batter (George Springer), a real MLB pitcher (Dylan
# Cease — 0.69 ERA / 17 K in 13 IP across 2 real starts vs Seattle,
# genuinely dramatic real data) and spot-checked for NHL. Real
# categories confirmed present: byOpponent (per-opponent-team splits —
# this season's real at-bats/starts against that specific team, often
# a small sample, which is why _prompt below is told to name the
# sample size rather than let a hot 4-AB split read as a big trend),
# byArena (real venue-specific career splits — includes tonight's
# actual ballpark when the player has played there), byBreakdown
# (includes real Home/Away splits). Individual batter-vs-THIS-EXACT-
# PITCHER splits are a real, separate, MLB-only data source already
# in this app (sports_client._fetch_mlb_vs_pitcher_raw, MLB Stats
# API's own "vsPlayer" split) — NOT wired in here, since it needs MLB
# Stats API's own player ids, a different id space than the ESPN ids
# this module works in throughout, and has no NHL/NFL equivalent; the
# user's own spec said "where available," and team-level opponent
# splits (this module) are the real, available, cross-sport answer.
PLAYER_SPLITS_CACHE_TTL_SECONDS = 12 * 60 * 60  # same slow-moving cadence as career stats


def _fetch_splits_raw(sport: str, league: str, athlete_id) -> dict:
    def _do():
        fetch_throttle.wait_turn()
        resp = requests.get(f"{PLAYER_STATS_BASE.format(sport=sport, league=league, athlete_id=athlete_id)}/splits", timeout=10)
        resp.raise_for_status()
        return resp.json()

    return _persisted_fetch(f"splits_{sport}_{league}_{athlete_id}", PLAYER_SPLITS_CACHE_TTL_SECONDS, _do)


def _find_split(splits: list[dict], name_hint: str) -> dict | None:
    """Fuzzy match by real display name — ESPN's own byOpponent/byArena
    entries aren't perfectly consistent about a "vs " prefix (confirmed
    live: some real entries are "Seattle Mariners", others "vs Buffalo
    Sabres"), so this checks the hint as a substring either direction
    rather than requiring an exact string match."""
    hint = name_hint.lower()
    for s in splits:
        display = (s.get("displayName") or "").lower()
        if display and (hint in display or display in hint):
            return s
    return None


def _split_stats(labels: list[str], split: dict | None) -> dict[str, str]:
    if not split:
        return {}
    stats = split.get("stats") or []
    return {label: stats[i] for i, label in enumerate(labels) if i < len(stats) and stats[i] not in (None, "-", "")}


def _named_split(sport: str, league: str, athlete_id, category_name: str, name_hint: str) -> dict[str, str]:
    try:
        data = _fetch_splits_raw(sport, league, athlete_id)
    except Exception:
        return {}
    labels = data.get("labels") or []
    category = next((c for c in data.get("splitCategories") or [] if c.get("name") == category_name), None)
    if not category:
        return {}
    return _split_stats(labels, _find_split(category.get("splits") or [], name_hint))


def opponent_split(sport: str, league: str, athlete_id, opponent_name: str) -> dict[str, str]:
    """This player's REAL stats against `opponent_name` specifically —
    {label: value}, {} if ESPN has no real split for this exact
    opponent (a real, common case — many pairs simply haven't played
    much this season) or the fetch fails. Often a genuinely small
    sample (a handful of at-bats/one start) — real either way, but the
    caller/prompt should say so rather than let a hot small sample read
    as an established trend."""
    return _named_split(sport, league, athlete_id, "byOpponent", opponent_name)


def venue_split(sport: str, league: str, athlete_id, venue_name: str) -> dict[str, str]:
    """This player's REAL career stats at `venue_name` specifically —
    {label: value}, {} if ESPN has no byArena category for this sport
    (confirmed live: NHL doesn't carry one) or no real split for this
    exact venue (never played there, or not enough of a sample for
    ESPN to report)."""
    return _named_split(sport, league, athlete_id, "byArena", venue_name)


def home_away_split(sport: str, league: str, athlete_id, is_home: bool) -> dict[str, str]:
    """This player's REAL Home or Away season split — {label: value}."""
    return _named_split(sport, league, athlete_id, "byBreakdown", "Home" if is_home else "Away")
