"""The Brayden Index (BRDN) page — see brayden_index.py for the actual
"market" (the periodic AI repricing, catalysts, evolving expectations).
This module only ever reads that already-computed state (current(),
history(), last_report(), expectations()) — no AI/network cost of its
own, safe on every rerun, same contract pages_portfolio.py's render()
already has.

Visual language deliberately reuses this app's existing tile/badge/
market-up/market-down classes (theme.py) rather than adding new CSS —
this is meant to read as a legitimate financial-market tile among the
app's other financial pages (Portfolio, Markets), not a separate
visual style bolted on."""

import html
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

import brayden_index
import tiles
from config import TIMEZONE

_SENTIMENT_TONE = {"Bullish": "good", "Bearish": "bad", "Neutral": "neutral", "Mixed": "neutral"}
_DIRECTION_COLOR = {"bullish": "#32D74B", "bearish": "#FF6961"}
_MAGNITUDE_WEIGHT = {"minor": 1, "moderate": 2, "major": 3}


def _catalyst_row(catalyst: dict) -> str:
    color = _DIRECTION_COLOR.get(catalyst["direction"], "#9BA0AC")
    arrow = "▲" if catalyst["direction"] == "bullish" else "▼"
    weight = _MAGNITUDE_WEIGHT.get(catalyst["magnitude"], 2)
    # A row of filled/empty dots for the magnitude — a glance-able
    # "how much did this matter" signal without pretending the false
    # numeric precision the user's own request explicitly didn't want
    # ("these should not necessarily be rigid numerical components").
    dots = "".join("●" if i < weight else "○" for i in range(3))
    label = html.escape(catalyst["label"])
    note = html.escape(catalyst.get("note", ""))
    note_html = f'<div class="tile-prev" style="margin-top:0.1rem;">{note}</div>' if note else ""
    return (
        f'<div style="padding:0.5rem 0; border-bottom:1px solid rgba(255,255,255,0.08);">'
        f'<div style="display:flex; justify-content:space-between; align-items:baseline;">'
        f'<span style="color:{color}; font-weight:600;">{arrow} {label}</span>'
        f'<span style="color:{color}; letter-spacing:0.1em;">{dots}</span>'
        f'</div>{note_html}</div>'
    )


