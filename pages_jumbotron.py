"""Jumbotron: a full-screen arena scoreboard that takes the kiosk over
for Jays/Habs games — session request: "I want the kiosk to run as
normal, but one hour before any game Habs or Jays, and during the game,
I want it to go to that exactly so the game can be enjoyed with this
system, before reverting back to the other system."

This page is deliberately NOT in config.PAGES — it never joins the
normal rotation. sports_alerts.takeover_state() decides when it owns
the screen (T-60 min through ~15 min past final), and app.py forces the
page and suppresses its own hero row while that's active.

Rendered as one single HTML block rather than Streamlit columns: the
kiosk viewport doesn't scroll, and a CSS grid gives exact control over
how the three panels share a fixed height in a way st.columns' own
gutters/wrapping don't. Every panel degrades on its own — a failed
fetch drops that section, not the board.

Data comes entirely from fetchers this app already had (sports_client
for game/standings/form/live detail, sports_alerts for scoring plays,
scores_client for the league-wide slate).
"""

import html
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
_RAIL = [
    {"sport": "nhl", "label": "CANADIENS", "fetch_status": sports_client.fetch_habs, "kickoff": "TO PUCK DROP"},
    {"sport": "mlb", "label": "BLUE JAYS", "fetch_status": sports_client.fetch_jays, "kickoff": "TO FIRST PITCH"},
    {"sport": "nfl", "label": "SAINTS", "fetch_status": sports_client.fetch_saints, "kickoff": "TO KICKOFF"},
]
# Around-the-leagues rail: session feedback — a real MLB slate is
# regularly 12-15 games, and capping to a handful was silently hiding
# most of tonight's games. Nothing is dropped now: each league gets
# every one of its games, split into AROUND_PAGE_SIZE-row pages, and
# the whole set of pages (across every league that has a game today,
# in league order) cycles on a wall-clock timer — the same
# int(time.time() // interval) % n pattern pages_household.py's own
# NEARBY rotation and the team-news rail used earlier this session.
# One page shown at a time rather than every league stacked at once,
# per session request: "when more than one league is active have it
# cycle them... if there's too many games... make a second page for
# that league it can flip to."
# NBA deliberately excluded — session request: "I don't really fuck
# with the NBA, and I don't really want it on my dashboard." Kept in
# sync by hand with scores_client.LEAGUES (see that module's own
# comment on the same removal) — this list is just keys, not the full
# registry, so it doesn't cascade automatically from that one.
_AROUND_LEAGUES = ["mlb", "nhl", "nfl"]
# Was 7 (8 clipped) — session feedback: "the around the league card is
# a little crowded," right after theme.py's own distance-readability
# pass made every row noticeably bigger (bigger logos, bigger type,
# more row padding — see .jumbo-mini's own comment). Same rows, same
# panel height, just fewer of them fit comfortably now.
_AROUND_PAGE_SIZE = 6
_AROUND_ROTATE_SECONDS = 12
_FORM_GAMES_SHOWN = 8
# Session follow-up: "I want the live fight to take up like the whole
# screen" shrank the full-card panel down to a 1fr reference strip
# under the now-dominant hero (see .jumbo-ufc-grid's own comment) —
# confirmed live (real 14-bout card, real row height) only 4 rows fit
# cleanly in that strip without clipping the last one, nowhere near all
# of them (kiosk never scrolls, so anything past that would just be
# permanently invisible rather than merely below the fold). Same
# fixed-page-size-cycling-on-a-wall-clock-timer shape as
# _AROUND_LEAGUES/_AROUND_PAGE_SIZE above, same 12s cadence.
_UFC_CARD_PAGE_SIZE = 4
_UFC_CARD_ROTATE_SECONDS = 12
# How long a recent-action ticker line (_ufc_board_html) holds the
# phase-line slot before reverting to the plain round/clock display —
# long enough to actually read from across the room, short enough that
# a real new development (or just the normal round/clock line) isn't
# stuck waiting behind a stale one.
_UFC_RECENT_EVENT_HOLD_SECONDS = 6


def _fmt_countdown(target: datetime, now: datetime) -> str:
    """H:MM:SS (or MM:SS under an hour — session request), ticking for
    real once a second — session request: bring
    seconds back but "uncorrelated to the sync up of the whole system"
    (a server-rendered digit only ever updates once per 5s rerun and
    visibly jumps by 5, which is exactly why seconds got dropped
    earlier this session). The string returned here is only ever the
    FIRST frame's value; app.py's own global live-countdown ticker
    script (injected once alongside its J-hotkey listener — same
    "make that logic work for all the timer elements" request this
    class name is shared with commute_reminder's leave headline and
    pages_sports' starting-soon badge) recomputes against the browser's
    own real clock every second from here on, independent of
    Streamlit's rerun cadence entirely."""
    target_ms = int(target.replace(tzinfo=ZoneInfo(TIMEZONE)).timestamp() * 1000)
    total = max(0, int((target - now).total_seconds()))
    # Session report: "four games that are more than a full day away
    # instead of having them count down the number of hours... the
    # saints game shows like two hundred and twenty two hours, which is
    # ridiculous... just make it show days and hours, and that's it."
    # A game a full week+ out was rendering as raw hours ("222:14:33")
    # since this never capped hours at 24 the way a real clock would —
    # mirrored in app.py's own kioskFmtClock, which is what actually
    # drives the display from the second frame on.
    if total >= 86400:
        days, rem = divmod(total, 86400)
        hours = rem // 3600
        fallback = f"{days}d {hours}h"
    else:
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        # Session request: drop the leading hour digit under an hour
        # ("43:55", not "0:43:55").
        fallback = f"{hours}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes}:{seconds:02d}"
    return f'<span class="live-countdown" data-target-ms="{target_ms}">{fallback}</span>'


def _digits_html(score) -> str:
    """A score as individual LED digit boxes."""
    text = str(score if score is not None else 0)
    return "".join(f'<span class="jumbo-digit">{html.escape(c)}</span>' for c in text)


def _record_for(status: dict) -> str:
    for row in status.get("standings") or []:
        if row.get("is_team"):
            return f'{row["wins"]}-{row["losses"]}'
    return ""


def _record_for_name(status: dict, name: str) -> str:
    """Opponent's record, when they happen to share our division (so
    they're already in the standings payload we fetched) — "" otherwise,
    rather than a whole extra API call for a nicety."""
    for row in status.get("standings") or []:
        if row.get("team") and row["team"].lower() in name.lower():
            return f'{row["wins"]}-{row["losses"]}'
    return ""


def _sides(status: dict, game: dict, team_label: str) -> tuple[dict, dict]:
    """(away, home) each {"name", "logo", "record", "is_us"} — the board
    is laid out as a real scoreboard (away on the left) rather than
    always putting us first, matching the big score digits' own
    away-left/home-right order."""
    us = {"name": team_label.title(), "logo": status["team_logo"], "record": _record_for(status), "is_us": True}
    them = {
        "name": game["opponent"],
        "logo": game["opponent_logo"],
        "record": _record_for_name(status, game["opponent"]),
        "is_us": False,
    }
    return (them, us) if game["is_home"] else (us, them)


def _sides_neutral(game: dict) -> tuple[dict, dict]:
    """_sides()'s equivalent for a semis/finals game between two teams
    we have no stake in (sports_alerts._neutral_playoff_candidates) —
    both "is_us": False, which is also what already makes _side_color/
    the digit-flash logic below fall through to each team's own REAL
    ESPN color and the same neutral flash treatment with no other code
    downstream needing to know this game is any different. `game`
    here is scores_client.fetch_playoff_round_games's own shape (
    "home"/"away", each already {"abbr","name","full_name","logo",
    "score","record"}), not the fetch_jays()/fetch_habs()/
    fetch_saints() shape _sides() above reads.

    Uses "full_name" ("Edmonton Oilers"), not the short "name"
    ("Oilers") _mini_row_html's compact rows use — this same value
    doubles as both the on-screen label and _side_color's lookup key
    into scores_client.team_color, which matches on ESPN's own full
    displayName (confirmed live: the short name silently misses there,
    always falling back to gray). Reads fine on-screen too — a fully-
    spelled-out matchup is more useful than an abbreviated one for two
    teams the board can't assume we already recognize the way we'd
    recognize our own team's short club name."""

    def side(s: dict) -> dict:
        return {"name": s.get("full_name") or s["name"], "logo": s["logo"], "record": s.get("record") or "", "is_us": False}

    return side(game["away"]), side(game["home"])


def _side_html(side: dict, dim: bool, has_ball: bool = False, accent_rgb: tuple[int, int, int] | None = None) -> str:
    """`has_ball` — NFL only (see _nfl_possession_home below); every
    other sport's call site just leaves the default False, zero visual
    change. Session request: "make it more obvious who has the ball...
    maybe a little ball icon next to their name." Same 🏈 glyph the
    situation strip's own possession badge already uses, but tied
    directly to the team's own name here — the strip's badge stays too
    (still useful when the board isn't wide enough to draw a clear line
    from the icon back to a specific name), this is a second, more
    direct cue, not a replacement.

    `accent_rgb` — session request: "incorporate the exact same
    systems... make sure this format is accepted" (the "Network
    Primetime" visual-polish pick, a diagonal team-color split behind
    each side). Sets --side-rgb inline so theme.py's own .jumbo-side
    ::before can paint that side's real color (the same away_rgb/
    home_rgb _board_html already computes for the board's ambient
    gradient wash — this just also hands it to the side that owns it).
    None (the default) falls back to theme.py's own neutral-slate
    fallback — every existing call site that predates this still
    renders exactly as it did before without passing anything new."""
    classes = "jumbo-side" + (" jumbo-side-dim" if dim else "")
    style = f' style="--side-rgb:{accent_rgb[0]},{accent_rgb[1]},{accent_rgb[2]}"' if accent_rgb else ""
    ball = '<span class="jumbo-side-ball">🏈</span>' if has_ball else ""
    return (
        f'<div class="{classes}"{style}>'
        f'<div class="jumbo-logobox"><img src="{html.escape(side["logo"])}" /></div>'
        f'<div class="jumbo-tname">{ball}{html.escape(side["name"])}</div>'
        f'<div class="jumbo-trec">{html.escape(side["record"])}</div>'
        f"</div>"
    )


_INNING_ARROW = {"Top": "▲", "Bottom": "▼"}


def _mlb_situation_html(game_id: int) -> str:
    detail = sports_client.fetch_mlb_live_detail(game_id)
    if not detail:
        return ""
    bases = detail.get("bases") or {}

    # Session request: "make the bases react when someone gets on with
    # a smooth lighting up animation" — same before/after comparison as
    # the count/outs pulse below, keyed by game_id so a different
    # game's own bases never inherit this one's "just lit up" moment.
    # Only the newly-occupied transition gets the one-shot flash (see
    # .jumbo-base-flash, theme.py) — a base that was already on, or one
    # that just cleared, doesn't replay it every rerun. The steady on/
    # off look itself (.jumbo-diamond rect.on) now also has a plain CSS
    # transition, so even a non-flash change (a runner forced out, say)
    # fades rather than snapping.
    prev_bases = st.session_state.get(f"jumbotron_mlb_bases_{game_id}", {})
    st.session_state[f"jumbotron_mlb_bases_{game_id}"] = dict(bases)

    def base_class(key: str) -> str:
        on = bool(bases.get(key))
        classes = "on" if on else ""
        if on and not prev_bases.get(key):
            classes = f"{classes} jumbo-base-flash".strip()
        return classes

    diamond = (
        '<svg class="jumbo-diamond" viewBox="0 0 34 34"><g transform="rotate(45 17 17)">'
        f'<rect x="21" y="9" width="8" height="8" class="{base_class("first")}"></rect>'
        f'<rect x="9" y="9" width="8" height="8" class="{base_class("second")}"></rect>'
        f'<rect x="9" y="21" width="8" height="8" class="{base_class("third")}"></rect>'
        "</g></svg>"
    )

    # Session request: "make counts and outs actual numbers instead of
    # dots" — was a row of small filled/unfilled circles, hard to read
    # at a glance from across the room; now the real "2-1" / "1 OUT"
    # text broadcasts already use. Still pulses on a genuine increase
    # (comparing to what was last rendered for this game, keyed by
    # game_id in session_state) — same reasoning as the old dots had,
    # just animating the number itself now instead of lighting up one
    # more dot. A new at-bat resetting the count to 0 never falsely
    # pulses anything: nothing to compare up against on the way down.
    # Session request: "make it so a ball is green and a strike is red
    # and make it flash when [one] comes through" — ball and strike now
    # get their own digit and their own color/flash instead of sharing
    # one plain "B-S" pulse, so which one just happened is readable at
    # a glance, not just that the count changed.
    #
    # A same-evening request to turn this into a strike-percentage
    # figure instead was tried and reverted right back — session
    # correction: "who wants the count shown as a percentage... I only
    # want it shown for the pitcher's total ball and strike count below
    # their ERA and their pitches." The at-bat's own live count stays
    # exactly as it was; the percentage version lives in
    # _current_matchup_html's own pitcher card instead (see that
    # function's own comment on _pitch_strike_pct_text).
    balls, strikes, outs = detail.get("balls") or 0, detail.get("strikes") or 0, detail.get("outs") or 0
    prev_counts = st.session_state.get(f"jumbotron_mlb_counts_{game_id}", {})
    st.session_state[f"jumbotron_mlb_counts_{game_id}"] = {"b": balls, "s": strikes, "o": outs}
    ball_flash = " jumbo-ball-flash" if balls > prev_counts.get("b", 0) else ""
    strike_flash = " jumbo-strike-flash" if strikes > prev_counts.get("s", 0) else ""
    outs_pulse = " jumbo-situ-pulse" if outs > prev_counts.get("o", 0) else ""

    # Session request: "put an up or down arrow beside inning instead
    # of top/bottom" — real scoreboard convention (▲ away batting/top,
    # ▼ home batting/bottom). MLB's own "Middle"/"End" inning-break
    # states have no such convention, so those still show as text.
    inning_state = detail.get("inning_state") or ""
    inning_num = detail.get("current_inning")
    arrow = _INNING_ARROW.get(inning_state)
    inning = f"{arrow} {inning_num}" if arrow and inning_num else f"{inning_state} {inning_num or ''}".strip()

    # Session request: "how can we improve the experience watching the
    # game... feel good and seamless" — fades in on a genuine inning/
    # half change rather than popping straight to the new text (see
    # app.py's kiosk-jumbo-fade); value is inning_state+number together
    # so "Top 4" -> "Bottom 4" still counts as a real change even though
    # the number alone didn't move.
    parts = (
        [
            f'<span class="jumbo-situ-hot" data-fade-slot="inning-{game_id}" '
            f'data-fade-value="{html.escape(inning_state)}:{inning_num}">{html.escape(inning)}</span>'
        ]
        if inning
        else []
    )
    parts.append(diamond)
    parts.append(
        f'<span class="jumbo-situ-count"><span class="jumbo-dim">COUNT</span> '
        f'<span class="jumbo-count-digit{ball_flash}">{balls}</span>-<span class="jumbo-count-digit{strike_flash}">{strikes}</span></span>'
    )
    parts.append(f'<span class="jumbo-situ-outs{outs_pulse}">{outs} OUT</span>')
    line = "".join(parts)
    # Session feedback: "get rid of the at bat and pitching thing below
    # the inning diamond, count, and outs since its already shown
    # below" — the Current Matchup card (_current_matchup_html) already
    # names both, with photos and OPS/ERA besides.
    return f'<div class="jumbo-situ">{line}</div>'


def _nhl_situation_html(game_id: int) -> str:
    detail = sports_client.fetch_nhl_live_detail(game_id)
    if not detail:
        return ""
    if detail.get("in_intermission"):
        label = detail.get("period_label") or ""
        text = f"INTERMISSION — END OF {label}".strip()
        return f'<div class="jumbo-situ"><span class="jumbo-situ-hot">{html.escape(text)}</span></div>'
    parts = []
    if detail.get("period_label"):
        parts.append(f'<span class="jumbo-situ-hot">{html.escape(detail["period_label"])} PERIOD</span>')
    if detail.get("clock"):
        parts.append(f'<span class="jumbo-clockbig">{html.escape(detail["clock"])}</span>')
    return f'<div class="jumbo-situ">{"".join(parts)}</div>' if parts else ""


def _neutral_situation_html(status_text: str | None) -> str:
    """The live-situation strip's fallback for a neutral MLB/NHL game
    (sports_alerts._neutral_playoff_candidates) — _mlb_situation_html's
    bases/count/outs diamond and _nhl_situation_html's period/clock
    both poll the OFFICIAL league API (MLB Stats API/NHL API) by THAT
    league's own game id, a different id space than the ESPN event id
    a neutral game's game_id actually is (see _board_html's own
    comment on why sport == "mlb" alone isn't enough to call those
    safely). ESPN's own status text (scores_client._normalize_game's
    "status_text" — e.g. "2nd - 10:21", "Top 5th") is the one live-
    situation source that DOES come from the same ESPN event this
    game's score/records/win-probability already do — thinner than the
    real diamond/clock widgets, but real and current rather than
    invented or silently blank."""
    if not status_text:
        return ""
    return f'<div class="jumbo-situ"><span class="jumbo-situ-hot">{html.escape(status_text.upper())}</span></div>'


_NFL_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


def _nfl_situation(game_id) -> dict:
    """{"status", "situation", "competitors"}, or {} if this game_id
    isn't on today's scoreboard. Split out from _nfl_situation_html so
    _side_html's own possession icon (rendered separately, in the
    matchup header above the situation strip) and the strip itself can
    share one read instead of each re-deriving it.

    sports_client.fetch_nfl_competition, NOT the match/_espn_match_for
    wrapper every other NFL panel on this board reads from — session
    report: "why is the NFL on the jumbotron screen not, like, live...
    it just stays frozen." That match-based path shares scores_client's
    5-MINUTE schedule-lookup cache; this one shares this app's own
    NFL-specific 5-second live cache instead, matching what _mlb_
    situation_html/_nhl_situation_html were already built on (see
    fetch_nfl_competition's own docstring for the full story)."""
    return sports_client.fetch_nfl_competition(game_id) or {}


def _nfl_possession_home(situation: dict, competitors: list[dict]) -> bool | None:
    """Whether the HOME team currently has the ball — ESPN's own
    situation.possession is a team id, matched against this
    competition's own competitors for their "homeAway" field (not a
    name-match — see _nfl_situation_html's own docstring on why).
    None pregame/postgame or on any missing field."""
    possession_id = situation.get("possession")
    if not possession_id:
        return None
    return next((c.get("homeAway") == "home" for c in competitors if c.get("id") == possession_id), None)


