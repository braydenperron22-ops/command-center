"""Scores page: today's full slate across MLB, NBA, NHL, and NFL (see
scores_client.py) — every game on the board, not just the Blue Jays/
Canadiens pages_sports.py already tracks. Rotates through whichever
leagues actually have a game today, skipping any that don't (same
"hide when there's nothing to show" reasoning as pages_sports.py's own
out-of-season team sections) — a summer day with only MLB playing
doesn't waste rotation time on three empty NBA/NHL/NFL slots.

Same shared-epoch pattern pages_home.py uses for its own US/Canada
rotation — passed in from app.py rather than computed fresh here, to
avoid the exact race condition already fixed for that page.
"""

import time

import streamlit as st

import scores_client
from config import SCORES_LEAGUE_ROTATION_SECONDS


def _active_leagues() -> list[dict]:
    """Every league (see scores_client.LEAGUES) with at least one game
    today — checked in fixed order so the rotation is stable/
    predictable rather than reshuffling based on dict iteration."""
    return [entry for entry in scores_client.LEAGUES if scores_client.fetch_games(entry["key"])]


def current_league(active: list[dict], epoch_seconds: float | None = None) -> dict:
    """Same reasoning as pages_home.current_country: a caller-supplied
    epoch keeps this in lockstep with whatever page-selection math
    app.py already did this rerun, rather than a second independent
    time.time() call that could straddle a boundary at a slightly
    different instant."""
    epoch_seconds = time.time() if epoch_seconds is None else epoch_seconds
    index = int(epoch_seconds // SCORES_LEAGUE_ROTATION_SECONDS) % len(active)
    return active[index]


def _score_side(team: dict, is_winner: bool) -> str:
    # Built as one flat line, no embedded newlines/indentation — a
    # multi-line f-string here reads to the markdown parser as an
    # indented code block once it's nested inside _game_card's own
    # multi-line template below (the same class of bug already
    # documented in pages_weather.py/pages_today.py for exactly this
    # reason), and renders as literal text instead of real HTML.
    winner_class = " score-card-winner" if is_winner else ""
    score_html = f'<span class="score-card-value">{team["score"]}</span>' if team["score"] is not None else ""
    logo_html = f'<img class="score-card-logo" src="{team["logo"]}" />' if team.get("logo") else ""
    return (
        f'<div class="score-card-row{winner_class}">'
        f'<div class="score-card-team">{logo_html}<span class="score-card-abbr">{team["abbr"]}</span></div>'
        f"{score_html}</div>"
    )


def _game_card(game: dict) -> str:
    home, away = game["home"], game["away"]
    home_wins = away_wins = False
    if game["state"] == "post" and home["score"] is not None and away["score"] is not None:
        try:
            home_wins = int(home["score"]) > int(away["score"])
            away_wins = int(away["score"]) > int(home["score"])
        except ValueError:
            pass
    status_class = " score-card-status-live" if game["state"] == "in" else ""
    return (
        f'<div class="score-card">{_score_side(away, away_wins)}{_score_side(home, home_wins)}'
        f'<div class="score-card-status{status_class}">{game["status_text"]}</div></div>'
    )


def render(rotation_epoch: float | None = None) -> None:
    st.markdown('<div class="page-title page-title-scores">Scores</div>', unsafe_allow_html=True)

    active = _active_leagues()
    if not active:
        st.markdown(
            '<div class="tile"><div class="tile-prev">No games across MLB, NBA, NHL, or NFL right now.</div></div>',
            unsafe_allow_html=True,
        )
        return

    league = current_league(active, rotation_epoch)
    games = scores_client.fetch_games(league["key"])

    st.markdown(
        f'<div style="text-align:center; margin-bottom:0.8rem;">'
        f'<div class="country-name">{league["label"]}</div></div>',
        unsafe_allow_html=True,
    )
    cards_html = "".join(_game_card(g) for g in games)
    st.markdown(f'<div class="scores-grid">{cards_html}</div>', unsafe_allow_html=True)