def render() -> None:
    st.markdown('<div class="page-title page-title-portfolio">Brayden Index</div>', unsafe_allow_html=True)

    data = brayden_index.current()
    price_history = brayden_index.history()
    report = brayden_index.last_report()

    tone = data["tone"]
    direction_class = "market-up" if tone == "good" else "market-down" if tone == "bad" else ""
    arrow = "▲" if tone == "good" else "▼" if tone == "bad" else "●"
    sign = "+" if data["change"] >= 0 else ""

    # Session report: "it's showing up 0.3%... that's over the hour,
    # not the day's return... meanwhile it's still down from where it
    # opened today." data["change"]/["pct_change"] are the day's real
    # cumulative move now (see brayden_index._day_open_price) — this
    # secondary line shows the LAST cycle's own move separately
    # (data["cycle_pct_change"]) specifically so the two numbers never
    # get conflated again the way they silently were before.
    cycle_pct = data["cycle_pct_change"]
    cycle_sign = "+" if cycle_pct >= 0 else ""
    cycle_class = "market-up" if cycle_pct > 0 else "market-down" if cycle_pct < 0 else ""

    sparkline_html = ""
    if len(price_history) >= 2:
        trend_tone = "good" if price_history[-1] >= price_history[0] else "bad"
        # A real full-width chart, not the tiny inline tile sparkline —
        # this is meant to be the "signature feature" centerpiece, same
        # zero-dependency inline-SVG technique as tiles.sparkline_svg
        # (see that function's own docstring), just sized for it.
        sparkline_html = tiles.sparkline_svg(price_history, trend_tone, width=640, height=140)

    sentiment = data["sentiment"]
    sentiment_tone = _SENTIMENT_TONE.get(sentiment, "neutral")

    # Session request: "when does the AI reprice... a little gauge to
    # show when the next reprice is." An honest estimate, not a
    # countdown clock — see brayden_index.next_reprice_estimate's own
    # docstring for why this can land a minute or two late in practice.
    # Server-computed and re-rendered each outer rerun (~65-120s), same
    # as everything else on this page — no client-side ticking needed
    # for something this coarse. No CSS transition on the fill bar
    # below on purpose — theme.py's own global animation kill switch
    # would just neuter it anyway (see that file's own docstring), so
    # it's left out rather than shipped as dead code. night_mode_active
    # defaults to False here on purpose, not threaded through from
    # app.py — this page can only ever actually render while night mode
    # is NOT active (night mode overrides page routing before this
    # dispatch branch is ever reached), so False is always correct by
    # construction, not an assumption.
    reprice = brayden_index.next_reprice_estimate()
    minutes_until = int(reprice["seconds_until"] // 60)
    if reprice["due"]:
        reprice_text = "Repricing due any moment"
    elif minutes_until < 1:
        reprice_text = "Repricing in under a minute"
    elif minutes_until == 1:
        reprice_text = "Next repricing in ~1 min"
    else:
        reprice_text = f"Next repricing in ~{minutes_until} min"
    fill_pct = reprice["pct_elapsed"] * 100

    hero_col, chart_col = st.columns([1, 2])
    with hero_col:
        st.markdown(
            f'<div class="tile">'
            f'<div class="tile-label">BRDN</div>'
            f'<div class="tile-value-row">'
            f'<div class="tile-value {direction_class}" style="font-size:2.8rem;">${data["price"]:.2f}</div>'
            f'</div>'
            f'<div class="tile-prev {direction_class}">'
            f'{arrow} {sign}${abs(data["change"]):.2f} ({sign}{data["pct_change"]:.2f}%) today'
            f'</div>'
            f'<div class="tile-prev {cycle_class}" style="opacity:0.7; font-size:0.85em;">'
            f'{cycle_sign}{cycle_pct:.2f}% last cycle'
            f'</div>'
            f'<div class="badge badge-{sentiment_tone}" style="margin-top:0.6rem;">{html.escape(sentiment)}</div>'
            f'<div class="tile-label" style="margin-top:1rem;">{html.escape(reprice_text).upper()}</div>'
            f'<div style="margin-top:0.35rem; height:6px; border-radius:3px; '
            f'background:rgba(255,255,255,0.1); overflow:hidden;">'
            f'<div style="height:100%; width:{fill_pct:.1f}%; border-radius:3px; '
            f'background:#5AC8FA;"></div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with chart_col:
        st.markdown(
            f'<div class="tile"><div class="tile-label">PRICE HISTORY</div>'
            f'<div style="margin-top:0.4rem;">{sparkline_html}</div></div>',
            unsafe_allow_html=True,
        )

    if report is None:
        st.markdown(
            '<div class="tile"><div class="tile-prev">'
            "Just IPO'd — the market's first real read on Brayden lands within the hour."
            "</div></div>",
            unsafe_allow_html=True,
        )
        return

    commentary_col, catalyst_col = st.columns(2)
    with commentary_col:
        commentary = html.escape(report.get("commentary", ""))
        expectations_text = html.escape(brayden_index.expectations())
        st.markdown(
            f'<div class="tile"><div class="tile-label">SHAREHOLDER COMMENTARY</div>'
            f'<div style="font-style:italic; margin-top:0.5rem; line-height:1.5;">"{commentary}"</div>'
            f'<div class="tile-label" style="margin-top:1rem;">WHAT THE MARKET BELIEVES</div>'
            f'<div class="tile-prev" style="margin-top:0.3rem; line-height:1.5;">{expectations_text}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with catalyst_col:
        catalysts = report.get("catalysts") or []
        rows = "".join(_catalyst_row(c) for c in catalysts) or '<div class="tile-prev">No named catalysts this cycle.</div>'
        st.markdown(
            f'<div class="tile"><div class="tile-label">WHY BRDN MOVED</div>'
            f'<div style="margin-top:0.4rem;">{rows}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="tile-prev" style="text-align:center; margin-top:0.4rem; opacity:0.6;">'
        "Simulated — a fictional index for fun, not real financial advice or a real security."
        "</div>",
        unsafe_allow_html=True,
    )

    _render_employment_report_section()


def _render_employment_report_section() -> None:
    """Session request: "let's do it, the quarterly notification... a
    copy of my data on LinkedIn as well as a little verbal update...
    framed as a quarterly employment report." No scraping happens
    anywhere (see brayden_index.py's own comment on why) — this is the
    self-serve filing spot the quarterly ntfy nudge points at. What's
    typed here lands in brayden_index.record_employment_report and
    feeds the NEXT repricing cycle as a real, fresh signal (see
    _gather_signals' own employment-report block) — filing it doesn't
    force a big move on its own; the market still decides whether
    what's actually in it is genuinely new news or nothing much
    changed, same as everything else BRDN reacts to."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    status = brayden_index.quarterly_report_status(now)
    report = brayden_index.employment_report()
    quarter = html.escape(status["current_quarter"])

    if status["filed_this_quarter"] and report:
        filed_at = datetime.fromtimestamp(report["filed_at"], tz=ZoneInfo(TIMEZONE))
        filed_label = f"{filed_at.strftime('%b')} {filed_at.day}"
        st.markdown(
            f'<div class="tile" style="margin-top:0.75rem;">'
            f'<div class="tile-label">{quarter} EMPLOYMENT REPORT — ON FILE</div>'
            f'<div class="tile-prev" style="margin-top:0.4rem; line-height:1.5;">{html.escape(report["summary"])}</div>'
            f'<div class="tile-prev" style="margin-top:0.4rem; opacity:0.6;">Filed {filed_label} — '
            "editing below re-files this quarter's report.</div>"
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="tile" style="margin-top:0.75rem;">'
            f'<div class="tile-label">{quarter} EMPLOYMENT REPORT — OUTSTANDING</div>'
            '<div class="tile-prev" style="margin-top:0.4rem; line-height:1.5;">'
            "Pull a copy of your LinkedIn data (Settings &gt; Data Privacy &gt; Get a copy of "
            "your data) and summarize what's changed — role, comp, standing, anything "
            "career-relevant. Nothing changed this quarter is a fine answer too."
            "</div></div>",
            unsafe_allow_html=True,
        )

    with st.form("brdn_employment_report_form", clear_on_submit=True):
        summary = st.text_area(
            f"{status['current_quarter']} update",
            placeholder="e.g. Promoted to Senior Advisor, comp bump, hit Q3 targets, LinkedIn shows two new endorsements...",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("File report")
    if submitted:
        if brayden_index.record_employment_report(summary, now):
            st.success(f"{status['current_quarter']} report filed — folded into the next repricing.")
        else:
            st.warning("Enter something before filing.")
