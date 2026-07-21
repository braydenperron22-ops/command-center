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
# Confirmed live: 8 rows fit fine pregame (2 lines each), but once
# records + a leader line are showing on every row (live/final games)
# an 8th row clips against the panel's fixed height. 7 leaves real
# margin at the tallest (leader-line-on-every-row) case.
_AROUND_PAGE_SIZE = 7
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

    # Session request: "are there animations for... there's a
    # strikeout" — pulses whichever dot just lit up (balls/strikes/
    # outs each compared to what was last rendered for this game,
    # keyed by game_id in session_state). A new at-bat resetting these
    # to a lower count never falsely pulses anything: there's no lit
    # dot to pulse the instant a count drops, only when it climbs.
    prev_counts = st.session_state.get(f"jumbotron_mlb_counts_{game_id}", {})
    current_counts = {"b": detail.get("balls") or 0, "s": detail.get("strikes") or 0, "o": detail.get("outs") or 0}
    st.session_state[f"jumbotron_mlb_counts_{game_id}"] = current_counts

    def dots(count, total, kind):
        count = count or 0
        just_up = count > prev_counts.get(kind, 0)
        out = []
        for i in range(total):
            classes = f"jumbo-dot jumbo-dot-{kind}"
            if i < count:
                classes += " on"
                if just_up and i == count - 1:
                    classes += " jumbo-dot-pulse"
            out.append(f'<i class="{classes}"></i>')
        return "".join(out)

    inning = f'{detail.get("inning_state") or ""} {detail.get("current_inning") or ""}'.strip()
    parts = [f'<span class="jumbo-situ-hot">{html.escape(inning)}</span>'] if inning else []
    parts.append(diamond)
    parts.append(f'<span class="jumbo-dots">{dots(current_counts["b"], 4, "b")}</span>')
    parts.append(f'<span class="jumbo-dots">{dots(current_counts["s"], 3, "s")}</span>')
    parts.append(f'<span class="jumbo-dots">{dots(current_counts["o"], 3, "o")}</span>')
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
    return (
        '<div class="jumbo-wp"><div class="jumbo-wp-title">WIN PROBABILITY</div>'
        f'<div class="jumbo-wp-bar"><div class="jumbo-wp-seg" style="width:{away_pct}%;background:{away_color}"></div>'
        f'<div class="jumbo-wp-seg" style="width:{home_pct}%;background:{home_color}"></div></div>'
        f'<div class="jumbo-wp-labels"><span><b>{away_pct}%</b> {html.escape(away["name"])}</span>'
        f'<span>{html.escape(home["name"])} <b>{home_pct}%</b></span></div></div>'
    )


def _top_performers_html(match: dict | None) -> str:
    """Session request: "stats leaders across both teams in each
    category... have their pictures show." Real headshots, straight
    from ESPN's own CDN — the same "Top Performers" grid the original
    static mockup had (leadersFrom()), ported because the data (and
    the photos) turned out to be one ESPN call away via
    _espn_match_for, not because the mockup's own click-through JS
    came with it. "" once a bad/missing headshot 404s (onerror hides
    just that image, not the whole card — a photo-less stat line still
    reads fine on its own)."""
    if not match:
        return ""
    leaders = scores_client.leaders_with_headshots(match)
    if not leaders:
        return ""
    cards = "".join(
        f'<div class="jumbo-leader">'
        + (f'<img class="jumbo-leader-hshot" src="{html.escape(l["hshot"])}" onerror="this.style.display=\'none\'" />' if l.get("hshot") else "")
        + f'<div class="jumbo-leader-col"><div class="jumbo-leader-stat">{html.escape(l["stat"])}</div>'
        f'<div class="jumbo-leader-cat">{html.escape(l["cat"])}</div>'
        f'<div class="jumbo-leader-who">{html.escape(l["who"])}</div></div></div>'
        for l in leaders
    )
    return f'<div class="jumbo-leaders"><div class="jumbo-sl">Top Performers</div><div class="jumbo-leadgrid">{cards}</div></div>'


def _board_html(state: dict, now: datetime) -> str:
    league, status, game = state["league"], state["status"], state["game"]
    sport, phase = league["sport"], state["phase"]
    away, home = _sides(status, game, league["label"])
    match = _espn_match_for(sport, game)

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
        situation += _pregame_extra_html(sport, game["game_id"])
        linescore, scoring, wp_html, leaders_html = "", "", "", ""
        dim_away = dim_home = False
    else:
        away_score = game["opp_score"] if game["is_home"] else game["team_score"]
        home_score = game["team_score"] if game["is_home"] else game["opp_score"]

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
        linescore = _linescore_html(sport, game["game_id"], away, home)
        scoring = _scoring_html(sport, game["game_id"])
        wp_html = _win_probability_html(sport, match, away, home) if phase == "live" else ""
        leaders_html = _top_performers_html(match)
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
    linescore_block = f'<div class="jumbo-linewrap">{linescore}</div>' if linescore else ""

    return (
        f'<div class="jumbo-panel jumbo-board{live_class}{win_burst}">'
        f'<div class="jumbo-ph"><span>{html.escape(league["label"])} · FEATURED</span>'
        f'<span class="jumbo-ph-right">{state_label}</span></div>'
        f'<div class="jumbo-board-body">'
        f'<div class="jumbo-matchup">{_side_html(away, dim_away)}{center}{_side_html(home, dim_home)}</div>'
        f"{wp_html}{situation}{linescore_block}{scoring}{leaders_html}"
        f"</div></div>"
    )


def _standings_mini_html(status: dict) -> str:
    """Compact division-standings snippet for the My Teams rail —
    session request, reusing the exact same status["standings"] list
    (see sports_client's own docstrings) the regular Sports page's
    _standings_table already renders. No new fetch: this data was
    already coming back from fetch_jays()/fetch_habs(), just unused on
    this page until now."""
    rows = status.get("standings") or []
    if not rows:
        return ""
    body = "".join(
        f'<div class="jumbo-standings-row{" jumbo-standings-row-team" if r["is_team"] else ""}">'
        f'<span class="jumbo-standings-rank">{r["rank"]}</span>'
        f'<span class="jumbo-standings-team">{html.escape(r["team"])}</span>'
        f'<span class="jumbo-standings-record">{r["wins"]}-{r["losses"]}</span>'
        f'<span class="jumbo-standings-extra">{r["extra"]}</span></div>'
        for r in rows
    )
    return f'<div class="jumbo-standings">{body}</div>'


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
        f'<div class="jumbo-gameline">{line}</div>'
        f"{_standings_mini_html(status)}</div>"
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
