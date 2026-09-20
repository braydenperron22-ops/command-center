"""Jumbotron data layer — every fetch, every derived value, every real
cross-rerun `st.session_state` read/write the board needs, with zero
HTML in it.

Split out of pages_jumbotron.py during the 2026-09-20 ground-up UI
rebuild. That module had grown to ~60 functions that each mixed a real
fetch/compute with string-building, which made a visual rebuild
impossible to do without also re-deriving (and risking) the data. The
rule now: this file decides WHAT is true, pages_jumbotron.py decides
what it LOOKS like, and the boundary between them is plain dicts.

Nothing here knows about CSS class names, `html.escape`, or markup. A
function returns None (or an empty list/dict) when there's genuinely
nothing to show — every caller on the render side treats that as "omit
this panel entirely," which is this app's established rule for missing
data everywhere else.

Data sources are untouched by the rebuild: sports_client (game/
standings/form/live detail), scores_client (league-wide slate, ESPN
cross-reference, win probability), ufc_client, pregame_storylines,
game_blurb.
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

import game_blurb
import pregame_storylines
import scores_client
import sports_client
import ufc_client
from config import TIMEZONE

# All three teams always appear in the My Teams rail, in the same
# priority order the toast queue and countdown headlines use — session
# request adding the Saints: "habs -> jays -> saints," lowest priority
# last (see sports_alerts.COUNTDOWN_PRIORITY, same ordering).
RAIL = [
    {"sport": "nhl", "label": "CANADIENS", "fetch_status": sports_client.fetch_habs, "kickoff": "TO PUCK DROP"},
    {"sport": "mlb", "label": "BLUE JAYS", "fetch_status": sports_client.fetch_jays, "kickoff": "TO FIRST PITCH"},
    {"sport": "nfl", "label": "SAINTS", "fetch_status": sports_client.fetch_saints, "kickoff": "TO KICKOFF"},
]

# Around-the-leagues rail: a real MLB slate is regularly 12-15 games and
# capping to a handful silently hid most of tonight's games. Nothing is
# dropped now — each league gets every one of its games, split into
# AROUND_PAGE_SIZE-row pages, and the whole set of pages cycles on a
# wall-clock timer. Pagination (not overflow) is the fit mechanism: the
# kiosk never scrolls, so anything past what fits would be permanently
# invisible, not merely below the fold. NBA deliberately excluded —
# session request: "I don't really fuck with the NBA."
AROUND_LEAGUES = ["mlb", "nhl", "nfl"]
AROUND_PAGE_SIZE = 6
AROUND_ROTATE_SECONDS = 12
FORM_GAMES_SHOWN = 8

# Same fixed-page-size/wall-clock-rotation discipline for the UFC full
# card — confirmed live against a real 14-bout card that only 4 rows fit
# cleanly in the reference strip under the hero.
UFC_CARD_PAGE_SIZE = 4
UFC_CARD_ROTATE_SECONDS = 12
# How long a recent-action line holds the UFC phase-line slot before
# reverting to the plain round/clock display.
UFC_RECENT_EVENT_HOLD_SECONDS = 6

STORYLINE_ROTATE_SECONDS = 22
LEADER_ROTATE_SECONDS = 5
STANDINGS_ROTATE_SECONDS = 20

TEAM_ESPN_NAME = {
    "mlb": sports_client.MLB_TEAM_NAME,
    "nhl": sports_client.NHL_TEAM_NAME,
    "nfl": sports_client.NFL_TEAM_NAME,
}
TEAM_FULL_NAME = {
    "mlb": sports_client.MLB_TEAM_NAME,
    "nhl": sports_client.NHL_TEAM_NAME,
    "nfl": sports_client.NFL_TEAM_NAME,
}
# Our own fixed per-team accent, as (r, g, b). Real data, not a design
# choice to re-make: the opponent's color comes straight from ESPN via
# scores_client.team_color and blends against these at a controlled
# alpha, so both sides need the same numeric form.
TEAM_COLOR_RGB = {"mlb": (62, 124, 201), "nhl": (216, 50, 63), "nfl": (211, 188, 141)}
OPPONENT_FALLBACK_RGB = (82, 92, 110)

PREGAME_SITUATION_LABEL = {"mlb": "FIRST PITCH", "nhl": "PUCK DROP", "nfl": "KICKOFF"}
NFL_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
INNING_ARROW = {"Top": "▲", "Bottom": "▼"}
TOP3_ROLE_LABEL = {"hitter": "Hitter", "starter": "Starting Pitcher", "reliever": "Reliever", "closer": "Closer"}

NEXT_GAME_FETCHER = {
    "mlb": sports_client.fetch_mlb_next_game,
    "nhl": sports_client.fetch_nhl_next_game,
    "nfl": sports_client.fetch_nfl_next_game,
}
NEXT_GAME_LEVEL_LABEL = {"preseason": "Preseason opener", "regular": "Season opener", "playoff": "Playoff opener"}

# ESPN's own abbreviation for each tracked team, so a live game can be
# picked straight out of scores_client.fetch_games(sport)'s already-
# fetched list rather than reshaping sports_client's own feeds.
PINNED_TEAM_ABBR = {
    "mlb": sports_client.MLB_TEAM_ABBR,
    "nhl": sports_client.NHL_TEAM_ABBR,
    "nfl": sports_client.NFL_TEAM_ABBR,
}

# Session request: "add conditional formatting to the strike% value for
# pitchers so i can see at a glance if a pitcher is flowing or is
# struggling to find the zone." League-average strike rate sits around
# 63-64%, so thresholds sit a healthy distance either side with a dead
# zone between them. The minimum pitch count guards against a small
# early-outing sample reading as a streak (3 pitches, 3 strikes = 100%
# means nothing).
STRIKE_PCT_HOT = 66
STRIKE_PCT_COLD = 58
STRIKE_PCT_MIN_PITCHES = 10

# Real Statcast plate coordinates (feet, 0 = the middle of the plate)
# plotted to scale, not a stylized zone graphic. The viewbox is wider
# and taller than the real zone so a genuine ball well outside it still
# lands on the diagram instead of clipping at the edge; the pZ range
# comfortably covers real strike-zone bounds for any batter height plus
# a couple of feet of margin either side. DO NOT retune these to make
# something "look" better — the transform is the data.
ZONE_PLATE_HALF_WIDTH_FT = 17 / 2 / 12  # real MLB plate width (17in), halved
ZONE_PX_RANGE_FT = 1.75  # +/- feet shown horizontally
ZONE_PZ_MIN_FT, ZONE_PZ_MAX_FT = 0.5, 4.5  # feet shown vertically
ZONE_SVG_W, ZONE_SVG_H = 140, 160
MAX_PITCHES_SHOWN = 8
PITCH_RESULT_COLOR = {"ball": "#32D74B", "strike": "#FF6961", "foul_frozen": "#9BA6BA"}

# MLB's own short classification for a play (result.event), grouped just
# enough to tone the full-screen announcement by what actually happened
# rather than re-deriving it from the free-text description. Not
# exhaustive — anything unlisted still shows, in the neutral tone.
HIT_EVENTS = {"Single", "Double", "Triple", "Home Run", "Walk", "Intent Walk", "Hit By Pitch"}
OUT_EVENTS = {
    "Strikeout", "Groundout", "Flyout", "Lineout", "Pop Out", "Double Play", "Triple Play",
    "Sac Fly", "Sac Bunt", "Field Out", "Force Out", "Grounded Into DP", "Fielders Choice Out",
}

# sports_client.delayed() already trails the raw feed by the jumbotron's
# own delay stepper, but that's a flat buffer on whatever state happened
# to get polled — it doesn't guarantee the moment the batting team
# changes stays on screen, especially when a whole half-inning break
# falls inside one 5s live-detail poll window. This holds the previous
# half's last real matchup for this long after the batting team changes.
MATCHUP_SWITCH_HOLD_SECONDS = 15
# MLB's own pitch-clock rule fixes every half-inning break at exactly
# this long (session correction: "its a 1:30 countdown").
MLB_BREAK_SECONDS = 90
# Session correction: "an NFL halftime lasts thirteen minutes. So from
# the time that halftime first updates, just make a ten minute timer."
# Deliberately shorter than the real break — end on the timer, never
# wait for play to actually resume.
NFL_HALFTIME_SECONDS = 10 * 60
# Session request: "delay the out of town scoreboard by like 15 seconds
# so i can actually see the last play of the inning."
OVERLAY_DELAY_SECONDS = 15
# Session request: "can the animation be longer than 3 seconds?" — the
# play-result announcement is re-rendered across as many reruns as it
# takes to fill this many real seconds, tracked from when the play was
# first detected rather than capped at whatever one rerun survives.
PLAY_RESULT_HOLD_SECONDS = 5


# --------------------------------------------------------------------
# Small pure helpers
# --------------------------------------------------------------------

def countdown(target: datetime, now: datetime) -> dict:
    """{"target_ms", "text"} for a live, once-a-second ticking countdown.

    `text` is only ever the FIRST frame's value — app.py's global
    live-countdown ticker script recomputes against the browser's own
    clock every second from there, independent of Streamlit's rerun
    cadence entirely. The render side MUST emit `target_ms` as
    data-target-ms on an element with class="live-countdown" or the
    number silently freezes at whatever this returned.

    Anything a full day or more out shows days+hours ("6d 4h"), not raw
    hours — session report: "the saints game shows like two hundred and
    twenty two hours, which is ridiculous." app.py's own kioskFmtClock
    mirrors this exact cutover, so the display can't flip from correct
    to wrong one second in.
    """
    target_ms = int(target.replace(tzinfo=ZoneInfo(TIMEZONE)).timestamp() * 1000)
    total = max(0, int((target - now).total_seconds()))
    if total >= 86400:
        days, rem = divmod(total, 86400)
        text = f"{days}d {rem // 3600}h"
    else:
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        # Session request: drop the leading hour digit under an hour
        # ("43:55", not "0:43:55").
        text = f"{hours}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes}:{seconds:02d}"
    return {"target_ms": target_ms, "text": text}


def fmt_break_clock(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def days_until_text(target: datetime, now: datetime) -> str:
    days = (target.date() - now.date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


def record_for(status: dict) -> str:
    for row in status.get("standings") or []:
        if row.get("is_team"):
            return f'{row["wins"]}-{row["losses"]}'
    return ""


def record_for_name(status: dict, name: str) -> str:
    """Opponent's record, when they happen to share our division (so
    they're already in the standings payload we fetched) — "" otherwise,
    rather than a whole extra API call for a nicety."""
    for row in status.get("standings") or []:
        if row.get("team") and row["team"].lower() in name.lower():
            return f'{row["wins"]}-{row["losses"]}'
    return ""


def sides(status: dict, game: dict, team_label: str) -> tuple[dict, dict]:
    """(away, home), each {"name", "logo", "record", "is_us"} — laid out
    as a real scoreboard (away on the left) rather than always putting us
    first, matching the big score digits' own away-left/home-right
    order."""
    us = {"name": team_label.title(), "logo": status["team_logo"], "record": record_for(status), "is_us": True}
    them = {
        "name": game["opponent"],
        "logo": game["opponent_logo"],
        "record": record_for_name(status, game["opponent"]),
        "is_us": False,
    }
    return (them, us) if game["is_home"] else (us, them)


def sides_neutral(game: dict) -> tuple[dict, dict]:
    """sides()'s equivalent for a semis/finals game between two teams we
    have no stake in. Both "is_us": False, which is also what makes
    side_color fall through to each team's own REAL ESPN color with no
    other code downstream needing to know this game is different.

    Uses "full_name" ("Edmonton Oilers"), not the short "name" — this
    same value doubles as side_color's lookup key into
    scores_client.team_color, which matches on ESPN's own full
    displayName (confirmed live: the short name silently misses there,
    always falling back to gray)."""

    def side(s: dict) -> dict:
        return {
            "name": s.get("full_name") or s["name"],
            "logo": s["logo"],
            "record": s.get("record") or "",
            "is_us": False,
        }

    return side(game["away"]), side(game["home"])


def side_color(sport: str, match: dict | None, side: dict) -> tuple[int, int, int]:
    """This side's real (r, g, b) — our own fixed team color, or the
    opponent's real color straight from ESPN. Falls back to a neutral
    gray whenever ESPN doesn't have today's game or genuinely has no
    usable color for that team."""
    if side["is_us"]:
        return TEAM_COLOR_RGB.get(sport, (255, 179, 0))
    if match is None:
        return OPPONENT_FALLBACK_RGB
    return scores_client.team_color(match["competition"], side["name"]) or OPPONENT_FALLBACK_RGB


def espn_match_for(sport: str, game: dict) -> dict | None:
    """The ESPN competition for this specific tracked-team game, if
    findable — backs win probability, top performers and every opponent
    color lookup, so it's resolved once per render, not per panel."""
    our_name = TEAM_ESPN_NAME.get(sport)
    if not our_name or not game.get("opponent"):
        return None
    return scores_client.find_espn_competition(sport, game["opponent"], our_name)