def _nfl_yards_out(situation: dict, possession_home: bool | None) -> int | None:
    """Distance remaining to the end zone the team WITH THE BALL is
    actually driving toward — session request: "make it more obvious
    how far away from the end zone they are. Instead of saying LAR
    forty six, be like, X amount of yards out." ESPN's own
    situation.yardLine is a fixed field-position coordinate (0 at the
    away team's own goal line, 100 at the home team's own goal line —
    confirmed against two real live snaps: Saints, the away team,
    facing 3rd & 1 at their OWN 36 — 64 yards from the Rams' end zone —
    read yardLine=64 directly; Rams, the home team, facing 2nd & Goal
    at the Saints' 8 — 8 yards from the Saints' end zone — read
    yardLine=92, i.e. 100-8), not "distance for whoever currently has
    the ball." The away team's own distance-to-score is that raw
    number directly; the home team's is the complement."""
    yard_line = situation.get("yardLine")
    if yard_line is None or possession_home is None:
        return None
    return yard_line if not possession_home else (100 - yard_line)


def _nfl_situation_html(game: dict) -> str:
    """Quarter + game clock, down & distance (as "yards out" from the
    end zone rather than raw field position — see _nfl_yards_out),
    live possession, red zone, and timeouts remaining — pulled from
    ESPN's own scoreboard "situation" object via sports_client.fetch_
    nfl_competition (see _nfl_situation's own docstring for why that's
    a fast, NFL-specific 5s cache now rather than the slow, match-based
    one this used to read from). First live game (Rams @ Saints,
    2026-08-22) confirmed the fuller shape live: downDistanceText,
    possession, isRedZone, home/awayTimeouts, yardLine all populate
    exactly as ESPN's own docs suggest.

    Live bug, first deploy of the original match-based version: this
    function used to skip unwrapping match["competition"] and read
    straight off `match`, so every field silently came back empty in
    the real render path — confirmed nothing showed at all ("I also
    can't see time, and downs, and quarter, and anything," reported
    even after a separate, real overflow bug in the same commit was
    also fixed) despite a passing unit test, because that test had
    manually pre-unwrapped match["competition"] before calling this,
    masking the exact mismatch the real call site hit. Moot now that
    there's no `match`/wrapper to unwrap in the first place, but kept
    here as a reminder of why this function's own inputs are worth
    double-checking against a real live game before trusting a passing
    test alone."""
    data = _nfl_situation(game["game_id"])
    if not data:
        return ""
    status = data["status"]
    period = status.get("period")
    clock = status.get("displayClock")
    game_id = game["game_id"]
    parts = []
    if isinstance(period, int) and period > 0:
        label = f"{_NFL_ORDINALS.get(period, f'{period}th')} QUARTER" if period <= 4 else "OVERTIME"
        parts.append(f'<span class="jumbo-situ-hot">{html.escape(label)}</span>')
    if clock:
        parts.append(f'<span class="jumbo-clockbig">{html.escape(str(clock))}</span>')

    situation = data["situation"]
    down_text = situation.get("shortDownDistanceText") or situation.get("downDistanceText")
    is_red_zone = bool(situation.get("isRedZone"))
    possession_home = _nfl_possession_home(situation, data["competitors"])
    yards_out = _nfl_yards_out(situation, possession_home)
    if down_text:
        display_text = f"{down_text} · {yards_out} yards out" if yards_out is not None else down_text
        parts.append(
            f'<span class="jumbo-situ-count" data-fade-slot="nfl-down-{game_id}" '
            f'data-fade-value="{html.escape(display_text)}">{html.escape(display_text)}</span>'
        )
    if is_red_zone:
        parts.append('<span class="jumbo-nfl-redzone-badge">RED ZONE</span>')

    if possession_home is not None:
        possession_is_us = possession_home == game["is_home"]
        tone = "jumbo-possession-us" if possession_is_us else "jumbo-possession-opp"
        label = "US" if possession_is_us else "OPP"
        parts.append(f'<span class="jumbo-possession {tone}">🏈 {label} BALL</span>')

    home_to, away_to = situation.get("homeTimeouts"), situation.get("awayTimeouts")
    if home_to is not None and away_to is not None:
        us_to, opp_to = (home_to, away_to) if game["is_home"] else (away_to, home_to)
        parts.append(f'<span class="jumbo-nfl-timeouts">TIMEOUTS {us_to}-{opp_to}</span>')

    return f'<div class="jumbo-situ">{"".join(parts)}</div>' if parts else ""


_TEAM_ESPN_NAME = {
    "mlb": sports_client.MLB_TEAM_NAME,
    "nhl": sports_client.NHL_TEAM_NAME,
    "nfl": sports_client.NFL_TEAM_NAME,
}
_TEAM_COLOR = {"mlb": "#3E7CC9", "nhl": "#D8323F", "nfl": "#D3BC8D"}  # matches the rail hero's own --tc values
# Same three colors as (r, g, b) — needed alongside the hex strings
# above for _side_color below, which has to blend an opponent's real
# ESPN color in at a controlled alpha (rgba(), not a flat hex fill).
_TEAM_COLOR_RGB = {"mlb": (62, 124, 201), "nhl": (216, 50, 63), "nfl": (211, 188, 141)}
_OPPONENT_FALLBACK_RGB = (82, 92, 110)  # matches the old fixed #525C6E gray


def _side_color(sport: str, match: dict | None, side: dict) -> tuple[int, int, int]:
    """This side's real (r, g, b) — our own fixed team color, or the
    opponent's real color straight from ESPN (scores_client.team_color)
    when this is the other team. Session request: "there was a cool
    dark gradient behind the big score section with both team's
    colors... the win bar could have the team's actual colors, right
    now the opponent's colors just default to gray." Falls back to the
    old fixed gray whenever ESPN doesn't have today's game or genuinely
    has no usable color for that team — same graceful degradation
    scores_client.team_color's own docstring already describes."""
    if side["is_us"]:
        return _TEAM_COLOR_RGB.get(sport, (255, 179, 0))
    if match is None:
        return _OPPONENT_FALLBACK_RGB
    return scores_client.team_color(match["competition"], side["name"]) or _OPPONENT_FALLBACK_RGB


# Pregame situation-strip label, per sport — was a hardcoded "FIRST
# PITCH"/"PUCK DROP" binary ternary before the Saints, which would have
# wrongly shown "PUCK DROP" for a football game.
_PREGAME_SITUATION_LABEL = {"mlb": "FIRST PITCH", "nhl": "PUCK DROP", "nfl": "KICKOFF"}


def _espn_match_for(sport: str, game: dict) -> dict | None:
    """The ESPN competition for this specific Jays/Habs game, if
    findable — see scores_client.find_espn_competition's own docstring
    for why name-matched rather than abbreviation-matched. Backs both
    _win_probability_html and _top_performers_html below so there's
    only ever one cross-reference lookup per render, not two."""
    our_name = _TEAM_ESPN_NAME.get(sport)
    if not our_name or not game.get("opponent"):
        return None
    return scores_client.find_espn_competition(sport, game["opponent"], our_name)


def _pregame_extra_html(sport: str, game_id: int) -> str:
    """Venue + real game-day weather + probable starters (MLB), or
    just the arena name (NHL — no probable-goalie field, and every
    rink is indoor) — session request, all from data already fetched
    elsewhere in this app (see sports_client.fetch_mlb_pregame_extra/
    fetch_nhl_venue's own docstrings). "" for NFL — no equivalent venue/
    weather fetch built for the Saints' own lighter-tier integration
    (see sports_client.py's own comment on why); was falling through to
    the NHL branch unconditionally before this got an explicit check,
    which would have called fetch_nhl_venue for a football game."""
    if sport == "mlb":
        extra = sports_client.fetch_mlb_pregame_extra(game_id)
        if not extra:
            return ""
        parts = []
        if extra.get("venue"):
            line = html.escape(extra["venue"])
            if extra.get("weather_line"):
                line += f' · {html.escape(extra["weather_line"])}'
            parts.append(f'<div class="jumbo-pregame-venue">{line}</div>')
        if extra.get("away_pitcher") or extra.get("home_pitcher"):
            probables = ['<div class="jumbo-probables">']
            for label, pitcher in (("AWAY · SP", extra.get("away_pitcher")), ("HOME · SP", extra.get("home_pitcher"))):
                if pitcher:
                    probables.append(f'<div><span class="jumbo-probables-label">{label}</span><b>{html.escape(pitcher)}</b></div>')
            probables.append("</div>")
            parts.append("".join(probables))
        return "".join(parts)
    if sport == "nhl":
        venue = sports_client.fetch_nhl_venue(game_id)
        return f'<div class="jumbo-pregame-venue">{html.escape(venue)}</div>' if venue else ""
    return ""


_STORYLINE_ROTATE_SECONDS = 10
_STORYLINE_CARDS_PER_SET = 3


