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
linescore or scoring-summary fetch drops that section, not the board.

Data comes entirely from fetchers this app already had (sports_client
for game/standings/form/live detail, sports_alerts for scoring plays,
scores_client for the league-wide slate); the only additions were the
two linescore fetchers in sports_client.
"""

import html
import time
from datetime import datetime

import streamlit as st

import scores_client
import sports_alerts
import sports_client

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
_AROUND_PAGE_SIZE = 8
_AROUND_ROTATE_SECONDS = 12
_SCORING_PLAYS_SHOWN = 4
_FORM_GAMES_SHOWN = 8


def _fmt_countdown(seconds: float) -> str:
    """H:MM, no seconds — session feedback: the kiosk only reruns every
    5s anyway, so a seconds digit just sat there looking like it was
    ticking and then jumped by 5. Whole minutes update rarely enough
    that the 5s rerun cadence never shows."""
    total = max(0, int(seconds))
    hours, minutes = divmod(total // 60, 60)
    return f"{hours}:{minutes:02d}"


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
    always putting us first, so the linescore rows below it line up with
    the logos above them."""
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


def _linescore_html(sport: str, game_id: int, away: dict, home: dict) -> str:
    fetch = sports_client.fetch_mlb_linescore if sport == "mlb" else sports_client.fetch_nhl_linescore
    data = fetch(game_id)
    if not data:
        return ""
    columns, totals, extras = data["columns"], data["totals"], data["extra_labels"]
    head = "".join(f"<th>{html.escape(c['label'])}</th>" for c in columns)
    head += "".join(f'<th class="jumbo-ls-tot">{html.escape(x)}</th>' for x in extras)
    keys = {"R": "runs", "T": "runs", "H": "hits", "E": "errors"}

    def row(side_key: str, side: dict) -> str:
        cells = "".join(
            f'<td>{"–" if c[side_key] is None else int(c[side_key])}</td>' for c in columns
        )
        cells += "".join(
            f'<td class="jumbo-ls-tot">{totals[side_key].get(keys[x]) if totals[side_key].get(keys[x]) is not None else "–"}</td>'
            for x in extras
        )
        return (
            f'<tr><td class="jumbo-ls-team"><img src="{html.escape(side["logo"])}" />'
            f'{html.escape(side["name"][:14])}</td>{cells}</tr>'
        )

    return (
        f'<table class="jumbo-linescore"><thead><tr><th></th>{head}</tr></thead>'
        f'<tbody>{row("away", away)}{row("home", home)}</tbody></table>'
    )


def _scoring_html(sport: str, game_id: int) -> str:
    fetch = sports_alerts._mlb_scoring_plays if sport == "mlb" else sports_alerts._nhl_scoring_plays
    try:
        plays = fetch(game_id)
    except Exception:
        return ""
    if not plays:
        return ""
    # Not truncated here — .jumbo-play-text ellipsizes in CSS, which
    # cuts to the actual rendered width instead of a character count
    # that lands mid-word at whatever the panel happens to be.
    rows = "".join(
        f'<div class="jumbo-play"><span class="jumbo-play-text">{html.escape(p["description"])}</span>'
        f'<span class="jumbo-play-score">{p["away_score"]}–{p["home_score"]}</span></div>'
        for p in plays[-_SCORING_PLAYS_SHOWN:][::-1]
    )
    return f'<div class="jumbo-scoring"><div class="jumbo-sl">Scoring Summary</div>{rows}</div>'


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

    def dots(count, total, kind):
        count = count or 0
        return "".join(
            f'<i class="jumbo-dot jumbo-dot-{kind}{" on" if i < count else ""}"></i>' for i in range(total)
        )

    inning = f'{detail.get("inning_state") or ""} {detail.get("current_inning") or ""}'.strip()
    parts = [f'<span class="jumbo-situ-hot">{html.escape(inning)}</span>'] if inning else []
    parts.append(diamond)
    parts.append(f'<span class="jumbo-dots">{dots(detail.get("balls"), 4, "b")}</span>')
    parts.append(f'<span class="jumbo-dots">{dots(detail.get("strikes"), 3, "s")}</span>')
    parts.append(f'<span class="jumbo-dots">{dots(detail.get("outs"), 3, "o")}</span>')
    line = "".join(parts)
    who = []
    if detail.get("batter"):
        who.append(f'<span class="jumbo-dim">AT BAT</span> {html.escape(detail["batter"])}')
    if detail.get("pitcher"):
        who.append(f'<span class="jumbo-dim">PITCHING</span> {html.escape(detail["pitcher"])}')
    who_line = f'<div class="jumbo-situ-who">{" · ".join(who)}</div>' if who else ""
    return f'<div class="jumbo-situ">{line}{who_line}</div>'


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


