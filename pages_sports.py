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

A rotating Team News tile lived here briefly and was removed at the
user's own request — see sports_alerts.py's module docstring.
"""

import html
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

import game_blurb
import sports_client
from config import TIMEZONE

# How close to first pitch/puck drop before the "starting soon" badge
# shows up — 2 hours is a reasonable "worth knowing about" window
# without flagging every game the moment it's merely today.
STARTING_SOON_MINUTES = 120

# Session request: "where's the playoff odds on both pages and the ai
# blurb on the main page" — both features (originally jumbotron-only)
# now also live here. Only mlb/nhl — this page has never covered the
# Saints/NFL (a jumbotron-only, deliberately lighter integration; see
# sports_client.py's own comment on why).
_TEAM_FULL_NAME = {"mlb": sports_client.MLB_TEAM_NAME, "nhl": sports_client.NHL_TEAM_NAME}


def _odds_suffix_html(status: dict) -> str:
    odds = status.get("playoff_odds") or {}
    return f' <span class="sports-odds-badge">· {html.escape(odds["display"])} PO</span>' if odds.get("display") else ""


# Session request: "for the teams that aren't currently in season, can
# we just have like a little countdown on their team bar for when
# their first game is" — used by _compact_tile_html's out-of-season
# branch below in place of the plain "Out of season." text, once one
# of these actually finds a next game.
_NEXT_GAME_FETCHER = {"mlb": sports_client.fetch_mlb_next_game, "nhl": sports_client.fetch_nhl_next_game}
_NEXT_GAME_LEVEL_LABEL = {"preseason": "Preseason opener", "regular": "Season opener", "playoff": "Playoff opener"}


def _days_until_text(target: datetime, now: datetime) -> str:
    days = (target.date() - now.date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


def _offseason_countdown_html(sport: str, now: datetime) -> str:
    """"Out of season." once fetch_*_next_game() itself comes up empty
    too — otherwise "Preseason opener Aug 15 · in 20 days."""
    next_game = _NEXT_GAME_FETCHER[sport]()
    if not next_game:
        return "Out of season."
    level_label = _NEXT_GAME_LEVEL_LABEL.get(next_game["level"], "Next game")
    date_text = next_game["start_time"].strftime("%b %-d")
    countdown_text = _days_until_text(next_game["start_time"], now)
    return f"{html.escape(level_label)} {date_text} · {countdown_text}"


def _blurb_html(sport: str, game: dict, team_label: str) -> str:
    """Pre/postgame AI blurb (see game_blurb.py's own docstring for the
    one-shot-per-game caching and where the ESPN facts come from) — ""
    while the game is live (no blurb for that state — the live
    situation panel already covers it), once ESPN doesn't have this
    game, or before the AI call has landed."""
    if game["state"] not in ("upcoming", "final"):
        return ""
    postgame = game["state"] == "final"
    our_name = _TEAM_FULL_NAME[sport]
    away_name = our_name if not game["is_home"] else game["opponent"]
    home_name = game["opponent"] if not game["is_home"] else our_name
    get_blurb = game_blurb.get_postgame_blurb if postgame else game_blurb.get_pregame_blurb
    text = get_blurb(sport, game["game_id"], team_label, away_name, home_name, game["opponent"])
    if not text:
        return ""
    label = "AI Recap" if postgame else "AI Preview"
    return f'<div class="sports-blurb"><div class="sports-blurb-label">{html.escape(label)}</div><div class="sports-blurb-text">{html.escape(text)}</div></div>'


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
    already uses). The minutes value itself does still tick for real
    once a second though, via app.py's global live-countdown ticker —
    session request: "make that logic work for all the timer
    elements" — so it never sits stale for up to 5s between reruns."""
    if game["state"] != "upcoming":
        return ""
    remaining_minutes = (game["start_time"] - now).total_seconds() / 60
    if not (0 <= remaining_minutes <= STARTING_SOON_MINUTES):
        return ""
    target_ms = int(game["start_time"].replace(tzinfo=ZoneInfo(TIMEZONE)).timestamp() * 1000)
    return (
        f'<div class="badge badge-neutral"><span class="live-countdown" data-target-ms="{target_ms}" '
        f'data-format="words" data-template="{html.escape(kickoff_label)} in {{}}">'
        f"{kickoff_label} in {_format_countdown(remaining_minutes)}</span></div>"
    )


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
    # "odds" (session request: "playoff odds for each of my teams" —
    # "where's the playoff odds on both pages") only ever carries a
    # value on our own team's row (see sports_client's own comment on
    # fetch_all_mlb_standings/fetch_all_nhl_standings), so every other
    # row's "" leaves this otherwise untouched.
    rows = "".join(
        f'<div class="sports-standings-row{" sports-standings-row-team" if r["is_team"] else ""}">'
        f'<span class="sports-standings-rank">{r["rank"]}</span>'
        f'<span class="sports-standings-team">{html.escape(r["team"])}</span>'
        f'<span class="sports-standings-record">{r["wins"]}-{r["losses"]}</span>'
        f'<span class="sports-standings-extra">{r["extra"]}</span>'
        + (
            f'<span class="sports-standings-odds">{html.escape((r.get("odds") or {})["display"])} PO</span>'
            if (r.get("odds") or {}).get("display")
            else ""
        )
        + "</div>"
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


def _compact_tile_html(label: str, status: dict | None, kickoff_label: str, now: datetime, sport: str) -> str:
    if status is None:
        return (
            f'<div class="tile"><div class="tile-label">{label}</div>'
            f'<div class="tile-prev">{_offseason_countdown_html(sport, now)}</div></div>'
        )
    game = status["game"]
    blurb_html = _blurb_html(sport, game, label.title()) if game else ""
    return (
        f'<div class="tile">'
        f'<div class="sports-team-header">'
        f'<img class="sports-team-logo" src="{status["team_logo"]}" />'
        f'<div class="tile-label">{label} · {status["division_name"].upper()}{_odds_suffix_html(status)}</div>'
        f"</div>"
        f"{_game_html(status, kickoff_label, now)}"
        f"{blurb_html}"
        f"{_form_strip_html(status)}"
        f"{_wildcard_html(status)}"
        f"{_standings_table(status)}"
        f"</div>"
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
        return

    now = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
    entries = [
        {"label": "BLUE JAYS", "status": jays, "kickoff_label": "First pitch", "sport": "mlb"},
        {"label": "CANADIENS", "status": habs, "kickoff_label": "Puck drop", "sport": "nhl"},
    ]
    # Session request: "instead of, like, having all the details, just
    # have the main status show on the top bar... rotate for all the
    # active sports right now." The full-width "comprehensive
    # scoreboard" swap-in (big score hero + inning/count/bases or
    # period/clock situation strip) is gone — headline_rotation.py's
    # own rotating top bar now carries that live status (see sports_
    # alerts.live_score_headline_candidates), and the toast alerts
    # (sports_alerts.get_new_alerts) already narrate every real scoring
    # play, which is what actually made the situation strip redundant
    # rather than just noisy. Always the plain 2-column compact layout
    # now, live or not — _compact_tile_html's own _game_html already
    # shows "LIVE {score} vs {opponent}" for a live game, just without
    # the extra detail panel underneath.
    for col, entry in zip(st.columns(2), entries):
        with col:
            st.markdown(
                _compact_tile_html(entry["label"], entry["status"], entry["kickoff_label"], now, entry["sport"]),
                unsafe_allow_html=True,
            )
