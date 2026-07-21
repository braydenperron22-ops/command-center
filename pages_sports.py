"""Sports page: Blue Jays (MLB) + Canadiens (NHL) — current/most recent
game plus full division standings (see sports_client.py). Each team's
whole section is hidden while its own league is out of season, so this
page can show just one team, or fall back to a quiet placeholder when
both leagues happen to be between seasons (their offseasons briefly
overlap in February) — no manual upkeep needed as real seasons start
and end.

While a game is actually live, that team's tile takes over as a full
comprehensive scoreboard (session request: "during a game the sports
page turns into a full comprehensive scoreboard") — a big score with
both team logos, then situational detail underneath (count/outs/
baserunners for MLB, period clock for NHL) from sports_client's own
fetch_mlb_live_detail/fetch_nhl_live_detail. Standings are still shown
below that, just no longer competing for space with the compact score
line the rest of the time.

Team News section: sports_alerts.team_news_headlines() surfaces Jays/
Habs headlines as a fleeting ~30s toast (see that module), the same
way news.get_new_alerts() surfaces market headlines as a toast — but
market headlines also get a persistent, browsable home on the News
page, and team news had no equivalent until now. Same seen-headline/
24h-window pattern as pages_news.py's own feed, kept in its own
session-state key so it's independent of the toast's separate seen-
tracking (a Jays trade story can appear in both places).
"""

import hashlib
import html
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

import sports_alerts
import sports_client
from config import TIMEZONE

TEAM_NEWS_WINDOW_SECONDS = 24 * 60 * 60
# Confirmed live: this page is already dense (standings + wild card +
# form strip above it), and this kiosk doesn't scroll — even 2 compact
# rows ran off the bottom of the viewport behind the ticker bar. One
# headline at a time, rotating, is the same fix pages_household.py's
# own NEARBY section already uses for exactly this problem (see
# _render_local_news there) — the toast still surfaces every headline
# the moment it's new either way; this is just "what did I miss."
TEAM_NEWS_ROTATION_SECONDS = 10

# How close to first pitch/puck drop before the "starting soon" badge
# shows up — 2 hours is a reasonable "worth knowing about" window
# without flagging every game the moment it's merely today.
STARTING_SOON_MINUTES = 120


def _format_countdown(total_minutes: float) -> str:
    total = max(0, int(total_minutes))
    hours, minutes = divmod(total, 60)
    return f"{hours}h {minutes}m" if hours > 0 else f"{minutes} min"


def _starting_soon_html(game: dict, kickoff_label: str, now: datetime) -> str:
    """A "First pitch in 45 min"/"Puck drop in 1h 30m" badge once an
    upcoming game is within STARTING_SOON_MINUTES — "" otherwise (not
    yet close, already started, or no game at all). Deliberately a
    plain neutral badge, not an animated/pulsing one — a static,
    confident cue reads clearly without competing for attention the
    way a pulsing element would (same reasoning tile-significant
    already uses)."""
    if game["state"] != "upcoming":
        return ""
    remaining_minutes = (game["start_time"] - now).total_seconds() / 60
    if not (0 <= remaining_minutes <= STARTING_SOON_MINUTES):
        return ""
    return f'<div class="badge badge-neutral">{kickoff_label} in {_format_countdown(remaining_minutes)}</div>'


def _game_html(status: dict, kickoff_label: str, now: datetime) -> str:
    game = status["game"]
    if game is None:
        return '<div class="tile-prev">No game scheduled right now.</div>'
    opponent = html.escape(game["opponent"])
    opponent_word = "vs" if game["is_home"] else "@"
    opponent_logo = f'<img class="sports-opponent-logo" src="{game["opponent_logo"]}" />'
    starting_soon_html = _starting_soon_html(game, kickoff_label, now)
    if game["state"] == "upcoming":
        start = game["start_time"]
        time_text = start.strftime("%I:%M %p").lstrip("0")
        value = f"{start.strftime('%a %b')} {start.day}, {time_text}"
        value_class, result = "", f"{opponent_word} {opponent}"
    else:
        value = f"{game['team_score']}-{game['opp_score']}"
        if game["state"] == "live":
            value_class, result = "", f"LIVE {opponent_word} {opponent}"
        else:
            won = game["team_score"] > game["opp_score"]
            value_class = "market-up" if won else "market-down"
            result = f"{'W' if won else 'L'} {opponent_word} {opponent}"
    # Built as one flat line, no embedded newlines/indentation — a
    # multi-line f-string here reads to the markdown parser as an
    # indented code block once it's nested inside render()'s own
    # multi-line template below (confirmed live: adding the third line
    # for starting_soon_html was what tipped an already-borderline
    # 2-line version over into this — same class of bug already
    # documented in pages_weather.py/pages_today.py/pages_scores.py for
    # exactly this reason).
    return (
        f'<div class="tile-value {value_class}">{value}</div>'
        f'<div class="tile-prev">{opponent_logo}{result}</div>'
        f"{starting_soon_html}"
    )


