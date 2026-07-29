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
import scores_client
import sports_alerts
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
_AROUND_LEAGUES = ["mlb", "nhl", "nba", "nfl"]
# Was 7 (8 clipped) — session feedback: "the around the league card is
# a little crowded," right after theme.py's own distance-readability
# pass made every row noticeably bigger (bigger logos, bigger type,
# more row padding — see .jumbo-mini's own comment). Same rows, same
# panel height, just fewer of them fit comfortably now.
_AROUND_PAGE_SIZE = 6
_AROUND_ROTATE_SECONDS = 12
_FORM_GAMES_SHOWN = 8


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
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    # Session request: drop the leading hour digit under an hour ("43:55",
    # not "0:43:55") — mirrored in app.py's own kioskFmtClock, which is
    # what actually drives the display from the second frame on.
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


def _side_html(side: dict, dim: bool) -> str:
    classes = "jumbo-side" + (" jumbo-side-dim" if dim else "")
    return (
        f'<div class="{classes}">'
        f'<div class="jumbo-logobox"><img src="{html.escape(side["logo"])}" /></div>'
        f'<div class="jumbo-tname">{html.escape(side["name"])}</div>'
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

    parts = [f'<span class="jumbo-situ-hot">{html.escape(inning)}</span>'] if inning else []
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


_NFL_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


def _nfl_situation_html(match: dict | None) -> str:
    """Quarter + game clock, plus down & distance when ESPN's own
    "situation" field carries it — lighter than the MLB/NHL situation
    strips above (no dedicated live-detail endpoint built for the
    Saints, see sports_client.py's own comment above
    NFL_TEAM_SCHEDULE_URL for why), built from the same ESPN
    competition object _win_probability_html/_top_performers_html
    already fetch via _espn_match_for, so this costs nothing extra.
    Best-effort: down/distance field names/shapes haven't been
    confirmed against a real live game yet — this was built during the
    NFL offseason with no live game to check the actual payload
    against — so every field is read defensively rather than trusted,
    same "never crash on an unexpected shape" posture the rest of this
    module already uses for genuinely verified data."""
    if not match:
        return ""
    status = match.get("status") or {}
    period = status.get("period")
    clock = status.get("displayClock")
    parts = []
    if isinstance(period, int) and period > 0:
        label = f"{_NFL_ORDINALS.get(period, f'{period}th')} QUARTER" if period <= 4 else "OVERTIME"
        parts.append(f'<span class="jumbo-situ-hot">{html.escape(label)}</span>')
    if clock:
        parts.append(f'<span class="jumbo-clockbig">{html.escape(str(clock))}</span>')
    situation = match.get("situation") or {}
    down, distance = situation.get("down"), situation.get("distance")
    if isinstance(down, int) and isinstance(distance, int) and 1 <= down <= 4:
        down_text = f"{_NFL_ORDINALS.get(down, f'{down}th')} & {distance}"
        parts.append(f'<span class="jumbo-situ-count">{html.escape(down_text)}</span>')
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


# Session request: the batter's new Savant "OVERALL" percentile average
# (see savant_client.batter_overall_percentile) should use "the baseball
# savant type of formatting where a hundred, like the best of the best,
# is red and the worst, or a zero, is blue." A continuous gradient, not
# the fixed hot/cold pulse the rest of this card uses (that's a
# streak/deviation signal — "better/worse than usual right now" — this
# is a stable season-quality score, closer to Savant's own percentile
# bar chart than to a hot streak). Two-segment linear blend through
# --bone (this card's own plain-white stat color) at the midpoint, so a
# perfectly average player's number looks exactly like every other
# unstyled stat on this card, and only actually diverges toward red or
# blue the further it sits from average — same idea ColorBrewer's RdBu
# diverging scale uses, which is what Savant's own chart approximates.
_SAVANT_COLD_RGB = (61, 133, 217)
_SAVANT_MID_RGB = (244, 241, 232)  # --bone
_SAVANT_HOT_RGB = (200, 40, 40)


def _savant_gradient_color(pct: int) -> str:
    pct = max(0, min(100, pct))
    lo, hi, t = (_SAVANT_COLD_RGB, _SAVANT_MID_RGB, pct / 50) if pct <= 50 else (_SAVANT_MID_RGB, _SAVANT_HOT_RGB, (pct - 50) / 50)
    r, g, b = (round(lo[i] + (hi[i] - lo[i]) * t) for i in range(3))
    return f"rgb({r},{g},{b})"


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
    # heat, style) tuples, so a pitcher can get ERA/PITCHES on one row
    # and STRIKE% on its own row underneath, while a batter's single-row
    # OPS is unaffected. Later session request ("does espn show hot
    # streaks or anything? yes please") added the batter's own second
    # row: career at-bats vs this exact pitcher, already None'd out by
    # sports_client when there's no history vs this pitcher, so `stats`
    # filtering them out here is enough, no extra branch needed. Follow-
    # up request added `heat` ("hot"/"cold"/None from sports_client's
    # _vs_pitcher_heat) — None for pitches/strike%, which aren't judged
    # hot/cold at all. A second follow-up request extended heat to
    # season OPS/ERA too (sports_client's _batter_season_heat/
    # _pitcher_season_heat, a delta off the player's own career line
    # rather than a fixed threshold). `style` was added for a later
    # session request that replaced the batter's rolling last-15 OPS
    # with a Savant percentile average formatted "like an overall" —
    # continuous red/blue gradient rather than a fixed hot/cold class,
    # so it needs a real inline style rather than another `heat` value
    # (see _savant_gradient_color) — None for every other stat here.
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
                f'<div class="jumbo-live-matchup-stat{" jumbo-live-matchup-stat-" + heat if heat else ""}"'
                f'{f" style=\"color:{style}\"" if style else ""}>{html.escape(str(value))}</div>'
                f'<div class="jumbo-live-matchup-stat-label">{html.escape(label)}</div>'
                f"</div>"
                for value, label, heat, style in stats
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
        return (
            f'<div class="jumbo-live-matchup-col">{photo}'
            f'<div class="jumbo-live-matchup-tag">{html.escape(tag)}</div>'
            f'<div class="jumbo-live-matchup-name">{html.escape(player["name"])}</div>'
            f"{rows_html}{line_html}"
            f"</div>"
        )

    overall = batter.get("overall_percentile")
    overall_style = _savant_gradient_color(overall) if overall is not None else None
    batter_rows = [
        [(batter.get("ops"), "OPS", batter.get("season_ops_heat"), None)],
        [
            (overall, "OVERALL", None, overall_style),
            (batter.get("vs_pitcher"), "VS PITCHER", batter.get("vs_pitcher_heat"), None),
        ],
    ]
    pitcher_rows = [
        [
            (pitcher.get("era"), "ERA", pitcher.get("season_era_heat"), None),
            (pitcher.get("pitches"), "PITCHES", None, None),
        ],
        [(strike_pct, "STRIKE%", strike_pct_heat, None)],
    ]
    return (
        f'<div class="jumbo-leaders"><div class="jumbo-sl">Current Matchup</div>'
        f'<div class="jumbo-live-matchup">'
        f'{col("At Bat", batter, batter_rows)}'
        f'<div class="jumbo-live-matchup-vs">VS</div>'
        f'{col("Pitching", pitcher, pitcher_rows, pitcher.get("line"))}'
        f"</div></div>"
    )


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
    return (
        f'<div class="jumbo-lastplay">'
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


def _between_play_overlay_html(state: dict, now: datetime) -> str:
    """Full-screen "out of town scoreboard" during a natural break in
    the featured game — session request: "between innings / periods
    can we go to a full screen out of town scoreboard. with a timer
    till the game resumes again." Qualifies on MLB half-inning breaks
    (inning_state Middle/End) and NHL intermissions (in_intermission).
    Held back OVERLAY_DELAY_SECONDS from when the break actually
    started (see _overlay_delay_elapsed above) before actually taking
    over the screen.

    Unlike the fixed-duration new-pitcher overlay, this isn't a timed
    toast — it's re-evaluated fresh every rerun and stays up for
    exactly as long as the break condition itself stays true, gone the
    instant play resumes. Both sports get a real countdown, driven by
    the same live-countdown ticker the pregame/leave-headline countdowns
    already use: NHL's own intermission clock carries one directly
    (intermission_seconds_remaining, the same number the broadcast's
    own countdown uses); MLB's live feed doesn't hand one back, but the
    pitch-clock rule fixes every half-inning break at MLB_BREAK_SECONDS,
    so _mlb_between_innings_target counts down against that instead.

    Shows every game around the leagues (scores_client.fetch_games,
    same source the sidebar's own Around The Leagues panel reads —
    including the featured game itself, still sitting mid-list; not
    worth the extra matching logic to filter out one row), full-screen
    since there's real room and a real reason to look elsewhere for a
    minute. "" outside a break, or if there's nothing to show."""
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
    else:
        return ""

    rows = []
    for key in _AROUND_LEAGUES:
        try:
            games = scores_client.fetch_games(key)
        except Exception:
            continue
        if not games:
            continue
        rows.append(f'<div class="jumbo-otc-league">{html.escape(key.upper())}</div>')
        rows.extend(_mini_row_html(g) for g in games)
    if not rows:
        return ""

    return (
        '<div class="jumbo-otc-overlay"><div class="jumbo-otc-inner">'
        '<div class="jumbo-otc-title">Out Of Town Scoreboard</div>'
        f'<div class="jumbo-otc-sub">{html.escape(headline)}</div>'
        f'<div class="jumbo-otc-timer-block">{timer_span}<div class="jumbo-otc-timer-label">{html.escape(timer_label)}</div></div>'
        f'<div class="jumbo-otc-grid">{"".join(rows)}</div>'
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


def _blurb_html(sport: str, game: dict, team_label: str, postgame: bool) -> str:
    """"" whenever ESPN doesn't have this game or the AI call itself
    failed/hasn't landed yet — same "just omit it" rule every other
    optional jumbotron panel already follows, not a loading spinner or
    placeholder text."""
    our_name = _TEAM_FULL_NAME[sport]
    away_name = our_name if not game["is_home"] else game["opponent"]
    home_name = game["opponent"] if not game["is_home"] else our_name
    get_blurb = game_blurb.get_postgame_blurb if postgame else game_blurb.get_pregame_blurb
    text = get_blurb(sport, game["game_id"], team_label, away_name, home_name, game["opponent"])
    if not text:
        return ""
    label = "AI Recap" if postgame else "AI Preview"
    return f'<div class="jumbo-blurb"><div class="jumbo-sl">{html.escape(label)}</div><div class="jumbo-blurb-text">{html.escape(text)}</div></div>'


def _board_html(state: dict, now: datetime) -> str:
    league, status, game = state["league"], state["status"], state["game"]
    sport, phase = league["sport"], state["phase"]
    away, home = _sides(status, game, league["label"])
    match = _espn_match_for(sport, game)
    if phase == "live" and sport == "mlb":
        leaders_html = _current_matchup_html(game["game_id"])
        last_play_html = _last_play_html(game["game_id"], away, home)
    else:
        # Season-long stat leaders, not per-game box score — confirmed
        # live ESPN's own scoreboard payload carries these regardless
        # of whether the game itself has started, so this shows well
        # before first pitch too, not just once the game goes live.
        leaders_html = _top_performers_html(match, time.time())
        last_play_html = ""

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
        situation += _pregame_extra_html(sport, game["game_id"])
        blurb_html = _blurb_html(sport, game, league["label"].title(), postgame=False)
        # Session request: "can we use money line to get approximate
        # win odds" — ESPN's own live win-probability model is always
        # None pregame (_win_probability_html falls back to the
        # moneyline itself once it sees that), so this now shows
        # something before first pitch instead of nothing.
        wp_html = _win_probability_html(sport, match, away, home)
        dim_away = dim_home = False
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
        # rather than the sub-5s one MLB/NHL get.
        if phase == "live" and sport in ("mlb", "nhl"):
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
            if sport == "mlb":
                situation = _mlb_situation_html(game["game_id"])
            elif sport == "nhl":
                situation = _nhl_situation_html(game["game_id"])
            else:
                situation = _nfl_situation_html(match)
        else:
            situation = ""
        blurb_html = _blurb_html(sport, game, league["label"].title(), postgame=True) if phase == "postgame" else ""
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
    win_burst = ""
    if phase == "postgame" and away_score is not None and home_score is not None:
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
    board_gradient = (
        "background:linear-gradient(90deg,"
        f"rgba({away_rgb[0]},{away_rgb[1]},{away_rgb[2]},0.22) 0%,"
        f"rgba({away_rgb[0]},{away_rgb[1]},{away_rgb[2]},0) 35%,"
        f"rgba({home_rgb[0]},{home_rgb[1]},{home_rgb[2]},0) 65%,"
        f"rgba({home_rgb[0]},{home_rgb[1]},{home_rgb[2]},0.22) 100%)"
    )

    return (
        f'<div class="jumbo-panel jumbo-board{live_class}{win_burst}">'
        f'<div class="jumbo-ph"><span>{html.escape(league["label"])} · FEATURED</span>'
        f'<span class="jumbo-ph-right">{state_label}</span></div>'
        f'<div class="jumbo-board-body" style="{board_gradient}">'
        f'<div class="jumbo-matchup">{_side_html(away, dim_away)}{center}{_side_html(home, dim_home)}</div>'
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
    coming around rather than looking like a static, capped list."""
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
    a config tweak to the existing one). This is a much simpler two-
    panel layout: a hero card for whichever bout matters most right
    now, and the full ordered card underneath it.

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

    if phase == "countdown":
        phase_html = f'<div class="jumbo-ufc-phase">STARTS IN {_fmt_countdown(event["start_time"], now)}</div>'
    elif hero["state"] == "live":
        phase_html = f'<div class="jumbo-ufc-phase jumbo-ufc-phase-live">LIVE · ROUND {hero["round"]} · {hero["clock"]}</div>'
    else:
        phase_html = '<div class="jumbo-ufc-phase">CARD UNDERWAY</div>'

    a, b = hero["fighter_a"], hero["fighter_b"]
    a_rec = f'<div class="jumbo-ufc-hero-record">{html.escape(a["record"])}</div>' if a["record"] else ""
    b_rec = f'<div class="jumbo-ufc-hero-record">{html.escape(b["record"])}</div>' if b["record"] else ""
    a_hl = " jumbo-ufc-winner" if hero["state"] == "final" and a["winner"] else ""
    b_hl = " jumbo-ufc-winner" if hero["state"] == "final" and b["winner"] else ""

    hero_html = (
        f'<div class="jumbo-ufc-hero">'
        f'<div class="jumbo-ufc-hero-fighter{a_hl}"><div class="jumbo-ufc-hero-name">{html.escape(a["name"])}</div>{a_rec}</div>'
        f'<div class="jumbo-ufc-hero-mid">'
        f'<div class="jumbo-ufc-hero-weight">{html.escape(hero["weight_class"])}</div>'
        f'<div class="jumbo-ufc-hero-vs">VS</div>'
        f"</div>"
        f'<div class="jumbo-ufc-hero-fighter{b_hl}"><div class="jumbo-ufc-hero-name">{html.escape(b["name"])}</div>{b_rec}</div>'
        f"</div>"
    )

    card_rows = "".join(_ufc_card_row_html(bout) for bout in bouts)

    return (
        f'<div class="jumbo-grid jumbo-ufc-grid">'
        f'<div class="jumbo-panel jumbo-ufc-hero-panel">'
        f'<div class="jumbo-ph"><span>{html.escape(event["name"])}</span></div>'
        f"{phase_html}{hero_html}"
        f"</div>"
        f'<div class="jumbo-panel jumbo-ufc-card-panel">'
        f'<div class="jumbo-ph"><span>Full Card</span></div>'
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
    if state.get("phase") == "live" and state.get("game") and state["league"]["sport"] == "mlb":
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
        f'<div class="jumbo-panel jumbo-rail"><div class="jumbo-ph"><span>My Teams</span></div>'
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