def strike_pct_heat(strikes, total_pitches) -> str | None:
    if not total_pitches or total_pitches < STRIKE_PCT_MIN_PITCHES:
        return None
    pct = strikes / total_pitches * 100
    if pct >= STRIKE_PCT_HOT:
        return "hot"
    if pct <= STRIKE_PCT_COLD:
        return "cold"
    return None


def zone_svg_x(px: float) -> float:
    return (px + ZONE_PX_RANGE_FT) / (2 * ZONE_PX_RANGE_FT) * ZONE_SVG_W


def zone_svg_y(pz: float) -> float:
    return ZONE_SVG_H - (pz - ZONE_PZ_MIN_FT) / (ZONE_PZ_MAX_FT - ZONE_PZ_MIN_FT) * ZONE_SVG_H


# --------------------------------------------------------------------
# NFL situation maths (pure, fed from one cached fetch)
# --------------------------------------------------------------------

def nfl_competition(game_id) -> dict:
    """{"status", "situation", "competitors"}, or {} if this game_id
    isn't on today's scoreboard.

    sports_client.fetch_nfl_competition, NOT the match/espn_match_for
    wrapper every other NFL panel reads — session report: "why is the
    NFL on the jumbotron screen not, like, live... it just stays
    frozen." That match-based path shares scores_client's 5-MINUTE
    schedule cache; this shares the NFL-specific 5-second live cache
    instead, matching MLB/NHL."""
    return sports_client.fetch_nfl_competition(game_id) or {}


def nfl_possession_home(situation: dict, competitors: list[dict]) -> bool | None:
    """Whether the HOME team currently has the ball — ESPN's own
    situation.possession is a team id, matched against this
    competition's competitors for their "homeAway" field (not a
    name-match). None pregame/postgame or on any missing field."""
    possession_id = (situation or {}).get("possession")
    if not possession_id:
        return None
    return next((c.get("homeAway") == "home" for c in (competitors or []) if c.get("id") == possession_id), None)


def nfl_yards_out(situation: dict, possession_home: bool | None) -> int | None:
    """Distance remaining to the end zone the team WITH THE BALL is
    actually driving toward — session request: "instead of saying LAR
    forty six, be like, X amount of yards out."

    ESPN's situation.yardLine is a fixed field-position coordinate (0 at
    the away team's own goal line, 100 at the home team's own goal line
    — confirmed against two real live snaps: the away team facing 3rd &
    1 at their OWN 36, 64 yards out, read yardLine=64 directly; the home
    team facing 2nd & Goal at the 8, 8 yards out, read yardLine=92). The
    away team's distance-to-score is that raw number; the home team's is
    the complement."""
    yard_line = (situation or {}).get("yardLine")
    if yard_line is None or possession_home is None:
        return None
    return yard_line if not possession_home else (100 - yard_line)


# --------------------------------------------------------------------
# Cross-rerun state helpers
# --------------------------------------------------------------------

def held_matchup(game_id: int, matchup: dict | None, half_marker: str) -> dict | None:
    """Which matchup to actually show right now — either the fresh one
    for the CURRENT half, or (for up to MATCHUP_SWITCH_HOLD_SECONDS
    after the batting half last changed) the previous half's last real
    matchup. Keyed by game_id + half_marker so a genuinely new half
    always starts its own fresh hold rather than inheriting one from a
    half two switches ago."""
    key = f"jumbotron_matchup_hold_{game_id}"
    now_ts = time.time()
    tracked = st.session_state.get(key)
    if tracked is None or tracked["marker"] != half_marker:
        st.session_state[key] = {
            "marker": half_marker,
            "matchup": matchup,
            "changed_at": now_ts,
            "prior_matchup": tracked["matchup"] if tracked else None,
        }
        tracked = st.session_state[key]
    elif matchup is not None:
        # Same half, fresher data for it — keep it current without
        # resetting the hold clock, which only cares about WHEN the half
        # itself last changed.
        tracked["matchup"] = matchup

    if tracked["prior_matchup"] is not None and now_ts - tracked["changed_at"] < MATCHUP_SWITCH_HOLD_SECONDS:
        return tracked["prior_matchup"]
    return tracked["matchup"]