def _wildcard_html(status: dict) -> str:
    """Division rank alone reads as "hopeless" for a team buried in a
    tough division even when it's genuinely alive for a Wild Card spot
    (see sports_client._fetch_mlb_wildcard / _fetch_nhl_wildcard).
    Omitted entirely whenever "wildcard" is missing/None — both leagues'
    fetchers already return None themselves once a team holds a real
    division spot, so there's nothing left to gate on here."""
    wildcard = status.get("wildcard")
    # Both value and rank are pulled from the same API payload as two
    # independent fields (see sports_client._fetch_mlb_wildcard/
    # _fetch_nhl_wildcard) — a response with one present but not the
    # other is possible, and used to render the literal text "rank
    # None" on the kiosk since only "value" was ever null-checked.
    if not wildcard or wildcard.get("value") is None or wildcard.get("rank") is None:
        return ""
    return f'<div class="tile-prev">Wild Card: {wildcard["value"]} {wildcard["unit"]} · rank {wildcard["rank"]}</div>'


def _standings_table(status: dict) -> str:
    # Flattened to one line per row, same reasoning as _game_html above.
    rows = "".join(
        f'<div class="sports-standings-row{" sports-standings-row-team" if r["is_team"] else ""}">'
        f'<span class="sports-standings-rank">{r["rank"]}</span>'
        f'<span class="sports-standings-team">{html.escape(r["team"])}</span>'
        f'<span class="sports-standings-record">{r["wins"]}-{r["losses"]}</span>'
        f'<span class="sports-standings-extra">{r["extra"]}</span>'
        f"</div>"
        for r in status["standings"]
    )
    return f'<div class="sports-standings">{rows}</div>' if rows else ""


def _form_strip_html(status: dict) -> str:
    """Last 10 completed games' outcomes as a compact W/L dot row (see
    sports_client._recent_form) — "" if there isn't any form yet (a
    season just started, or the fetch itself is between seasons)."""
    form = status.get("recent_form")
    if not form:
        return ""
    dots = "".join(f'<span class="form-dot form-dot-{"win" if r == "W" else "loss"}">{r}</span>' for r in form)
    return f'<div class="form-strip"><span class="form-strip-label">Last {len(form)}</span>{dots}</div>'


def _compact_tile_html(label: str, status: dict | None, kickoff_label: str, now: datetime) -> str:
    if status is None:
        return (
            f'<div class="tile"><div class="tile-label">{label}</div>'
            f'<div class="tile-prev">Out of season.</div></div>'
        )
    return (
        f'<div class="tile">'
        f'<div class="sports-team-header">'
        f'<img class="sports-team-logo" src="{status["team_logo"]}" />'
        f'<div class="tile-label">{label} · {status["division_name"].upper()}</div>'
        f"</div>"
        f"{_game_html(status, kickoff_label, now)}"
        f"{_form_strip_html(status)}"
        f"{_wildcard_html(status)}"
        f"{_standings_table(status)}"
        f"</div>"
    )


def _live_score_hero_html(status: dict, game: dict) -> str:
    """Big score, both team logos either side — session feedback: lead
    with this instead of the small inning/period line score table that
    used to sit here, matching the same "readable from across the room"
    priority the rest of this kiosk already gives its headline numbers."""
    team_score = game["team_score"] if game["team_score"] is not None else 0
    opp_score = game["opp_score"] if game["opp_score"] is not None else 0
    return (
        f'<div class="live-score-hero">'
        f'<img src="{status["team_logo"]}" />'
        f'<div class="live-score-hero-value">{team_score}<span class="live-score-hero-sep">-</span>{opp_score}</div>'
        f'<img src="{game["opponent_logo"]}" />'
        f"</div>"
    )


