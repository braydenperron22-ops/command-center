"""Sports page: Blue Jays (MLB) + Canadiens (NHL) — current/most recent
game plus full division standings (see sports_client.py). Each team's
whole section is hidden while its own league is out of season, so this
page can show just one team, or fall back to a quiet placeholder when
both leagues happen to be between seasons (their offseasons briefly
overlap in February) — no manual upkeep needed as real seasons start
and end.
"""

import streamlit as st

import sports_client


def _game_html(status: dict) -> str:
    game = status["game"]
    if game is None:
        return '<div class="tile-prev">No game scheduled right now.</div>'
    opponent_word = "vs" if game["is_home"] else "@"
    if game["state"] == "upcoming":
        start = game["start_time"]
        time_text = start.strftime("%I:%M %p").lstrip("0")
        value = f"{start.strftime('%a %b')} {start.day}, {time_text}"
        value_class, result = "", f"{opponent_word} {game['opponent']}"
    else:
        value = f"{game['team_score']}-{game['opp_score']}"
        if game["state"] == "live":
            value_class, result = "", f"LIVE {opponent_word} {game['opponent']}"
        else:
            won = game["team_score"] > game["opp_score"]
            value_class = "market-up" if won else "market-down"
            result = f"{'W' if won else 'L'} {opponent_word} {game['opponent']}"
    return f"""<div class="tile-value {value_class}">{value}</div>
        <div class="tile-prev">{result}</div>"""


def _standings_table(status: dict) -> str:
    rows = "".join(
        f"""<div class="sports-standings-row{' sports-standings-row-team' if r['is_team'] else ''}">
            <span class="sports-standings-rank">{r['rank']}</span>
            <span class="sports-standings-team">{r['team']}</span>
            <span class="sports-standings-record">{r['wins']}-{r['losses']}</span>
            <span class="sports-standings-extra">{r['extra']}</span>
        </div>"""
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

    # Always two columns, even with only one team in season — a single
    # team otherwise stretches to the full page width and reads sparse.
    # The out-of-season slot gets its own quiet placeholder instead of
    # just disappearing, so the layout doesn't reflow every few months.
    for col, label, status in zip(st.columns(2), ("BLUE JAYS", "CANADIENS"), (jays, habs)):
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
                    <div class="tile-label">{label} · {status['division_name'].upper()}</div>
                    {_game_html(status)}
                    {_standings_table(status)}</div>""",
                unsafe_allow_html=True,
            )
