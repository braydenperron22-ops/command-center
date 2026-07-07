"""Watchlist page: yfinance price history + classic technical indicators
(technical_analysis.py) rendered as the same tile language used
everywhere else in the app — tone-colored accent strip, sparkline,
badge, metric rows.

The one interactive element in an otherwise passive kiosk display: a
text input to edit the tracked tickers, persisted via watchlist_store so
every device hitting this app sees the same list, not just whichever
browser session happens to be open.
"""

import streamlit as st

import technical_analysis as ta
import tiles
import watchlist_store
from config import MAX_WATCHLIST_SHOWN, WATCHLIST_ROW_SIZE

TONE_LABEL = {"good": "BULLISH", "bad": "BEARISH", "neutral": "NEUTRAL"}
ZONE_LABEL = {"entry": "ACCUMULATION ZONE", "exit": "TRIM ZONE"}
ZONE_CAPTION = {
    "entry": "Near support, pulled back, RSI cooling — confluence favors adding",
    "exit": "Near resistance, extended, RSI hot — confluence favors trimming",
}


def _metric_row(label: str, value: str) -> str:
    return (
        f'<div class="market-metric"><span class="market-metric-label">{label}</span>'
        f'<span class="market-metric-value">{value}</span></div>'
    )


def _render_tile(symbol: str) -> None:
    analysis = ta.analyze(symbol)
    if not analysis:
        st.markdown(
            f"""<div class="tile">
                <div class="tile-label">{symbol}</div>
                <div class="tile-prev">data unavailable</div>
            </div>""",
            unsafe_allow_html=True,
        )
        return

    tone = analysis["tone"]
    zone = analysis["zone"]
    accent_class = f"tile-accent-{tone}"
    badge_class = f"badge-{tone}"
    sparkline = tiles.sparkline_svg(analysis["history"], tone)
    target_caption = (
        "Expected trading range (support–resistance)" if tone == "neutral"
        else "Resistance + Fibonacci extension + trend confluence"
    )

    zone_html = ""
    if zone:
        zone_html = f"""<div class="zone-banner zone-{zone}">{ZONE_LABEL[zone]}</div>
            <div class="severity-caption">{ZONE_CAPTION[zone]}</div>"""

    st.markdown(
        f"""<div class="tile {accent_class}">
            <div class="tile-label">{symbol}</div>
            <div class="tile-value-row">
                <div class="tile-value">${analysis['price']:.2f}</div>{sparkline}
            </div>
            <div class="badge {badge_class}">{TONE_LABEL[tone]}</div>
            {zone_html}
            {_metric_row("RSI (14)", f"{analysis['rsi']:.0f}")}
            {_metric_row("Support", f"${analysis['support']:.2f}")}
            {_metric_row("Resistance", f"${analysis['resistance']:.2f}")}
            {_metric_row("Target Range", f"${analysis['target_low']:.2f} – ${analysis['target_high']:.2f}")}
            <div class="severity-caption">{target_caption}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def render() -> None:
    st.markdown('<div class="page-title page-title-watchlist">Watchlist</div>', unsafe_allow_html=True)

    tickers = watchlist_store.load()

    with st.form("watchlist_form", clear_on_submit=False):
        raw = st.text_input(
            "Tickers (comma-separated)",
            value=", ".join(tickers),
            key="watchlist_input",
        )
        submitted = st.form_submit_button("Update Watchlist")
    if submitted:
        new_tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
        if new_tickers:
            watchlist_store.save(new_tickers)
            tickers = new_tickers

    tickers = tickers[:MAX_WATCHLIST_SHOWN]
    if not tickers:
        st.markdown(
            '<div class="tile"><div class="tile-prev">No tickers in your watchlist yet — add some above.</div></div>',
            unsafe_allow_html=True,
        )
        return

    for row_start in range(0, len(tickers), WATCHLIST_ROW_SIZE):
        row_tickers = tickers[row_start:row_start + WATCHLIST_ROW_SIZE]
        cols = st.columns(len(row_tickers))
        for col, symbol in zip(cols, row_tickers):
            with col:
                _render_tile(symbol)
