"""Jumbotron: a full-screen arena scoreboard that takes the kiosk over
for Jays/Habs/Saints games (and UFC cards) — session request: "I want
the kiosk to run as normal, but one hour before any game Habs or Jays,
and during the game, I want it to go to that exactly so the game can be
enjoyed with this system, before reverting back to the other system."

This page is deliberately NOT in config.PAGES — it never joins the
normal rotation. sports_alerts.takeover_state() decides when it owns the
screen (T-60 min through ~15 min past final), and app.py forces the page
and suppresses its own hero row while that's active.

RENDER ONLY. Every fetch, every derived value and every real
cross-rerun session_state read/write lives in jumbotron_data.py — this
module turns those plain dicts into markup and nothing else. Three rules
this rebuild (2026-09-20) is built around, each one a real bug that
already happened here:

1. **One height budget, computed once.** `.jumbo-root` owns a single
   explicit height (theme.py's --jumbo-budget-h, the only `vh` in the
   whole jumbotron stylesheet); every panel below sizes as a flex/grid
   fraction of that already-budgeted box. The board is excluded from the
   app's stepped zoom media queries at the source rather than fighting
   them with an override downstream.
2. **Pagination is the fit mechanism, `overflow:hidden` is only the
   safety net.** The kiosk never scrolls, so anything past what fits is
   permanently invisible, not merely below the fold. Every list that can
   grow unboundedly (Around The Leagues, standings, UFC card, batting
   order, storyline cards) is paged or bounded.
3. **Nothing depends on a CSS animation to reach its correct
   appearance.** Animations are permanently off app-wide (theme.py's
   global kill switch). Full-screen overlays here are *presence-gated* —
   jumbotron_data returns None and the element simply isn't emitted —
   and therefore must never carry a resting opacity:0/visibility:hidden
   anywhere in CSS. A resting-hidden style is exactly what made the
   play-result announcement and the enter/exit curtain invisible for
   good once the kill switch landed.

The one genuine JS hook that survives is `class="live-countdown"` +
`data-target-ms`: app.py's global ticker rewrites those elements once a
second against the browser's own clock, which a 5s (let alone 75s)
Streamlit rerun cadence can't do. `data-wp-key`/`data-fade-slot` are
gone — the scripts that consumed them were removed with the animations.
"""

import html
from datetime import datetime

import streamlit as st

import jumbotron_data as jd
import sports_client


# --------------------------------------------------------------------
# Small shared builders
# --------------------------------------------------------------------