def _mlb_situation_html(detail: dict) -> str:
    outs, balls, strikes = detail.get("outs"), detail.get("balls"), detail.get("strikes")
    inning_state, current = detail.get("inning_state") or "", detail.get("current_inning")
    inning_text = f"{inning_state} {current}".strip()
    bases = detail.get("bases") or {}
    diamond = (
        '<span class="base-diamond">'
        f'<span class="base-second{" base-on" if bases.get("second") else ""}"></span>'
        f'<span class="base-third{" base-on" if bases.get("third") else ""}"></span>'
        f'<span class="base-first{" base-on" if bases.get("first") else ""}"></span>'
        "</span>"
    )
    parts = [diamond]
    if inning_text:
        parts.insert(0, f"<span><strong>{html.escape(inning_text)}</strong></span>")
    if outs is not None:
        parts.append(f'<span>{outs} out{"s" if outs != 1 else ""}</span>')
    if balls is not None and strikes is not None:
        parts.append(f"<span>{balls}-{strikes} count</span>")
    if detail.get("batter"):
        parts.append(f'<span>At bat: <strong>{html.escape(detail["batter"])}</strong></span>')
    if detail.get("pitcher"):
        parts.append(f'<span>Pitching: <strong>{html.escape(detail["pitcher"])}</strong></span>')
    return f'<div class="game-situation">{"".join(parts)}</div>'


def _nhl_situation_html(detail: dict) -> str:
    period_label, clock = detail.get("period_label"), detail.get("clock")
    parts = []
    if detail.get("in_intermission"):
        text = f"Intermission — end of {period_label}" if period_label else "Intermission"
        parts.append(f"<span><strong>{html.escape(text)}</strong></span>")
    else:
        if period_label:
            parts.append(f"<span><strong>{html.escape(period_label)} period</strong></span>")
        if clock:
            parts.append(f"<span>{html.escape(clock)} remaining</span>")
    return f'<div class="game-situation">{"".join(parts)}</div>' if parts else ""


def _situation_html(sport: str, detail: dict) -> str:
    return _mlb_situation_html(detail) if sport == "mlb" else _nhl_situation_html(detail)


def _render_live_tile(label: str, status: dict, sport: str) -> None:
    game = status["game"]
    detail_fetcher = sports_client.fetch_mlb_live_detail if sport == "mlb" else sports_client.fetch_nhl_live_detail
    detail = detail_fetcher(game["game_id"])
    opponent = html.escape(game["opponent"])
    opponent_word = "vs" if game["is_home"] else "@"
    # The score itself comes from the compact game dict either way, so
    # the hero renders even on a live-detail fetch failure — only the
    # situation panel underneath it (count/period-clock etc.) goes
    # missing rather than the whole tile falling back to something
    # smaller.
    situation_html = _situation_html(sport, detail) if detail is not None else ""

    st.markdown(
        f'<div class="tile">'
        f'<div class="live-scoreboard-header">'
        f'<div class="sports-team-header">'
        f'<img class="sports-team-logo" src="{status["team_logo"]}" />'
        f'<div class="tile-label">{label} · {opponent_word} {opponent}</div>'
        f"</div>"
        f'<div class="live-scoreboard-badge">LIVE</div>'
        f"</div>"
        f"{_live_score_hero_html(status, game)}"
        f"{situation_html}"
        f"{_form_strip_html(status)}"
        f"{_wildcard_html(status)}"
        f"{_standings_table(status)}"
        f"</div>",
        unsafe_allow_html=True,
    )


