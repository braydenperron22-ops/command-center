"""Sports page: Blue Jays (MLB) + Canadiens (NHL) — current/most recent
game plus full division standings (see sports_client.py). Each team's
whole section is hidden while its own league is out of season, so this
page can show just one team, or fall back to a quiet placeholder when
both leagues happen to be between seasons (their offseasons briefly
overlap in February) — no manual upkeep needed as real seasons start
and end.
"""

import html
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

import sports_client
from config import TIMEZONE

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

    # Always two columns, even with only one team in season — a single
    # team otherwise stretches to the full page width and reads sparse.
    # The out-of-season slot gets its own quiet placeholder instead of
    # just disappearing, so the layout doesn't reflow every few months.
    for col, label, status, kickoff_label in zip(
        st.columns(2), ("BLUE JAYS", "CANADIENS"), (jays, habs), ("First pitch", "Puck drop")
    ):
        with col:
            if status is None:
                st.markdown(
                    f"""<div class="tile">
                        <div class="tile-label">{label}</div>
                        <div class="tile-prev">Out of season.</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
                continue
            st.markdown(
                f"""<div class="tile">
                    <div class="sports-team-header">
                        <img class="sports-team-logo" src="{status['team_logo']}" />
                        <div class="tile-label">{label} · {status['division_name'].upper()}</div>
                    </div>
                    {_game_html(status, kickoff_label, now)}
                    {_wildcard_html(status)}
                    {_standings_table(status)}</div>""",
                unsafe_allow_html=True,
            )