def mlb_between_innings_target(game_id: int, detail: dict, now_ts: float) -> float | None:
    """The real epoch-seconds timestamp this break should end at, or
    None if not currently between innings. Keyed by inning+half (not
    just game_id) so a fresh break starts its own countdown rather than
    inheriting the last one's target."""
    inning_state = detail.get("inning_state")
    key = f"jumbotron_mlb_break_{game_id}"
    if inning_state not in ("Middle", "End"):
        st.session_state.pop(key, None)
        return None
    marker = f"{inning_state}:{detail.get('current_inning')}"
    tracked = st.session_state.get(key)
    if not tracked or tracked.get("marker") != marker:
        tracked = {"marker": marker, "started_at": now_ts}
        st.session_state[key] = tracked
    return tracked["started_at"] + MLB_BREAK_SECONDS


def nfl_halftime_target(game_id, detail: dict, now_ts: float) -> float | None:
    """Keyed by game_id alone, unlike MLB's version — a single game only
    ever has one halftime, so there's no second occurrence that could
    inherit a stale target."""
    key = f"jumbotron_nfl_halftime_{game_id}"
    if not detail.get("is_halftime"):
        st.session_state.pop(key, None)
        return None
    tracked = st.session_state.get(key)
    if not tracked:
        tracked = {"started_at": now_ts}
        st.session_state[key] = tracked
    return tracked["started_at"] + NFL_HALFTIME_SECONDS


def overlay_delay_elapsed(game_id: int, marker: str, now_ts: float) -> bool:
    key = f"jumbotron_overlay_delay_{game_id}"
    tracked = st.session_state.get(key)
    if not tracked or tracked.get("marker") != marker:
        tracked = {"marker": marker, "started_at": now_ts}
        st.session_state[key] = tracked
    return now_ts - tracked["started_at"] >= OVERLAY_DELAY_SECONDS


# --------------------------------------------------------------------
# Live situation strips
# --------------------------------------------------------------------

def mlb_situation_data(game_id: int) -> dict | None:
    """Inning/bases/count/outs for the live-situation strip, plus
    "just changed" flags for each.

    The flags are a real before/after comparison against what was last
    rendered for THIS game (keyed by game_id so a different game's bases
    never inherit this one's "just lit up" moment). They drive a static
    highlight state, not an animation — this app's global animation kill
    switch means anything keyframe-driven never plays, so the changed
    state has to BE a resting appearance."""
    detail = sports_client.fetch_mlb_live_detail(game_id)
    if not detail:
        return None
    bases = detail.get("bases") or {}

    prev_bases = st.session_state.get(f"jumbotron_mlb_bases_{game_id}", {})
    st.session_state[f"jumbotron_mlb_bases_{game_id}"] = dict(bases)

    base_state = {}
    for key in ("first", "second", "third"):
        on = bool(bases.get(key))
        base_state[key] = {"on": on, "new": on and not prev_bases.get(key)}

    balls, strikes, outs = detail.get("balls") or 0, detail.get("strikes") or 0, detail.get("outs") or 0
    prev_counts = st.session_state.get(f"jumbotron_mlb_counts_{game_id}", {})
    st.session_state[f"jumbotron_mlb_counts_{game_id}"] = {"b": balls, "s": strikes, "o": outs}

    # Session request: "put an up or down arrow beside inning instead of
    # top/bottom" — real scoreboard convention (▲ top, ▼ bottom). MLB's
    # own "Middle"/"End" inning-break states have no such convention, so
    # those still show as text.
    inning_state = detail.get("inning_state") or ""
    inning_num = detail.get("current_inning")
    arrow = INNING_ARROW.get(inning_state)
    inning = f"{arrow} {inning_num}" if arrow and inning_num else f"{inning_state} {inning_num or ''}".strip()

    return {
        "kind": "mlb",
        "inning": inning,
        "bases": base_state,
        "balls": balls,
        "strikes": strikes,
        "outs": outs,
        "ball_new": balls > prev_counts.get("b", 0),
        "strike_new": strikes > prev_counts.get("s", 0),
        "out_new": outs > prev_counts.get("o", 0),
    }


def nhl_situation_data(game_id: int) -> dict | None:
    detail = sports_client.fetch_nhl_live_detail(game_id)
    if not detail:
        return None
    if detail.get("in_intermission"):
        label = detail.get("period_label") or ""
        return {"kind": "nhl", "intermission": f"INTERMISSION — END OF {label}".strip()}
    return {
        "kind": "nhl",
        "intermission": None,
        "period_label": detail.get("period_label") or "",
        "clock": detail.get("clock") or "",
    }


def neutral_situation_data(status_text: str | None) -> dict | None:
    """The live-situation fallback for a neutral MLB/NHL game. The real
    diamond/period widgets poll the OFFICIAL league API by THAT league's
    own game id, a different id space than the ESPN event id a neutral
    game's game_id actually is — ESPN's own status text ("2nd - 10:21",
    "Top 5th") is the one live source that comes from the same ESPN
    event this game's score and records already do."""
    if not status_text:
        return None
    return {"kind": "neutral", "text": status_text.upper()}


def nfl_situation_data(game: dict, data: dict | None = None) -> dict | None:
    """Quarter + clock, down & distance (as yards out from the end zone),
    possession, red zone and timeouts. `data` lets the caller pass the
    one already-resolved nfl_competition() read in rather than making a
    second one."""
    data = nfl_competition(game["game_id"]) if data is None else data
    if not data:
        return None
    status = data.get("status") or {}
    situation = data.get("situation") or {}
    period = status.get("period")

    label = None
    if isinstance(period, int) and period > 0:
        label = f"{NFL_ORDINALS.get(period, f'{period}th')} QUARTER" if period <= 4 else "OVERTIME"

    possession_home = nfl_possession_home(situation, data.get("competitors") or [])
    yards_out = nfl_yards_out(situation, possession_home)
    down_text = situation.get("shortDownDistanceText") or situation.get("downDistanceText")
    if down_text and yards_out is not None:
        down_text = f"{down_text} · {yards_out} yards out"

    possession_label = None
    if possession_home is not None:
        possession_is_us = possession_home == game["is_home"]
        possession_label = {"is_us": possession_is_us, "text": "US BALL" if possession_is_us else "OPP BALL"}

    timeouts = None
    home_to, away_to = situation.get("homeTimeouts"), situation.get("awayTimeouts")
    if home_to is not None and away_to is not None:
        us_to, opp_to = (home_to, away_to) if game["is_home"] else (away_to, home_to)
        timeouts = f"TIMEOUTS {us_to}-{opp_to}"

    out = {
        "kind": "nfl",
        "period_label": label,
        "clock": str(status.get("displayClock")) if status.get("displayClock") else None,
        "down_text": down_text,
        "red_zone": bool(situation.get("isRedZone")),
        "possession": possession_label,
        "timeouts": timeouts,
        "possession_home": possession_home,
    }
    return out if any((label, out["clock"], down_text, possession_label, timeouts)) else None


# --------------------------------------------------------------------
# Pregame / blurb / storylines
# --------------------------------------------------------------------

def pregame_extra_data(sport: str, game_id: int) -> dict | None:
    """Venue + real game-day weather + probable starters (MLB), or just
    the arena name (NHL — no probable-goalie field, and every rink is
    indoor). None for NFL: no equivalent venue/weather fetch exists for
    the Saints' lighter-tier integration, and falling through to the NHL
    branch would call fetch_nhl_venue for a football game."""
    if sport == "mlb":
        extra = sports_client.fetch_mlb_pregame_extra(game_id)
        if not extra:
            return None
        return {
            "venue": extra.get("venue") or "",
            "weather_line": extra.get("weather_line") or "",
            "away_pitcher": extra.get("away_pitcher"),
            "home_pitcher": extra.get("home_pitcher"),
        }
    if sport == "nhl":
        venue = sports_client.fetch_nhl_venue(game_id)
        return {"venue": venue, "weather_line": "", "away_pitcher": None, "home_pitcher": None} if venue else None
    return None