def _board_html(state: dict, now: datetime) -> str:
    league, status, game = state["league"], state["status"], state["game"]
    sport, phase = league["sport"], state["phase"]
    away, home = _sides(status, game, league["label"])

    if phase == "pregame":
        remaining = (game["start_time"] - now).total_seconds()
        kickoff = next((r["kickoff"] for r in _RAIL if r["sport"] == sport), "TO FIRST PITCH")
        center = (
            f'<div class="jumbo-center"><div class="jumbo-vs">VS</div>'
            f'<div class="jumbo-countdown">{_fmt_countdown(remaining)}</div>'
            f'<div class="jumbo-cd-label">{html.escape(kickoff)}</div></div>'
        )
        start_text = game["start_time"].strftime("%-I:%M %p")
        situation = f'<div class="jumbo-situ"><span class="jumbo-situ-hot">FIRST PITCH {html.escape(start_text)}</span></div>' if sport == "mlb" else f'<div class="jumbo-situ"><span class="jumbo-situ-hot">PUCK DROP {html.escape(start_text)}</span></div>'
        linescore, scoring = "", ""
        dim_away = dim_home = False
    else:
        away_score = game["opp_score"] if game["is_home"] else game["team_score"]
        home_score = game["team_score"] if game["is_home"] else game["opp_score"]
        final_badge = '<div class="jumbo-final-badge">FINAL</div>' if phase == "postgame" else ""
        center = (
            f'<div class="jumbo-center"><div class="jumbo-score">'
            f'<span class="jumbo-digitbox">{_digits_html(away_score)}</span>'
            f'<span class="jumbo-dash">—</span>'
            f'<span class="jumbo-digitbox">{_digits_html(home_score)}</span>'
            f"</div>{final_badge}</div>"
        )
        if phase == "live":
            situation = _mlb_situation_html(game["game_id"]) if sport == "mlb" else _nhl_situation_html(game["game_id"])
        else:
            situation = ""
        linescore = _linescore_html(sport, game["game_id"], away, home)
        scoring = _scoring_html(sport, game["game_id"])
        # Only a finished game has a settled winner to dim the loser
        # against — during a live game the trailing side is still very
        # much in it.
        if phase == "postgame" and away_score is not None and home_score is not None:
            dim_away, dim_home = away_score < home_score, home_score < away_score
        else:
            dim_away = dim_home = False

    state_label = {
        "live": '<span class="jumbo-live">● LIVE</span>',
        "pregame": "UPCOMING",
        "postgame": "FINAL",
    }[phase]
    live_class = " jumbo-board-live" if phase == "live" else ""
    linescore_block = f'<div class="jumbo-linewrap">{linescore}</div>' if linescore else ""

    return (
        f'<div class="jumbo-panel jumbo-board{live_class}">'
        f'<div class="jumbo-ph"><span>{html.escape(league["label"])} · FEATURED</span>'
        f'<span class="jumbo-ph-right">{state_label}</span></div>'
        f'<div class="jumbo-board-body">'
        f'<div class="jumbo-matchup">{_side_html(away, dim_away)}{center}{_side_html(home, dim_home)}</div>'
        f"{situation}{linescore_block}{scoring}"
        f"</div></div>"
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
        remaining = (game["start_time"] - now).total_seconds()
        line = (
            f'{versus} <b>{html.escape(game["opponent"])}</b>'
            f'<span class="jumbo-gl-cd">{_fmt_countdown(remaining)}</span>'
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
    state = g["state"]
    if state == "pre":
        status_text = g["start_time"].strftime("%-I:%M") if g.get("start_time") else ""
    else:
        status_text = g.get("status_text") or ""
    row_class = "jumbo-mini" + (" jumbo-mini-live" if state == "in" else " jumbo-mini-final" if state == "post" else "")

    def team_row(side):
        score = "" if state == "pre" else (side.get("score") or "")
        logo = f'<img src="{html.escape(side["logo"])}" />' if side.get("logo") else ""
        return (
            f'<div class="jumbo-mini-team">{logo}'
            f'<span class="jumbo-mini-abbr">{html.escape(side.get("abbr") or "")}</span>'
            f'<span class="jumbo-mini-score">{html.escape(str(score))}</span></div>'
        )

    return (
        f'<div class="{row_class}"><div class="jumbo-mini-teams">'
        f'{team_row(g["away"])}{team_row(g["home"])}</div>'
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
    return f'<div class="jumbo-around-league">{label}</div>' + "".join(_mini_row_html(g) for g in chunk)


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

    st.markdown(
        f'<div class="jumbo">'
        f'<div class="jumbo-marquee">'
        f'<div class="jumbo-brand">FANCAVE<span>JUMBOTRON</span></div>'
        f'<div class="jumbo-clock">{clock}<em>{meridiem}</em></div>'
        f'<div class="jumbo-dateline">{dateline}</div>'
        f'<div class="jumbo-spacer"></div>{weather_chip}</div>'
        f'<div class="jumbo-grid">'
        f'<div class="jumbo-panel jumbo-rail"><div class="jumbo-ph"><span>My Teams</span></div>'
        f'<div class="jumbo-rail-body">{rail}</div></div>'
        f"{_board_html(state, now)}"
        f"{around_block}"
        f"</div></div>",
        unsafe_allow_html=True,
    )