def _e(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _rgb(rgb: tuple[int, int, int]) -> str:
    return f"{rgb[0]},{rgb[1]},{rgb[2]}"


def _countdown_html(cd: dict, extra_class: str = "", fmt: str = "") -> str:
    """The live-ticking countdown element. `data-target-ms` is what
    app.py's global ticker binds to — dropping it freezes the number at
    whatever the server rendered."""
    fmt_attr = f' data-format="{fmt}"' if fmt else ""
    cls = f"live-countdown {extra_class}".strip()
    return f'<span class="{cls}" data-target-ms="{cd["target_ms"]}"{fmt_attr}>{_e(cd["text"])}</span>'


def _panel_header(title: str, right: str = "") -> str:
    right_html = f'<span class="jumbo-ph-r">{right}</span>' if right else ""
    return f'<div class="jumbo-ph"><span class="jumbo-ph-t">{_e(title)}</span>{right_html}</div>'


def _section_label(text: str) -> str:
    return f'<div class="jumbo-sl">{_e(text)}</div>'


# --------------------------------------------------------------------
# Live situation strip
# --------------------------------------------------------------------

def _diamond_render(bases: dict) -> str:
    """Base diamond. A newly-occupied base gets a distinct *resting*
    style (jumbo-base-new), not a one-shot flash — animations never play
    on this kiosk, so "just changed" has to be a real appearance."""

    def cls(key: str) -> str:
        b = bases[key]
        return ("on" if b["on"] else "") + (" jumbo-base-new" if b["new"] else "")

    return (
        '<svg class="jumbo-diamond" viewBox="0 0 34 34"><g transform="rotate(45 17 17)">'
        f'<rect x="21" y="9" width="8" height="8" class="{cls("first")}"></rect>'
        f'<rect x="9" y="9" width="8" height="8" class="{cls("second")}"></rect>'
        f'<rect x="9" y="21" width="8" height="8" class="{cls("third")}"></rect>'
        "</g></svg>"
    )


def _situation_render(situation: dict | None) -> str:
    if not situation:
        return ""
    kind = situation["kind"]
    parts: list[str] = []

    if kind == "mlb":
        if situation["inning"]:
            parts.append(f'<span class="jumbo-situ-key">{_e(situation["inning"])}</span>')
        parts.append(_diamond_render(situation["bases"]))
        ball_cls = " jumbo-count-new" if situation["ball_new"] else ""
        strike_cls = " jumbo-count-new" if situation["strike_new"] else ""
        outs_cls = " jumbo-count-new" if situation["out_new"] else ""
        parts.append(
            '<span class="jumbo-situ-cell"><span class="jumbo-situ-cap">COUNT</span>'
            f'<span class="jumbo-situ-num"><span class="jumbo-ball{ball_cls}">{situation["balls"]}</span>'
            f'<span class="jumbo-situ-sep">-</span>'
            f'<span class="jumbo-strike{strike_cls}">{situation["strikes"]}</span></span></span>'
        )
        parts.append(
            '<span class="jumbo-situ-cell"><span class="jumbo-situ-cap">OUTS</span>'
            f'<span class="jumbo-situ-num{outs_cls}">{situation["outs"]}</span></span>'
        )
    elif kind == "nhl":
        if situation.get("intermission"):
            parts.append(f'<span class="jumbo-situ-key">{_e(situation["intermission"])}</span>')
        else:
            if situation.get("period_label"):
                parts.append(f'<span class="jumbo-situ-key">{_e(situation["period_label"])} PERIOD</span>')
            if situation.get("clock"):
                parts.append(f'<span class="jumbo-situ-clock">{_e(situation["clock"])}</span>')
    elif kind == "neutral":
        parts.append(f'<span class="jumbo-situ-key">{_e(situation["text"])}</span>')
    elif kind == "nfl":
        if situation.get("period_label"):
            parts.append(f'<span class="jumbo-situ-key">{_e(situation["period_label"])}</span>')
        if situation.get("clock"):
            parts.append(f'<span class="jumbo-situ-clock">{_e(situation["clock"])}</span>')
        if situation.get("down_text"):
            parts.append(f'<span class="jumbo-situ-down">{_e(situation["down_text"])}</span>')
        if situation.get("red_zone"):
            parts.append('<span class="jumbo-chip jumbo-chip-alert">RED ZONE</span>')
        possession = situation.get("possession")
        if possession:
            tone = "jumbo-chip-us" if possession["is_us"] else "jumbo-chip-opp"
            parts.append(f'<span class="jumbo-chip {tone}">{_e(possession["text"])}</span>')
        if situation.get("timeouts"):
            parts.append(f'<span class="jumbo-situ-sub">{_e(situation["timeouts"])}</span>')

    return f'<div class="jumbo-situ">{"".join(parts)}</div>' if parts else ""


# --------------------------------------------------------------------
# Matchup header / score
# --------------------------------------------------------------------

def _side_render(side: dict, rgb: tuple[int, int, int], dim: bool, has_ball: bool = False) -> str:
    """One team column. The team's real color is a flat 4px rule across
    the top of the panel — no diagonal clip-path, no gradient wash: the
    diagonal geometry this replaced is what clipped real content every
    time the angle or padding moved."""
    classes = "jumbo-side" + (" jumbo-side-dim" if dim else "")
    ball = '<span class="jumbo-side-ball">🏈</span>' if has_ball else ""
    record = f'<div class="jumbo-trec">{_e(side["record"])}</div>' if side.get("record") else ""
    return (
        f'<div class="{classes}" style="--side-rgb:{_rgb(rgb)}">'
        f'<div class="jumbo-side-rule"></div>'
        f'<div class="jumbo-logobox"><img src="{_e(side["logo"])}" /></div>'
        f'<div class="jumbo-tname">{ball}{_e(side["name"])}</div>'
        f"{record}"
        f"</div>"
    )


def _center_render(board: dict) -> str:
    phase = board["phase"]
    if phase == "pregame":
        if board["delay_text"]:
            inner = f'<div class="jumbo-delayed">{_e(board["delay_text"])}</div>'
        else:
            inner = f'<div class="jumbo-countdown">{_countdown_html(board["countdown"])}</div>'
        return (
            '<div class="jumbo-center">'
            '<div class="jumbo-vs">VS</div>'
            f"{inner}"
            f'<div class="jumbo-cd-label">{_e(board["kickoff_label"])}</div>'
            "</div>"
        )
    away_cls = "jumbo-score-num" + (" jumbo-score-changed" if board["away_score_changed"] else "")
    home_cls = "jumbo-score-num" + (" jumbo-score-changed" if board["home_score_changed"] else "")
    away = board["away_score"] if board["away_score"] is not None else 0
    home = board["home_score"] if board["home_score"] is not None else 0
    final = '<div class="jumbo-final-badge">FINAL</div>' if phase == "postgame" else ""
    return (
        '<div class="jumbo-center">'
        '<div class="jumbo-score">'
        f'<span class="{away_cls}">{_e(away)}</span>'
        '<span class="jumbo-score-sep">–</span>'
        f'<span class="{home_cls}">{_e(home)}</span>'
        "</div>"
        f"{final}"
        "</div>"
    )


# --------------------------------------------------------------------
# Win probability
# --------------------------------------------------------------------

def _win_probability_render(wp: dict | None) -> str:
    if not wp:
        return ""
    away_color = f"rgb({_rgb(wp['away_color'])})"
    home_color = f"rgb({_rgb(wp['home_color'])})"
    return (
        '<div class="jumbo-wp">'
        f'<div class="jumbo-wp-title">{_e(wp["title"])}</div>'
        '<div class="jumbo-wp-row">'
        f'<div class="jumbo-wp-pct" style="color:{away_color}">{wp["away_pct"]}%</div>'
        '<div class="jumbo-wp-bar">'
        f'<div class="jumbo-wp-seg" style="width:{wp["away_pct"]}%;background:{away_color}"></div>'
        f'<div class="jumbo-wp-seg" style="width:{wp["home_pct"]}%;background:{home_color}"></div>'
        "</div>"
        f'<div class="jumbo-wp-pct" style="color:{home_color}">{wp["home_pct"]}%</div>'
        "</div>"
        f'<div class="jumbo-wp-labels"><span>{_e(wp["away_name"])}</span>'
        f'<span>{_e(wp["home_name"])}</span></div>'
        "</div>"
    )


# --------------------------------------------------------------------
# Feature panel — the board's flexible bottom half
# --------------------------------------------------------------------

def _leaders_render(data: dict) -> str:
    """Season stat leaders — one spotlit big, the rest listed beside it
    so the card reads as "here's the whole leaderboard, spotlighting
    one" rather than a single stat floating in a blank card."""
    leaders, index, leader = data["leaders"], data["index"], data["leader"]
    hshot = (
        f'<img class="jumbo-leader-photo" src="{_e(leader["hshot"])}" onerror="this.style.display=\'none\'" />'
        if leader.get("hshot")
        else ""
    )
    page_label = f"{index + 1}/{len(leaders)}" if len(leaders) > 1 else ""
    items = "".join(
        f'<div class="jumbo-leader-item{" jumbo-leader-item-on" if i == index else ""}">'
        f'<span class="jumbo-leader-who">{_e(l["who"])}</span>'
        f'<span class="jumbo-leader-stat">{_e(l["stat"])} {_e(l["cat"])}</span></div>'
        for i, l in enumerate(leaders)
    )
    title = "Top Performers" + (f" · {page_label}" if page_label else "")
    return (
        '<div class="jumbo-feature-inner">'
        f"{_section_label(title)}"
        '<div class="jumbo-leader-card">'
        f"{hshot}"
        '<div class="jumbo-leader-big">'
        f'<div class="jumbo-leader-value">{_e(leader["stat"])}</div>'
        f'<div class="jumbo-leader-cat">{_e(leader["cat"])}</div>'
        f'<div class="jumbo-leader-name">{_e(leader["who"])}</div>'
        "</div>"
        f'<div class="jumbo-leader-list">{items}</div>'
        "</div></div>"
    )


def _top3_render(performers: list[dict]) -> str:
    """Postgame Game Score trio — always exactly 3, already ranked, so
    all three show at once rather than rotating. The best (index 0) gets
    the one warm accent this board reserves for "the one that matters."""
    cards = []
    for i, p in enumerate(performers):
        photo = (
            f'<img class="jumbo-top3-photo" src="{_e(p["photo"])}" onerror="this.style.display=\'none\'" />'
            if p.get("photo")
            else ""
        )
        logo = f'<img class="jumbo-top3-logo" src="{_e(p["logo"])}" />' if p.get("logo") else ""
        role = jd.TOP3_ROLE_LABEL.get(p.get("role"), (p.get("role") or "").title())
        cls = "jumbo-top3-card jumbo-top3-best" if i == 0 else "jumbo-top3-card"
        cards.append(
            f'<div class="{cls}">'
            f'<div class="jumbo-top3-photowrap">{photo}{logo}</div>'
            f'<div class="jumbo-top3-name">{_e(p["name"])}</div>'
            f'<div class="jumbo-top3-role">{_e(role)}</div>'
            f'<div class="jumbo-top3-summary">{_e(p["summary"])}</div>'
            f'<div class="jumbo-top3-score"><span class="jumbo-top3-score-num">{_e(p["game_score"])}</span>'
            '<span class="jumbo-top3-score-cap">GAME SCORE</span></div>'
            "</div>"
        )
    return (
        '<div class="jumbo-feature-inner">'
        f'{_section_label("Top Performers")}'
        f'<div class="jumbo-top3">{"".join(cards)}</div>'
        "</div>"
    )


def _storylines_render(data: dict) -> str:
    """Pregame warm-up show — one full-width card at a time (session
    request: "big... take up the whole bottom part... one card at a
    time... look professional"). Transaction-sourced cards have no real
    headshot by design (ESPN's feed there is plain prose with no athlete
    id), so those get a plain initial rather than a broken image."""
    c = data["card"]
    if c.get("photo"):
        photo = f'<img class="jumbo-story-photo" src="{_e(c["photo"])}" />'
    else:
        initial = _e(c["name"][:1].upper()) if c.get("name") else "?"
        photo = f'<div class="jumbo-story-photo jumbo-story-photo-blank">{initial}</div>'
    tag = (
        f'<div class="jumbo-story-tag jumbo-story-tag-{_e(c.get("tag_category", "default"))}">{_e(c["tag"])}</div>'
        if c.get("tag")
        else ""
    )
    headline = f'<div class="jumbo-story-headline">{_e(c["headline"])}</div>' if c.get("headline") else ""
    statline = f'<div class="jumbo-story-stat">{_e(c["stat_line"])}</div>' if c.get("stat_line") else ""
    page = f" · {data['index'] + 1}/{data['total']}" if data["total"] > 1 else ""
    return (
        '<div class="jumbo-feature-inner">'
        f'{_section_label("Pregame" + page)}'
        f'<div class="jumbo-story-card" style="--story-rgb:{_rgb(data["accent_rgb"])}">'
        f'<div class="jumbo-story-photowrap">{photo}</div>'
        '<div class="jumbo-story-main">'
        f"{tag}{headline}"
        f'<div class="jumbo-story-name">{_e(c["name"])}</div>'
        f"{statline}"
        f'<div class="jumbo-story-text">{_e(c["storyline"])}</div>'
        "</div></div></div>"
    )


def _strike_zone_render(zone: dict | None) -> str:
    """The zone box (this batter's own real strikeZoneTop/Bottom, not a
    generic average) plus one dot per pitch at its real (px, pz).
    Falls back to a plain VS divider when there's genuinely no pitch
    data for the current at-bat yet."""
    if not zone:
        return '<div class="jumbo-matchup-vs">VS</div>'
    box = zone["box"]
    dots = []
    chips = []
    for d in zone["dots"]:
        stroke = ' stroke="#FFFFFF" stroke-width="1.5"' if d["is_last"] else ""
        r = 8 if d["is_last"] else 6
        dots.append(
            f'<circle cx="{d["cx"]:.1f}" cy="{d["cy"]:.1f}" r="{r}" fill="{d["color"]}"{stroke} '
            f'opacity="{d["opacity"]:.2f}" />'
        )
        chips.append(f'<div class="jumbo-pitch-chip" style="color:{d["color"]}">{_e(d["speed"])} {_e(d["type"])}</div>')
    return (
        '<div class="jumbo-zone">'
        f'<svg class="jumbo-zone-svg" viewBox="0 0 {jd.ZONE_SVG_W} {jd.ZONE_SVG_H}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect x="{box["x1"]:.1f}" y="{box["y1"]:.1f}" width="{box["x2"] - box["x1"]:.1f}" '
        f'height="{box["y2"] - box["y1"]:.1f}" fill="none" stroke="#7B8494" stroke-width="2" />'
        f'{"".join(dots)}'
        "</svg>"
        f'<div class="jumbo-pitch-chips">{"".join(chips)}</div>'
        "</div>"
    )


def _matchup_col_render(col: dict) -> str:
    player = col["player"]
    photo = (
        f'<img class="jumbo-mu-photo" src="{_e(player["photo"])}" onerror="this.style.display=\'none\'" />'
        if player.get("photo")
        else ""
    )
    rows_html = ""
    for stats in col["rows"]:
        blocks = "".join(
            f'<div class="jumbo-mu-stat-block">'
            f'<div class="jumbo-mu-stat{" jumbo-mu-stat-" + heat if heat else ""}">{_e(value)}</div>'
            f'<div class="jumbo-mu-stat-cap">{_e(label)}</div>'
            "</div>"
            for value, label, heat in stats
            if value is not None
        )
        if blocks:
            rows_html += f'<div class="jumbo-mu-stat-row">{blocks}</div>'
    if not rows_html:
        rows_html = '<div class="jumbo-mu-stat-row"><div class="jumbo-mu-stat-block"><div class="jumbo-mu-stat">—</div></div></div>'
    # The pitcher's full line is appended strictly after every stat row,
    # never inserted above the name/photo — session request: "add the
    # full line score... without making the pitcher's name shift up."
    line = f'<div class="jumbo-mu-line">{_e(col["line"])}</div>' if col.get("line") else ""
    return (
        '<div class="jumbo-mu-col">'
        f"{photo}"
        f'<div class="jumbo-mu-tag">{_e(col["tag"])}</div>'
        f'<div class="jumbo-mu-name">{_e(player["name"])}</div>'
        f"{rows_html}{line}"
        "</div>"
    )


def _current_matchup_render(data: dict) -> str:
    return (
        '<div class="jumbo-feature-inner">'
        f'{_section_label("Current Matchup")}'
        '<div class="jumbo-mu">'
        f'{_matchup_col_render(data["batter"])}'
        f'{_strike_zone_render(data["zone"])}'
        f'{_matchup_col_render(data["pitcher"])}'
        "</div></div>"
    )


_FEATURE_RENDERERS = {
    "leaders": _leaders_render,
    "top3": _top3_render,
    "storylines": _storylines_render,
    "matchup": _current_matchup_render,
}


def _last_play_render(play: dict | None, away: dict, home: dict) -> str:
    if not play:
        return ""
    return (
        '<div class="jumbo-lastplay">'
        '<div class="jumbo-lastplay-score">'
        f'<img class="jumbo-lastplay-logo" src="{_e(away["logo"])}" />'
        f'<span class="jumbo-lastplay-tally">{_e(play["away_score"])}–{_e(play["home_score"])}</span>'
        f'<img class="jumbo-lastplay-logo" src="{_e(home["logo"])}" />'
        "</div>"
        f'<div class="jumbo-lastplay-desc">{_e(play["description"])}</div>'
        "</div>"
    )


def _blurb_render(blurb: dict | None) -> str:
    if not blurb:
        return ""
    return (
        '<div class="jumbo-blurb">'
        f'{_section_label(blurb["label"])}'
        f'<div class="jumbo-blurb-text">{_e(blurb["text"])}</div>'
        "</div>"
    )


def _pregame_extra_render(extra: dict | None) -> str:
    if not extra:
        return ""
    parts = []
    if extra.get("venue"):
        line = _e(extra["venue"])
        if extra.get("weather_line"):
            line += f' · {_e(extra["weather_line"])}'
        parts.append(f'<div class="jumbo-venue">{line}</div>')
    if extra.get("away_pitcher") or extra.get("home_pitcher"):
        cells = "".join(
            f'<div class="jumbo-probable"><span class="jumbo-probable-cap">{_e(label)}</span>'
            f'<b>{_e(pitcher)}</b></div>'
            for label, pitcher in (("AWAY · SP", extra.get("away_pitcher")), ("HOME · SP", extra.get("home_pitcher")))
            if pitcher
        )
        parts.append(f'<div class="jumbo-probables">{cells}</div>')
    return "".join(parts)


def _board_render(board: dict) -> str:
    phase = board["phase"]
    state_label = {
        "live": '<span class="jumbo-state jumbo-state-live"><i></i>LIVE</span>',
        "pregame": '<span class="jumbo-state">UPCOMING</span>',
        "postgame": '<span class="jumbo-state">FINAL</span>',
    }[phase]
    classes = "jumbo-panel jumbo-board"
    if phase == "live":
        classes += " jumbo-board-live"
    if board["win_celebration"]:
        classes += " jumbo-board-won"

    feature = ""
    renderer = _FEATURE_RENDERERS.get(board["content_kind"])
    if renderer and board["content"]:
        feature = renderer(board["content"])

    start_label = (
        f'<div class="jumbo-situ"><span class="jumbo-situ-key">{_e(board["start_label"])}</span></div>'
        if board.get("start_label")
        else ""
    )

    return (
        f'<section class="{classes}" style="--away-rgb:{_rgb(board["away_rgb"])};--home-rgb:{_rgb(board["home_rgb"])}">'
        f'<div class="jumbo-ph"><span class="jumbo-ph-t">{_e(board["league_label"])} · Featured</span>'
        f'<span class="jumbo-ph-r">{state_label}</span></div>'
        '<div class="jumbo-board-body">'
        '<div class="jumbo-matchup">'
        f'{_side_render(board["away"], board["away_rgb"], board["dim_away"], board["nfl_possession_home"] is False)}'
        f'{_center_render(board)}'
        f'{_side_render(board["home"], board["home_rgb"], board["dim_home"], board["nfl_possession_home"] is True)}'
        "</div>"
        f'{start_label}'
        f'{_situation_render(board["situation"])}'
        f'{_pregame_extra_render(board["pregame_extra"])}'
        f'{_win_probability_render(board["win_probability"])}'
        f'{_blurb_render(board["blurb"])}'
        f'<div class="jumbo-feature">{feature}</div>'
        f'{_last_play_render(board["last_play"], board["away"], board["home"])}'
        "</div></section>"
    )


# --------------------------------------------------------------------
# My Teams rail / batting order (mutually exclusive)
# --------------------------------------------------------------------

def _rail_hero_render(hero: dict) -> str:
    sport = hero["sport"]
    classes = f'jumbo-hero jumbo-hero-{sport}' + (" jumbo-hero-live" if hero.get("live") else "")

    if hero["kind"] == "offseason":
        off = hero.get("offseason")
        line = (
            f'{_e(off["label"])} {_e(off["date_text"])} · {_e(off["countdown_text"])}'
            if off
            else "OFFSEASON"
        )
        return (
            f'<div class="{classes}"><div class="jumbo-hero-rule"></div>'
            f'<div class="jumbo-hero-head"><div class="jumbo-hero-id">'
            f'<div class="jumbo-hero-name">{_e(hero["label"])}</div></div></div>'
            f'<div class="jumbo-gameline jumbo-gameline-quiet">{line}</div></div>'
        )

    if hero["kind"] == "no_game":
        line = "No game on today's slate"
    elif hero["kind"] == "upcoming":
        cd = (
            '<span class="jumbo-gl-cd jumbo-gl-cd-delayed">DELAYED</span>'
            if hero["delayed"]
            else f'<span class="jumbo-gl-cd">{_countdown_html(hero["countdown"])}</span>'
        )
        line = f'{_e(hero["versus"])} <b>{_e(hero["opponent"])}</b>{cd}'
    else:
        score = f'<span class="jumbo-gl-score">{_e(hero["team_score"])}–{_e(hero["opp_score"])}</span>'
        if hero["kind"] == "final":
            mark = '<b class="jumbo-w">W</b>' if hero["won"] else '<b class="jumbo-l">L</b>'
            line = f'{mark} {score} {_e(hero["versus"])} <b>{_e(hero["opponent"])}</b> · FINAL'
        else:
            line = f'{score} {_e(hero["versus"])} <b>{_e(hero["opponent"])}</b>'

    form_html = ""
    if hero.get("form"):
        dots = "".join(f'<i class="jumbo-form-{"w" if r == "W" else "l"}"></i>' for r in hero["form"])
        form_html = f'<div class="jumbo-form"><span class="jumbo-form-cap">FORM</span>{dots}</div>'

    odds = f' <span class="jumbo-hero-odds">· {_e(hero["odds"])} PO</span>' if hero.get("odds") else ""
    return (
        f'<div class="{classes}"><div class="jumbo-hero-rule"></div>'
        f'<div class="jumbo-hero-head"><img src="{_e(hero["logo"])}" />'
        f'<div class="jumbo-hero-id"><div class="jumbo-hero-name">{_e(hero["label"])}</div>'
        f'<div class="jumbo-hero-div">{_e(hero["division"])}{odds}</div></div>'
        f'<div class="jumbo-hero-rec"><div class="jumbo-hero-rec-v">{_e(hero["record"])}</div>'
        '<div class="jumbo-hero-rec-c">RECORD</div></div></div>'
        f"{form_html}"
        f'<div class="jumbo-gameline">{line}</div></div>'
    )


def _ufc_rail_hero_render(hero: dict) -> str:
    kind = hero["kind"]
    if kind == "live":
        if hero.get("fighter_a"):
            line = f'LIVE · <b>{_e(hero["fighter_a"])}</b> vs <b>{_e(hero["fighter_b"])}</b>'
        else:
            line = "LIVE"
    elif kind == "underway":
        line = "Card underway"
    elif kind == "countdown":
        line = f'Starts <span class="jumbo-gl-cd">{_countdown_html(hero["countdown"])}</span>'
    elif kind == "scheduled":
        line = f'<span class="jumbo-quiet">{_e(hero["date_text"])} · {_e(hero["countdown_text"])}</span>'
    else:
        line = '<span class="jumbo-quiet">No event scheduled</span>'
    live_cls = " jumbo-hero-live" if kind == "live" else ""
    return (
        f'<div class="jumbo-hero jumbo-hero-ufc{live_cls}"><div class="jumbo-hero-rule"></div>'
        '<div class="jumbo-hero-head"><div class="jumbo-hero-id">'
        '<div class="jumbo-hero-name">UFC</div>'
        f'<div class="jumbo-hero-div">{_e(hero["detail"])}</div></div></div>'
        f'<div class="jumbo-gameline">{line}</div></div>'
    )


_LINEUP_HEADER = (
    '<div class="jumbo-lineup-head-row">'
    '<span class="jumbo-lineup-num">#</span>'
    '<span class="jumbo-lineup-name">PLAYER</span>'
    '<span class="jumbo-lineup-pos">POS</span>'
    '<span class="jumbo-lineup-ab">AB</span>'
    '<span class="jumbo-lineup-ops">OPS</span>'
    "</div>"
)


def _batting_order_render(data: dict) -> str:
    """The batting order for whichever team is at bat — jersey number,
    player, position, this game's line, and OPS colored by real league
    percentile tier. The current batter gets a left accent bar rather
    than a full-row wash, specifically so it doesn't fight the tier
    color sitting in the same row."""
    team = data["team"]
    head = (
        f'<div class="jumbo-lineup-head" style="--side-rgb:{_rgb(data["accent_rgb"])}">'
        f'<div class="jumbo-lineup-head-rule"></div>'
        f'<img class="jumbo-lineup-logo" src="{_e(team["logo"])}" />'
        '<div class="jumbo-lineup-headtext">'
        f'<div class="jumbo-lineup-team">{_e(team["name"])}</div>'
        '<div class="jumbo-lineup-atbat">At Bat</div>'
        "</div></div>"
    )
    rows = []
    for row in data["rows"]:
        e = row["entry"]
        row_cls = "jumbo-lineup-row" + (" jumbo-lineup-row-on" if row["is_current"] else "")
        ops_cls = "jumbo-lineup-ops" + (f" jumbo-lineup-ops-{row['tier']}" if row["tier"] else "")
        rows.append(
            f'<div class="{row_cls}">'
            f'<span class="jumbo-lineup-num">{_e(e.get("number") or "")}</span>'
            f'<span class="jumbo-lineup-name">{_e(e["short_name"].upper())}</span>'
            f'<span class="jumbo-lineup-pos">{_e(e.get("position") or "")}</span>'
            f'<span class="jumbo-lineup-ab">{_e(e.get("game_line") or "")}</span>'
            f'<span class="{ops_cls}">{_e(e.get("ops") or "—")}</span>'
            "</div>"
        )
    return f'{head}{_LINEUP_HEADER}{"".join(rows)}'


# --------------------------------------------------------------------
# Around The Leagues / standings
# --------------------------------------------------------------------

def _mini_row_render(row: dict) -> str:
    g, state = row["game"], row["state"]
    row_cls = "jumbo-mini" + (" jumbo-mini-live" if state == "in" else " jumbo-mini-final" if state == "post" else "")

    def team_row(side: dict) -> str:
        score = "" if state == "pre" else (side.get("score") or "")
        logo = f'<img src="{_e(side["logo"])}" />' if side.get("logo") else ""
        record = f'<span class="jumbo-mini-rec">{_e(side["record"])}</span>' if side.get("record") else ""
        return (
            f'<div class="jumbo-mini-team">{logo}'
            f'<span class="jumbo-mini-abbr">{_e(side.get("abbr") or "")}</span>{record}'
            f'<span class="jumbo-mini-score">{_e(score)}</span></div>'
        )

    leader = row.get("leader")
    leader_html = (
        f'<div class="jumbo-mini-leader">★ {_e(leader["name"])} '
        f'<span class="jumbo-mini-leader-stat">{_e(leader["stat_line"])}</span></div>'
        if leader
        else ""
    )
    return (
        f'<div class="{row_cls}"><div class="jumbo-mini-teams">'
        f'{team_row(g["away"])}{team_row(g["home"])}{leader_html}</div>'
        f'<div class="jumbo-mini-status">{_e(row["status_text"])}</div></div>'
    )


def _ufc_pinned_row_render(bout: dict) -> str:
    """A .jumbo-mini-shaped row for a pinned live UFC bout — fighters
    instead of teams, round/clock instead of a score. Reuses the same
    classes so it sits flush in the same grid as the team rows."""

    def fighter(f: dict) -> str:
        record = f'<span class="jumbo-mini-rec">{_e(f["record"])}</span>' if f.get("record") else ""
        return f'<div class="jumbo-mini-team"><span class="jumbo-mini-abbr">{_e(f["short_name"])}</span>{record}</div>'

    status = f'Rd {bout["round"]} · {bout["clock"]}'.strip(" ·") if bout.get("round") else "Live"
    return (
        '<div class="jumbo-mini jumbo-mini-live"><div class="jumbo-mini-teams">'
        f'{fighter(bout["fighter_a"])}{fighter(bout["fighter_b"])}</div>'
        f'<div class="jumbo-mini-status">{_e(status)}</div></div>'
    )


def _around_render(around: dict | None) -> str:
    if not around:
        return ""
    rows = "".join(_mini_row_render(r) for r in around["rows"])
    return (
        '<section class="jumbo-panel jumbo-around">'
        f'{_panel_header("Around The Leagues", _e(around["label"]))}'
        f'<div class="jumbo-around-body">{rows}</div>'
        "</section>"
    )


def _standings_render(standings: dict | None) -> str:
    if not standings:
        return ""
    rows = "".join(
        f'<div class="jumbo-st-row{" jumbo-st-row-us" if r["is_team"] else ""}">'
        f'<span class="jumbo-st-rank">{_e(r["rank"])}</span>'
        + (f'<img class="jumbo-st-logo" src="{_e(r["logo"])}" />' if r.get("logo") else "")
        + f'<span class="jumbo-st-team">{_e(r["team"])}</span>'
        f'<span class="jumbo-st-rec">{_e(r["wins"])}-{_e(r["losses"])}</span>'
        f'<span class="jumbo-st-extra">{_e(r["extra"])}</span>'
        + (
            f'<span class="jumbo-st-odds">{_e((r.get("odds") or {})["display"])} PO</span>'
            if (r.get("odds") or {}).get("display")
            else ""
        )
        + "</div>"
        for r in standings["rows"]
    )
    title = f'{standings["league"]} · {standings["division"]}{standings["page_label"]}'
    return (
        '<section class="jumbo-panel jumbo-standings-panel">'
        f'{_panel_header(title)}'
        f'<div class="jumbo-st-body"><div class="jumbo-st">{rows}</div></div>'
        "</section>"
    )


# --------------------------------------------------------------------
# Presence-gated full-screen overlay
#
# Emitted ONLY on the reruns its data function says it belongs on. No
# CSS rule gives it a resting opacity:0/visibility:hidden — if the div
# is in the DOM it is visible, full stop.
# --------------------------------------------------------------------

def _between_play_render(data: dict | None) -> str:
    if not data:
        return ""
    pinned = ""
    if data["pinned_rows"] or data["pinned_bout"]:
        rows = "".join(_mini_row_render(r) for r in data["pinned_rows"])
        if data["pinned_bout"]:
            rows += _ufc_pinned_row_render(data["pinned_bout"])
        pinned = f'<div class="jumbo-otc-league">Pinned</div><div class="jumbo-otc-grid">{rows}</div>'
    rows_html = "".join(_mini_row_render(r) for r in data["rows"])
    timer = (
        f'<div class="jumbo-otc-timer live-countdown" data-target-ms="{data["target_ms"]}" '
        f'data-format="clock">{_e(data["timer_text"])}</div>'
    )
    return (
        '<div class="jumbo-otc-overlay"><div class="jumbo-otc-inner">'
        '<div class="jumbo-otc-title">Out Of Town Scoreboard</div>'
        f'<div class="jumbo-otc-sub">{_e(data["headline"])}</div>'
        f'<div class="jumbo-otc-timer-block">{timer}'
        f'<div class="jumbo-otc-timer-cap">{_e(data["timer_label"])}</div></div>'
        f"{pinned}"
        f'<div class="jumbo-otc-league">{_e(data["page_label"])}</div>'
        f'<div class="jumbo-otc-grid">{rows_html}</div>'
        "</div></div>"
    )


# --------------------------------------------------------------------
# UFC board
# --------------------------------------------------------------------

def _ufc_fighter_render(fighter: dict, profile: dict | None, is_winner: bool, corner: str, knockdowns: int) -> str:
    """One side of the hero face-off. `corner` ("a"/"b") is the same
    red/blue pair the stat bars use — a broadcast convention, not each
    fighter's real color: checked live, no such data exists anywhere in
    ESPN's UFC feed. Every optional line omits itself when the profile
    fetch failed rather than showing a broken image."""
    classes = f"jumbo-ufc-fighter jumbo-ufc-corner-{corner}" + (" jumbo-ufc-winner" if is_winner else "")
    photo = ""
    if profile and profile.get("headshot"):
        flag = f'<img class="jumbo-ufc-flag" src="{_e(fighter["flag"])}" />' if fighter.get("flag") else ""
        photo = (
            '<div class="jumbo-ufc-photowrap">'
            f'<img class="jumbo-ufc-photo" src="{_e(profile["headshot"])}" '
            "onerror=\"this.parentElement.style.display='none'\" />"
            f"{flag}</div>"
        )
    nickname = (
        f'<div class="jumbo-ufc-nick">&ldquo;{_e(profile["nickname"])}&rdquo;</div>'
        if profile and profile.get("nickname")
        else ""
    )
    methods = []
    if profile:
        for key, cap in (("wins_ko", "KO"), ("wins_sub", "SUB"), ("wins_dec", "DEC")):
            if profile.get(key):
                methods.append(f'{profile[key]} {cap}')
    method_html = f'<div class="jumbo-ufc-method">{_e(" · ".join(methods))}</div>' if methods else ""
    record = f'<span class="jumbo-ufc-record">{_e(fighter["record"])}</span>' if fighter.get("record") else ""
    kd = f'<span class="jumbo-ufc-kd">KD ×{knockdowns}</span>' if knockdowns > 0 else ""
    return (
        f'<div class="{classes}"><div class="jumbo-ufc-corner-rule"></div>'
        f"{photo}"
        f'<div class="jumbo-ufc-name">{_e(fighter["name"])}</div>'
        f"{nickname}"
        f'<div class="jumbo-ufc-recordline">{record}{kd}</div>'
        f"{method_html}"
        "</div>"
    )


def _ufc_phase_render(phase_line: dict) -> str:
    kind = phase_line["kind"]
    if kind == "countdown":
        return f'<div class="jumbo-ufc-phase">STARTS IN {_countdown_html(phase_line["countdown"])}</div>'
    if kind == "recent":
        return (
            f'<div class="jumbo-ufc-phase jumbo-ufc-phase-live jumbo-ufc-recent-{_e(phase_line["accent"])}">'
            f'{_e(phase_line["text"])}</div>'
        )
    if kind == "live":
        return f'<div class="jumbo-ufc-phase jumbo-ufc-phase-live">{_e(phase_line["text"])}</div>'
    return f'<div class="jumbo-ufc-phase">{_e(phase_line["text"])}</div>'


def _ufc_bout_status_render(bout: dict) -> str:
    """Plain "Upcoming", "LIVE · Rn M:SS" or "FINAL · Rn M:SS" — the
    winner is shown by highlighting their name in the row, not repeated
    here, and no finishing method (deliberately not guessed)."""
    if bout["state"] == "live":
        return f'<span class="jumbo-ufc-row-live">LIVE · R{_e(bout["round"])} {_e(bout["clock"])}</span>'
    if bout["state"] == "final":
        return f'<span class="jumbo-ufc-row-final">FINAL · R{_e(bout["round"])} {_e(bout["clock"])}</span>'
    return '<span class="jumbo-ufc-row-up">Upcoming</span>'


def _ufc_card_row_render(bout: dict) -> str:
    a, b = bout["fighter_a"], bout["fighter_b"]
    row_cls = "jumbo-ufc-row" + (" jumbo-ufc-row-main" if bout["is_main_event"] else "")
    a_cls = "jumbo-ufc-row-fighter" + (" jumbo-ufc-winner" if a["winner"] else "")
    b_cls = "jumbo-ufc-row-fighter" + (" jumbo-ufc-winner" if b["winner"] else "")
    return (
        f'<div class="{row_cls}">'
        f'<span class="jumbo-ufc-row-weight">{_e(bout["weight_class"])}</span>'
        f'<span class="{a_cls}">{_e(a["short_name"])}</span>'
        '<span class="jumbo-ufc-row-vs">vs</span>'
        f'<span class="{b_cls}">{_e(b["short_name"])}</span>'
        f'<span class="jumbo-ufc-row-status">{_ufc_bout_status_render(bout)}</span>'
        "</div>"
    )


def _ufc_board_render(board: dict) -> str:
    tot = ""
    if board["tale_of_tape"]:
        cells = "".join(
            '<div class="jumbo-ufc-tot-cell">'
            f'<span class="jumbo-ufc-tot-a">{_e(c["a"])}</span>'
            f'<span class="jumbo-ufc-tot-cap">{_e(c["label"])}</span>'
            f'<span class="jumbo-ufc-tot-b">{_e(c["b"])}</span>'
            "</div>"
            for c in board["tale_of_tape"]
        )
        tot = f'<div class="jumbo-ufc-tot">{cells}</div>'

    stats = ""
    if board["stat_rows"]:
        rows = "".join(
            '<div class="jumbo-ufc-stat-row">'
            f'<div class="jumbo-ufc-stat-cap">{_e(r["label"])}</div>'
            '<div class="jumbo-ufc-stat-line">'
            f'<div class="jumbo-ufc-stat-v jumbo-ufc-stat-va">{_e(r["a_display"])}</div>'
            '<div class="jumbo-ufc-stat-bar">'
            f'<div class="jumbo-ufc-seg jumbo-ufc-seg-a" style="width:{r["a_pct"]}%"></div>'
            f'<div class="jumbo-ufc-seg jumbo-ufc-seg-b" style="width:{r["b_pct"]}%"></div>'
            "</div>"
            f'<div class="jumbo-ufc-stat-v jumbo-ufc-stat-vb">{_e(r["b_display"])}</div>'
            "</div>"
            f'<div class="jumbo-ufc-stat-names"><span>{_e(r["a_short"])}</span>'
            f'<span>{_e(r["b_short"])}</span></div>'
            "</div>"
            for r in board["stat_rows"]
        )
        stats = f'<div class="jumbo-ufc-stats">{rows}</div>'

    card_rows = "".join(_ufc_card_row_render(b) for b in board["card_bouts"])
    venue = _e(board["venue"]) if board["venue"] else ""

    return (
        '<div class="jumbo-grid jumbo-ufc-grid">'
        '<section class="jumbo-panel jumbo-ufc-hero-panel">'
        f'{_panel_header(board["event_name"], venue)}'
        '<div class="jumbo-ufc-hero-body">'
        f'{_ufc_phase_render(board["phase_line"])}'
        '<div class="jumbo-ufc-hero">'
        f'{_ufc_fighter_render(board["fighter_a"], board["profile_a"], board["a_winner"], "a", board["a_knockdowns"])}'
        '<div class="jumbo-ufc-mid">'
        f'<div class="jumbo-ufc-weight">{_e(board["weight_class"])}</div>'
        '<div class="jumbo-ufc-vs">VS</div>'
        "</div>"
        f'{_ufc_fighter_render(board["fighter_b"], board["profile_b"], board["b_winner"], "b", board["b_knockdowns"])}'
        "</div>"
        f"{tot}{stats}"
        "</div></section>"
        '<section class="jumbo-panel jumbo-ufc-card-panel">'
        f'{_panel_header(board["card_label"])}'
        f'<div class="jumbo-ufc-card-body">{card_rows}</div>'
        "</section></div>"
    )


# --------------------------------------------------------------------
# Marquee + page shell
# --------------------------------------------------------------------

def _marquee_render(m: dict) -> str:
    wx = ""
    if m["temp"] is not None:
        wx = (
            f'<div class="jumbo-wx"><span class="jumbo-wx-temp">{m["temp"]:.0f}°</span>'
            '<span class="jumbo-wx-loc">CORBEIL</span></div>'
        )
    return (
        '<header class="jumbo-marquee">'
        '<div class="jumbo-brand">FANCAVE<span>JUMBOTRON</span></div>'
        f'<div class="jumbo-clock">{_e(m["clock"])}<em>{_e(m["meridiem"])}</em></div>'
        f'<div class="jumbo-dateline">{_e(m["dateline"])}</div>'
        f'<div class="jumbo-spacer"></div>{wx}</header>'
    )


# --------------------------------------------------------------------
# Controls (real Streamlit widgets — the only interactive UI in the app)
# --------------------------------------------------------------------

@st.fragment
def _delay_stepper() -> None:
    """The live-data delay control, in its own fragment — session
    report: tapping +/- felt unresponsive, "only updates when the page
    updates after the 5 second pause." A plain widget here reruns the
    WHOLE jumbotron page (every fetch, every HTML block) before the
    change shows up, and a tap landing mid-rerun gets silently dropped.
    A fragment's rerun only re-executes this function.

    Do NOT remove the @st.fragment decorator — that unresponsiveness was
    a real, previously-fixed bug.

    Session follow-up: "make it so i can type my ideal stream delay
    please. the plus/minus boxes are finnicky" — this kiosk is a
    touchscreen with no physical keyboard, and tapping into a native
    number field brings up the OS's own numeric keypad. `value=delay`
    only seeds the widget's very first render for its key; Streamlit
    tracks live edits in session_state from there, so this doesn't fight
    in-progress typing on the fragment's later reruns.

    No explicit st.rerun(scope="fragment") — confirmed live that raises
    StreamlitAPIException here, and a number_input's changed value
    already triggers Streamlit's own fragment-scoped rerun."""
    delay = sports_client.get_live_delay_seconds()
    st.markdown('<div class="jumbo-delay-label">DELAY</div>', unsafe_allow_html=True)
    new_delay = st.number_input(
        "Delay", min_value=0, max_value=60, step=5, value=delay,
        key="jumbotron_delay_input", label_visibility="collapsed",
    )
    if new_delay != delay:
        sports_client.set_live_delay_seconds(int(new_delay))


def _controls(state: dict) -> None:
    """Bottom-left control cluster — session request: "an end session
    button... that closes out the game session," later "can you make
    [the live-data delay] a setting i can adjust throughout the game."
    Grouped in one st.container(key=...) so theme.py can lay them out as
    a single fixed-position row via that key's own class."""
    if not state.get("game"):
        return
    with st.container(key="jumbotron_controls"):
        if st.button("✕ End Session", key="jumbotron_end_session_btn"):
            # Setting the dismissal flag alone wouldn't take effect
            # until the next autorefresh — st.rerun() makes the takeover
            # drop the instant this is clicked.
            st.session_state["jumbotron_dismissed_game_id"] = state["game"]["game_id"]
            st.rerun()
        _delay_stepper()


# --------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------

def _render_ufc(now: datetime, ufc_state: dict, weather: dict | None) -> None:
    """A UFC takeover shares only the marquee with the team board —
    everything under it is its own two-row grid, since a fight card is a
    genuinely different data shape from one team's evolving score."""
    data = jd.ufc_page_data(now, ufc_state, weather)
    st.markdown(
        '<div class="jumbo-root">'
        f'{_marquee_render(data["marquee"])}'
        f'{_ufc_board_render(data["board"])}'
        "</div>",
        unsafe_allow_html=True,
    )


def render(now: datetime, state: dict | None, weather: dict | None, ufc_state: dict | None = None) -> None:
    """`state` is sports_alerts.takeover_state()'s own return value —
    passed in rather than re-derived here so app.py's routing decision
    and this page's content can never disagree about which game owns the
    screen. `ufc_state` takes over entirely when set (app.py has already
    resolved the "Habs playing" exception before it's passed in)."""
    if ufc_state is not None:
        _render_ufc(now, ufc_state, weather)
        return
    if not state:
        # A fragment tick can outlive the takeover that started it by up
        # to one outer-rerun cycle. Nothing to draw; the outer script
        # routes away on its own next pass.
        return

    data = jd.page_data(now, state, weather)

    if data["batting_order"]:
        rail_title = "Batting Order"
        rail_body = _batting_order_render(data["batting_order"])
    else:
        rail_title = "My Teams"
        rail_body = "".join(_rail_hero_render(h) for h in data["rail"]["teams"])
        rail_body += _ufc_rail_hero_render(data["rail"]["ufc"])

    st.markdown(
        '<div class="jumbo-root">'
        f'{_marquee_render(data["marquee"])}'
        '<div class="jumbo-grid">'
        '<div class="jumbo-col-rail">'
        '<section class="jumbo-panel jumbo-rail">'
        f'{_panel_header(rail_title)}'
        f'<div class="jumbo-rail-body">{rail_body}</div>'
        "</section>"
        f'{_standings_render(data["standings"])}'
        "</div>"
        f'{_board_render(data["board"])}'
        f'{_around_render(data["around"])}'
        "</div>"
        f'{_between_play_render(data["between_play"])}'
        "</div>",
        unsafe_allow_html=True,
    )

    _controls(state)