def blurb_data(sport: str, game: dict, team_label: str, postgame: bool, status: dict | None = None) -> dict | None:
    """None whenever ESPN doesn't have this game or the AI call failed /
    hasn't landed — same "just omit it" rule every other optional panel
    follows, not a loading spinner."""
    our_name = TEAM_FULL_NAME[sport]
    away_name = our_name if not game["is_home"] else game["opponent"]
    home_name = game["opponent"] if not game["is_home"] else our_name
    fn = game_blurb.get_postgame_blurb if postgame else game_blurb.get_pregame_blurb
    text = fn(sport, game["game_id"], team_label, away_name, home_name, game["opponent"], status)
    if not text:
        return None
    return {"label": "AI Recap" if postgame else "AI Preview", "text": text}


def blurb_data_neutral(sport: str, game: dict, postgame: bool) -> dict | None:
    """blurb_data()'s equivalent for a semis/finals game between two
    teams we have no stake in — game_blurb needs a genuinely different
    entry point for that shape, not the same one with our_name blanked."""
    away_name = game["away"].get("full_name") or game["away"]["name"]
    home_name = game["home"].get("full_name") or game["home"]["name"]
    fn = game_blurb.get_neutral_postgame_blurb if postgame else game_blurb.get_neutral_pregame_blurb
    text = fn(sport, game["game_id"], away_name, home_name, game["match"], game.get("round_text"), game.get("series_summary"))
    if not text:
        return None
    return {"label": "AI Recap" if postgame else "AI Preview", "text": text}


