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

import scores_client
import sports_alerts
import sports_client
from config import TIMEZONE

# Both teams always appear in the My Teams rail, Habs first — the same
# priority order the toast queue and countdown headlines use.
_RAIL = [
    {"sport": "nhl", "label": "CANADIENS", "fetch_status": sports_client.fetch_habs, "kickoff": "TO PUCK DROP"},
    {"sport": "mlb", "label": "BLUE JAYS", "fetch_status": sports_client.fetch_jays, "kickoff": "TO FIRST PITCH"},
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
# Confirmed live: 8 rows fit fine pregame (2 lines each), but once
# records + a leader line are showing on every row (live/final games)
# an 8th row clips against the panel's fixed height. 7 leaves real
# margin at the tallest (leader-line-on-every-row) case.
_AROUND_PAGE_SIZE = 7
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
    diamond = (
        '<svg class="jumbo-diamond" viewBox="0 0 34 34"><g transform="rotate(45 17 17)">'
        f'<rect x="21" y="9" width="8" height="8" class="{"on" if bases.get("first") else ""}"></rect>'
        f'<rect x="9" y="9" width="8" height="8" class="{"on" if bases.get("second") else ""}"></rect>'
        f'<rect x="9" y="21" width="8" height="8" class="{"on" if bases.get("third") else ""}"></rect>'
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
    balls, strikes, outs = detail.get("balls") or 0, detail.get("strikes") or 0, detail.get("outs") or 0
    prev_counts = st.session_state.get(f"jumbotron_mlb_counts_{game_id}", {})
    st.session_state[f"jumbotron_mlb_counts_{game_id}"] = {"b": balls, "s": strikes, "o": outs}
    count_pulse = " jumbo-situ-pulse" if balls > prev_counts.get("b", 0) or strikes > prev_counts.get("s", 0) else ""
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
    parts.append(f'<span class="jumbo-situ-count{count_pulse}"><span class="jumbo-dim">COUNT</span> {balls}-{strikes}</span>')
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


_TEAM_ESPN_NAME = {"mlb": sports_client.MLB_TEAM_NAME, "nhl": sports_client.NHL_TEAM_NAME}
_TEAM_COLOR = {"mlb": "#3E7CC9", "nhl": "#D8323F"}  # matches the rail hero's own --tc values


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
    fetch_nhl_venue's own docstrings)."""
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
    venue = sports_client.fetch_nhl_venue(game_id)
    return f'<div class="jumbo-pregame-venue">{html.escape(venue)}</div>' if venue else ""


def _win_probability_html(sport: str, match: dict | None, away: dict, home: dict) -> str:
    """Live win-probability bar — session request. Only ESPN's own
    payload carries this (the native MLB/NHL APIs the rest of the
    board runs on don't), and only once ESPN's model has enough of the
    game to compute one — "" both when match is None (no ESPN game
    found) and pregame (confirmed live: null before the game starts),
    same as the original static mockup's own st==='in' gate."""
    if not match:
        return ""
    home_pct = scores_client.win_probability(match)
    if home_pct is None:
        return ""
    home_pct = round(home_pct)
    away_pct = 100 - home_pct
    team_color = _TEAM_COLOR.get(sport, "#FFB300")
    away_color = team_color if away["is_us"] else "#525C6E"
    home_color = team_color if home["is_us"] else "#525C6E"
    # Session feedback: "find a better way to show the win odds since
    # its hard to see" — was an 11px-tall bar with 11px percentages
    # written below each end. The percentages themselves are now the
    # headline (big numbers flanking the bar, not small print under
    # it), and the bar itself is thick enough to read as a real
    # visual split rather than a thin stripe.
    return (
        '<div class="jumbo-wp"><div class="jumbo-wp-title">WIN PROBABILITY</div>'
        '<div class="jumbo-wp-row">'
        f'<div class="jumbo-wp-pct" style="color:{away_color}">{away_pct}%</div>'
        f'<div class="jumbo-wp-bar"><div class="jumbo-wp-seg" style="width:{away_pct}%;background:{away_color}"></div>'
        f'<div class="jumbo-wp-seg" style="width:{home_pct}%;background:{home_color}"></div></div>'
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


def _current_matchup_html(game_id: int) -> str:
    """Replaces the Top Performers panel with the two players actually
    involved in the live at-bat while a game is live — session request:
    "during the game can you make the top performers tab show current
    pitcher and batter and their stats use OPS for batter and ERA for
    pitchers." Photo-up-top, stat-below-name layout — session request:
    "add the pitcher and batter pics and put the stats below them like
    youd see on a jumbotron in the ballpark." MLB only (no batter/
    pitcher concept in hockey — NHL keeps the season-leaders rotation
    throughout). "" between innings, when the live feed has no one
    currently at the plate/mound to name (see sports_client.
    fetch_mlb_live_matchup's own docstring)."""
    matchup = sports_client.fetch_mlb_live_matchup(game_id)
    if not matchup:
        return ""
    batter, pitcher = matchup["batter"], matchup["pitcher"]

    # Session request: "add a ball and strike count below era and
    # pitches" — clarified to mean the whole outing's ball/strike split
    # (sports_client.fetch_mlb_live_matchup's own "balls"/"strikes"),
    # not the live at-bat's own count _mlb_situation_html's strip above
    # already shows — a different number, so a distinct "B-S" label
    # here rather than reusing "COUNT".
    balls, strikes = pitcher.get("balls"), pitcher.get("strikes")
    pitch_split = f"{balls}-{strikes}" if balls is not None and strikes is not None else None

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
    # — `stat_rows` is a list of rows, each a list of (value, label)
    # pairs, so a pitcher can get ERA/PITCHES on one row and B-S on its
    # own row underneath, while a batter's single-row OPS is unaffected.
    def col(tag: str, player: dict, stat_rows: list[list[tuple]]) -> str:
        photo = (
            f'<img class="jumbo-live-matchup-photo" src="{html.escape(player["photo"])}" onerror="this.style.display=\'none\'" />'
            if player.get("photo")
            else ""
        )
        rows_html = ""
        for stats in stat_rows:
            blocks = "".join(
                f'<div class="jumbo-live-matchup-stat-block">'
                f'<div class="jumbo-live-matchup-stat">{html.escape(str(value))}</div>'
                f'<div class="jumbo-live-matchup-stat-label">{html.escape(label)}</div>'
                f"</div>"
                for value, label in stats
                if value is not None
            )
            if blocks:
                rows_html += f'<div class="jumbo-live-matchup-stat-row">{blocks}</div>'
        if not rows_html:
            rows_html = '<div class="jumbo-live-matchup-stat-row"><div class="jumbo-live-matchup-stat-block"><div class="jumbo-live-matchup-stat">—</div></div></div>'
        return (
            f'<div class="jumbo-live-matchup-col">{photo}'
            f'<div class="jumbo-live-matchup-tag">{html.escape(tag)}</div>'
            f'<div class="jumbo-live-matchup-name">{html.escape(player["name"])}</div>'
            f"{rows_html}"
            f"</div>"
        )

    return (
        f'<div class="jumbo-leaders"><div class="jumbo-sl">Current Matchup</div>'
        f'<div class="jumbo-live-matchup">'
        f'{col("At Bat", batter, [[(batter.get("ops"), "OPS")]])}'
        f'<div class="jumbo-live-matchup-vs">VS</div>'
        f'{col("Pitching", pitcher, [[(pitcher.get("era"), "ERA"), (pitcher.get("pitches"), "PITCHES")], [(pitch_split, "B-S")]])}'
        f"</div></div>"
    )


_PITCHER_OVERLAY_HOLD_SECONDS = 8


def _pitcher_change_overlay_html(game_id: int, pitcher_id: int | None, team_label: str) -> str:
    """Full-screen "new pitcher" intro, fixed over the entire kiosk —
    session request: "can we create a full screen toast for when a new
    pitcher comes in that shows their full profile and season stats."

    Fires once per genuine pitching change — tracked as "last pitcher
    seen for this game_id"; a change is only real once a previous
    pitcher was already on record, so this stays silent on the game's
    very first live sighting (that's just whoever started, not a
    substitution) and fires again if the same pitcher somehow comes
    back later (rare, but happens in extras). Held for
    _PITCHER_OVERLAY_HOLD_SECONDS across however many 5s reruns that
    spans, via the exact shown_at/elapsed + animation-delay technique
    the bottom toast bars already use (see sports_alerts.
    render_alert_bar) — long enough to actually read a full stat line,
    not just glanced at like the jumbotron's own mode-switch transition
    curtain (2.4s, see app.py)."""
    if not pitcher_id:
        return ""
    last_key = f"jumbotron_last_pitcher_{game_id}"
    shown_key = f"jumbotron_pitcher_overlay_{game_id}"
    last_pitcher_id = st.session_state.get(last_key)
    now_ts = time.time()

    if pitcher_id != last_pitcher_id:
        if last_pitcher_id is not None:
            st.session_state[shown_key] = {"pitcher_id": pitcher_id, "shown_at": now_ts}
        st.session_state[last_key] = pitcher_id

    active = st.session_state.get(shown_key)
    if not active or active.get("pitcher_id") != pitcher_id:
        return ""
    elapsed = now_ts - active["shown_at"]
    if elapsed > _PITCHER_OVERLAY_HOLD_SECONDS:
        st.session_state[shown_key] = None
        return ""

    profile = sports_client.fetch_mlb_pitcher_profile(pitcher_id)
    if not profile:
        return ""

    photo = (
        f'<img class="jumbo-pitcher-overlay-photo" src="{html.escape(profile["photo"])}" onerror="this.style.display=\'none\'" />'
        if profile.get("photo")
        else ""
    )
    throws = {"R": "RHP", "L": "LHP"}.get(profile.get("throws") or "", "")
    bio_parts = [
        p
        for p in [
            f'#{profile["number"]}' if profile.get("number") else "",
            throws,
            profile.get("height") or "",
            f'{profile["weight"]} lbs' if profile.get("weight") else "",
            f'Age {profile["age"]}' if profile.get("age") else "",
        ]
        if p
    ]
    bio = " · ".join(bio_parts)

    def stat_block(value, label: str) -> str:
        if value is None:
            return ""
        return (
            f'<div class="jumbo-pitcher-overlay-stat">'
            f'<div class="jumbo-pitcher-overlay-stat-v">{html.escape(str(value))}</div>'
            f'<div class="jumbo-pitcher-overlay-stat-l">{html.escape(label)}</div></div>'
        )

    win_loss = f'{profile["wins"]}-{profile["losses"]}' if profile.get("wins") is not None and profile.get("losses") is not None else None
    stats = "".join(
        [
            stat_block(profile.get("era"), "ERA"),
            stat_block(win_loss, "W-L"),
            stat_block(profile.get("strikeouts"), "SO"),
            stat_block(profile.get("whip"), "WHIP"),
            stat_block(profile.get("innings_pitched"), "IP"),
        ]
    )

    delay = f"animation-delay: -{elapsed:.2f}s;"
    role_line = f'{profile["role"]} · ' if profile.get("role") else ""
    return (
        f'<div class="jumbo-pitcher-overlay" style="{delay}"><div class="jumbo-pitcher-overlay-inner">'
        f'<div class="jumbo-pitcher-overlay-label">Now Pitching for the {html.escape(team_label.title())}</div>'
        f"{photo}"
        f'<div class="jumbo-pitcher-overlay-name">{html.escape(profile["name"])}</div>'
        f'<div class="jumbo-pitcher-overlay-bio">{html.escape(role_line)}{html.escape(bio)}</div>'
        f'<div class="jumbo-pitcher-overlay-stats">{stats}</div>'
        f"</div></div>"
    )


def _fmt_break_clock(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def _mlb_between_innings_state(game_id: int, detail: dict, now_ts: float) -> tuple[bool, float]:
    """(is_between, elapsed_seconds since this specific break started).
    MLB publishes no official countdown for a half-inning break (it
    runs however long the broadcast's own commercial pod does, nothing
    in the API says when it ends), so this counts up from when the
    break was first observed rather than fabricating a countdown to an
    unknown resume time — see _between_play_overlay_html's own
    docstring. Keyed by inning+half (not just game_id) so the next
    break starts its own count at 0 rather than inheriting the last
    one's elapsed time."""
    inning_state = detail.get("inning_state")
    key = f"jumbotron_mlb_break_{game_id}"
    if inning_state not in ("Middle", "End"):
        st.session_state.pop(key, None)
        return False, 0.0
    marker = f"{inning_state}:{detail.get('current_inning')}"
    tracked = st.session_state.get(key)
    if not tracked or tracked.get("marker") != marker:
        tracked = {"marker": marker, "started_at": now_ts}
        st.session_state[key] = tracked
    return True, now_ts - tracked["started_at"]


def _between_play_overlay_html(state: dict, now: datetime) -> str:
    """Full-screen "out of town scoreboard" during a natural break in
    the featured game — session request: "between innings / periods
    can we go to a full screen out of town scoreboard. with a timer
    till the game resumes again." Qualifies on MLB half-inning breaks
    (inning_state Middle/End) and NHL intermissions (in_intermission).

    Unlike the fixed-duration new-pitcher overlay, this isn't a timed
    toast — it's re-evaluated fresh every rerun and stays up for
    exactly as long as the break condition itself stays true, gone the
    instant play resumes. NHL's own intermission clock carries a real
    countdown (intermission_seconds_remaining, the same number the
    broadcast's own countdown uses) — MLB has no equivalent, so that
    side counts up elapsed break time instead of guessing at a
    countdown (see _mlb_between_innings_state's own docstring).

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
        is_between, elapsed = _mlb_between_innings_state(game_id, detail, now_ts)
        if not is_between:
            return ""
        headline = f'{(detail.get("inning_state") or "").upper()} OF {detail.get("current_inning") or ""}'.strip()
        timer_span = f'<div class="jumbo-otc-timer">{html.escape(_fmt_break_clock(elapsed))}</div>'
        timer_label = "BREAK TIME ELAPSED"
    elif sport == "nhl":
        detail = sports_client.fetch_nhl_live_detail(game_id)
        if not detail or not detail.get("in_intermission"):
            return ""
        headline = "INTERMISSION"
        secs = detail.get("intermission_seconds_remaining")
        if secs is None:
            return ""
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


def _board_html(state: dict, now: datetime) -> str:
    league, status, game = state["league"], state["status"], state["game"]
    sport, phase = league["sport"], state["phase"]
    away, home = _sides(status, game, league["label"])
    match = _espn_match_for(sport, game)
    if phase == "live" and sport == "mlb":
        leaders_html = _current_matchup_html(game["game_id"])
    else:
        # Season-long stat leaders, not per-game box score — confirmed
        # live ESPN's own scoreboard payload carries these regardless
        # of whether the game itself has started, so this shows well
        # before first pitch too, not just once the game goes live.
        leaders_html = _top_performers_html(match, time.time())

    if phase == "pregame":
        kickoff = next((r["kickoff"] for r in _RAIL if r["sport"] == sport), "TO FIRST PITCH")
        center = (
            f'<div class="jumbo-center"><div class="jumbo-vs">VS</div>'
            f'<div class="jumbo-countdown">{_fmt_countdown(game["start_time"], now)}</div>'
            f'<div class="jumbo-cd-label">{html.escape(kickoff)}</div></div>'
        )
        start_text = game["start_time"].strftime("%-I:%M %p")
        situation = f'<div class="jumbo-situ"><span class="jumbo-situ-hot">FIRST PITCH {html.escape(start_text)}</span></div>' if sport == "mlb" else f'<div class="jumbo-situ"><span class="jumbo-situ-hot">PUCK DROP {html.escape(start_text)}</span></div>'
        situation += _pregame_extra_html(sport, game["game_id"])
        wp_html = ""
        dim_away = dim_home = False
    else:
        away_score = game["opp_score"] if game["is_home"] else game["team_score"]
        home_score = game["team_score"] if game["is_home"] else game["opp_score"]

        # Session report: "the big score takes forever to update" —
        # game["team_score"]/["opp_score"] come from the schedule
        # endpoint, only refreshed every 5 minutes. The live-detail
        # endpoints (fetch_mlb_live_detail/fetch_nhl_live_detail) poll
        # every 30s for the inning/clock situation below and carry the
        # real live score too — this call is the same cached one
        # _mlb_situation_html/_nhl_situation_html make right after, so
        # it's not an extra request, just used here first.
        if phase == "live":
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
            situation = _mlb_situation_html(game["game_id"]) if sport == "mlb" else _nhl_situation_html(game["game_id"])
        else:
            situation = ""
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

    return (
        f'<div class="jumbo-panel jumbo-board{live_class}{win_burst}">'
        f'<div class="jumbo-ph"><span>{html.escape(league["label"])} · FEATURED</span>'
        f'<span class="jumbo-ph-right">{state_label}</span></div>'
        f'<div class="jumbo-board-body">'
        f'<div class="jumbo-matchup">{_side_html(away, dim_away)}{center}{_side_html(home, dim_home)}</div>'
        f"{wp_html}{situation}{leaders_html}"
        f"</div></div>"
    )


_STANDINGS_ROTATE_SECONDS = 20


def _standings_rows_html(rows: list[dict]) -> str:
    """Division-standings rows with team logos — session request.
    Reuses the exact same row shape (see sports_client's own docstrings
    on fetch_jays/fetch_habs/fetch_all_mlb_standings/
    fetch_all_nhl_standings) the regular Sports page's _standings_table
    already renders, now with each row's own "logo" field (added
    specifically for this)."""
    if not rows:
        return ""
    return "".join(
        f'<div class="jumbo-standings-row{" jumbo-standings-row-team" if r["is_team"] else ""}">'
        f'<span class="jumbo-standings-rank">{r["rank"]}</span>'
        + (f'<img class="jumbo-standings-logo" src="{html.escape(r["logo"])}" />' if r.get("logo") else "")
        + f'<span class="jumbo-standings-team">{html.escape(r["team"])}</span>'
        f'<span class="jumbo-standings-record">{r["wins"]}-{r["losses"]}</span>'
        f'<span class="jumbo-standings-extra">{r["extra"]}</span></div>'
        for r in rows
    )


def _rotating_standings_html(now_ts: float) -> str:
    """Bottom-left rotating division standings — session request: "make
    the standings rotate between all divisions and all leagues so i can
    get a full deep dive on sports while in game mode." Every MLB and
    NHL division (sports_client.fetch_all_mlb_standings/
    fetch_all_nhl_standings — the Jays' and Habs' own team-specific
    fetches underneath _RAIL are unrelated and keep the "My Teams" rail
    unchanged), not just the two divisions the Jays/Habs themselves sit
    in. NHL divisions still show even in the Habs' own offseason — see
    fetch_all_nhl_standings's own docstring for why that's a deliberate
    choice rather than an oversight."""
    candidates = sports_client.fetch_all_mlb_standings() + sports_client.fetch_all_nhl_standings()
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
            f'<div class="jumbo-gameline jumbo-offseason">OFFSEASON</div></div>'
        )
    game = status.get("game")
    record = _record_for(status)
    live = bool(game and game["state"] == "live")

    if not game:
        line = "No game on today's slate"
    elif game["state"] == "upcoming":
        versus = "vs" if game["is_home"] else "@"
        line = (
            f'{versus} <b>{html.escape(game["opponent"])}</b>'
            f'<span class="jumbo-gl-cd">{_fmt_countdown(game["start_time"], now)}</span>'
        )
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

    live_chip = '<div class="jumbo-livechip">LIVE</div>' if live else ""
    division = status.get("division_name") or ""
    return (
        f'<div class="jumbo-hero jumbo-hero-{entry["sport"]}{" jumbo-hero-live" if live else ""}">'
        f"{live_chip}"
        f'<div class="jumbo-hero-head"><img src="{html.escape(status["team_logo"])}" />'
        f'<div class="jumbo-hero-id"><div class="jumbo-hero-name">{html.escape(entry["label"].title())}</div>'
        f'<div class="jumbo-hero-div">{html.escape(division)}</div></div>'
        f'<div class="jumbo-hero-rec"><div class="jumbo-hero-rec-v">{html.escape(record)}</div>'
        f'<div class="jumbo-hero-rec-l">RECORD</div></div></div>'
        f"{form_html}"
        f'<div class="jumbo-gameline">{line}</div></div>'
    )


def _mini_row_html(g: dict) -> str:
    """Session request: bring back the records + standout-performer
    line the regular rotation's Scores page already shows (see
    scores_client._game_leader) — both were already sitting unused on
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


def render(now: datetime, state: dict, weather: dict | None) -> None:
    """`state` is sports_alerts.takeover_state()'s own return value —
    passed in rather than re-derived here so app.py's routing decision
    and this page's content can never disagree about which game owns
    the screen."""
    clock = now.strftime("%-I:%M")
    meridiem = now.strftime("%p")
    dateline = now.strftime("%A, %B %-d").upper()
    weather_chip = ""
    if weather and weather.get("temp_c") is not None:
        weather_chip = (
            f'<div class="jumbo-wx"><span class="jumbo-wx-temp">{weather["temp_c"]:.0f}°</span>'
            f'<span class="jumbo-wx-loc">CORBEIL</span></div>'
        )

    rail = "".join(_rail_hero_html(entry, now) for entry in _RAIL)
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

    # Full-screen new-pitcher overlay — MLB only (see
    # _pitcher_change_overlay_html's own docstring), computed from the
    # same live matchup fetch_mlb_live_matchup the Current Matchup card
    # already pulls this rerun (no extra request).
    pitcher_overlay = ""
    if state["phase"] == "live" and state["league"]["sport"] == "mlb" and state["game"]:
        matchup = sports_client.fetch_mlb_live_matchup(state["game"]["game_id"])
        if matchup and matchup.get("pitcher"):
            pitcher_overlay = _pitcher_change_overlay_html(
                state["game"]["game_id"], matchup["pitcher"].get("id"), state["league"]["label"]
            )

    # Full-screen out-of-town scoreboard during a natural break in the
    # featured game (see _between_play_overlay_html's own docstring) —
    # lower z-index than the new-pitcher overlay above so the two never
    # visually fight if a pitching change happens to land right at a
    # half-inning break: the pitcher overlay's own 8s hold plays on top
    # first, then this (still active for the rest of the real break)
    # is what's left showing underneath once that hold ends.
    between_play_overlay = _between_play_overlay_html(state, now)

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
        f"</div>{between_play_overlay}{pitcher_overlay}</div>",
        unsafe_allow_html=True,
    )