def _storyline_cards_html(sport: str, game: dict, team_label: str, match: dict | None, now_ts: float) -> str:
    """Pregame warm-up show — session request: "make it almost like a
    show, like a pregame show," replacing the plain AI Preview blurb
    and season-stat-leaders card with real player/team storylines (see
    pregame_storylines.py's own docstring for the full data story:
    transactions, team news, league-wide leaders, injuries, this
    game's own leaders — a call-up making their debut is exactly the
    kind of thing this surfaces, the real inspiration for this whole
    feature). "" whenever there's nothing real to build a card from
    yet — same "just omit it" rule every other optional jumbotron
    panel already follows.

    Cards are generated ONCE per game_id (pregame_storylines' own
    persisted, restart-surviving cache) — this function only handles
    the ALREADY-generated set's rotation, same int(now_ts // N) %
    len(...) pattern _top_performers_html/_rotating_standings_html/
    _around_html already use, no new mechanism. _TEAM_FULL_NAME is
    defined further down this file (see that dict's own comment) —
    fine to reference here since Python only resolves it when this
    function actually runs, well after the whole module has loaded."""
    our_name = _TEAM_FULL_NAME[sport]
    away_name = our_name if not game["is_home"] else game["opponent"]
    home_name = game["opponent"] if not game["is_home"] else our_name
    cards = pregame_storylines.get_storyline_cards(
        sport, game["game_id"], team_label, away_name, home_name, game["opponent"], match
    )
    if not cards:
        return ""

    page_size = _STORYLINE_CARDS_PER_SET
    pages = [cards[i : i + page_size] for i in range(0, len(cards), page_size)]
    index = int(now_ts // _STORYLINE_ROTATE_SECONDS) % len(pages)
    page = pages[index]

    card_parts = []
    for c in page:
        if c.get("photo"):
            photo_html = f'<img class="jumbo-storyline-photo" src="{html.escape(c["photo"])}" />'
        else:
            # No real photo for this card's subject (see pregame_
            # storylines._parse's own docstring on when this happens —
            # most often a transaction-sourced storyline; ESPN's own
            # feed there is plain prose with no athlete id to look up
            # a headshot from) — a plain initial circle instead of a
            # broken image or a misleadingly-wrong team's logo.
            initial = html.escape(c["name"][:1].upper()) if c["name"] else "?"
            photo_html = f'<div class="jumbo-storyline-photo jumbo-storyline-photo-blank">{initial}</div>'
        role_html = f'<div class="jumbo-storyline-role">{html.escape(c["role"])}</div>' if c.get("role") else ""
        stat_html = f'<div class="jumbo-storyline-stat">{html.escape(c["stat_line"])}</div>' if c.get("stat_line") else ""
        card_parts.append(
            f'<div class="jumbo-storyline-card">'
            f'<div class="jumbo-storyline-photowrap">{photo_html}</div>'
            f'<div class="jumbo-storyline-name">{html.escape(c["name"])}</div>'
            f"{role_html}{stat_html}"
            f'<div class="jumbo-storyline-text">{html.escape(c["storyline"])}</div>'
            f"</div>"
        )
    dots_html = ""
    if len(pages) > 1:
        dots = "".join(
            f'<span class="jumbo-storyline-dot{" jumbo-storyline-dot-active" if i == index else ""}"></span>'
            for i in range(len(pages))
        )
        dots_html = f'<div class="jumbo-storyline-dots">{dots}</div>'
    return f'<div class="jumbo-storyline-cards">{"".join(card_parts)}</div>{dots_html}'


def _win_probability_html(sport: str, match: dict | None, away: dict, home: dict) -> str:
    """Win-probability bar — session request. Only ESPN's own payload
    carries either source (the native MLB/NHL APIs the rest of the
    board runs on don't). ESPN's own live model (scores_client.
    win_probability, updated play-by-play) is preferred once it has
    enough of the game to compute one; pregame, when that's always None
    (confirmed live), falls back to the moneyline instead (scores_client.
    moneyline_win_probability — session request: "can we use money line
    to get approximate win odds") rather than showing nothing until
    first pitch. "" only when match is None (no ESPN game found) or
    neither source has anything yet (moneylines usually don't post
    until a day or two out)."""
    if not match:
        return ""
    home_pct = scores_client.win_probability(match)
    title = "WIN PROBABILITY"
    if home_pct is None:
        home_pct = scores_client.moneyline_win_probability(match)
        title = "PREGAME ODDS"
    if home_pct is None:
        return ""
    home_pct = round(home_pct)
    away_pct = 100 - home_pct
    away_color = "rgb({},{},{})".format(*_side_color(sport, match, away))
    home_color = "rgb({},{},{})".format(*_side_color(sport, match, home))
    # Session feedback: "find a better way to show the win odds since
    # its hard to see" — was an 11px-tall bar with 11px percentages
    # written below each end. The percentages themselves are now the
    # headline (big numbers flanking the bar, not small print under
    # it), and the bar itself is thick enough to read as a real
    # visual split rather than a thin stripe.
    #
    # Session request: "can you make the win probability bar update
    # smoother instead of jumping" — .jumbo-wp-seg's own CSS transition
    # can't animate this on its own: Streamlit re-renders this whole
    # markdown block from scratch every rerun, so these are brand new
    # DOM nodes each time with the new width already baked into the
    # inline style, not an existing element whose width property just
    # changed — nothing for a CSS transition to animate from. data-wp-
    # key (stable per game+side, unlike the DOM node itself) and data-
    # wp-pct let app.py's kiosk-wp-smoother script (injected once,
    # survives the churn the same way the countdown ticker does) track
    # the last real percentage itself and animate old -> new by hand.
    event_id = match.get("event_id", "")
    return (
        f'<div class="jumbo-wp"><div class="jumbo-wp-title">{title}</div>'
        '<div class="jumbo-wp-row">'
        f'<div class="jumbo-wp-pct" style="color:{away_color}">{away_pct}%</div>'
        f'<div class="jumbo-wp-bar">'
        f'<div class="jumbo-wp-seg" data-wp-key="{event_id}-away" data-wp-pct="{away_pct}" style="width:{away_pct}%;background:{away_color}"></div>'
        f'<div class="jumbo-wp-seg" data-wp-key="{event_id}-home" data-wp-pct="{home_pct}" style="width:{home_pct}%;background:{home_color}"></div>'
        "</div>"
        f'<div class="jumbo-wp-pct" style="color:{home_color}">{home_pct}%</div>'
        "</div>"
        f'<div class="jumbo-wp-labels"><span>{html.escape(away["name"])}</span>'
        f'<span>{html.escape(home["name"])}</span></div></div>'
    )


_LEADER_ROTATE_SECONDS = 5


def _top_performers_html(match: dict | None, now_ts: float) -> str:
    """Session request: "make top performers bigger or put them in a
    single slot that rotates continuously" — one big card at a time
    (real headshot straight from ESPN's own CDN, same data as before —
    see _espn_match_for/scores_client.leaders_with_headshots), cycling
    on the same wall-clock-timer pattern the Around The Leagues page-
    flip and team-news rail already use elsewhere in this app, rather
    than cramming every category into a shared-width grid row. Fades in
    only on a genuine index change (see the shared jumbo-around-fade-*
    classes' own comment for why), not every 5s rerun."""
    if not match:
        return ""
    leaders = scores_client.leaders_with_headshots(match)
    if not leaders:
        return ""
    index = int(now_ts // _LEADER_ROTATE_SECONDS) % len(leaders)
    leader = leaders[index]

    identity = f"{match.get('event_id')}:{index}"
    changed = identity != st.session_state.get("jumbotron_leader_identity")
    st.session_state["jumbotron_leader_identity"] = identity
    fade_class = ""
    if changed:
        tick = st.session_state.get("jumbotron_leader_fade_tick", 0) + 1
        st.session_state["jumbotron_leader_fade_tick"] = tick
        fade_class = " jumbo-around-fade-a" if tick % 2 == 0 else " jumbo-around-fade-b"

    hshot = (
        f'<img class="jumbo-leader-big-hshot" src="{html.escape(leader["hshot"])}" onerror="this.style.display=\'none\'" />'
        if leader.get("hshot")
        else ""
    )
    page_label = f" · {index + 1}/{len(leaders)}" if len(leaders) > 1 else ""

    # Session feedback: the big card left a lot of empty space next to
    # the single featured stat — "put the names in the big empty slot."
    # Fills it with the full roster this rotates through, the current
    # one highlighted, rather than leaving the rest of the card blank
    # between rotations.
    name_list = "".join(
        f'<div class="jumbo-leader-name-item{" jumbo-leader-name-active" if i == index else ""}">'
        f'<span class="jumbo-leader-name-who">{html.escape(l["who"])}</span>'
        f'<span class="jumbo-leader-name-stat">{html.escape(l["stat"])} {html.escape(l["cat"])}</span></div>'
        for i, l in enumerate(leaders)
    )

    return (
        f'<div class="jumbo-leaders"><div class="jumbo-sl">Top Performers{page_label}</div>'
        f'<div class="jumbo-leader-big{fade_class}">{hshot}'
        f'<div class="jumbo-leader-big-col">'
        f'<div class="jumbo-leader-big-stat">{html.escape(leader["stat"])}</div>'
        f'<div class="jumbo-leader-big-cat">{html.escape(leader["cat"])}</div>'
        f'<div class="jumbo-leader-big-who">{html.escape(leader["who"])}</div>'
        f"</div>"
        f'<div class="jumbo-leader-namelist">{name_list}</div>'
        f"</div></div>"
    )


_TOP3_ROLE_LABEL = {"hitter": "Hitter", "starter": "Starting Pitcher", "reliever": "Reliever", "closer": "Closer"}


def _top_3_performers_html(performers: list[dict]) -> str:
    """Postgame replacement for the single rotating ESPN leader card —
    session request: "can we fix post game so it shows the 3 best
    players of the game if ESPN has something like that. if not make
    your own algorithm that ranks players." ESPN's free API had nothing
    like it, but MLB's own boxscore endpoint turned out to already
    carry exactly this (sports_client.fetch_mlb_top_performers's own
    docstring has the full story) — always exactly 3, already ranked by
    a real Game Score, so this just lays out all 3 at once rather than
    rotating through them one at a time the way the season-stat-leader
    version above does. The best of the 3 (always index 0 — MLB's own
    list is pre-sorted) gets the same gold spotlight treatment this
    board already reserves for "the one that matters most" elsewhere
    (.jumbo-final-badge, the current-batter row). [] performers means
    the caller should fall back to _top_performers_html instead — see
    _board_html's own postgame branch."""
    if not performers:
        return ""
    cards = []
    for i, p in enumerate(performers):
        photo = (
            f'<img class="jumbo-top3-photo" src="{html.escape(p["photo"])}" onerror="this.style.display=\'none\'" />'
            if p.get("photo")
            else ""
        )
        logo = f'<img class="jumbo-top3-logo" src="{html.escape(p["logo"])}" />' if p.get("logo") else ""
        role = html.escape(_TOP3_ROLE_LABEL.get(p.get("role"), (p.get("role") or "").title()))
        card_class = "jumbo-top3-card jumbo-top3-card-best" if i == 0 else "jumbo-top3-card"
        cards.append(
            f'<div class="{card_class}">'
            f'<div class="jumbo-top3-photowrap">{photo}{logo}</div>'
            f'<div class="jumbo-top3-name">{html.escape(p["name"])}</div>'
            f'<div class="jumbo-top3-role">{role}</div>'
            f'<div class="jumbo-top3-summary">{html.escape(p["summary"])}</div>'
            f'<div class="jumbo-top3-score"><span class="jumbo-top3-score-num">{p["game_score"]}</span>'
            f'<span class="jumbo-top3-score-label">Game Score</span></div>'
            f"</div>"
        )
    return f'<div class="jumbo-leaders"><div class="jumbo-sl">Top Performers</div><div class="jumbo-top3">{"".join(cards)}</div></div>'


# Session request: "at the end of an inning on the last out, it'll
# automatically go to the other team's batter when I'm on delay, before
# the play even populates for me." sports_client.delayed() already
# trails the raw feed by the jumbotron's own delay stepper, but that's
# a flat buffer on whatever inning/batter state happened to get polled
# — it doesn't guarantee the actual moment the batting team changes
# gets held on screen, especially when the whole half-inning break
# falls inside a single LIVE_DETAIL_CACHE_TTL_SECONDS (5s) poll window
# and MLB's feed jumps straight from the last out to the next team's
# leadoff batter with no "Middle"/"End" state ever observed in between.
# Same reasoning as OVERLAY_DELAY_SECONDS below (that one holds the
# out-of-town scoreboard back so the last play stays visible) — this
# holds the previous half's last real matchup on screen for this long
# after the batting team actually changes, rather than swapping to the
# new team the instant the delayed feed reports one.
MATCHUP_SWITCH_HOLD_SECONDS = 15


def _held_matchup(game_id: int, matchup: dict | None, half_marker: str) -> dict | None:
    """Which matchup dict to actually show right now — either the fresh
    one for the CURRENT half, or (for up to MATCHUP_SWITCH_HOLD_SECONDS
    after the batting half last changed) the previous half's last real
    matchup instead. Keyed by game_id + half_marker (inning_state:
    current_inning, e.g. "Top:4") so a genuinely new half always starts
    its own fresh hold rather than inheriting one from a half two
    switches ago — same marker shape _mlb_between_innings_target above
    already uses for the same reason."""
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
        # Same half, fresher data for it (a new batter within the same
        # half's lineup, or just-updated stats) — keep it current
        # without resetting the hold clock, which only cares about
        # WHEN the half itself last changed.
        tracked["matchup"] = matchup

    if tracked["prior_matchup"] is not None and now_ts - tracked["changed_at"] < MATCHUP_SWITCH_HOLD_SECONDS:
        return tracked["prior_matchup"]
    return tracked["matchup"]


# Session request: "add conditional formatting to the strike% value for
# pitchers so i can see at a glance if a pitcher is flowing or is
# struggling to find the zone" — same fire/ice hot-cold treatment the
# batter's OPS stats already get (_vs_pitcher_heat/_batter_season_heat
# in sports_client.py), reusing col()'s existing heat plumbing rather than
# adding a new visual language. League-average strike rate sits around
# 63-64%, so thresholds sit a healthy distance either side of that with
# a dead zone in between (normal outings shouldn't flicker orange/blue).
# A minimum pitch count guards against a small early-outing sample
# reading as a hot/cold streak (3 pitches, 3 strikes = 100% means
# nothing) — same idea as vs-pitcher's own VS_PITCHER_MIN_AB.
STRIKE_PCT_HOT = 66
STRIKE_PCT_COLD = 58
STRIKE_PCT_MIN_PITCHES = 10


def _strike_pct_heat(strikes: int, total_pitches: int) -> str | None:
    if total_pitches < STRIKE_PCT_MIN_PITCHES:
        return None
    pct = strikes / total_pitches * 100
    if pct >= STRIKE_PCT_HOT:
        return "hot"
    if pct <= STRIKE_PCT_COLD:
        return "cold"
    return None


# Session request: "add a strike zone between the 2 players and show
# balls in green strikes in red and fouls with 2 strikes are just
# grey... pull the most recent pitches in their short form with speeds
# to go below the zone." Real Statcast plate coordinates (feet, 0 = the
# middle of the plate) plotted to scale rather than a stylized/fake
# zone graphic — sports_client.fetch_mlb_recent_pitches already does
# the fetching/classifying; this just draws it. Viewbox is wider/taller
# than the real zone itself so a genuine ball well outside it still
# shows up on the diagram instead of clipping at the edge; pZ range
# (0.5-4.5ft) comfortably covers real strike-zone bounds for any batter
# height plus a couple feet of margin either side.
_ZONE_PLATE_HALF_WIDTH_FT = 17 / 2 / 12  # real MLB plate width (17in), halved for center-relative px
_ZONE_PX_RANGE_FT = 1.75  # +/- feet shown horizontally
_ZONE_PZ_MIN_FT, _ZONE_PZ_MAX_FT = 0.5, 4.5  # feet shown vertically
_ZONE_SVG_W, _ZONE_SVG_H = 140, 160
_MAX_PITCHES_SHOWN = 8  # a full-count battle can run well past this; only the most recent stay legible at this size
_PITCH_RESULT_COLOR = {"ball": "#32D74B", "strike": "#FF6961", "foul_frozen": "#9BA6BA"}


def _zone_svg_x(px: float) -> float:
    return (px + _ZONE_PX_RANGE_FT) / (2 * _ZONE_PX_RANGE_FT) * _ZONE_SVG_W


def _zone_svg_y(pz: float) -> float:
    return _ZONE_SVG_H - (pz - _ZONE_PZ_MIN_FT) / (_ZONE_PZ_MAX_FT - _ZONE_PZ_MIN_FT) * _ZONE_SVG_H


def _strike_zone_svg(game_id: int, zone_top: float, zone_bottom: float, pitches: list[dict]) -> str:
    """The zone box (this batter's own real strikeZoneTop/Bottom, not a
    generic average — varies by stance/height) plus one dot per pitch,
    plotted at its own real (px, pz). Older pitches fade toward
    transparent and shrink slightly; the most recent gets a white
    outline and full opacity, so the sequence itself — not just each
    pitch's own color — is readable at a glance.

    Session request: "how can we improve the experience watching the
    game... feel good and seamless." The newest dot gets a real fade-in
    (data-fade-slot/-value, see app.py's kiosk-jumbo-fade) keyed by that
    pitch's own identity (location+speed+type) rather than just an
    index, so a genuinely new pitch fades in while a rerun that hasn't
    seen a new one yet doesn't replay the animation on the same dot."""
    if zone_top is None or zone_bottom is None or not pitches:
        return ""
    zx1, zx2 = _zone_svg_x(-_ZONE_PLATE_HALF_WIDTH_FT), _zone_svg_x(_ZONE_PLATE_HALF_WIDTH_FT)
    zy1, zy2 = _zone_svg_y(zone_top), _zone_svg_y(zone_bottom)
    n = len(pitches)
    dots = []
    for i, p in enumerate(pitches):
        cx, cy = _zone_svg_x(p["px"]), _zone_svg_y(p["pz"])
        color = _PITCH_RESULT_COLOR.get(p["result"], "#9BA6BA")
        is_last = i == n - 1
        r = 8 if is_last else 6
        stroke = ' stroke="#fff" stroke-width="1.5"' if is_last else ""
        opacity = 0.5 + 0.5 * (i + 1) / n
        fade_attrs = ""
        if is_last:
            pitch_identity = f"{p['px']:.3f}-{p['pz']:.3f}-{p.get('speed')}-{p.get('type')}"
            fade_attrs = f' data-fade-slot="pitchdot-{game_id}" data-fade-value="{html.escape(pitch_identity)}"'
        dots.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{color}"{stroke} '
            f'opacity="{opacity:.2f}"{fade_attrs} />'
        )
    return (
        f'<svg class="jumbo-strikezone-svg" viewBox="0 0 {_ZONE_SVG_W} {_ZONE_SVG_H}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect x="{zx1:.1f}" y="{zy1:.1f}" width="{zx2 - zx1:.1f}" height="{zy2 - zy1:.1f}" '
        f'fill="none" stroke="#9BA6BA" stroke-width="2" rx="2" />'
        f'{"".join(dots)}'
        f"</svg>"
    )


def _recent_pitches_html(pitches: list[dict]) -> str:
    """The short-form pitch sequence below the zone — speed + MLB's own
    2-letter pitch-type code ("97 FF"), color-matched to that pitch's
    own dot in the zone above, oldest to newest left to right so the
    order reads the same direction as the at-bat actually happened."""
    chips = []
    for p in pitches:
        color = _PITCH_RESULT_COLOR.get(p["result"], "#9BA6BA")
        speed = round(p["speed"]) if p.get("speed") is not None else "—"
        ptype = html.escape(p.get("type") or "—")
        chips.append(f'<div class="jumbo-pitch-chip" style="color:{color}">{speed} {ptype}</div>')
    return f'<div class="jumbo-pitch-chips">{"".join(chips)}</div>'


def _strike_zone_block_html(game_id: int) -> str:
    """The full replacement for the plain "VS" divider — falls back to
    that plain text whenever there's genuinely no pitch data yet for
    the current at-bat (sports_client.fetch_mlb_recent_pitches's own
    None cases), rather than leaving a blank gap between the two player
    columns."""
    pitch_info = sports_client.fetch_mlb_recent_pitches(game_id)
    if not pitch_info:
        return '<div class="jumbo-live-matchup-vs">VS</div>'
    shown = pitch_info["pitches"][-_MAX_PITCHES_SHOWN:]
    zone_svg = _strike_zone_svg(game_id, pitch_info["zone_top"], pitch_info["zone_bottom"], shown)
    if not zone_svg:
        return '<div class="jumbo-live-matchup-vs">VS</div>'
    return f'<div class="jumbo-strikezone">{zone_svg}{_recent_pitches_html(shown)}</div>'


def _current_matchup_html(game_id: int) -> str:
    """Replaces the Top Performers panel with the two players actually
    involved in the live at-bat while a game is live — session request:
    "during the game can you make the top performers tab show current
    pitcher and batter and their stats use OPS for batter and ERA for
    pitchers." Photo-up-top, stat-below-name layout — session request:
    "add the pitcher and batter pics and put the stats below them like
    youd see on a jumbotron in the ballpark." MLB only (no batter/
    pitcher concept in hockey — NHL keeps the season-leaders rotation
    throughout). "" between innings (past MATCHUP_SWITCH_HOLD_SECONDS'
    own hold on the previous half's last batter), when the live feed
    has no one currently at the plate/mound to name (see sports_client.
    fetch_mlb_live_matchup's own docstring)."""
    detail = sports_client.fetch_mlb_live_detail(game_id)
    half_marker = f"{detail.get('inning_state') if detail else None}:{detail.get('current_inning') if detail else None}"
    matchup = _held_matchup(game_id, sports_client.fetch_mlb_live_matchup(game_id), half_marker)
    if not matchup:
        return ""
    batter, pitcher = matchup["batter"], matchup["pitcher"]

    # Session request: "add a ball and strike count below era and
    # pitches" — clarified to mean the whole outing's ball/strike split
    # (sports_client.fetch_mlb_live_matchup's own "balls"/"strikes"),
    # not the live at-bat's own count _mlb_situation_html's strip above
    # already shows — a different number, so a distinct label here
    # rather than reusing "COUNT". Session follow-up, after a same-
    # evening detour that put a strike% figure in _mlb_situation_html's
    # own strip instead and got immediately reverted ("who wants the
    # count shown as a percentage... I only want it shown for the
    # pitcher's total ball and strike count below their ERA and their
    # pitches"): the raw split here is now that percentage instead —
    # this is specifically the slot it was asked for, unlike the at-bat
    # strip above, which keeps its own real "2-1"-style count untouched.
    balls, strikes = pitcher.get("balls"), pitcher.get("strikes")
    total_pitches = (balls or 0) + (strikes or 0)
    strike_pct = f"{round(strikes / total_pitches * 100)}%" if balls is not None and strikes is not None and total_pitches else None
    strike_pct_heat = _strike_pct_heat(strikes, total_pitches) if strike_pct is not None else None

    # Session feedback: "make the ops and era less clunky... the whole
    # matchup thing needs to be easier to read." A value+unit crammed
    # into one string ("4.31 ERA") at one size read busy from across
    # the room — split into a big number plus a small caption underneath,
    # the same big-stat/small-caption pattern _top_performers_html's own
    # big card already uses (jumbo-leader-big-stat/-cat). Later request:
    # "for pitchers add number of pitches below ERA and then just do
    # average for batter" — a pitcher now carries two stat blocks side
    # by side, a batter just the one; `stats` takes however many
    # (value, label) pairs apply, skipping any that came back None.
    # Session request: "move that count below the other pitcher stats"
    # — `stat_rows` is a list of rows, each a list of (value, label,
    # heat) tuples, so a pitcher can get ERA/PITCHES on one row and
    # STRIKE% on its own row underneath, while a batter's single-row OPS
    # is unaffected. Later session request ("does espn show hot streaks
    # or anything? yes please") added the batter's own second row:
    # career average vs this exact pitcher, already None'd out by
    # sports_client when there's no history vs this pitcher, so `stats`
    # filtering them out here is enough, no extra branch needed. Follow-
    # up request added `heat` ("hot"/"cold"/None from sports_client's
    # _vs_pitcher_heat) — None for pitches/strike%, which aren't judged
    # hot/cold at all. A second follow-up request extended heat to
    # season OPS/ERA too (sports_client's _batter_season_heat/
    # _pitcher_season_heat, a delta off the player's own career line
    # rather than a fixed threshold). A Savant "OVERALL" percentile score
    # briefly lived here too (needing a 4th `style` tuple slot for its
    # own continuous gradient color) — removed per session feedback
    # ("let's get rid of the overall rating from baseball... OPS is just
    # a better stat"), taking that slot back out with it.
    def col(tag: str, player: dict, stat_rows: list[list[tuple]], line: str | None = None) -> str:
        photo = (
            f'<img class="jumbo-live-matchup-photo" src="{html.escape(player["photo"])}" onerror="this.style.display=\'none\'" />'
            if player.get("photo")
            else ""
        )
        rows_html = ""
        for stats in stat_rows:
            blocks = "".join(
                f'<div class="jumbo-live-matchup-stat-block">'
                f'<div class="jumbo-live-matchup-stat{" jumbo-live-matchup-stat-" + heat if heat else ""}">'
                f"{html.escape(str(value))}</div>"
                f'<div class="jumbo-live-matchup-stat-label">{html.escape(label)}</div>'
                f"</div>"
                for value, label, heat in stats
                if value is not None
            )
            if blocks:
                rows_html += f'<div class="jumbo-live-matchup-stat-row">{blocks}</div>'
        if not rows_html:
            rows_html = '<div class="jumbo-live-matchup-stat-row"><div class="jumbo-live-matchup-stat-block"><div class="jumbo-live-matchup-stat">—</div></div></div>'
        # Session request: "add the full line score for the active
        # pitchers below balls and strike count without making the
        # pitchers name shift up" — appended strictly after every stat
        # row, never before the name/photo/tag above, so there's
        # nothing here that could move them: this is the last thing in
        # the column, not an insertion above anything already placed.
        line_html = f'<div class="jumbo-live-matchup-line">{html.escape(line)}</div>' if line else ""
        # Session request: "how can we improve the experience watching
        # the game... feel good and seamless and like its all
        # orchestrated" — this whole column (photo/name/every stat)
        # fades in together whenever the actual player changes (a new
        # batter up, a pitching change), instead of every piece just
        # popping to the new player's values independently. Slot is
        # per-tag ("At Bat" vs "Pitching") so the two columns' fades
        # are tracked separately (see app.py's kiosk-jumbo-fade).
        slot = f"matchup-{tag.lower().replace(' ', '-')}"
        return (
            f'<div class="jumbo-live-matchup-col" data-fade-slot="{slot}" data-fade-value="{player.get("id", "")}">{photo}'
            f'<div class="jumbo-live-matchup-tag">{html.escape(tag)}</div>'
            f'<div class="jumbo-live-matchup-name">{html.escape(player["name"])}</div>'
            f"{rows_html}{line_html}"
            f"</div>"
        )

    batter_rows = [
        [(batter.get("ops"), "OPS", batter.get("season_ops_heat"))],
        [(batter.get("vs_pitcher"), "VS PITCHER", batter.get("vs_pitcher_heat"))],
    ]
    pitcher_rows = [
        [
            (pitcher.get("era"), "ERA", pitcher.get("season_era_heat")),
            (pitcher.get("pitches"), "PITCHES", None),
            # Session request: "add the strikeouts to the big stats for
            # pitchers" — this game's own strikeout total (sports_client.
            # fetch_mlb_live_matchup's "strikeouts", off the same boxscore
            # PITCHES/line already come from), not judged hot/cold.
            (pitcher.get("strikeouts"), "K", None),
        ],
        [(strike_pct, "STRIKE%", strike_pct_heat)],
    ]
    return (
        f'<div class="jumbo-leaders"><div class="jumbo-sl">Current Matchup</div>'
        f'<div class="jumbo-live-matchup">'
        f'{col("At Bat", batter, batter_rows)}'
        f'{_strike_zone_block_html(game_id)}'
        f'{col("Pitching", pitcher, pitcher_rows, pitcher.get("line"))}'
        f"</div></div>"
    )


def _batting_order_row_html(entry: dict, is_current: bool, tier: str | None, team_key: str = "") -> str:
    ops = html.escape(entry["ops"]) if entry.get("ops") else "—"
    number = html.escape(str(entry["number"])) if entry.get("number") else ""
    position = html.escape(entry.get("position") or "")
    # Session request: "add the results from the at bat in the
    # lineup... dont show anything if theres nothing" — an empty span
    # (not a placeholder dash) whenever this hitter has no official at-
    # bat yet this game, so the column just goes quiet instead of
    # showing a misleading "0/0" for someone who hasn't hit yet.
    game_line = html.escape(entry["game_line"]) if entry.get("game_line") else ""
    row_class = "jumbo-lineup-row jumbo-lineup-row-current" if is_current else "jumbo-lineup-row"
    ops_class = f"jumbo-lineup-ops jumbo-lineup-ops-{tier}" if tier else "jumbo-lineup-ops"
    # Session request: "how can we improve the experience watching the
    # game... feel good and seamless" — the current-batter row fades in
    # when the highlight moves to a new hitter, rather than the accent
    # bar just snapping onto whichever row happens to render with
    # jumbo-lineup-row-current this time (see app.py's kiosk-jumbo-fade).
    # Only the currently-highlighted row carries the attributes at
    # all — a row that's never "current" has nothing to fade.
    fade_attrs = (
        f' data-fade-slot="lineup-current-{html.escape(team_key)}" data-fade-value="{html.escape(entry.get("name", ""))}"'
        if is_current
        else ""
    )
    return (
        f'<div class="{row_class}"{fade_attrs}>'
        f'<span class="jumbo-lineup-num">{number}</span>'
        f'<span class="jumbo-lineup-name">{html.escape(entry["short_name"].upper())}</span>'
        f'<span class="jumbo-lineup-pos">{position}</span>'
        f'<span class="jumbo-lineup-gameline">{game_line}</span>'
        f'<span class="{ops_class}">{ops}</span>'
        f"</div>"
    )


_BATTING_ORDER_HEADER = (
    '<div class="jumbo-lineup-header">'
    '<span class="jumbo-lineup-num">#</span>'
    '<span class="jumbo-lineup-name">PLAYER</span>'
    '<span class="jumbo-lineup-pos">POS</span>'
    '<span class="jumbo-lineup-gameline">AB</span>'
    '<span class="jumbo-lineup-ops">OPS</span>'
    "</div>"
)


def _batting_order_rail_html(
    entries: list[dict], team: dict, current_batter: str | None, accent_rgb: tuple[int, int, int] | None = None
) -> str:
    """The batting order for whichever team is actually at bat right
    now — one clean stat per hitter — session request, after attending
    a real Jays game: "they had the batting order, and the only stat
    they showed was OPS. This gave me a very easy way of seeing who is
    the best hitter for each team." Session follow-up, with a real
    photo of Rogers Centre's own board as the reference: "make it just
    the team that's up to bat... number, player, position, and OPS...
    make it look as close to that as possible." Row order alone conveys
    batting position (1st through 9th) exactly like the real board —
    the number shown per row is the player's jersey number, not a
    lineup slot (see sports_client.fetch_mlb_batting_order's own
    docstring).

    Second follow-up: "bonus points if you can highlight who's actually
    up to bat right now and add the team logos at top." `current_batter`
    (a full name, from the same live-detail fetch render() already made
    to pick which side is up) is matched against each entry's own real
    name — a plain string compare, not an id, since that's all the
    boxscore's own hitter entries carry, but a lineup's 9 real full
    names are exactly as reliable a key as an id would be within one
    game. The logo block reuses the same team dict _sides()/_side_html
    already build (same "logo"/"name" keys), so this needed no new data
    of its own. See render()'s own comment for how the at-bat side and
    the rail-takeover gating (live + top MLB priority) are decided.

    Third follow-up, after seeing color-option drafts: "get me B [the
    performance-heat option], but... find the league average ops...
    top ten percent gets brightest green, top twenty five medium green,
    average or near average neutral white, bottom twenty five red...
    dynamic so it shows exactly where they are in context to the
    entire league." Each row's OPS color comes from sports_client.
    ops_tier() against fetch_league_ops_tiers()' real, current
    qualified-hitter percentile cutoffs (a fresh 149-hitter distribution
    this session, not a fixed number) — the at-bat highlight itself
    moved to a left accent bar (jumbo-lineup-row-current) rather than a
    full-row color wash specifically so it doesn't fight the tier
    color sitting right next to it in the same row.

    `accent_rgb` — session follow-up to the featured board's own
    Network Primetime reskin: "show me what it would look like if you
    gave the entire rest of the jumbotron this kind of emphasis," then
    "build it into the real jumbotron." Sets --side-rgb inline so
    theme.py's own .jumbo-lineup-head can paint the same diagonal
    team-color wash the featured board's .jumbo-side already uses —
    render() passes _side_color's own result for whichever side is
    actually batting (not always "us"; the opponent's lineup shows the
    same way when they're up). Deliberately NOT applied to .jumbo-
    lineup-row-current (the current-batter highlight) — that row
    already went through a real color-clash fix earlier (a solid wash
    fought the OPS tier color sitting in the same row, see that CSS
    rule's own comment); this stays scoped to the team header, which
    has no competing color of its own."""
    tiers = sports_client.fetch_league_ops_tiers()
    style = f' style="--side-rgb:{accent_rgb[0]},{accent_rgb[1]},{accent_rgb[2]}"' if accent_rgb else ""
    head = (
        f'<div class="jumbo-lineup-head"{style}>'
        f'<img class="jumbo-lineup-logo" src="{html.escape(team["logo"])}" />'
        f'<div class="jumbo-lineup-headtext">'
        f'<div class="jumbo-lineup-teamname">{html.escape(team["name"])}</div>'
        f'<div class="jumbo-lineup-atbat">At Bat</div>'
        f"</div></div>"
    )
    rows = "".join(
        _batting_order_row_html(
            e,
            current_batter is not None and e.get("name") == current_batter,
            sports_client.ops_tier(e.get("ops"), tiers),
            team["name"],
        )
        for e in entries
    )
    return f"{head}{_BATTING_ORDER_HEADER}{rows}"


def _last_play_html(game_id: int, away: dict, home: dict) -> str:
    """A compact "last play" strip below the Current Matchup card —
    session request: "add a play badge that shows the last play from
    the live game feed and situation TOR LOGO 0-1 BOS LOGO ie: ____
    grounded out to first directly from the live feed... below the
    batter pitcher matchup." The description is MLB's own real sentence
    for the play, used verbatim (see sports_client.fetch_mlb_last_play's
    own docstring), not paraphrased. "" whenever there's genuinely no
    completed play yet (top of the 1st) or the fetch fails — no gap
    left in the layout, same as _current_matchup_html's own between-
    innings "" case just above."""
    play = sports_client.fetch_mlb_last_play(game_id)
    if not play:
        return ""
    # The score as of THIS play specifically (the live feed's own
    # per-play result, not the board's separately-fetched current
    # score) — self-consistent with the play description sitting right
    # next to it, even in the rare rerun where the two would otherwise
    # momentarily disagree.
    away_score = play["away_score"] if play["away_score"] is not None else "–"
    home_score = play["home_score"] if play["home_score"] is not None else "–"
    # Session request: "how can we improve the experience watching the
    # game... feel good and seamless" — the whole strip fades in when a
    # genuinely new play lands (keyed by the play's own description
    # text — a real new sentence every time, unlike the score alone,
    # which can repeat across reruns while this same play is still the
    # latest one), instead of the score/description just snapping to
    # the new play's text (see app.py's kiosk-jumbo-fade).
    play_key = html.escape(play["description"])
    return (
        f'<div class="jumbo-lastplay" data-fade-slot="lastplay-{game_id}" data-fade-value="{play_key}">'
        f'<div class="jumbo-lastplay-score">'
        f'<img class="jumbo-lastplay-logo" src="{html.escape(away["logo"])}" />'
        f'<span class="jumbo-lastplay-tally">{away_score}–{home_score}</span>'
        f'<img class="jumbo-lastplay-logo" src="{html.escape(home["logo"])}" />'
        f"</div>"
        f'<div class="jumbo-lastplay-desc">{html.escape(play["description"])}</div>'
        f"</div>"
    )


def _fmt_break_clock(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


# MLB's own pitch-clock rule fixes every half-inning break at exactly
# this long (session correction: "its a 1:30 countdown" — the live
# feed itself doesn't hand back a literal countdown field, but the
# rule does fix the number, so a real countdown is possible after all).
MLB_BREAK_SECONDS = 90


def _mlb_between_innings_target(game_id: int, detail: dict, now_ts: float) -> float | None:
    """The real epoch-seconds timestamp this break should end at, or
    None if not currently between innings. Keyed by inning+half (not
    just game_id) so a fresh break starts its own MLB_BREAK_SECONDS
    countdown rather than inheriting the last one's target. If the
    real game ever runs past 0:00 (a pitching change mid-break, say),
    the countdown just holds at 0:00 — the live-countdown ticker
    already clamps negative to zero — rather than going negative or
    looking broken."""
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


# Session correction: "an NFL halftime lasts thirteen minutes. So from
# the time that halftime first updates, just make a ten minute timer."
# Deliberately shorter than the real ~13-minute halftime — same "end
# the timer a bit ahead of the real break, never wait for play to
# actually resume" buffer already established for MLB above (session
# request there: "make the out of town scoreboard end the second the
# timer is over").
NFL_HALFTIME_SECONDS = 10 * 60


def _nfl_halftime_target(game_id, detail: dict, now_ts: float) -> float | None:
    """The real epoch-seconds timestamp this halftime countdown should
    end at, or None if it isn't currently halftime. Keyed by game_id
    alone, not a marker like MLB's own version above needs — a single
    game only ever has one halftime, so there's no second occurrence
    within the same game that could accidentally inherit a stale
    target the way a fresh half-inning break could."""
    key = f"jumbotron_nfl_halftime_{game_id}"
    if not detail.get("is_halftime"):
        st.session_state.pop(key, None)
        return None
    tracked = st.session_state.get(key)
    if not tracked:
        tracked = {"started_at": now_ts}
        st.session_state[key] = tracked
    return tracked["started_at"] + NFL_HALFTIME_SECONDS


# Session request: "delay the out of town scoreboard by like 15
# seconds so i can actually see the last play of the inning" — the
# overlay used to take the whole screen the instant a break started,
# covering the very play (and the last-play badge) that just ended it
# before there was any real chance to read it. Tracks when THIS
# specific break/intermission first became true (keyed by game_id plus
# a marker, so a new break always gets its own fresh window rather
# than inheriting one from whatever break happened before it) — a
# separate concern from MLB_BREAK_SECONDS/NHL's own clock above, which
# are about "when does the game resume," not "how long to keep showing
# the featured board before switching away from it."
OVERLAY_DELAY_SECONDS = 15


def _overlay_delay_elapsed(game_id: int, marker: str, now_ts: float) -> bool:
    key = f"jumbotron_overlay_delay_{game_id}"
    tracked = st.session_state.get(key)
    if not tracked or tracked.get("marker") != marker:
        tracked = {"marker": marker, "started_at": now_ts}
        st.session_state[key] = tracked
    return now_ts - tracked["started_at"] >= OVERLAY_DELAY_SECONDS


def _around_leagues_pages(now_ts: float) -> list[tuple[str, int, int, list[dict]]]:
    """Every game for every active league (_AROUND_LEAGUES), split into
    fixed-size pages (_AROUND_PAGE_SIZE) as (league_key, page_index,
    page_total, chunk) tuples — nothing capped or dropped, just paged.
    One page is meant to be shown at a time, picked by index
    (int(now_ts // _AROUND_ROTATE_SECONDS) % len(pages)) at each of
    this list's two call sites: _around_html's own sidebar rail, and
    _between_play_overlay_html's full-screen version. Shared here so
    both build the identical page set from the identical data on the
    identical clock, rather than risking two independent copies of
    this same pagination logic quietly drifting apart."""
    pages: list[tuple[str, int, int, list[dict]]] = []
    order = {"in": 0, "pre": 1, "post": 2}
    for key in _AROUND_LEAGUES:
        try:
            games = scores_client.fetch_games(key)
        except Exception:
            continue
        if not games:
            continue
        # Live first, then upcoming, then finals — the same ordering
        # priority the board itself uses.
        games = sorted(games, key=lambda g: order.get(g["state"], 3))
        chunks = [games[i : i + _AROUND_PAGE_SIZE] for i in range(0, len(games), _AROUND_PAGE_SIZE)]
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            pages.append((key, i, total, chunk))
    return pages


# Session request: "if there's a game going on with another one of my
# teams... I want [the out-of-town scoreboard] to have a permanent game
# on there for the team that's playing... that can't be trumped by
# anything." ESPN's own abbreviation for each tracked team, so a live
# game can be picked straight out of scores_client.fetch_games(sport)'s
# own already-fetched, already-_mini_row_html-shaped list rather than
# re-fetching or reshaping anything from sports_client's differently-
# shaped Jays/Habs/Saints feeds.
_PINNED_TEAM_ABBR = {
    "mlb": sports_client.MLB_TEAM_ABBR,
    "nhl": sports_client.NHL_TEAM_ABBR,
    "nfl": sports_client.NFL_TEAM_ABBR,
}


def _pinned_team_games(exclude_sport: str) -> list[dict]:
    """The live game (if any) for every tracked team other than
    exclude_sport — the team already featured on the main board, whose
    own break is the entire reason this overlay is up right now, so
    pinning it again here would just be redundant. "Live" only (state
    == "in"): "if there's a game going ON," not one that's upcoming or
    already final."""
    out = []
    for sport, abbr in _PINNED_TEAM_ABBR.items():
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


def _pinned_ufc_bout(now: datetime) -> tuple[dict, dict] | None:
    """(event, bout) for a live UFC card right now, or None — same
    "going on" bar as _pinned_team_games, and the same coverage window
    (Saturday nights) ufc_client.takeover_state itself already uses for
    the main board, so this only ever fires exactly when a real UFC
    night is actually live. Independent of app.py's own _ufc_takeover
    (which app.py deliberately nulls out when a live Habs/Jays game
    already owns the main screen — see its own comment) since a pinned
    slot here is exactly the case that suppression exists for: UFC
    still going on in the background while a team game is featured."""
    ufc_state = ufc_client.takeover_state(now)
    if not ufc_state or ufc_state["phase"] != "live":
        return None
    bout = ufc_client.current_bout(ufc_state["event"])
    if not bout:
        return None
    return ufc_state["event"], bout


def _ufc_pinned_row_html(bout: dict) -> str:
    """A .jumbo-mini-shaped row for the pinned live UFC bout — fighters
    instead of teams, round/clock instead of a score, so this is its
    own small renderer rather than coercing fight data into _mini_row_
    html's team-game shape (see ufc_client's own docstring on why a
    bout needed a genuinely different shape in the first place). Reuses
    the exact same CSS classes so it still sits flush in the same grid
    as the team rows around it."""

    def fighter_row(f: dict) -> str:
        record = f'<span class="jumbo-mini-record">{html.escape(f["record"])}</span>' if f.get("record") else ""
        return f'<div class="jumbo-mini-team"><span class="jumbo-mini-abbr">{html.escape(f["short_name"])}</span>{record}</div>'

    status_text = f'Rd {bout["round"]} · {bout["clock"]}'.strip(" ·") if bout.get("round") else "Live"
    return (
        '<div class="jumbo-mini jumbo-mini-live"><div class="jumbo-mini-teams">'
        f'{fighter_row(bout["fighter_a"])}{fighter_row(bout["fighter_b"])}</div>'
        f'<div class="jumbo-mini-status">{html.escape(status_text)}</div></div>'
    )


def _between_play_overlay_html(state: dict, now: datetime) -> str:
    """Full-screen "out of town scoreboard" during a natural break in
    the featured game — session request: "between innings / periods
    can we go to a full screen out of town scoreboard. with a timer
    till the game resumes again," later extended to a third sport:
    "make it so that the out of town scoreboard shows during baseball
    between innings, NHL intermissions, and NFL half times." Qualifies
    on MLB half-inning breaks (inning_state Middle/End), NHL
    intermissions (in_intermission), and NFL halftime (ESPN's own
    STATUS_HALFTIME status). Held back OVERLAY_DELAY_SECONDS from when
    the break actually started (see _overlay_delay_elapsed above)
    before actually taking over the screen.

    Unlike the fixed-duration new-pitcher overlay, this isn't a timed
    toast — it's re-evaluated fresh every rerun and stays up for
    exactly as long as the break condition itself stays true, gone the
    instant play resumes. All three sports get a real countdown, driven
    by the same live-countdown ticker the pregame/leave-headline
    countdowns already use: NHL's own intermission clock carries one
    directly (intermission_seconds_remaining, the same number the
    broadcast's own countdown uses); MLB's and NFL's live feeds don't
    hand one back, but each has its own fixed reference to count down
    against instead — MLB's real pitch-clock rule (MLB_BREAK_SECONDS),
    and NFL_HALFTIME_SECONDS (session correction: "an NFL halftime
    lasts thirteen minutes... just make a ten minute timer" — a
    deliberate buffer under the real length, same "end on the timer
    itself, never wait for play to actually resume" reasoning
    MLB_BREAK_SECONDS's own use already established).

    Shows every game around the leagues (scores_client.fetch_games,
    same source the sidebar's own Around The Leagues panel reads —
    including the featured game itself, still sitting mid-list; not
    worth the extra matching logic to filter out one row), full-screen
    since there's real room and a real reason to look elsewhere for a
    minute. "" outside a break, or if there's nothing to show.

    Never triggers for a neutral MLB/NHL game (sports_alerts._neutral_
    playoff_candidates): fetch_mlb_live_detail/fetch_nhl_live_detail
    below poll the official league API by ITS OWN game id, which a
    neutral game's ESPN-sourced game_id isn't (see _board_html's own
    comment on this same id-space mismatch) — `if not detail: return
    ""` a few lines down means this degrades to simply never detecting
    a break rather than crashing, so a neutral game just never gets
    this particular overlay. A real gap, not worth chasing down for a
    between-innings/intermission nicety when everything that actually
    carries the game (score, situation, blurb, win probability) stays
    correct either way."""
    if state.get("phase") != "live" or not state.get("game"):
        return ""
    sport = state["league"]["sport"]
    game = state["game"]
    game_id = game["game_id"]
    now_ts = time.time()

    if sport == "mlb":
        detail = sports_client.fetch_mlb_live_detail(game_id)
        if not detail:
            return ""
        target_ts = _mlb_between_innings_target(game_id, detail, now_ts)
        if target_ts is None:
            return ""
        # Session request: "make the out of town scoreboard end the
        # second the timer is over" — MLB_BREAK_SECONDS is an estimate
        # (a real break can run long — a pitching change, a replay
        # review), so the real inning_state can still say "still
        # between innings" for a while after this countdown already
        # hit 0:00. Ending on the timer itself, not on the game
        # actually resuming, means it never sits on a stalled "0:00".
        if target_ts - now_ts <= 0:
            return ""
        marker = f'{detail.get("inning_state")}:{detail.get("current_inning")}'
        if not _overlay_delay_elapsed(game_id, marker, now_ts):
            return ""
        headline = f'{(detail.get("inning_state") or "").upper()} OF {detail.get("current_inning") or ""}'.strip()
        target_ms = int(target_ts * 1000)
        timer_span = f'<div class="jumbo-otc-timer live-countdown" data-target-ms="{target_ms}" data-format="clock">{html.escape(_fmt_break_clock(target_ts - now_ts))}</div>'
        timer_label = "GAME RESUMES IN"
    elif sport == "nhl":
        detail = sports_client.fetch_nhl_live_detail(game_id)
        if not detail or not detail.get("in_intermission"):
            return ""
        secs = detail.get("intermission_seconds_remaining")
        # Same reasoning as the MLB branch above — NHL's own clock is
        # real (not an estimate), but polling lag can still leave
        # in_intermission true for a tick or two after it hits 0.
        if secs is None or secs <= 0:
            return ""
        marker = f'intermission:{detail.get("period_label")}'
        if not _overlay_delay_elapsed(game_id, marker, now_ts):
            return ""
        headline = "INTERMISSION"
        target_ms = int((now_ts + secs) * 1000)
        timer_span = f'<div class="jumbo-otc-timer live-countdown" data-target-ms="{target_ms}" data-format="clock">{html.escape(_fmt_break_clock(secs))}</div>'
        timer_label = "UNTIL PUCK DROP"
    elif sport == "nfl":
        detail = sports_client.fetch_nfl_live_detail(game_id)
        if not detail:
            return ""
        target_ts = _nfl_halftime_target(game_id, detail, now_ts)
        if target_ts is None:
            return ""
        # Same reasoning as the MLB branch above — NFL_HALFTIME_SECONDS
        # is a deliberate buffer, not the real ~13-minute length, so
        # this ends on the timer itself rather than waiting for
        # is_halftime to actually flip back to False.
        if target_ts - now_ts <= 0:
            return ""
        marker = "halftime"
        if not _overlay_delay_elapsed(game_id, marker, now_ts):
            return ""
        headline = "HALFTIME"
        target_ms = int(target_ts * 1000)
        timer_span = f'<div class="jumbo-otc-timer live-countdown" data-target-ms="{target_ms}" data-format="clock">{html.escape(_fmt_break_clock(target_ts - now_ts))}</div>'
        timer_label = "SECOND HALF IN"
    else:
        return ""

    # Session request: "don't be afraid to make them switch pages
    # because right now you have MLB and NHL or NFL on one [page],
    # which is starting to look a little cramped." Real bug, not just
    # a look: every league's every game used to get dumped into one
    # unbounded .jumbo-otc-grid with overflow-y:auto — on a kiosk
    # nobody can scroll (see this app's own established "never rely on
    # overflow-y:auto to hide list content" rule), so on a real multi-
    # league night, games past whatever silently fit were permanently
    # invisible, not just visually tight. Same paginate-and-rotate-on-
    # a-wall-clock-timer pattern _around_html's own sidebar rail
    # already uses (_around_leagues_pages) — one league's one page at
    # a time instead, cycling through everything rather than cramming
    # it all in at once.
    pages = _around_leagues_pages(now_ts)
    if not pages:
        return ""
    index = int(now_ts // _AROUND_ROTATE_SECONDS) % len(pages)
    league_key, page_num, page_total, chunk = pages[index]
    page_label = league_key.upper() + (f" · {page_num + 1}/{page_total}" if page_total > 1 else "")

    # Pinned rows (see _pinned_team_games/_pinned_ufc_bout's own
    # docstrings) — dropped from the rotating chunk first so a pinned
    # team's own game never shows twice just because the rotation
    # happened to land on its league's page too, then the chunk is
    # trimmed to leave room: this overlay's whole reason for switching
    # to fixed-size pages in the first place (see the comment above)
    # was a kiosk that can't scroll silently losing rows past whatever
    # fit, and unconditionally adding pinned rows on top of an already-
    # tuned-to-fit page would reintroduce exactly that.
    pinned_games = _pinned_team_games(exclude_sport=sport)
    pinned_keys = {(g["home"]["abbr"], g["away"]["abbr"]) for g in pinned_games}
    chunk = [g for g in chunk if (g["home"]["abbr"], g["away"]["abbr"]) not in pinned_keys]
    pinned_bout = _pinned_ufc_bout(now)
    pinned_total = len(pinned_games) + (1 if pinned_bout else 0)
    chunk = chunk[: max(1, _AROUND_PAGE_SIZE - pinned_total)]
    rows_html = "".join(_mini_row_html(g) for g in chunk)

    pinned_html = ""
    if pinned_games or pinned_bout:
        pinned_rows = "".join(_mini_row_html(g) for g in pinned_games)
        if pinned_bout:
            pinned_rows += _ufc_pinned_row_html(pinned_bout[1])
        pinned_html = f'<div class="jumbo-otc-league">Pinned</div><div class="jumbo-otc-grid">{pinned_rows}</div>'

    # Same page-change crossfade _around_html's own sidebar rail uses
    # (see its own comment on why two alternating classes, not one) —
    # its own dedicated session_state keys, not shared with that rail,
    # since the two rotate independently even though both read off the
    # same underlying page list/clock. Pinned rows above are deliberately
    # outside this — they don't "change pages," so they never fade.
    identity = f"{league_key}:{page_num}"
    changed = identity != st.session_state.get("jumbotron_otc_identity")
    st.session_state["jumbotron_otc_identity"] = identity
    fade_class = ""
    if changed:
        tick = st.session_state.get("jumbotron_otc_fade_tick", 0) + 1
        st.session_state["jumbotron_otc_fade_tick"] = tick
        fade_class = " jumbo-around-fade-a" if tick % 2 == 0 else " jumbo-around-fade-b"

    return (
        '<div class="jumbo-otc-overlay"><div class="jumbo-otc-inner">'
        '<div class="jumbo-otc-title">Out Of Town Scoreboard</div>'
        f'<div class="jumbo-otc-sub">{html.escape(headline)}</div>'
        f'<div class="jumbo-otc-timer-block">{timer_span}<div class="jumbo-otc-timer-label">{html.escape(timer_label)}</div></div>'
        f'{pinned_html}'
        f'<div class="jumbo-otc-league">{html.escape(page_label)}</div>'
        f'<div class="jumbo-otc-grid{fade_class}">{rows_html}</div>'
        "</div></div>"
    )


# MLB's own short classification for a play (result.event) — grouped
# just enough to color the takeover by what actually happened, not
# re-derived from the free-text description (same "use the API's own
# field, don't guess" reasoning as the description text itself). Not
# exhaustive — anything not listed here still shows (via event.upper()
# in _play_result_overlay_html), just in the neutral tone.
_HIT_EVENTS = {"Single", "Double", "Triple", "Home Run", "Walk", "Intent Walk", "Hit By Pitch"}
_OUT_EVENTS = {
    "Strikeout", "Groundout", "Flyout", "Lineout", "Pop Out", "Double Play", "Triple Play",
    "Sac Fly", "Sac Bunt", "Field Out", "Force Out", "Grounded Into DP", "Fielders Choice Out",
}


# Session request: "can the animation be longer than 3 seconds?" — the
# first version was a genuine single-shot CSS animation, which capped
# out at how long its own DOM node survives before the next 5s rerun
# replaces it (the same hard ceiling the out-of-town overlay and the
# postgame win-burst already live within). To hold for longer than one
# rerun cycle, _play_result_overlay_html now tracks WHEN a play was
# first detected (not just whether it's been shown once) and keeps
# re-rendering it across as many reruns as it takes to fill this many
# seconds, with a negative animation-delay computed fresh each time so
# the CSS hold/fade timeline picks up exactly where real elapsed time
# says it should — same technique app.py's own rotation-timer-fill bar
# already uses for a countdown that has to survive multiple reruns
# without visibly restarting.
PLAY_RESULT_HOLD_SECONDS = 5


def _play_result_overlay_html(game_id: int, play: dict | None) -> str:
    """Full-screen announcement of what the last play actually was,
    held for PLAY_RESULT_HOLD_SECONDS — session request: "add an
    animation that takes up the screen after every play. Single,
    Double, Triple, Home Run, Lineout, Strikout, Pop Out etc so i can
    tell what happened. this alert should be based on the last play
    bar." Reuses the exact same data sports_client.fetch_mlb_last_play
    already hands the last-play badge (see its own docstring) — no
    extra request, and "based on the last play bar" is literally true,
    not just similar.

    Session-guarded per (game_id, this specific play's identity): a
    genuinely new play resets the hold window's start time; the same
    play re-detected on a later rerun keeps counting from when it was
    first seen, not restarting the clock. "" once PLAY_RESULT_HOLD_
    SECONDS has genuinely elapsed, or if there's no play yet."""
    if not play or not play.get("event"):
        return ""
    identity = f'{play.get("description")}|{play["away_score"]}|{play["home_score"]}'
    key = f"jumbotron_last_play_shown_{game_id}"
    now_ts = time.time()
    tracked = st.session_state.get(key)
    if not tracked or tracked.get("identity") != identity:
        tracked = {"identity": identity, "started_at": now_ts}
        st.session_state[key] = tracked
    elapsed = now_ts - tracked["started_at"]
    if elapsed >= PLAY_RESULT_HOLD_SECONDS:
        return ""
    event = play["event"]
    tone = "hit" if event in _HIT_EVENTS else "out" if event in _OUT_EVENTS else "neutral"
    # Both animations get the same negative delay so a rerun landing
    # mid-hold picks up exactly where it should — the text's own 0.5s
    # pop-in has long since "finished" and just sits settled, and the
    # outer hold-fade is wherever real elapsed time says it should be,
    # not restarted from 0% the way a fresh DOM node normally would be.
    delay_style = f"animation-delay: -{elapsed:.2f}s;"
    overlay_style = f"{delay_style} animation-duration: {PLAY_RESULT_HOLD_SECONDS}s;"
    return (
        f'<div class="jumbo-play-overlay jumbo-play-overlay-{tone}" style="{overlay_style}">'
        f'<div class="jumbo-play-text" style="{delay_style}">{html.escape(event.upper())}</div>'
        f"</div>"
    )


# Session request: "make a pre and postgame ai overview thats only
# generated once. give it a bunch of info from the espn API and have
# it do a pre and post game blurb" — see game_blurb.py's own docstring
# for the one-shot-per-game caching and where the ESPN facts come from.
_TEAM_FULL_NAME = {"mlb": sports_client.MLB_TEAM_NAME, "nhl": sports_client.NHL_TEAM_NAME, "nfl": sports_client.NFL_TEAM_NAME}

# Session request: "for the teams that aren't currently in season, can
# we just have like a little countdown on their team bar for when
# their first game is" — used by _rail_hero_html's OFFSEASON branch
# below in place of the plain "OFFSEASON" text, once one of these
# actually finds a next game (see each fetch_*_next_game's own
# docstring for why the lookup differs per sport).
_NEXT_GAME_FETCHER = {
    "mlb": sports_client.fetch_mlb_next_game,
    "nhl": sports_client.fetch_nhl_next_game,
    "nfl": sports_client.fetch_nfl_next_game,
}
_NEXT_GAME_LEVEL_LABEL = {"preseason": "Preseason opener", "regular": "Season opener", "playoff": "Playoff opener"}


def _days_until_text(target: datetime, now: datetime) -> str:
    days = (target.date() - now.date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


def _offseason_countdown_html(sport: str, now: datetime) -> str:
    """"OFFSEASON" once fetch_*_next_game() itself comes up empty too
    (no schedule published that far out yet) — otherwise a compact
    "Preseason opener Aug 15 · in 20 days" line, same jumbo-offseason
    styling/slot as the plain text it replaces."""
    next_game = _NEXT_GAME_FETCHER[sport]()
    if not next_game:
        return '<div class="jumbo-gameline jumbo-offseason">OFFSEASON</div>'
    level_label = _NEXT_GAME_LEVEL_LABEL.get(next_game["level"], "Next game")
    date_text = next_game["start_time"].strftime("%b %-d")
    countdown_text = _days_until_text(next_game["start_time"], now)
    return (
        f'<div class="jumbo-gameline jumbo-offseason jumbo-offseason-countdown">'
        f"{html.escape(level_label)} {date_text} · {countdown_text}</div>"
    )


def _blurb_html(sport: str, game: dict, team_label: str, postgame: bool, status: dict | None = None) -> str:
    """"" whenever ESPN doesn't have this game or the AI call itself
    failed/hasn't landed yet — same "just omit it" rule every other
    optional jumbotron panel already follows, not a loading spinner or
    placeholder text.

    `status` (fetch_jays()/fetch_habs()/fetch_saints() shape — see
    game_blurb._stakes_line) is passed to both pregame and postgame now —
    a recap says what the result meant for the race, a preview says why
    the race matters going in."""
    our_name = _TEAM_FULL_NAME[sport]
    away_name = our_name if not game["is_home"] else game["opponent"]
    home_name = game["opponent"] if not game["is_home"] else our_name
    if postgame:
        text = game_blurb.get_postgame_blurb(sport, game["game_id"], team_label, away_name, home_name, game["opponent"], status)
    else:
        text = game_blurb.get_pregame_blurb(sport, game["game_id"], team_label, away_name, home_name, game["opponent"], status)
    if not text:
        return ""
    label = "AI Recap" if postgame else "AI Preview"
    return f'<div class="jumbo-blurb"><div class="jumbo-sl">{html.escape(label)}</div><div class="jumbo-blurb-text">{html.escape(text)}</div></div>'


def _blurb_html_neutral(sport: str, game: dict, postgame: bool) -> str:
    """_blurb_html()'s equivalent for a semis/finals game between two
    teams we have no stake in — see game_blurb.get_neutral_pregame_
    blurb/get_neutral_postgame_blurb's own docstrings for why this
    can't just call the same functions with our_name blanked out."""
    away_name = game["away"].get("full_name") or game["away"]["name"]
    home_name = game["home"].get("full_name") or game["home"]["name"]
    fn = game_blurb.get_neutral_postgame_blurb if postgame else game_blurb.get_neutral_pregame_blurb
    text = fn(sport, game["game_id"], away_name, home_name, game["match"], game.get("round_text"), game.get("series_summary"))
    if not text:
        return ""
    label = "AI Recap" if postgame else "AI Preview"
    return f'<div class="jumbo-blurb"><div class="jumbo-sl">{html.escape(label)}</div><div class="jumbo-blurb-text">{html.escape(text)}</div></div>'


def _board_html(state: dict, now: datetime) -> str:
    league, status, game = state["league"], state["status"], state["game"]
    sport, phase = league["sport"], state["phase"]
    neutral = league.get("neutral", False)
    if neutral:
        away, home = _sides_neutral(game)
        match = game["match"]
    else:
        away, home = _sides(status, game, league["label"])
        match = _espn_match_for(sport, game)
    # sport == "mlb" alone isn't enough below — _current_matchup_html/
    # _last_play_html/fetch_mlb_top_performers all poll MLB Stats API
    # by ITS OWN gamePk, which is what game["game_id"] holds for a
    # tracked Jays game (sports_client.fetch_jays's own id space) but
    # NOT for a neutral one (game["game_id"] there is ESPN's own event
    # id — see sports_alerts._neutral_playoff_candidates). Feeding an
    # ESPN id into an MLB Stats API lookup doesn't crash (every one of
    # these already tolerates "not found") but silently produces
    # nothing, which is worse than just falling through to the
    # ESPN/match-based rotation below like a neutral NHL/NFL game
    # already does.
    if phase == "live" and sport == "mlb" and not neutral:
        leaders_html = _current_matchup_html(game["game_id"])
        last_play_html = _last_play_html(game["game_id"], away, home)
    elif phase == "postgame" and sport == "mlb" and not neutral:
        # Session request: "fix post game so it shows the 3 best
        # players of the game." Real MLB Game Score ranking (see
        # sports_client.fetch_mlb_top_performers's own docstring) rather
        # than the season-stat-leader rotation below — falls back to
        # that same rotation on the rare chance MLB's own boxscore
        # doesn't have it for some reason, so postgame never goes blank.
        performers = sports_client.fetch_mlb_top_performers(game["game_id"])
        leaders_html = _top_3_performers_html(performers) if performers else _top_performers_html(match, time.time())
        last_play_html = ""
    else:
        # Season-long stat leaders, not per-game box score — confirmed
        # live ESPN's own scoreboard payload carries these regardless
        # of whether the game itself has started, so this shows well
        # before first pitch too, not just once the game goes live.
        leaders_html = _top_performers_html(match, time.time())
        last_play_html = ""

    # Default here, before the pregame/live/postgame split below — only
    # the NFL-live branch inside it ever sets this to a real bool (see
    # that branch's own comment); every other phase/sport leaves it
    # None, which _side_html's own has_ball param already treats as
    # "no icon" via the plain `is` comparisons at the call site below.
    nfl_possession_home = None

    if phase == "pregame":
        kickoff = next((r["kickoff"] for r in _RAIL if r["sport"] == sport), "TO FIRST PITCH")
        # Session report: "the jays game is delayed can you make it
        # show delayed instead of sitting at 0:00." The live-countdown
        # ticker (app.py's kioskFmtClock) floors at 0 once its target
        # passes and just holds there forever — nothing distinguishes
        # "first pitch is seconds away" from "the scheduled time has
        # genuinely come and gone and nothing's happening" (a rain
        # delay, most often). Once `now` has caught up to the real
        # scheduled start, there's nothing left to count down to at
        # all, so this switches to a plain status label instead of a
        # ticking number. MLB's own detail_state (see sports_client.
        # _normalize_mlb_game) already carries the real reason when
        # there is one ("Delayed Start: Rain") — used verbatim, same
        # preference for real official text over a generic label this
        # app already applies elsewhere (scoring-play descriptions,
        # pitcher line summaries); also correctly shows "Warmup" if
        # that's still running past the nominal start time, which used
        # to read as stuck at 0:00 too. NHL/NFL have no equivalent
        # detail field (sports_client's own comment on why), so those
        # just get a plain "DELAYED".
        if now >= game["start_time"]:
            delay_text = (game.get("detail_state") or "Delayed").upper() if sport == "mlb" else "DELAYED"
            countdown_html = f'<div class="jumbo-countdown jumbo-countdown-delayed">{html.escape(delay_text)}</div>'
        else:
            countdown_html = f'<div class="jumbo-countdown">{_fmt_countdown(game["start_time"], now)}</div>'
        center = (
            f'<div class="jumbo-center"><div class="jumbo-vs">VS</div>'
            f"{countdown_html}"
            f'<div class="jumbo-cd-label">{html.escape(kickoff)}</div></div>'
        )
        start_text = game["start_time"].strftime("%-I:%M %p")
        start_label = _PREGAME_SITUATION_LABEL.get(sport, "START")
        situation = f'<div class="jumbo-situ"><span class="jumbo-situ-hot">{html.escape(start_label)} {html.escape(start_text)}</span></div>'
        # _pregame_extra_html is MLB Stats API/NHL API game_id-keyed too
        # (see the "leaders_html"/"last_play_html" comment above on why
        # that's the wrong id space for a neutral game) — no ESPN-based
        # equivalent exists, so this is one genuine gap for a neutral
        # pregame board rather than something worth faking.
        if not neutral:
            situation += _pregame_extra_html(sport, game["game_id"])
        # Session request: "a completely new experience... like a
        # pregame show" — replaces the plain AI Preview blurb AND the
        # season-stat-leaders card (leaders_html, set above this phase
        # split) with a rotating set of real player/team storyline
        # cards. Neutral (semis/finals) games keep the original blurb —
        # pregame_storylines' own material-gathering is built entirely
        # around one of OUR 3 tracked teams (espn_extras.fetch_
        # transactions/fetch_team_news/fetch_league_leaders all take a
        # specific team id), not a "two teams we have no stake in"
        # shape the way _blurb_html_neutral already handles.
        if neutral:
            blurb_html = _blurb_html_neutral(sport, game, postgame=False)
        else:
            blurb_html = ""
            leaders_html = _storyline_cards_html(sport, game, league["label"].title(), match, time.time())
        # Session request: "can we use money line to get approximate
        # win odds" — ESPN's own live win-probability model is always
        # None pregame (_win_probability_html falls back to the
        # moneyline itself once it sees that), so this now shows
        # something before first pitch instead of nothing.
        wp_html = _win_probability_html(sport, match, away, home)
        dim_away = dim_home = False
    else:
        if neutral:
            away_score = int(game["away"]["score"]) if game["away"].get("score") not in (None, "") else None
            home_score = int(game["home"]["score"]) if game["home"].get("score") not in (None, "") else None
        else:
            away_score = game["opp_score"] if game["is_home"] else game["team_score"]
            home_score = game["team_score"] if game["is_home"] else game["opp_score"]

        # Session report: "the big score takes forever to update" —
        # game["team_score"]/["opp_score"] come from the schedule
        # endpoint, only refreshed every 5 minutes. The live-detail
        # endpoints (fetch_mlb_live_detail/fetch_nhl_live_detail) poll
        # every LIVE_DETAIL_CACHE_TTL_SECONDS (sports_client.py — 5s,
        # matching the app's own rerun cadence) for the inning/clock
        # situation below and carry the real live score too — this call
        # is the same cached one _mlb_situation_html/_nhl_situation_html
        # make right after, so it's not an extra request, just used here
        # first. No equivalent live-detail endpoint exists for the
        # Saints (see sports_client.py's own comment on why) — NFL just
        # keeps the schedule-level score, a 5-minute-stale worst case
        # rather than the sub-5s one MLB/NHL get. Skipped for a neutral
        # game too — same "wrong id space" reason as
        # _mlb_situation_html/_nhl_situation_html below (confirmed live:
        # this silently called the real NHL API with an ESPN event id
        # before this guard existed) — the schedule-level score from
        # `game` above is neutral games' own worst case, same as NFL's
        # always is.
        if phase == "live" and sport in ("mlb", "nhl") and not neutral:
            live_detail = (
                sports_client.fetch_mlb_live_detail(game["game_id"])
                if sport == "mlb"
                else sports_client.fetch_nhl_live_detail(game["game_id"])
            )
            if live_detail and live_detail.get("away_score") is not None and live_detail.get("home_score") is not None:
                away_score, home_score = live_detail["away_score"], live_detail["home_score"]

        # Session request: "are there animations for when the j score
        # or the j's win" — the original static mockup had a full-
        # screen confetti blast on every score, dropped when this page
        # was first built (see sports_alerts.py's module docstring) as
        # too fragile against Streamlit's rerun model. This is the
        # Streamlit-safe version of that same idea: compare this game's
        # score to what was last rendered (stored in session_state,
        # keyed by game_id so two different games can't cross-
        # contaminate each other's "did it just change" read), and flash
        # the digit box for one rerun when it moves. A brighter gold
        # flash when OUR side's score is the one that moved, a dimmer
        # neutral one for the opponent's — reusing _sides()' own
        # "is_us" tag rather than re-deriving which digitbox is ours.
        score_key = f"jumbotron_last_score_{game['game_id']}"
        prev_scores = st.session_state.get(score_key)
        away_flash = home_flash = ""
        if prev_scores is not None and phase == "live":
            prev_away, prev_home = prev_scores
            if away_score is not None and away_score != prev_away:
                away_flash = " jumbo-digitbox-flash-us" if away["is_us"] else " jumbo-digitbox-flash-opp"
            if home_score is not None and home_score != prev_home:
                home_flash = " jumbo-digitbox-flash-us" if home["is_us"] else " jumbo-digitbox-flash-opp"
        st.session_state[score_key] = (away_score, home_score)

        final_badge = '<div class="jumbo-final-badge">FINAL</div>' if phase == "postgame" else ""
        center = (
            f'<div class="jumbo-center"><div class="jumbo-score">'
            f'<span class="jumbo-digitbox{away_flash}">{_digits_html(away_score)}</span>'
            f'<span class="jumbo-dash">—</span>'
            f'<span class="jumbo-digitbox{home_flash}">{_digits_html(home_score)}</span>'
            f"</div>{final_badge}</div>"
        )
        if phase == "live":
            if neutral and sport in ("mlb", "nhl"):
                situation = _neutral_situation_html(game.get("status_text"))
            elif sport == "mlb":
                situation = _mlb_situation_html(game["game_id"])
            elif sport == "nhl":
                situation = _nhl_situation_html(game["game_id"])
            else:
                # Computed here too (not only inside _nfl_situation_html
                # itself) so _side_html's own possession icon in the
                # matchup header below can use the same read — session
                # request: "make it more obvious who has the ball... a
                # little ball icon next to their name."
                nfl_data = _nfl_situation(game["game_id"])
                nfl_possession_home = _nfl_possession_home(nfl_data["situation"], nfl_data["competitors"])
                situation = _nfl_situation_html(game)
        else:
            situation = ""
        blurb_html = ""
        if phase == "postgame":
            blurb_html = (
                _blurb_html_neutral(sport, game, postgame=True)
                if neutral
                else _blurb_html(sport, game, league["label"].title(), postgame=True, status=status)
            )
        wp_html = _win_probability_html(sport, match, away, home) if phase == "live" else ""
        # Only a finished game has a settled winner to dim the loser
        # against — during a live game the trailing side is still very
        # much in it.
        if phase == "postgame" and away_score is not None and home_score is not None:
            dim_away, dim_home = away_score < home_score, home_score < away_score
        else:
            dim_away = dim_home = False

    # One-time win celebration — session-guarded per game_id so it
    # plays exactly once, the moment a win is first observed, rather
    # than replaying every rerun for the whole ~15min postgame hold.
    # No "our side" to celebrate for in a neutral game — see
    # _sides_neutral's own docstring — so this stays "" unconditionally
    # rather than picking one side by convention.
    win_burst = ""
    if not neutral and phase == "postgame" and away_score is not None and home_score is not None:
        our_score = away_score if away["is_us"] else home_score
        their_score = home_score if away["is_us"] else away_score
        win_key = f"jumbotron_win_shown_{game['game_id']}"
        if our_score > their_score and not st.session_state.get(win_key):
            win_burst = " jumbo-win-burst"
            st.session_state[win_key] = True

    state_label = {
        "live": '<span class="jumbo-live">● LIVE</span>',
        "pregame": "UPCOMING",
        "postgame": "FINAL",
    }[phase]
    live_class = " jumbo-board-live" if phase == "live" else ""
    # Session request: "in the original prototype there was a cool dark
    # gradient behind the big score section with both team's colors."
    # Each side's own real color (_side_color — our fixed color, or the
    # opponent's real ESPN one) washes in from its own edge at a low
    # enough alpha to stay a mood-lighting effect, not a bright fill —
    # fading to nothing by the middle so the score digits themselves
    # sit on the plain dark panel, not on top of a color transition.
    # Applied to the whole board body (not just .jumbo-matchup) so it
    # reads as ambient arena lighting behind the whole panel rather than
    # a hard-edged color band that stops dead above the win-probability
    # bar — the score still sits right at the top of it either way.
    away_rgb, home_rgb = _side_color(sport, match, away), _side_color(sport, match, home)
    # Session request: "how can we improve the experience watching the
    # game... feel good and seamless and like its all orchestrated in a
    # sophisticated manner." The live pulse used to glow a fixed generic
    # red (--live) regardless of which team was actually playing — this
    # ties it to OUR team's own real accent color instead (the same
    # _TEAM_COLOR_RGB the board gradient/win-probability bar already
    # use for "our" side), so the whole board's own identity feels
    # specific to whichever sport/team is actually up, not a stock
    # "something's live" indicator. A plain CSS variable rather than a
    # new class per sport — theme.py's .jumbo-board-live reads it with
    # a fallback to the old red, so a sport this ever runs for without
    # setting it still looks exactly as it did before. No fixed "our
    # team" color exists for a neutral game — the home side's own real
    # ESPN color (already computed above) stands in for it instead.
    live_glow = home_rgb if neutral else _TEAM_COLOR_RGB.get(sport)
    board_style = f' style="--live-glow-rgb:{live_glow[0]},{live_glow[1]},{live_glow[2]}"' if live_glow else ""

    board_gradient = (
        "background:linear-gradient(90deg,"
        f"rgba({away_rgb[0]},{away_rgb[1]},{away_rgb[2]},0.22) 0%,"
        f"rgba({away_rgb[0]},{away_rgb[1]},{away_rgb[2]},0) 35%,"
        f"rgba({home_rgb[0]},{home_rgb[1]},{home_rgb[2]},0) 65%,"
        f"rgba({home_rgb[0]},{home_rgb[1]},{home_rgb[2]},0.22) 100%)"
    )

    return (
        f'<div class="jumbo-panel jumbo-board{live_class}{win_burst}"{board_style}>'
        f'<div class="jumbo-ph"><span>{html.escape(league["label"])} · FEATURED</span>'
        f'<span class="jumbo-ph-right">{state_label}</span></div>'
        f'<div class="jumbo-board-body" style="{board_gradient}">'
        f'<div class="jumbo-matchup">'
        f'{_side_html(away, dim_away, has_ball=nfl_possession_home is False, accent_rgb=away_rgb)}{center}'
        f'{_side_html(home, dim_home, has_ball=nfl_possession_home is True, accent_rgb=home_rgb)}</div>'
        f"{wp_html}{situation}{blurb_html}{leaders_html}{last_play_html}"
        f"</div></div>"
    )


_STANDINGS_ROTATE_SECONDS = 20


def _standings_rows_html(rows: list[dict]) -> str:
    """Division-standings rows with team logos — session request.
    Reuses the exact same row shape (see sports_client's own docstrings
    on fetch_jays/fetch_habs/fetch_all_mlb_standings/
    fetch_all_nhl_standings) the regular Sports page's _standings_table
    already renders, now with each row's own "logo" field (added
    specifically for this). "odds" (session request: "playoff odds for
    each of my teams") only ever carries a value on our own team's row
    (see fetch_all_mlb_standings/fetch_all_nhl_standings/
    _nfl_division_rows) — every other row's "" leaves the layout
    otherwise untouched."""
    if not rows:
        return ""
    return "".join(
        f'<div class="jumbo-standings-row{" jumbo-standings-row-team" if r["is_team"] else ""}">'
        f'<span class="jumbo-standings-rank">{r["rank"]}</span>'
        + (f'<img class="jumbo-standings-logo" src="{html.escape(r["logo"])}" />' if r.get("logo") else "")
        + f'<span class="jumbo-standings-team">{html.escape(r["team"])}</span>'
        f'<span class="jumbo-standings-record">{r["wins"]}-{r["losses"]}</span>'
        f'<span class="jumbo-standings-extra">{r["extra"]}</span>'
        + (
            f'<span class="jumbo-standings-odds">{html.escape((r.get("odds") or {})["display"])} PO</span>'
            if (r.get("odds") or {}).get("display")
            else ""
        )
        + "</div>"
        for r in rows
    )


def _rotating_standings_html(now_ts: float) -> str:
    """Bottom-left rotating division standings — session request: "make
    the standings rotate between all divisions and all leagues so i can
    get a full deep dive on sports while in game mode." Every MLB, NHL,
    and NFL division (sports_client.fetch_all_mlb_standings/
    fetch_all_nhl_standings/fetch_all_nfl_standings — the Jays'/Habs'/
    Saints' own team-specific fetches underneath _RAIL are unrelated
    and keep the "My Teams" rail unchanged), not just the three
    divisions those teams themselves sit in. NHL/NFL divisions still
    show even in the Habs'/Saints' own offseason — see
    fetch_all_nhl_standings's own docstring for why that's a deliberate
    choice rather than an oversight; the same reasoning applies to NFL.
    Session request adding the Saints: "NFL as a whole... league-wide
    NFL scores" — this is the standings half of that; the Around The
    Leagues panel (_around_html below) already covers the scores half,
    unchanged, since NFL was already in its own _AROUND_LEAGUES list."""
    candidates = (
        sports_client.fetch_all_mlb_standings()
        + sports_client.fetch_all_nhl_standings()
        + sports_client.fetch_all_nfl_standings()
    )
    if not candidates:
        return ""

    index = int(now_ts // _STANDINGS_ROTATE_SECONDS) % len(candidates)
    entry = candidates[index]
    division = html.escape(entry["division_name"])
    league = html.escape(entry["league"])
    page_label = f" · {index + 1}/{len(candidates)}" if len(candidates) > 1 else ""

    identity = f"{league}:{division}"
    changed = identity != st.session_state.get("jumbotron_standings_identity")
    st.session_state["jumbotron_standings_identity"] = identity
    fade_class = ""
    if changed:
        tick = st.session_state.get("jumbotron_standings_fade_tick", 0) + 1
        st.session_state["jumbotron_standings_fade_tick"] = tick
        fade_class = " jumbo-around-fade-a" if tick % 2 == 0 else " jumbo-around-fade-b"

    return (
        f'<div class="jumbo-ph"><span>{league} · {division}{page_label}</span></div>'
        f'<div class="jumbo-standings-body{fade_class}">'
        f'<div class="jumbo-standings">{_standings_rows_html(entry["rows"])}</div></div>'
    )


def _rail_hero_html(entry: dict, now: datetime) -> str:
    status = entry["fetch_status"]()
    if not status:
        return (
            f'<div class="jumbo-hero jumbo-hero-{entry["sport"]}">'
            f'<div class="jumbo-hero-head"><div class="jumbo-hero-name">{html.escape(entry["label"].title())}</div></div>'
            f"{_offseason_countdown_html(entry['sport'], now)}</div>"
        )
    game = status.get("game")
    record = _record_for(status)
    live = bool(game and game["state"] == "live")

    if not game:
        line = "No game on today's slate"
    elif game["state"] == "upcoming":
        versus = "vs" if game["is_home"] else "@"
        # Same "delayed instead of stuck at 0:00" fix as the featured
        # board's own countdown (_board_html) — this compact rail chip
        # has no room for MLB's full detail_state text, so it's kept to
        # a short, generic "DELAYED" here rather than duplicating the
        # board's own longer, real-reason label.
        if now >= game["start_time"]:
            cd_html = '<span class="jumbo-gl-cd jumbo-gl-cd-delayed">DELAYED</span>'
        else:
            cd_html = f'<span class="jumbo-gl-cd">{_fmt_countdown(game["start_time"], now)}</span>'
        line = f'{versus} <b>{html.escape(game["opponent"])}</b>{cd_html}'
    else:
        versus = "vs" if game["is_home"] else "@"
        score = f'<span class="jumbo-gl-score">{game["team_score"]}–{game["opp_score"]}</span>'
        if game["state"] == "final":
            won = (game["team_score"] or 0) > (game["opp_score"] or 0)
            mark = '<b class="jumbo-w">W</b>' if won else '<b class="jumbo-l">L</b>'
            line = f'{mark} {score} {versus} <b>{html.escape(game["opponent"])}</b> · FINAL'
        else:
            line = f'{score} {versus} <b>{html.escape(game["opponent"])}</b>'

    form = status.get("recent_form") or []
    form_html = ""
    if form:
        dots = "".join(
            f'<i class="jumbo-form-{"w" if r == "W" else "l"}"></i>' for r in form[-_FORM_GAMES_SHOWN:]
        )
        form_html = f'<div class="jumbo-form"><span class="jumbo-form-label">FORM</span>{dots}</div>'

    division = status.get("division_name") or ""
    # Session request: "can we pull playoff odds for each of my teams?"
    # Tucked onto the division line rather than its own row — this rail
    # card's vertical space is already tightly tuned (see the padding
    # trims earlier this session to fit all 3 teams). "" whenever ESPN
    # hasn't computed real odds yet (offseason/preseason — see
    # sports_client._espn_playoff_odds's own docstring), not a seed
    # number alone, which reads as noise without the percent next to it.
    odds = status.get("playoff_odds") or {}
    odds_html = f' <span class="jumbo-hero-odds">· {html.escape(odds["display"])} PO</span>' if odds.get("display") else ""
    return (
        f'<div class="jumbo-hero jumbo-hero-{entry["sport"]}{" jumbo-hero-live" if live else ""}">'
        f'<div class="jumbo-hero-head"><img src="{html.escape(status["team_logo"])}" />'
        f'<div class="jumbo-hero-id"><div class="jumbo-hero-name">{html.escape(entry["label"].title())}</div>'
        f'<div class="jumbo-hero-div">{html.escape(division)}{odds_html}</div></div>'
        f'<div class="jumbo-hero-rec"><div class="jumbo-hero-rec-v">{html.escape(record)}</div>'
        f'<div class="jumbo-hero-rec-l">RECORD</div></div></div>'
        f"{form_html}"
        f'<div class="jumbo-gameline">{line}</div></div>'
    )


def _ufc_rail_hero_html(now: datetime) -> str:
    """UFC's own "My Teams" rail card — session request: "can you add
    the UFC in the my teams section?" Genuinely different shape from
    the other three cards (no team/record/standings/division/recent-
    form — see ufc_client.py's own docstring on why UFC needed a
    separate data model entirely), so this doesn't reuse
    _rail_hero_html at all, just its outer .jumbo-hero slot/sizing for
    visual consistency. Deliberately NOT gated to the Saturday-5pm
    takeover window (ufc_client.takeover_state) — that window decides
    when UFC is worth taking over the WHOLE screen for; this card's
    job is just "what's the UFC status right now," visible the whole
    time some other sport's game owns the featured board, the same way
    the Habs/Jays/Saints cards already are for each other. Checks
    TODAY specifically first (a live card, or a same-day countdown to
    one), falling back to whatever's next on the calendar otherwise —
    same "OFFSEASON" vs "next game in N days" shape _offseason_
    countdown_html already uses for the other three."""
    event = ufc_client.fetch_event_for_date(now.date())
    live = False
    if event and event["state"] != "final":
        if event["state"] == "live":
            live = True
            bout = ufc_client.current_bout(event)
            if bout:
                line = (
                    f'LIVE · <b>{html.escape(bout["fighter_a"]["short_name"])}</b> vs '
                    f'<b>{html.escape(bout["fighter_b"]["short_name"])}</b>'
                )
            else:
                line = "LIVE"
        elif now >= event["start_time"]:
            line = "Card underway"
        else:
            line = f'Starts {_fmt_countdown(event["start_time"], now)}'
        detail = html.escape(event["name"])
    else:
        next_event = ufc_client.fetch_next_event(now)
        if not next_event:
            detail, line = "", '<span class="jumbo-offseason">No event scheduled</span>'
        else:
            date_text = next_event["start_time"].strftime("%b %-d")
            countdown_text = _days_until_text(next_event["start_time"], now)
            detail = html.escape(next_event["name"])
            line = f'<span class="jumbo-offseason">{date_text} · {countdown_text}</span>'

    return (
        f'<div class="jumbo-hero jumbo-hero-ufc{" jumbo-hero-live" if live else ""}">'
        f'<div class="jumbo-hero-head"><div class="jumbo-hero-id">'
        f'<div class="jumbo-hero-name">UFC</div>'
        f'<div class="jumbo-hero-div">{detail}</div></div></div>'
        f'<div class="jumbo-gameline">{line}</div></div>'
    )


def _mini_row_html(g: dict) -> str:
    """Session request: bring back the records + standout-performer
    line the regular rotation's Scores page already shows (see
    scores_client.game_leader) — both were already sitting unused on
    every game dict fetch_games returns, so this is purely additive,
    no new fetching. The leader line only exists once state != "pre"
    (see scores_client._normalize_game), same as ESPN's own leaders
    payload being empty pregame."""
    state = g["state"]
    if state == "pre":
        status_text = g["start_time"].strftime("%-I:%M") if g.get("start_time") else ""
    else:
        status_text = g.get("status_text") or ""
        # Session report: "the rain delay in the philly/baltimore game is
        # way too big" — ESPN's own shortDetail appends the inning to any
        # in-progress delay ("Rain Delay, Bottom 3rd"), and .jumbo-mini-
        # status has no nowrap/truncation, so that wraps to two lines and
        # blows up this one row's height next to every other single-line
        # "TOP 4TH"-style status. The inning is redundant here anyway (the
        # row already shows the score), so a delay just keeps its own
        # reason and drops everything ESPN tacked on after the comma.
        if "delay" in status_text.lower():
            status_text = status_text.split(",")[0].strip()
    row_class = "jumbo-mini" + (" jumbo-mini-live" if state == "in" else " jumbo-mini-final" if state == "post" else "")

    def team_row(side):
        score = "" if state == "pre" else (side.get("score") or "")
        logo = f'<img src="{html.escape(side["logo"])}" />' if side.get("logo") else ""
        record = f'<span class="jumbo-mini-record">{html.escape(side["record"])}</span>' if side.get("record") else ""
        return (
            f'<div class="jumbo-mini-team">{logo}'
            f'<span class="jumbo-mini-abbr">{html.escape(side.get("abbr") or "")}</span>{record}'
            f'<span class="jumbo-mini-score">{html.escape(str(score))}</span></div>'
        )

    leader = g.get("leader")
    leader_html = (
        f'<div class="jumbo-mini-leader">★ {html.escape(leader["name"])} '
        f'<span class="jumbo-mini-leader-stat">{html.escape(leader["stat_line"])}</span></div>'
        if leader
        else ""
    )

    return (
        f'<div class="{row_class}"><div class="jumbo-mini-teams">'
        f'{team_row(g["away"])}{team_row(g["home"])}{leader_html}</div>'
        f'<div class="jumbo-mini-status">{html.escape(status_text)}</div></div>'
    )


def _around_html(now_ts: float) -> str:
    """Body HTML for the Around The Leagues panel. Every game for every
    active league is kept — nothing capped or dropped — split into
    fixed-size pages so the fixed-height panel never overflows, with
    one page on screen at a time rotating on a wall-clock timer (same
    int(time.time() // interval) % n pattern as pages_household.py's
    NEARBY rotation and the team-news rail earlier this session). A
    league light on games (or the only league with any game today)
    just gets its one page shown continuously — nothing to rotate to
    changes that. The current page's own league + "X/Y" page count is
    the header (e.g. "MLB · 2/3"), so it's always clear there's more
    coming around rather than looking like a static, capped list.
    Page-building itself lives in _around_leagues_pages, shared with
    _between_play_overlay_html's own full-screen version of this same
    rotation."""
    pages = _around_leagues_pages(now_ts)
    if not pages:
        return ""

    index = int(now_ts // _AROUND_ROTATE_SECONDS) % len(pages)
    league_key, page_num, page_total, chunk = pages[index]
    label = league_key.upper() + (f" · {page_num + 1}/{page_total}" if page_total > 1 else "")
    rows_html = "".join(_mini_row_html(g) for g in chunk)

    # Session request: "add a cool animation to make it less robotic" —
    # fires a fade/slide-in ONLY on a genuine page change, not on every
    # 5s rerun (a static page re-rendering identical content every tick
    # would otherwise look like it's constantly restarting). Alternating
    # between two identically-defined keyframe classes on each real
    # change is the same restart-forcing trick news.py's toast bars use
    # (see its own STRETCH_END/SLIDE_END comment) — necessary because
    # Streamlit patches this same markdown block in place across
    # reruns, and re-applying the exact same class name is a no-op for
    # an already-finished CSS animation.
    identity = f"{league_key}:{page_num}"
    changed = identity != st.session_state.get("jumbotron_around_identity")
    st.session_state["jumbotron_around_identity"] = identity
    fade_class = ""
    if changed:
        tick = st.session_state.get("jumbotron_around_fade_tick", 0) + 1
        st.session_state["jumbotron_around_fade_tick"] = tick
        fade_class = " jumbo-around-fade-a" if tick % 2 == 0 else " jumbo-around-fade-b"

    return f'<div class="jumbo-around-page{fade_class}"><div class="jumbo-around-league">{label}</div>{rows_html}</div>'


@st.fragment
def _delay_stepper() -> None:
    """The live-data delay control, split into its own fragment —
    session report: tapping +/- felt unresponsive, "only updates when
    the page updates after the 5 second pause." A plain st.button here
    reruns the WHOLE jumbotron page (every sports/weather fetch, every
    HTML block) before the click's own effect shows up, and a tap that
    lands mid-rerun (the rest of the page is still catching up from the
    previous click) gets silently dropped — with the rest of the page
    this heavy, that's a real, repeated wait, not a one-off. A
    fragment's own rerun only re-executes this function, so a change
    here updates as fast as Streamlit can redraw one small widget,
    regardless of how long the surrounding page takes.

    Session follow-up: "make it so i can type my ideal stream delay
    please. the plus/minus boxes are finnicky" — this kiosk is a
    touchscreen with no physical keyboard (see the earlier "make it
    easier to click up/down on it" bump to these same controls' own
    tap-target size, still not enough on its own). Swapped the +/-
    button pair for a single st.number_input: tapping into a native
    number field brings up the OS's own on-screen numeric keypad,
    letting the exact value be typed directly instead of repeated small
    taps. `value=delay` only seeds this widget's very first render for
    its key — Streamlit tracks live edits in session_state from there,
    so this doesn't fight the user's own in-progress typing on this
    fragment's later, unrelated reruns (every 5s, riding the outer
    app's own st_autorefresh).

    No explicit st.rerun(scope="fragment") here, unlike the old button
    handlers — confirmed live that raises StreamlitAPIException
    ("can only be specified... during fragment reruns"). A button's
    own click doesn't rerun anything on its own, so the old code had to
    force one; a number_input's changed value already triggers
    Streamlit's own automatic fragment-scoped rerun by itself, so
    calling this a second time was both redundant and, apparently, not
    actually legal to do here."""
    delay = sports_client.get_live_delay_seconds()
    st.markdown('<div class="jumbo-delay-label">DELAY</div>', unsafe_allow_html=True)
    new_delay = st.number_input(
        "Delay", min_value=0, max_value=60, step=5, value=delay,
        key="jumbotron_delay_input", label_visibility="collapsed",
    )
    if new_delay != delay:
        sports_client.set_live_delay_seconds(int(new_delay))


def _ufc_bout_status_html(bout: dict) -> str:
    """The right-hand status chip for one row in the full-card list —
    plain "Upcoming" for a bout that hasn't started, "LIVE · Rn M:SS"
    while it's happening, or "FINAL · Rn M:SS" once it's over — the
    winner itself is shown by highlighting their name in the row via
    .jumbo-ufc-winner (see _ufc_card_row_html), not repeated here. No
    finishing method (KO/submission/decision) — see ufc_client's own
    docstring on why that's deliberately left out rather than guessed."""
    if bout["state"] == "live":
        return f'<span class="jumbo-ufc-live">LIVE · R{bout["round"]} {bout["clock"]}</span>'
    if bout["state"] == "final":
        return f'<span class="jumbo-ufc-final">FINAL · R{bout["round"]} {bout["clock"]}</span>'
    return '<span class="jumbo-ufc-upcoming">Upcoming</span>'


def _ufc_card_row_html(bout: dict) -> str:
    a, b = bout["fighter_a"], bout["fighter_b"]
    row_class = "jumbo-ufc-card-row"
    if bout["is_main_event"]:
        row_class += " jumbo-ufc-card-row-main"
    a_class = "jumbo-ufc-card-fighter jumbo-ufc-winner" if a["winner"] else "jumbo-ufc-card-fighter"
    b_class = "jumbo-ufc-card-fighter jumbo-ufc-winner" if b["winner"] else "jumbo-ufc-card-fighter"
    return (
        f'<div class="{row_class}">'
        f'<span class="jumbo-ufc-card-weight">{html.escape(bout["weight_class"])}</span>'
        f'<span class="{a_class}">{html.escape(a["short_name"])}</span>'
        f'<span class="jumbo-ufc-card-vs">vs</span>'
        f'<span class="{b_class}">{html.escape(b["short_name"])}</span>'
        f'<span class="jumbo-ufc-card-status">{_ufc_bout_status_html(bout)}</span>'
        f"</div>"
    )




def _ufc_stat_bar_html(
    bout_id: str, label: str, a_short: str, b_short: str, a_display: str, b_display: str, a_val: float, b_val: float
) -> str:
    """One live stat comparison row — same big-flanking-numbers-plus-
    bar shape as _win_probability_html's own bar (session request:
    "live fight stats... similar to how a baseball or hockey game would
    look"), adapted for a raw count/time comparison instead of a
    percentage: there's no real MMA win-probability model to substitute
    (ESPN's pickcenterAvailable is false on every bout — confirmed
    live, see ufc_client.fetch_bout_stats' own docstring), so the bar's
    width reflects each fighter's actual share of the two combined
    (landed strikes, landed takedowns, seconds of control) rather than
    a probability — real volume/control differential is genuinely what
    a fight gets read by, unlike a score-derived model.

    Session follow-up: "make everything more interactive." This kiosk
    has no real click/touch interaction to give it (session precedent
    elsewhere in this app), so "interactive" here means the board
    visibly reacting to what's actually happening — the two flanking
    numbers fade on a genuine change via the shared kiosk-jumbo-fade
    mechanism (data-fade-slot/data-fade-value, see app.py's own
    comment), the same "this just changed" cue the NFL board's own
    down-and-distance figure already uses, rather than silently
    updating to a new number every 5s rerun with no visual cue at all."""
    total = a_val + b_val
    a_pct = round(100 * a_val / total) if total else 50
    b_pct = 100 - a_pct
    return (
        f'<div class="jumbo-ufc-stat-row">'
        f'<div class="jumbo-ufc-stat-title">{html.escape(label)}</div>'
        f'<div class="jumbo-ufc-stat-line">'
        f'<div class="jumbo-ufc-stat-value jumbo-ufc-stat-a" data-fade-slot="ufc-stat-{bout_id}-{label}-a" '
        f'data-fade-value="{html.escape(a_display)}">{html.escape(a_display)}</div>'
        f'<div class="jumbo-ufc-stat-bar">'
        f'<div class="jumbo-ufc-stat-seg jumbo-ufc-stat-seg-a" style="width:{a_pct}%"></div>'
        f'<div class="jumbo-ufc-stat-seg jumbo-ufc-stat-seg-b" style="width:{b_pct}%"></div>'
        f"</div>"
        f'<div class="jumbo-ufc-stat-value jumbo-ufc-stat-b" data-fade-slot="ufc-stat-{bout_id}-{label}-b" '
        f'data-fade-value="{html.escape(b_display)}">{html.escape(b_display)}</div>'
        f"</div>"
        f'<div class="jumbo-ufc-stat-labels"><span>{html.escape(a_short)}</span><span>{html.escape(b_short)}</span></div>'
        f"</div>"
    )


def _ufc_stats_html(bout_id: str, fighter_a: dict, fighter_b: dict, stats: dict) -> str:
    """Significant Strikes / Takedowns / Control Time — the same trio a
    real UFC broadcast's own lower-third leans on — for whichever bout
    is the current hero. "" whenever fetch_bout_stats itself came back
    None (a real fetch failure, not just a scoreless bout — see that
    function's own docstring); a scoreless-but-fetched bout still shows
    real 0s/0:00, an honest "nothing's happened yet" rather than
    missing content."""
    if not stats:
        return ""
    a, b = stats["fighter_a"], stats["fighter_b"]

    def num(text: str | None) -> float:
        try:
            return float(text)
        except (TypeError, ValueError):
            return 0.0

    rows = [
        _ufc_stat_bar_html(
            bout_id,
            "SIG. STRIKES",
            fighter_a["short_name"],
            fighter_b["short_name"],
            f'{a.get("sig_strikes_landed") or 0}/{a.get("sig_strikes_attempted") or 0}',
            f'{b.get("sig_strikes_landed") or 0}/{b.get("sig_strikes_attempted") or 0}',
            num(a.get("sig_strikes_landed")),
            num(b.get("sig_strikes_landed")),
        ),
        _ufc_stat_bar_html(
            bout_id,
            "TAKEDOWNS",
            fighter_a["short_name"],
            fighter_b["short_name"],
            f'{a.get("takedowns_landed") or 0}/{a.get("takedowns_attempted") or 0}',
            f'{b.get("takedowns_landed") or 0}/{b.get("takedowns_attempted") or 0}',
            num(a.get("takedowns_landed")),
            num(b.get("takedowns_landed")),
        ),
        _ufc_stat_bar_html(
            bout_id,
            "CONTROL TIME",
            fighter_a["short_name"],
            fighter_b["short_name"],
            a.get("control_time") or "0:00",
            b.get("control_time") or "0:00",
            ufc_client.parse_control_time_seconds(a.get("control_time")),
            ufc_client.parse_control_time_seconds(b.get("control_time")),
        ),
    ]
    return f'<div class="jumbo-ufc-stats">{"".join(rows)}</div>'


def _ufc_kd_badge_html(stat_line: dict | None) -> str:
    """Small "KD x2" badge — knockdowns are rare and dramatic enough to
    call out on their own rather than bury in a bar row alongside
    steadier volume stats like strikes/takedowns. "" whenever there
    genuinely aren't any (the common case) or stats didn't load."""
    kd = (stat_line or {}).get("knockdowns")
    try:
        kd_n = int(float(kd))
    except (TypeError, ValueError):
        return ""
    return f'<span class="jumbo-ufc-kd-badge">KD ×{kd_n}</span>' if kd_n > 0 else ""


def _ufc_fighter_hero_html(fighter: dict, profile: dict | None, is_winner: bool, accent: str, kd_badge: str = "") -> str:
    """One side of the hero face-off — photo, flag, name, nickname,
    record, and career win-method breakdown. Session request: "add
    player photos... make it feel more professional... right now it
    just has the name." `accent` ("a"/"b") matches the same red/blue
    corner pair _ufc_stats_html's own bars already use for these two
    fighters (see that CSS's own comment on why it's a broadcast
    convention, not each fighter's real color — checked live, no such
    data exists anywhere in ESPN's own UFC feed),
    so a viewer can connect "this photo" to "this side of the stat
    bars below" at a glance. profile (ufc_client.fetch_fighter_profile)
    is None on a fetch failure — every optional line below just omits
    itself rather than showing a broken image or blank space, same
    "never show a placeholder for missing data" rule this app already
    follows everywhere else."""
    hl = " jumbo-ufc-winner" if is_winner else ""
    photo_html = ""
    if profile and profile.get("headshot"):
        flag_html = f'<img class="jumbo-ufc-flag" src="{html.escape(fighter["flag"])}" />' if fighter.get("flag") else ""
        photo_html = (
            f'<div class="jumbo-ufc-photo-wrap jumbo-ufc-photo-{accent}">'
            f'<img class="jumbo-ufc-photo" src="{html.escape(profile["headshot"])}" '
            f'onerror="this.parentElement.style.display=\'none\'" />{flag_html}'
            f"</div>"
        )
    nickname_html = (
        f'<div class="jumbo-ufc-hero-nickname">&ldquo;{html.escape(profile["nickname"])}&rdquo;</div>'
        if profile and profile.get("nickname")
        else ""
    )
    method_parts = []
    if profile:
        if profile.get("wins_ko"):
            method_parts.append(f'{profile["wins_ko"]} KO')
        if profile.get("wins_sub"):
            method_parts.append(f'{profile["wins_sub"]} SUB')
        if profile.get("wins_dec"):
            method_parts.append(f'{profile["wins_dec"]} DEC')
    method_html = f'<div class="jumbo-ufc-hero-method">{" &middot; ".join(method_parts)}</div>' if method_parts else ""
    record_html = f'<span class="jumbo-ufc-hero-record-text">{html.escape(fighter["record"])}</span>' if fighter.get("record") else ""
    # jumbo-ufc-hero-fighter-{accent} — session request: "incorporate
    # the exact same systems... make sure this format is accepted"
    # (the "Network Primetime" pick: a diagonal color panel behind
    # each side of a matchup, already built for the team-sport board's
    # own .jumbo-side). UFC already had a fixed red/blue corner accent
    # for the photo ring/stat bars (see this function's own docstring
    # on why fixed, not a real per-fighter color) — this just also
    # hands that same accent to the outer wrapper so theme.py can paint
    # the same diagonal panel behind the whole fighter card, not just
    # the photo ring.
    return (
        f'<div class="jumbo-ufc-hero-fighter jumbo-ufc-hero-fighter-{accent}{hl}">'
        f"{photo_html}"
        f'<div class="jumbo-ufc-hero-name">{html.escape(fighter["name"])}</div>'
        f"{nickname_html}"
        f'<div class="jumbo-ufc-hero-record">{record_html}{kd_badge}</div>'
        f"{method_html}"
        f"</div>"
    )


def _ufc_tale_of_tape_html(profile_a: dict | None, profile_b: dict | None, win_prob: dict | None = None) -> str:
    """Height/reach/age(/win%), one compact row — session request: "make
    it more obvious... more professional," the same "tale of the tape"
    comparison every real UFC broadcast leads with. One line, not three
    stacked rows: .jumbo-ufc-hero-panel is a fixed-height, non-
    scrolling kiosk panel already carrying two photos, two names,
    records, and the live stat bars below — a live bug fixed earlier
    this session (the NFL situation strip's own last-play line pushing
    its panel's actually-wanted content off-screen) is exactly the
    failure mode staying this compact avoids. "" whenever either
    profile fetch failed — a partial tale of the tape (one side blank)
    would read as a data error, not an honest gap.

    win_prob (ufc_client.fetch_win_probability) adds a 4th cell — real
    win probability, session request: "look at other sources... improve
    the viewing experience." Reuses this same row/cell markup rather
    than adding new panel height, since the hero panel is already at
    its real height budget (see this function's own comment above).
    Omitted (not blank) when no market's been matched yet, same "never
    show a placeholder for missing data" rule the rest of this cell
    already follows."""
    if not profile_a or not profile_b:
        return ""
    cells = []
    for label, key in (("HT", "height"), ("REACH", "reach"), ("AGE", "age")):
        va, vb = profile_a.get(key), profile_b.get(key)
        if va is None or vb is None:
            continue
        cells.append(
            f'<div class="jumbo-ufc-tot-cell">'
            f'<span class="jumbo-ufc-tot-a">{html.escape(str(va))}</span>'
            f'<span class="jumbo-ufc-tot-label">{label}</span>'
            f'<span class="jumbo-ufc-tot-b">{html.escape(str(vb))}</span>'
            f"</div>"
        )
    if win_prob and win_prob.get("prob_a") is not None and win_prob.get("prob_b") is not None:
        cells.append(
            f'<div class="jumbo-ufc-tot-cell">'
            f'<span class="jumbo-ufc-tot-a">{round(win_prob["prob_a"] * 100)}%</span>'
            f'<span class="jumbo-ufc-tot-label">WIN%</span>'
            f'<span class="jumbo-ufc-tot-b">{round(win_prob["prob_b"] * 100)}%</span>'
            f"</div>"
        )
    return f'<div class="jumbo-ufc-tot">{"".join(cells)}</div>' if cells else ""


def _ufc_board_html(ufc_state: dict, now: datetime) -> str:
    """Full board content for a UFC takeover — session request: "add
    UFC to the jumbotron," scoped by follow-up answers to exactly two
    modes: an upcoming-event countdown, and a live card that tracks
    itself bout-by-bout ("auto rotation between fights") — no postgame
    recap (see ufc_client.takeover_state's own docstring on why
    coverage just ends once the card goes final).

    Deliberately does not reuse _board_html/the My Teams rail/Around
    The Leagues panel below it — those are all built around one
    team's single evolving score (see this module's own render()
    docstring on why UFC needed a genuinely separate render path, not
    a config tweak to the existing one). Two panels: a hero card for
    whichever bout matters most right now, and the full ordered card
    underneath it — session follow-up: "I want the live fight to take
    up like the whole screen... both fighters and live fight stats" —
    the hero panel is now the dominant 3fr share of the grid (see
    .jumbo-ufc-grid's own comment), with the full card list shrunk to a
    reference strip underneath rather than splitting the screen evenly.

    The hero shows the MAIN EVENT specifically during "countdown"
    (the actual draw worth building anticipation for — ufc_client.
    current_bout would otherwise return the earliest, least
    interesting prelim, since nothing's happened yet to track), and
    ufc_client.current_bout's own live-tracking pick once the card is
    underway."""
    event = ufc_state["event"]
    phase = ufc_state["phase"]
    bouts = event["bouts"]
    hero = bouts[-1] if phase == "countdown" else ufc_client.current_bout(event)
    a, b = hero["fighter_a"], hero["fighter_b"]

    # Only once the hero bout has actually started — a countdown/
    # not-yet-fought hero has nothing real to compare yet (see
    # fetch_bout_stats' own docstring on why an all-zero fetch is still
    # "real," just not worth a whole panel before first punch).
    stats = None
    if phase != "countdown" and hero["state"] in ("live", "final"):
        try:
            stats = ufc_client.fetch_bout_stats(event["event_id"], hero["bout_id"], a["id"], b["id"])
        except Exception:
            stats = None

    if phase == "countdown":
        phase_html = f'<div class="jumbo-ufc-phase">STARTS IN {_fmt_countdown(event["start_time"], now)}</div>'
    elif hero["state"] == "live":
        # Recent-action ticker — session follow-up: "how else can we
        # improve the viewing experience... I genuinely want to enjoy
        # watching this." Temporarily takes over this same phase-line
        # slot (no new panel space needed — this hero panel is already
        # at its real height budget, see _ufc_tale_of_tape_html's own
        # docstring on the live overflow bug that stays deliberately
        # avoided) for a few seconds right after a real stat delta
        # lands, then reverts to the plain round/clock line. Built from
        # ufc_client.recent_event's own attributed stat-delta detection,
        # not ESPN's unattributed play-by-play log — see that module's
        # own comment for why. Held in session_state (not just "was the
        # most recent recent_event() call non-None") since a genuine
        # delta is only ever detected on the ONE rerun it actually
        # lands — every rerun straight after would otherwise see zero
        # further delta and revert instantly, showing it for well under
        # one 5s autorefresh tick.
        recent = ufc_client.recent_event(hero["bout_id"], a, b, stats)
        hold_key = f"jumbotron_ufc_recent_{hero['bout_id']}"
        if recent:
            st.session_state[hold_key] = {**recent, "at": time.time()}
        held = st.session_state.get(hold_key)
        if held and time.time() - held["at"] < _UFC_RECENT_EVENT_HOLD_SECONDS:
            tone_class = f" jumbo-ufc-phase-recent-{held['accent']}"
            phase_html = f'<div class="jumbo-ufc-phase jumbo-ufc-phase-live{tone_class}">{html.escape(held["text"])}</div>'
        else:
            phase_html = f'<div class="jumbo-ufc-phase jumbo-ufc-phase-live">LIVE · ROUND {hero["round"]} · {hero["clock"]}</div>'
    else:
        phase_html = '<div class="jumbo-ufc-phase">CARD UNDERWAY</div>'

    a_kd_badge = _ufc_kd_badge_html(stats["fighter_a"] if stats else None)
    b_kd_badge = _ufc_kd_badge_html(stats["fighter_b"] if stats else None)
    a_hl = hero["state"] == "final" and a["winner"]
    b_hl = hero["state"] == "final" and b["winner"]

    # Bio data (photo/nickname/height/reach/age/career method split) —
    # own long-cached fetch (ufc_client.PROFILE_CACHE_TTL_SECONDS, 6h),
    # separate from the live per-round stats above. Only for the hero
    # bout's own two fighters, not the whole 13-bout card below — see
    # this module's own comment on why that scope was chosen.
    try:
        profile_a = ufc_client.fetch_fighter_profile(a["id"])
    except Exception:
        profile_a = None
    try:
        profile_b = ufc_client.fetch_fighter_profile(b["id"])
    except Exception:
        profile_b = None

    # Real win probability — session request: "look at other sources...
    # improve the viewing experience" -> approved "real win probability."
    # Own fetch (Polymarket, not ESPN), same delay treatment as the
    # live stats above (see ufc_client.fetch_win_probability's own
    # docstring on why a swinging line is as much of a spoiler as a
    # live stat number).
    try:
        win_prob = ufc_client.fetch_win_probability(a["name"], b["name"], hero["bout_id"])
    except Exception:
        win_prob = None

    hero_html = (
        f'<div class="jumbo-ufc-hero">'
        f"{_ufc_fighter_hero_html(a, profile_a, a_hl, 'a', a_kd_badge)}"
        f'<div class="jumbo-ufc-hero-mid">'
        f'<div class="jumbo-ufc-hero-weight">{html.escape(hero["weight_class"])}</div>'
        f'<div class="jumbo-ufc-hero-vs">VS</div>'
        f"</div>"
        f"{_ufc_fighter_hero_html(b, profile_b, b_hl, 'b', b_kd_badge)}"
        f"</div>"
        f"{_ufc_tale_of_tape_html(profile_a, profile_b, win_prob)}"
    )

    stats_html = _ufc_stats_html(hero["bout_id"], a, b, stats)

    # Paginated the same way _around_html above handles a slate that
    # doesn't fit — see _UFC_CARD_PAGE_SIZE's own comment on why the
    # now-much-shorter card strip needs this for a real full-size card.
    pages = [bouts[i : i + _UFC_CARD_PAGE_SIZE] for i in range(0, len(bouts), _UFC_CARD_PAGE_SIZE)]
    page_total = len(pages) or 1
    page_index = int(time.time() // _UFC_CARD_ROTATE_SECONDS) % page_total
    page_bouts = pages[page_index] if pages else []
    card_label = "Full Card" + (f" · {page_index + 1}/{page_total}" if page_total > 1 else "")
    card_rows = "".join(_ufc_card_row_html(bout) for bout in page_bouts)

    # Venue — session request: "look at other sources... improve the
    # viewing experience" -> approved "venue line." Free from the same
    # scoreboard payload ufc_client._normalize_event already reads (no
    # extra fetch) — rendered into the existing .jumbo-ph-right slot
    # (same header row, right-aligned) rather than a new line, so it
    # costs zero extra height in this already-tight fixed panel (see
    # _ufc_tale_of_tape_html's own comment on that budget). "" (nothing
    # rendered) when ESPN hasn't published a venue for this card yet —
    # confirmed live this can be genuinely absent well before an event.
    venue_html = f'<span class="jumbo-ph-right">{html.escape(event["venue"])}</span>' if event.get("venue") else ""

    return (
        f'<div class="jumbo-grid jumbo-ufc-grid">'
        f'<div class="jumbo-panel jumbo-ufc-hero-panel">'
        f'<div class="jumbo-ph"><span>{html.escape(event["name"])}</span>{venue_html}</div>'
        f"{phase_html}{hero_html}{stats_html}"
        f"</div>"
        f'<div class="jumbo-panel jumbo-ufc-card-panel">'
        f'<div class="jumbo-ph"><span>{html.escape(card_label)}</span></div>'
        f'<div class="jumbo-ufc-card-body">{card_rows}</div>'
        f"</div>"
        f"</div>"
    )


def _render_ufc(now: datetime, ufc_state: dict, weather: dict | None) -> None:
    """The whole UFC takeover render — shares only the outer marquee
    header (clock/date/weather) with the team-scoreboard render()
    below for visual consistency; everything under it is
    _ufc_board_html's own two-panel layout instead of the rail/board/
    Around The Leagues grid a team takeover uses."""
    clock = now.strftime("%-I:%M")
    meridiem = now.strftime("%p")
    dateline = now.strftime("%A, %B %-d").upper()
    weather_chip = ""
    if weather and weather.get("temp_c") is not None:
        weather_chip = (
            f'<div class="jumbo-wx"><span class="jumbo-wx-temp">{weather["temp_c"]:.0f}°</span>'
            f'<span class="jumbo-wx-loc">CORBEIL</span></div>'
        )
    st.markdown(
        f'<div class="jumbo">'
        f'<div class="jumbo-marquee">'
        f'<div class="jumbo-brand">FANCAVE<span>JUMBOTRON</span></div>'
        f'<div class="jumbo-clock">{clock}<em>{meridiem}</em></div>'
        f'<div class="jumbo-dateline">{dateline}</div>'
        f'<div class="jumbo-spacer"></div>{weather_chip}</div>'
        f"{_ufc_board_html(ufc_state, now)}"
        f"</div>",
        unsafe_allow_html=True,
    )


def render(now: datetime, state: dict, weather: dict | None, ufc_state: dict | None = None) -> None:
    """`state` is sports_alerts.takeover_state()'s own return value —
    passed in rather than re-derived here so app.py's routing decision
    and this page's content can never disagree about which game owns
    the screen. `ufc_state` (ufc_client.takeover_state's own return
    value) takes over entirely when set — app.py's own routing already
    resolved the "Habs playing" exception before this is ever passed
    in, so its mere presence here means UFC has already won the
    screen; see _render_ufc."""
    if ufc_state is not None:
        _render_ufc(now, ufc_state, weather)
        return
    clock = now.strftime("%-I:%M")
    meridiem = now.strftime("%p")
    dateline = now.strftime("%A, %B %-d").upper()
    weather_chip = ""
    if weather and weather.get("temp_c") is not None:
        weather_chip = (
            f'<div class="jumbo-wx"><span class="jumbo-wx-temp">{weather["temp_c"]:.0f}°</span>'
            f'<span class="jumbo-wx-loc">CORBEIL</span></div>'
        )

    # Session request (after attending a real Jays game): "put the
    # batting order in the my teams section, but only when the game is
    # live... go over the ufc, the saints, the blue jays, and the
    # canadiens... only show it when the blue jays have top priority
    # overall of the teams that are playing." `state` is sports_alerts.
    # takeover_state()'s own result — COUNTDOWN_PRIORITY/
    # _takeover_priority (that module's own priority list) already
    # decided which team "has top priority" by the time it got here
    # (live beats pregame/postgame, then team priority breaks ties
    # within a phase), so this only needs to check which league
    # actually won: MLB, and specifically "live" — pregame/postgame
    # don't replace the rail, only an actual live game does.
    #
    # Session follow-up, with a real photo of the actual Rogers Centre
    # board as the reference: "make it just the team that's up to bat...
    # highlight who's actually up to bat right now and add the team
    # logos at top." One live-detail fetch (the same one _mlb_situation_
    # html/_current_matchup_html already poll — 5s TTL, no extra request)
    # gives both "which side is up" (inning_state) and "who's actually
    # at the plate" (batter, matched against the lineup by name in
    # _batting_order_rail_html) in one call.
    #
    # Second follow-up: "source ops the same way its sourced in the head
    # to head matchup so it updates after plays in the batting order
    # too." fetch_mlb_lineup_live_ops swaps each entry's boxscore-
    # sourced OPS for the same per-player /people read the Current
    # Matchup card's own batter stat uses (its own 20s cache, not the
    # usual 5s — see that function's own comment on why 9 players is a
    # genuinely different cost than that card's one or two).
    batting_entries = None
    if (
        state.get("phase") == "live"
        and state.get("game")
        and state["league"]["sport"] == "mlb"
        and not state["league"].get("neutral")
    ):
        game_id = state["game"]["game_id"]
        full_order = sports_client.fetch_mlb_batting_order(game_id)
        live_detail = sports_client.fetch_mlb_live_detail(game_id) if full_order else None
        inning_state = live_detail.get("inning_state") if live_detail else None
        batting_side = ("home" if inning_state in ("Bottom", "Middle") else "away") if inning_state else None
        if full_order and batting_side:
            batting_entries = sports_client.fetch_mlb_lineup_live_ops(full_order[batting_side])
            batting_entries = sports_client.fetch_mlb_lineup_game_line(game_id, batting_entries)
            current_batter = live_detail.get("batter")

    if batting_entries:
        away, home = _sides(state["status"], state["game"], state["league"]["label"])
        batting_team = home if batting_side == "home" else away
        batting_match = _espn_match_for(state["league"]["sport"], state["game"])
        batting_rgb = _side_color(state["league"]["sport"], batting_match, batting_team)
        rail_label = "Batting Order"
        rail = _batting_order_rail_html(batting_entries, batting_team, current_batter, accent_rgb=batting_rgb)
    else:
        rail_label = "My Teams"
        rail = "".join(_rail_hero_html(entry, now) for entry in _RAIL) + _ufc_rail_hero_html(now)
    around = _around_html(time.time())
    around_block = (
        f'<div class="jumbo-panel jumbo-around"><div class="jumbo-ph"><span>Around The Leagues</span></div>'
        f'<div class="jumbo-around-body">{around}</div></div>'
        if around
        else ""
    )
    # Session request: division standings moved out of each hero card
    # (where both used to sit permanently stacked) into their own
    # rotating panel at the bottom of this same column — see
    # _rotating_standings_html's own docstring.
    standings = _rotating_standings_html(time.time())
    standings_block = f'<div class="jumbo-panel jumbo-standings-panel">{standings}</div>' if standings else ""

    # Full-screen out-of-town scoreboard during a natural break in the
    # featured game (see _between_play_overlay_html's own docstring).
    between_play_overlay = _between_play_overlay_html(state, now)

    # Full-screen play-result announcement (see _play_result_overlay_html's
    # own docstring) — MLB-live only, same gating _current_matchup_html
    # already uses; NHL has no per-play "event" classification to key off.
    play_result_overlay = ""
    if (
        state.get("phase") == "live"
        and state.get("game")
        and state["league"]["sport"] == "mlb"
        and not state["league"].get("neutral")
    ):
        play_result_overlay = _play_result_overlay_html(
            state["game"]["game_id"], sports_client.fetch_mlb_last_play(state["game"]["game_id"])
        )

    st.markdown(
        f'<div class="jumbo">'
        f'<div class="jumbo-marquee">'
        f'<div class="jumbo-brand">FANCAVE<span>JUMBOTRON</span></div>'
        f'<div class="jumbo-clock">{clock}<em>{meridiem}</em></div>'
        f'<div class="jumbo-dateline">{dateline}</div>'
        f'<div class="jumbo-spacer"></div>{weather_chip}</div>'
        f'<div class="jumbo-grid">'
        f'<div class="jumbo-rail-col">'
        f'<div class="jumbo-panel jumbo-rail"><div class="jumbo-ph"><span>{rail_label}</span></div>'
        f'<div class="jumbo-rail-body">{rail}</div></div>'
        f"{standings_block}"
        f"</div>"
        f"{_board_html(state, now)}"
        f"{around_block}"
        f"</div>{play_result_overlay}{between_play_overlay}</div>",
        unsafe_allow_html=True,
    )

    # Bottom-left control cluster — session request: "an end session
    # button... that closes out the game session," later "can you make
    # [the live-data delay] a setting i can adjust throughout the game."
    # Real Streamlit widgets (this app's first — everything else here is
    # passive display), grouped in one st.container(key=...) so theme.py
    # can lay them out as a single fixed-position row via that key's own
    # CSS class rather than the old single-button div[data-testid=
    # "stButton"] rule (which only worked while this was the app's only
    # button at all).
    if state.get("game"):
        with st.container(key="jumbotron_controls"):
            if st.button("✕ End Session", key="jumbotron_end_session_btn"):
                # Setting the dismissal flag alone wouldn't take effect
                # until the next 5s autorefresh — st.rerun() makes the
                # takeover actually drop the instant this is clicked.
                st.session_state["jumbotron_dismissed_game_id"] = state["game"]["game_id"]
                st.rerun()

            _delay_stepper()