def storyline_data(sport: str, game: dict, team_label: str, match: dict | None, now_ts: float) -> dict | None:
    """Pregame warm-up show — real player/team storylines (transactions,
    team news, league-wide leaders, injuries, this game's own leaders).
    Cards are generated ONCE per game_id by pregame_storylines' own
    persisted cache; this only handles the already-generated set's
    rotation, the same wall-clock pattern every other rotating panel
    uses. None whenever there's nothing real to build a card from."""
    our_name = TEAM_FULL_NAME[sport]
    away_name = our_name if not game["is_home"] else game["opponent"]
    home_name = game["opponent"] if not game["is_home"] else our_name
    cards = pregame_storylines.get_storyline_cards(
        sport, game["game_id"], team_label, away_name, home_name, game["opponent"], match
    )
    if not cards:
        return None
    index = int(now_ts // STORYLINE_ROTATE_SECONDS) % len(cards)
    return {
        "card": cards[index],
        "index": index,
        "total": len(cards),
        "accent_rgb": TEAM_COLOR_RGB.get(sport, (255, 179, 0)),
    }


# --------------------------------------------------------------------
# Win probability / performers / live matchup
# --------------------------------------------------------------------

def win_probability_data(sport: str, match: dict | None, away: dict, home: dict) -> dict | None:
    """Two-tier fallback, in this order and no other:
      1. ESPN's own live model (scores_client.win_probability, updated
         play-by-play) once it has enough of the game to compute one.
      2. The moneyline (scores_client.moneyline_win_probability) —
         pregame the live model is always None, confirmed live, so this
         is what shows before first pitch.
      3. None (panel omitted entirely) when neither source has anything.
    Only ESPN's payload carries either; the native MLB/NHL APIs the rest
    of this board runs on don't."""
    if not match:
        return None
    home_pct = scores_client.win_probability(match)
    title = "WIN PROBABILITY"
    if home_pct is None:
        home_pct = scores_client.moneyline_win_probability(match)
        title = "PREGAME ODDS"
    if home_pct is None:
        return None
    home_pct = round(home_pct)
    return {
        "title": title,
        "home_pct": home_pct,
        "away_pct": 100 - home_pct,
        "away_color": side_color(sport, match, away),
        "home_color": side_color(sport, match, home),
        "away_name": away["name"],
        "home_name": home["name"],
    }


def top_performers_data(match: dict | None, now_ts: float) -> dict | None:
    """Season-long stat leaders with real ESPN headshots, one spotlit at
    a time on a wall-clock rotation. Confirmed live that ESPN's
    scoreboard payload carries these regardless of whether the game has
    started, so this shows well before first pitch too."""
    if not match:
        return None
    leaders = scores_client.leaders_with_headshots(match)
    if not leaders:
        return None
    index = int(now_ts // LEADER_ROTATE_SECONDS) % len(leaders)
    return {"leaders": leaders, "index": index, "leader": leaders[index]}


def top3_performers_data(game_id: int) -> list[dict]:
    """Postgame "3 best players of the game" — MLB's own boxscore
    endpoint already carries a real, pre-ranked Game Score trio (see
    sports_client.fetch_mlb_top_performers). [] means the caller should
    fall back to the season-leader rotation so postgame never goes
    blank."""
    return sports_client.fetch_mlb_top_performers(game_id) or []


def strike_zone_data(game_id: int) -> dict | None:
    """The most recent pitches of the live at-bat, already plotted to
    real SVG coordinates. None whenever there's genuinely no pitch data
    for the current at-bat yet."""
    pitch_info = sports_client.fetch_mlb_recent_pitches(game_id)
    if not pitch_info:
        return None
    zone_top, zone_bottom = pitch_info["zone_top"], pitch_info["zone_bottom"]
    if zone_top is None or zone_bottom is None or not pitch_info["pitches"]:
        return None
    shown = pitch_info["pitches"][-MAX_PITCHES_SHOWN:]
    n = len(shown)
    dots = []
    for i, p in enumerate(shown):
        dots.append({
            "cx": zone_svg_x(p["px"]),
            "cy": zone_svg_y(p["pz"]),
            "color": PITCH_RESULT_COLOR.get(p["result"], "#9BA6BA"),
            "is_last": i == n - 1,
            # Older pitches fade toward transparent so the SEQUENCE, not
            # just each pitch's color, is readable at a glance.
            "opacity": 0.5 + 0.5 * (i + 1) / n,
            "speed": round(p["speed"]) if p.get("speed") is not None else "—",
            "type": p.get("type") or "—",
        })
    return {
        "box": {
            "x1": zone_svg_x(-ZONE_PLATE_HALF_WIDTH_FT),
            "x2": zone_svg_x(ZONE_PLATE_HALF_WIDTH_FT),
            "y1": zone_svg_y(zone_top),
            "y2": zone_svg_y(zone_bottom),
        },
        "dots": dots,
    }


def current_matchup_data(game_id: int) -> dict | None:
    """The two players actually involved in the live at-bat, with the
    stat rows each one gets. None between innings (past the matchup
    hold) or when the live feed has nobody at the plate/mound.

    Stat rows are [(value, label, heat), ...] per row; a None value is
    dropped by the render side. The heat values come from sports_client
    (vs-pitcher history, season OPS/ERA deltas) except STRIKE%, which is
    classified here against real league-average thresholds."""
    detail = sports_client.fetch_mlb_live_detail(game_id)
    half_marker = f"{detail.get('inning_state') if detail else None}:{detail.get('current_inning') if detail else None}"
    matchup = held_matchup(game_id, sports_client.fetch_mlb_live_matchup(game_id), half_marker)
    if not matchup:
        return None
    batter, pitcher = matchup["batter"], matchup["pitcher"]

    # The whole outing's ball/strike split as a percentage — session
    # correction: "I only want it shown for the pitcher's total ball and
    # strike count below their ERA and their pitches," specifically NOT
    # the at-bat's own live count, which keeps its real "2-1" form in
    # the situation strip.
    balls, strikes = pitcher.get("balls"), pitcher.get("strikes")
    total_pitches = (balls or 0) + (strikes or 0)
    strike_pct = (
        f"{round(strikes / total_pitches * 100)}%"
        if balls is not None and strikes is not None and total_pitches
        else None
    )
    heat = strike_pct_heat(strikes, total_pitches) if strike_pct is not None else None

    return {
        "batter": {
            "player": batter,
            "tag": "At Bat",
            "rows": [
                [(batter.get("ops"), "OPS", batter.get("season_ops_heat"))],
                [(batter.get("vs_pitcher"), "VS PITCHER", batter.get("vs_pitcher_heat"))],
            ],
            "line": None,
        },
        "pitcher": {
            "player": pitcher,
            "tag": "Pitching",
            "rows": [
                [
                    (pitcher.get("era"), "ERA", pitcher.get("season_era_heat")),
                    (pitcher.get("pitches"), "PITCHES", None),
                    (pitcher.get("strikeouts"), "K", None),
                ],
                [(strike_pct, "STRIKE%", heat)],
            ],
            "line": pitcher.get("line"),
        },
        "zone": strike_zone_data(game_id),
    }


def last_play_data(game_id: int) -> dict | None:
    """MLB's own real sentence for the last completed play, used
    verbatim. The score carried here is the live feed's own per-play
    result (not the board's separately-fetched current score) so the two
    are self-consistent even in a rerun where they'd momentarily
    disagree. None at the top of the 1st or on a fetch failure."""
    play = sports_client.fetch_mlb_last_play(game_id)
    if not play:
        return None
    return {
        "description": play["description"],
        "away_score": play["away_score"] if play["away_score"] is not None else "–",
        "home_score": play["home_score"] if play["home_score"] is not None else "–",
    }


def batting_order_data(state: dict) -> dict | None:
    """The batting order for whichever team is actually at bat, with
    each hitter's OPS already tiered against real, current league
    percentile cutoffs — session request, after attending a real Jays
    game: "they had the batting order, and the only stat they showed was
    OPS. This gave me a very easy way of seeing who is the best hitter."

    Live MLB only, and only when MLB actually won the takeover (
    sports_alerts' own priority already decided that by the time `state`
    gets here). None otherwise, which puts the My Teams rail back."""
    if (
        state.get("phase") != "live"
        or not state.get("game")
        or state["league"]["sport"] != "mlb"
        or state["league"].get("neutral")
    ):
        return None
    game_id = state["game"]["game_id"]
    full_order = sports_client.fetch_mlb_batting_order(game_id)
    if not full_order:
        return None
    live_detail = sports_client.fetch_mlb_live_detail(game_id)
    inning_state = live_detail.get("inning_state") if live_detail else None
    if not inning_state:
        return None
    batting_side = "home" if inning_state in ("Bottom", "Middle") else "away"
    # fetch_mlb_lineup_live_ops swaps each entry's boxscore-sourced OPS
    # for the same per-player read the Current Matchup card uses, so the
    # two can't disagree mid-game.
    entries = sports_client.fetch_mlb_lineup_live_ops(full_order[batting_side])
    entries = sports_client.fetch_mlb_lineup_game_line(game_id, entries)
    if not entries:
        return None

    away, home = sides(state["status"], state["game"], state["league"]["label"])
    team = home if batting_side == "home" else away
    match = espn_match_for(state["league"]["sport"], state["game"])
    tiers = sports_client.fetch_league_ops_tiers()
    current_batter = live_detail.get("batter") if live_detail else None
    rows = [
        {
            "entry": e,
            "is_current": current_batter is not None and e.get("name") == current_batter,
            "tier": sports_client.ops_tier(e.get("ops"), tiers),
        }
        for e in entries
    ]
    return {
        "team": team,
        "rows": rows,
        "accent_rgb": side_color(state["league"]["sport"], match, team),
    }


# --------------------------------------------------------------------
# Around the leagues / standings / rail
# --------------------------------------------------------------------

def mini_row_data(g: dict) -> dict:
    """One compact game row. The records and standout-performer line
    were already sitting unused on every game dict fetch_games returns,
    so they cost no extra fetching; the leader line only exists once
    state != "pre", same as ESPN's own leaders payload."""
    state = g["state"]
    if state == "pre":
        status_text = g["start_time"].strftime("%-I:%M") if g.get("start_time") else ""
    else:
        status_text = g.get("status_text") or ""
        # Session report: "the rain delay in the philly/baltimore game
        # is way too big" — ESPN appends the inning to any in-progress
        # delay ("Rain Delay, Bottom 3rd"), which wraps to two lines and
        # blows up this row's height. The inning is redundant here (the
        # row already shows the score), so a delay keeps its reason only.
        if "delay" in status_text.lower():
            status_text = status_text.split(",")[0].strip()
    return {"game": g, "state": state, "status_text": status_text, "leader": g.get("leader")}


def around_leagues_pages(now_ts: float) -> list[tuple[str, int, int, list[dict]]]:
    """Every game for every active league, split into fixed-size pages
    as (league_key, page_index, page_total, chunk). Nothing capped or
    dropped, just paged — one page shown at a time, picked by
    int(now_ts // AROUND_ROTATE_SECONDS) % len(pages) at each call site.
    Shared by the sidebar rail and the full-screen out-of-town overlay
    so both build the identical page set from the identical data on the
    identical clock."""
    pages: list[tuple[str, int, int, list[dict]]] = []
    order = {"in": 0, "pre": 1, "post": 2}
    for key in AROUND_LEAGUES:
        try:
            games = scores_client.fetch_games(key)
        except Exception:
            continue
        if not games:
            continue
        games = sorted(games, key=lambda g: order.get(g["state"], 3))
        chunks = [games[i : i + AROUND_PAGE_SIZE] for i in range(0, len(games), AROUND_PAGE_SIZE)]
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            pages.append((key, i, total, chunk))
    return pages


def around_data(now_ts: float) -> dict | None:
    """The current Around The Leagues page. The page-count label ("MLB ·
    2/3") is the entire "content just changed" signal — the old
    alternating fade-class trick that used to sit here was deleted in
    the 2026-09-20 rebuild: it existed only to force a CSS animation
    restart, which this app's global kill switch has prevented from ever
    running."""
    pages = around_leagues_pages(now_ts)
    if not pages:
        return None
    index = int(now_ts // AROUND_ROTATE_SECONDS) % len(pages)
    league_key, page_num, page_total, chunk = pages[index]
    label = league_key.upper() + (f" · {page_num + 1}/{page_total}" if page_total > 1 else "")
    return {"label": label, "rows": [mini_row_data(g) for g in chunk]}


def standings_data(now_ts: float) -> dict | None:
    """Bottom-left rotating division standings — every MLB, NHL and NFL
    division, not just the three our own teams sit in. NHL/NFL divisions
    still show in their own offseason, deliberately."""
    candidates = (
        sports_client.fetch_all_mlb_standings()
        + sports_client.fetch_all_nhl_standings()
        + sports_client.fetch_all_nfl_standings()
    )
    if not candidates:
        return None
    index = int(now_ts // STANDINGS_ROTATE_SECONDS) % len(candidates)
    entry = candidates[index]
    return {
        "league": entry["league"],
        "division": entry["division_name"],
        "page_label": f" · {index + 1}/{len(candidates)}" if len(candidates) > 1 else "",
        "rows": entry["rows"],
    }


def offseason_data(sport: str, now: datetime) -> dict | None:
    """None once fetch_*_next_game() itself comes up empty (no schedule
    published that far out yet) — the render side shows a plain
    "OFFSEASON" in that case."""
    next_game = NEXT_GAME_FETCHER[sport]()
    if not next_game:
        return None
    return {
        "label": NEXT_GAME_LEVEL_LABEL.get(next_game["level"], "Next game"),
        "date_text": next_game["start_time"].strftime("%b %-d"),
        "countdown_text": days_until_text(next_game["start_time"], now),
    }


def rail_hero_data(entry: dict, now: datetime) -> dict:
    """One My Teams card. `kind` tells the render side which shape it
    got: "offseason", "no_game", "upcoming", "live" or "final"."""
    status = entry["fetch_status"]()
    base = {"sport": entry["sport"], "label": entry["label"].title()}
    if not status:
        return {**base, "kind": "offseason", "offseason": offseason_data(entry["sport"], now)}

    game = status.get("game")
    out = {
        **base,
        "logo": status["team_logo"],
        "record": record_for(status),
        "division": status.get("division_name") or "",
        "odds": (status.get("playoff_odds") or {}).get("display") or "",
        "form": (status.get("recent_form") or [])[-FORM_GAMES_SHOWN:],
        "live": bool(game and game["state"] == "live"),
    }
    if not game:
        return {**out, "kind": "no_game"}
    if game["state"] == "upcoming":
        return {
            **out,
            "kind": "upcoming",
            "versus": "vs" if game["is_home"] else "@",
            "opponent": game["opponent"],
            # Same "delayed instead of stuck at 0:00" rule as the
            # featured board's own countdown; this compact chip has no
            # room for MLB's full detail_state text, so it stays generic.
            "delayed": now >= game["start_time"],
            "countdown": None if now >= game["start_time"] else countdown(game["start_time"], now),
        }
    return {
        **out,
        "kind": "final" if game["state"] == "final" else "live",
        "versus": "vs" if game["is_home"] else "@",
        "opponent": game["opponent"],
        "team_score": game["team_score"],
        "opp_score": game["opp_score"],
        "won": (game["team_score"] or 0) > (game["opp_score"] or 0),
    }


def ufc_rail_hero_data(now: datetime) -> dict:
    """UFC's own My Teams card — genuinely different shape from the
    other three (no team/record/standings/division/form). Deliberately
    NOT gated to the Saturday takeover window: that window decides when
    UFC is worth taking over the WHOLE screen; this card's job is just
    "what's the UFC status right now.\""""
    event = ufc_client.fetch_event_for_date(now.date())
    if event and event["state"] != "final":
        if event["state"] == "live":
            bout = ufc_client.current_bout(event)
            return {
                "kind": "live",
                "detail": event["name"],
                "fighter_a": bout["fighter_a"]["short_name"] if bout else None,
                "fighter_b": bout["fighter_b"]["short_name"] if bout else None,
            }
        if now >= event["start_time"]:
            return {"kind": "underway", "detail": event["name"]}
        return {"kind": "countdown", "detail": event["name"], "countdown": countdown(event["start_time"], now)}
    next_event = ufc_client.fetch_next_event(now)
    if not next_event:
        return {"kind": "none", "detail": ""}
    return {
        "kind": "scheduled",
        "detail": next_event["name"],
        "date_text": next_event["start_time"].strftime("%b %-d"),
        "countdown_text": days_until_text(next_event["start_time"], now),
    }


# --------------------------------------------------------------------
# Presence-gated full-screen overlays
#
# Both return None on every rerun they should NOT be on screen. That is
# the ONLY gate — the render side simply doesn't emit the element, and
# no CSS anywhere gives these a resting opacity:0/visibility:hidden. A
# resting-hidden style is exactly what made both of these invisible for
# good once the global animation kill switch landed.
# --------------------------------------------------------------------

def pinned_team_games(exclude_sport: str) -> list[dict]:
    """The live game (if any) for every tracked team other than the one
    already featured on the main board. "Live" only (state == "in")."""
    out = []
    for sport, abbr in PINNED_TEAM_ABBR.items():
        if sport == exclude_sport:
            continue
        try:
            games = scores_client.fetch_games(sport)
        except Exception:
            continue
        game = next((g for g in games if g["state"] == "in" and abbr in (g["home"]["abbr"], g["away"]["abbr"])), None)
        if game:
            out.append(game)
    return out


def pinned_ufc_bout(now: datetime) -> tuple[dict, dict] | None:
    """(event, bout) for a live UFC card right now, or None. Independent
    of app.py's own _ufc_takeover (which it nulls out when a team game
    owns the screen) since a pinned slot here is exactly the case that
    suppression exists for."""
    ufc_state = ufc_client.takeover_state(now)
    if not ufc_state or ufc_state["phase"] != "live":
        return None
    bout = ufc_client.current_bout(ufc_state["event"])
    if not bout:
        return None
    return ufc_state["event"], bout


def between_play_overlay_data(state: dict, now: datetime) -> dict | None:
    """Full-screen out-of-town scoreboard during a natural break in the
    featured game: MLB half-inning breaks, NHL intermissions, NFL
    halftime. Held back OVERLAY_DELAY_SECONDS from when the break
    actually started so the play that ended it stays readable first.

    Ends on its own timer rather than waiting for play to resume —
    MLB_BREAK_SECONDS/NFL_HALFTIME_SECONDS are deliberate references, so
    a real break running long never leaves this sitting on a stalled
    0:00 (session request: "make the out of town scoreboard end the
    second the timer is over").

    Never triggers for a neutral game: the live-detail fetches poll the
    official league API by ITS OWN game id, which a neutral game's
    ESPN-sourced id isn't, so `if not detail` degrades to simply never
    detecting a break rather than crashing."""
    if state.get("phase") != "live" or not state.get("game"):
        return None
    sport = state["league"]["sport"]
    game = state["game"]
    game_id = game["game_id"]
    now_ts = time.time()

    if sport == "mlb":
        detail = sports_client.fetch_mlb_live_detail(game_id)
        if not detail:
            return None
        target_ts = mlb_between_innings_target(game_id, detail, now_ts)
        if target_ts is None or target_ts - now_ts <= 0:
            return None
        marker = f'{detail.get("inning_state")}:{detail.get("current_inning")}'
        if not overlay_delay_elapsed(game_id, marker, now_ts):
            return None
        headline = f'{(detail.get("inning_state") or "").upper()} OF {detail.get("current_inning") or ""}'.strip()
        remaining = target_ts - now_ts
        timer_label = "GAME RESUMES IN"
    elif sport == "nhl":
        detail = sports_client.fetch_nhl_live_detail(game_id)
        if not detail or not detail.get("in_intermission"):
            return None
        secs = detail.get("intermission_seconds_remaining")
        if secs is None or secs <= 0:
            return None
        marker = f'intermission:{detail.get("period_label")}'
        if not overlay_delay_elapsed(game_id, marker, now_ts):
            return None
        headline = "INTERMISSION"
        target_ts = now_ts + secs
        remaining = secs
        timer_label = "UNTIL PUCK DROP"
    elif sport == "nfl":
        detail = sports_client.fetch_nfl_live_detail(game_id)
        if not detail:
            return None
        target_ts = nfl_halftime_target(game_id, detail, now_ts)
        if target_ts is None or target_ts - now_ts <= 0:
            return None
        if not overlay_delay_elapsed(game_id, "halftime", now_ts):
            return None
        headline = "HALFTIME"
        remaining = target_ts - now_ts
        timer_label = "SECOND HALF IN"
    else:
        return None

    pages = around_leagues_pages(now_ts)
    if not pages:
        return None
    index = int(now_ts // AROUND_ROTATE_SECONDS) % len(pages)
    league_key, page_num, page_total, chunk = pages[index]
    page_label = league_key.upper() + (f" · {page_num + 1}/{page_total}" if page_total > 1 else "")

    # Pinned rows are dropped from the rotating chunk first (so a pinned
    # game never shows twice), then the chunk is trimmed to leave room:
    # this overlay moved to fixed-size pages precisely because a kiosk
    # that can't scroll was silently losing rows past whatever fit, and
    # adding pinned rows on top of an already-tuned page would
    # reintroduce exactly that.
    pinned_games = pinned_team_games(exclude_sport=sport)
    pinned_keys = {(g["home"]["abbr"], g["away"]["abbr"]) for g in pinned_games}
    chunk = [g for g in chunk if (g["home"]["abbr"], g["away"]["abbr"]) not in pinned_keys]
    bout_pair = pinned_ufc_bout(now)
    pinned_total = len(pinned_games) + (1 if bout_pair else 0)
    chunk = chunk[: max(1, AROUND_PAGE_SIZE - pinned_total)]

    return {
        "headline": headline,
        "timer_label": timer_label,
        "target_ms": int(target_ts * 1000),
        "timer_text": fmt_break_clock(remaining),
        "page_label": page_label,
        "rows": [mini_row_data(g) for g in chunk],
        "pinned_rows": [mini_row_data(g) for g in pinned_games],
        "pinned_bout": bout_pair[1] if bout_pair else None,
    }


def play_result_data(state: dict) -> dict | None:
    """Full-screen announcement of what the last play actually was, held
    for PLAY_RESULT_HOLD_SECONDS of real elapsed time across however
    many reruns that takes. MLB-live only (NHL has no per-play "event"
    classification to key off), non-neutral only (same id-space reason
    as everything else that polls MLB Stats API directly).

    Session-guarded per (game_id, this play's identity): a genuinely new
    play resets the hold window; the same play re-detected later keeps
    counting from when it was first seen. Returns None the moment the
    window has elapsed — which is what takes the element out of the DOM
    entirely."""
    if (
        state.get("phase") != "live"
        or not state.get("game")
        or state["league"]["sport"] != "mlb"
        or state["league"].get("neutral")
    ):
        return None
    game_id = state["game"]["game_id"]
    play = sports_client.fetch_mlb_last_play(game_id)
    if not play or not play.get("event"):
        return None
    identity = f'{play.get("description")}|{play["away_score"]}|{play["home_score"]}'
    key = f"jumbotron_last_play_shown_{game_id}"
    now_ts = time.time()
    tracked = st.session_state.get(key)
    if not tracked or tracked.get("identity") != identity:
        tracked = {"identity": identity, "started_at": now_ts}
        st.session_state[key] = tracked
    if now_ts - tracked["started_at"] >= PLAY_RESULT_HOLD_SECONDS:
        return None
    event = play["event"]
    tone = "hit" if event in HIT_EVENTS else "out" if event in OUT_EVENTS else "neutral"
    return {"text": event.upper(), "tone": tone}


# --------------------------------------------------------------------
# Featured board
# --------------------------------------------------------------------

def board_data(state: dict, now: datetime) -> dict:
    """Everything the featured board needs, with `content_kind` naming
    which feature panel the render side should draw:
      "storylines"  — pregame warm-up cards (tracked teams only)
      "matchup"     — the live at-bat (MLB live, non-neutral)
      "top3"        — postgame Game Score trio (MLB postgame, non-neutral)
      "leaders"     — season stat leaders, the general fallback
      None          — nothing available, panel omitted
    """
    league, status, game = state["league"], state["status"], state["game"]
    sport, phase = league["sport"], state["phase"]
    neutral = league.get("neutral", False)
    now_ts = time.time()

    if neutral:
        away, home = sides_neutral(game)
        match = game["match"]
    else:
        away, home = sides(status, game, league["label"])
        match = espn_match_for(sport, game)

    # sport == "mlb" alone isn't enough below: the live matchup / last
    # play / top-performers fetches all poll MLB Stats API by ITS OWN
    # gamePk, which game["game_id"] holds for a tracked Jays game but
    # NOT for a neutral one (that's an ESPN event id). Feeding an ESPN
    # id there doesn't crash — it silently produces nothing, which is
    # worse than falling through to the ESPN/match-based rotation.
    content_kind = None
    content = None
    last_play = None
    if phase == "live" and sport == "mlb" and not neutral:
        content = current_matchup_data(game["game_id"])
        content_kind = "matchup" if content else None
        last_play = last_play_data(game["game_id"])
    elif phase == "postgame" and sport == "mlb" and not neutral:
        performers = top3_performers_data(game["game_id"])
        if performers:
            content_kind, content = "top3", performers
        else:
            content = top_performers_data(match, now_ts)
            content_kind = "leaders" if content else None
    else:
        content = top_performers_data(match, now_ts)
        content_kind = "leaders" if content else None

    out = {
        "league_label": league["label"],
        "sport": sport,
        "phase": phase,
        "neutral": neutral,
        "away": away,
        "home": home,
        "away_rgb": side_color(sport, match, away),
        "home_rgb": side_color(sport, match, home),
        "content_kind": content_kind,
        "content": content,
        "last_play": last_play,
        "nfl_possession_home": None,
        "situation": None,
        "pregame_extra": None,
        "blurb": None,
        "win_probability": None,
        "countdown": None,
        "delay_text": None,
        "kickoff_label": None,
        "start_label": None,
        "away_score": None,
        "home_score": None,
        "away_score_changed": False,
        "home_score_changed": False,
        "dim_away": False,
        "dim_home": False,
        "win_celebration": False,
    }

    if phase == "pregame":
        out["kickoff_label"] = next((r["kickoff"] for r in RAIL if r["sport"] == sport), "TO FIRST PITCH")
        # Session report: "the jays game is delayed can you make it show
        # delayed instead of sitting at 0:00." Once `now` has caught up
        # to the scheduled start there's nothing left to count down to,
        # so this switches to a plain status label. MLB's own
        # detail_state carries the real reason when there is one
        # ("Delayed Start: Rain"); NHL/NFL have no equivalent field.
        if now >= game["start_time"]:
            out["delay_text"] = (game.get("detail_state") or "Delayed").upper() if sport == "mlb" else "DELAYED"
        else:
            out["countdown"] = countdown(game["start_time"], now)
        out["start_label"] = (
            f'{PREGAME_SITUATION_LABEL.get(sport, "START")} {game["start_time"].strftime("%-I:%M %p")}'
        )
        if not neutral:
            out["pregame_extra"] = pregame_extra_data(sport, game["game_id"])
        # A pregame show replaces BOTH the plain AI Preview blurb and
        # the season-leaders card for our own teams. Neutral games keep
        # the blurb: pregame_storylines' material-gathering is built
        # entirely around one of OUR tracked teams.
        if neutral:
            out["blurb"] = blurb_data_neutral(sport, game, postgame=False)
        else:
            storylines = storyline_data(sport, game, league["label"].title(), match, now_ts)
            if storylines:
                out["content_kind"], out["content"] = "storylines", storylines
        out["win_probability"] = win_probability_data(sport, match, away, home)
        return out

    if neutral:
        away_score = int(game["away"]["score"]) if game["away"].get("score") not in (None, "") else None
        home_score = int(game["home"]["score"]) if game["home"].get("score") not in (None, "") else None
    else:
        away_score = game["opp_score"] if game["is_home"] else game["team_score"]
        home_score = game["team_score"] if game["is_home"] else game["opp_score"]

    # Session report: "the big score takes forever to update" — the
    # schedule endpoint only refreshes every 5 minutes, while the
    # live-detail endpoints poll every 5s for the situation strip below
    # and carry the real live score too. Same cached call, used here
    # first. No equivalent exists for NFL or for a neutral game (wrong
    # id space), which keep the schedule-level score.
    if phase == "live" and sport in ("mlb", "nhl") and not neutral:
        live_detail = (
            sports_client.fetch_mlb_live_detail(game["game_id"])
            if sport == "mlb"
            else sports_client.fetch_nhl_live_detail(game["game_id"])
        )
        if live_detail and live_detail.get("away_score") is not None and live_detail.get("home_score") is not None:
            away_score, home_score = live_detail["away_score"], live_detail["home_score"]

    # Score-change detection, keyed by game_id so two different games
    # can't cross-contaminate each other's "did it just change" read.
    # Drives a static highlight, not a flash animation — see
    # mlb_situation_data's own note on why.
    score_key = f"jumbotron_last_score_{game['game_id']}"
    prev_scores = st.session_state.get(score_key)
    if prev_scores is not None and phase == "live":
        prev_away, prev_home = prev_scores
        out["away_score_changed"] = away_score is not None and away_score != prev_away
        out["home_score_changed"] = home_score is not None and home_score != prev_home
    st.session_state[score_key] = (away_score, home_score)

    out["away_score"], out["home_score"] = away_score, home_score

    if phase == "live":
        if neutral and sport in ("mlb", "nhl"):
            out["situation"] = neutral_situation_data(game.get("status_text"))
        elif sport == "mlb":
            out["situation"] = mlb_situation_data(game["game_id"])
        elif sport == "nhl":
            out["situation"] = nhl_situation_data(game["game_id"])
        else:
            # Resolved once here so the possession icon next to the team
            # name and the situation strip share one read.
            nfl_data = nfl_competition(game["game_id"])
            out["situation"] = nfl_situation_data(game, nfl_data)
            out["nfl_possession_home"] = nfl_possession_home(
                nfl_data.get("situation") or {}, nfl_data.get("competitors") or []
            )
        out["win_probability"] = win_probability_data(sport, match, away, home)

    if phase == "postgame":
        out["blurb"] = (
            blurb_data_neutral(sport, game, postgame=True)
            if neutral
            else blurb_data(sport, game, league["label"].title(), postgame=True, status=status)
        )
        # Only a finished game has a settled winner to dim the loser
        # against — during a live game the trailing side is still in it.
        if away_score is not None and home_score is not None:
            out["dim_away"], out["dim_home"] = away_score < home_score, home_score < away_score
            # One-time win celebration, session-guarded per game_id so
            # it marks the moment a win is first observed rather than
            # re-firing every rerun of the ~15min postgame hold. No "our
            # side" exists in a neutral game, so it stays off there.
            if not neutral:
                our_score = away_score if away["is_us"] else home_score
                their_score = home_score if away["is_us"] else away_score
                win_key = f"jumbotron_win_shown_{game['game_id']}"
                if our_score > their_score and not st.session_state.get(win_key):
                    out["win_celebration"] = True
                    st.session_state[win_key] = True

    return out


# --------------------------------------------------------------------
# UFC
# --------------------------------------------------------------------

def ufc_stat_rows(bout_id: str, fighter_a: dict, fighter_b: dict, stats: dict | None) -> list[dict]:
    """Significant Strikes / Takedowns / Control Time — the trio a real
    UFC broadcast's lower-third leans on. Each bar's width is each
    fighter's actual share of the two combined (landed strikes, landed
    takedowns, seconds of control), NOT a win probability: ESPN's
    pickcenter is unavailable on every bout, confirmed live, and real
    volume/control differential is genuinely what a fight gets read by.
    [] whenever the stats fetch itself failed; a scoreless-but-fetched
    bout still shows real 0s, an honest "nothing's happened yet.\""""
    if not stats:
        return []
    a, b = stats["fighter_a"], stats["fighter_b"]

    def num(text) -> float:
        try:
            return float(text)
        except (TypeError, ValueError):
            return 0.0

    specs = [
        (
            "SIG. STRIKES",
            f'{a.get("sig_strikes_landed") or 0}/{a.get("sig_strikes_attempted") or 0}',
            f'{b.get("sig_strikes_landed") or 0}/{b.get("sig_strikes_attempted") or 0}',
            num(a.get("sig_strikes_landed")),
            num(b.get("sig_strikes_landed")),
        ),
        (
            "TAKEDOWNS",
            f'{a.get("takedowns_landed") or 0}/{a.get("takedowns_attempted") or 0}',
            f'{b.get("takedowns_landed") or 0}/{b.get("takedowns_attempted") or 0}',
            num(a.get("takedowns_landed")),
            num(b.get("takedowns_landed")),
        ),
        (
            "CONTROL TIME",
            a.get("control_time") or "0:00",
            b.get("control_time") or "0:00",
            ufc_client.parse_control_time_seconds(a.get("control_time")),
            ufc_client.parse_control_time_seconds(b.get("control_time")),
        ),
    ]
    rows = []
    for label, a_display, b_display, a_val, b_val in specs:
        total = a_val + b_val
        a_pct = round(100 * a_val / total) if total else 50
        rows.append({
            "label": label,
            "a_display": a_display,
            "b_display": b_display,
            "a_pct": a_pct,
            "b_pct": 100 - a_pct,
            "a_short": fighter_a["short_name"],
            "b_short": fighter_b["short_name"],
        })
    return rows


def ufc_knockdowns(stat_line: dict | None) -> int:
    """Knockdowns are rare and dramatic enough to call out on their own
    rather than bury in a bar row next to steadier volume stats. 0 both
    when there genuinely aren't any and when stats didn't load."""
    try:
        return max(0, int(float((stat_line or {}).get("knockdowns"))))
    except (TypeError, ValueError):
        return 0


def ufc_tale_of_tape(profile_a: dict | None, profile_b: dict | None, win_prob: dict | None) -> list[dict]:
    """Height/reach/age (and real win% when a market's been matched) as
    one compact row of cells. [] whenever either profile fetch failed —
    a half-populated tale of the tape reads as a data error, not an
    honest gap."""
    if not profile_a or not profile_b:
        return []
    cells = []
    for label, key in (("HT", "height"), ("REACH", "reach"), ("AGE", "age")):
        va, vb = profile_a.get(key), profile_b.get(key)
        if va is None or vb is None:
            continue
        cells.append({"label": label, "a": str(va), "b": str(vb)})
    if win_prob and win_prob.get("prob_a") is not None and win_prob.get("prob_b") is not None:
        cells.append({
            "label": "WIN%",
            "a": f'{round(win_prob["prob_a"] * 100)}%',
            "b": f'{round(win_prob["prob_b"] * 100)}%',
        })
    return cells


def ufc_board_data(ufc_state: dict, now: datetime) -> dict:
    """The hero bout (plus its live stats, profiles, odds) and the
    current page of the full card.

    The hero is the MAIN EVENT specifically during "countdown" — the
    actual draw worth building anticipation for, since current_bout
    would otherwise return the earliest, least interesting prelim with
    nothing having happened yet — and current_bout's own live-tracking
    pick once the card is underway."""
    event = ufc_state["event"]
    phase = ufc_state["phase"]
    bouts = event["bouts"]
    hero = bouts[-1] if phase == "countdown" else ufc_client.current_bout(event)
    a, b = hero["fighter_a"], hero["fighter_b"]

    # Only once the hero bout has actually started — a not-yet-fought
    # hero has nothing real to compare.
    stats = None
    if phase != "countdown" and hero["state"] in ("live", "final"):
        try:
            stats = ufc_client.fetch_bout_stats(event["event_id"], hero["bout_id"], a["id"], b["id"])
        except Exception:
            stats = None

    phase_line = {"kind": "underway", "text": "CARD UNDERWAY"}
    if phase == "countdown":
        phase_line = {"kind": "countdown", "countdown": countdown(event["start_time"], now)}
    elif hero["state"] == "live":
        # Recent-action ticker: temporarily takes over this same line for
        # a few seconds right after a real stat delta lands, then reverts
        # to the plain round/clock. Held in session_state because a
        # genuine delta is only detected on the ONE rerun it lands —
        # every rerun straight after sees zero further delta and would
        # revert instantly.
        recent = ufc_client.recent_event(hero["bout_id"], a, b, stats)
        hold_key = f"jumbotron_ufc_recent_{hero['bout_id']}"
        if recent:
            st.session_state[hold_key] = {**recent, "at": time.time()}
        held = st.session_state.get(hold_key)
        if held and time.time() - held["at"] < UFC_RECENT_EVENT_HOLD_SECONDS:
            phase_line = {"kind": "recent", "text": held["text"], "accent": held["accent"]}
        else:
            phase_line = {"kind": "live", "text": f'LIVE · ROUND {hero["round"]} · {hero["clock"]}'}

    # Bio data — its own long-cached (6h) fetch, separate from the live
    # per-round stats, and only for the hero bout's two fighters.
    try:
        profile_a = ufc_client.fetch_fighter_profile(a["id"])
    except Exception:
        profile_a = None
    try:
        profile_b = ufc_client.fetch_fighter_profile(b["id"])
    except Exception:
        profile_b = None
    try:
        win_prob = ufc_client.fetch_win_probability(a["name"], b["name"], hero["bout_id"])
    except Exception:
        win_prob = None

    # Paginated on a wall-clock timer, same discipline as Around The
    # Leagues — the card strip is a fixed-height reference band under a
    # dominant hero, and a real card runs well past what fits.
    pages = [bouts[i : i + UFC_CARD_PAGE_SIZE] for i in range(0, len(bouts), UFC_CARD_PAGE_SIZE)]
    page_total = len(pages) or 1
    page_index = int(time.time() // UFC_CARD_ROTATE_SECONDS) % page_total

    return {
        "event_name": event["name"],
        # Free from the same scoreboard payload ufc_client already
        # reads; genuinely absent well before some events.
        "venue": event.get("venue") or "",
        "phase_line": phase_line,
        "hero": hero,
        "weight_class": hero["weight_class"],
        "fighter_a": a,
        "fighter_b": b,
        "profile_a": profile_a,
        "profile_b": profile_b,
        "a_winner": hero["state"] == "final" and a["winner"],
        "b_winner": hero["state"] == "final" and b["winner"],
        "a_knockdowns": ufc_knockdowns(stats["fighter_a"] if stats else None),
        "b_knockdowns": ufc_knockdowns(stats["fighter_b"] if stats else None),
        "tale_of_tape": ufc_tale_of_tape(profile_a, profile_b, win_prob),
        "stat_rows": ufc_stat_rows(hero["bout_id"], a, b, stats),
        "card_label": "Full Card" + (f" · {page_index + 1}/{page_total}" if page_total > 1 else ""),
        "card_bouts": pages[page_index] if pages else [],
    }


# --------------------------------------------------------------------
# Page-level assembly
# --------------------------------------------------------------------

def marquee_data(now: datetime, weather: dict | None) -> dict:
    return {
        "clock": now.strftime("%-I:%M"),
        "meridiem": now.strftime("%p"),
        "dateline": now.strftime("%A, %B %-d").upper(),
        "temp": weather.get("temp_c") if weather and weather.get("temp_c") is not None else None,
    }


def page_data(now: datetime, state: dict, weather: dict | None) -> dict:
    """One pass over everything the team-sport board needs. The rail is
    mutually exclusive: a live MLB game that won the takeover replaces
    My Teams with the batting order, otherwise My Teams shows."""
    now_ts = time.time()
    batting = batting_order_data(state)
    return {
        "marquee": marquee_data(now, weather),
        "batting_order": batting,
        "rail": None if batting else {
            "teams": [rail_hero_data(entry, now) for entry in RAIL],
            "ufc": ufc_rail_hero_data(now),
        },
        "board": board_data(state, now),
        "around": around_data(now_ts),
        "standings": standings_data(now_ts),
        "play_result": play_result_data(state),
        "between_play": between_play_overlay_data(state, now),
        "has_game": bool(state.get("game")),
    }


def ufc_page_data(now: datetime, ufc_state: dict, weather: dict | None) -> dict:
    return {"marquee": marquee_data(now, weather), "board": ufc_board_data(ufc_state, now)}