def _team_news_relative_time(seconds_ago: float) -> str:
    minutes = int(seconds_ago / 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    return f"{hours}h ago"


def _render_team_news() -> None:
    """Persistent, browsable Jays/Habs news feed — see module docstring.
    One headline at a time, rotating on a wall-clock timer (same
    int(time.time() // interval) % n pattern as pages_household.py's
    own NEARBY section) rather than a full list, to fit this already-
    dense page's fixed, no-scroll viewport. Renders nothing at all (not
    even an empty-state tile) when there's genuinely no recent team
    news, so a quiet news day doesn't cost this page a tile just to say
    so."""
    seen_at = st.session_state.setdefault("sports_news_feed_seen_at", {})
    now_ts = time.time()

    for item in sports_alerts.team_news_headlines():
        h = hashlib.sha1(item["headline"].encode()).hexdigest()
        if h not in seen_at:
            seen_at[h] = {
                "headline": item["headline"],
                "first_seen": now_ts,
                # The RSS item's own publish time, when the feed carries
                # one — used for the "X ago" display below instead of
                # first_seen, same reasoning as pages_household.py's own
                # NEARBY row (a story Google surfaced today but that was
                # actually published yesterday should say "yesterday,"
                # not "just now").
                "published": item["published"].timestamp() if item["published"] else None,
                "team_label": item["team_label"],
            }

    for h in [h for h, e in seen_at.items() if now_ts - e["first_seen"] > TEAM_NEWS_WINDOW_SECONDS]:
        del seen_at[h]

    entries = sorted(seen_at.values(), key=lambda e: e["published"] or e["first_seen"], reverse=True)
    if not entries:
        return

    index = int(now_ts // TEAM_NEWS_ROTATION_SECONDS) % len(entries)
    entry = entries[index]
    age_seconds = now_ts - (entry["published"] or entry["first_seen"])
    row = f"""<div class="news-feed-row compact">
        <div class="news-feed-headline">{html.escape(entry['headline'])}</div>
        <div class="news-feed-meta">{entry['team_label'].title()} · {_team_news_relative_time(age_seconds)}</div>
    </div>"""
    st.markdown(
        f'<div class="tile"><div class="tile-label">TEAM NEWS · {index + 1}/{len(entries)}</div>'
        f'<div class="news-feed-list">{row}</div></div>',
        unsafe_allow_html=True,
    )


def render() -> None:
    st.markdown('<div class="page-title page-title-sports">Sports</div>', unsafe_allow_html=True)

    jays = sports_client.fetch_jays()
    habs = sports_client.fetch_habs()

    if not jays and not habs:
        st.markdown(
            '<div class="tile"><div class="tile-prev">Both MLB and NHL are between seasons right now.</div></div>',
            unsafe_allow_html=True,
        )
        # Team news (trades, roster moves) keeps happening in the
        # offseason even with no games to show — doesn't need either
        # league to be active the way the rest of this page does.
        _render_team_news()
        return

    now = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
    entries = [
        {"label": "BLUE JAYS", "status": jays, "kickoff_label": "First pitch", "sport": "mlb"},
        {"label": "CANADIENS", "status": habs, "kickoff_label": "Puck drop", "sport": "nhl"},
    ]
    live = [e for e in entries if e["status"] and e["status"]["game"] and e["status"]["game"]["state"] == "live"]

    if not live:
        # Neither team is live — the original 2-column compact layout.
        # An out-of-season team keeps its own quiet placeholder slot
        # instead of the grid reflowing to a single stretched column.
        for col, entry in zip(st.columns(2), entries):
            with col:
                st.markdown(
                    _compact_tile_html(entry["label"], entry["status"], entry["kickoff_label"], now),
                    unsafe_allow_html=True,
                )
        _render_team_news()
        return

    # A live game takes over as a full-width comprehensive scoreboard —
    # standings/wildcard alone aren't what matters most while a game is
    # actually being played. Any other team renders underneath as its
    # own full-width compact tile (clearly secondary beneath the live
    # spotlight, rather than splitting a now-pointless 2-column grid).
    # Team news is skipped here (unlike the two branches above) — a live
    # scoreboard plus standings already fills this kiosk's fixed, no-
    # scroll viewport, and a live game itself is the more urgent thing
    # to show than a news headline; toasts still surface breaking team
    # news regardless of which page is up.
    for entry in live:
        _render_live_tile(entry["label"], entry["status"], entry["sport"])
    for entry in entries:
        if entry in live:
            continue
        st.markdown(
            _compact_tile_html(entry["label"], entry["status"], entry["kickoff_label"], now),
            unsafe_allow_html=True,
        )
