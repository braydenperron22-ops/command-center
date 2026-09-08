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

import streamlit as st

import brayden_index
import tiles

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

    hero_col, chart_col = st.columns([1, 2])
    with hero_col:
        st.markdown(
            f'<div class="tile">'
            f'<div class="tile-label">BRDN</div>'
            f'<div class="tile-value-row">'
            f'<div class="tile-value {direction_class}" style="font-size:2.8rem;">${data["price"]:.2f}</div>'
            f'</div>'
            f'<div class="tile-prev {direction_class}">'
            f'{arrow} {sign}${abs(data["change"]):.2f} ({sign}{data["pct_change"]:.2f}%) this cycle'
            f'</div>'
            f'<div class="badge badge-{sentiment_tone}" style="margin-top:0.6rem;">{html.escape(sentiment)}</div>'
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
