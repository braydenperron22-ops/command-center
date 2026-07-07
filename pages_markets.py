"""Markets page: intraday / 1-month / YTD % change for indices/FX/
commodities/crypto, via yfinance (market_yf_client.py).

Which instruments show swaps by market status: real indices during
NYSE/TSX hours, futures outside those hours (still live), crypto on
weekends. Gold/crude/USD-CAD are always shown via their own always-
appropriate quote (futures for commodities, spot for FX) regardless of
status. Intraday gets the same hero-value treatment as the macro tiles'
current reading, with 1M/YTD as secondary rows and a full year of daily
closes as a trend chart below — matches the Home page's visual hierarchy
instead of treating all three timeframes (or the trend) equally.
"""

import streamlit as st

import market_yf_client
import tiles
from config import (
    MARKET_INSTRUMENTS_ALWAYS,
    MARKET_INSTRUMENTS_CLOSED,
    MARKET_INSTRUMENTS_OPEN,
    MARKET_INSTRUMENTS_WEEKEND,
)

STATUS_INSTRUMENTS = {
    "open": MARKET_INSTRUMENTS_OPEN,
    "closed": MARKET_INSTRUMENTS_CLOSED,
    "weekend": MARKET_INSTRUMENTS_WEEKEND,
}


def _metric_row(label: str, pct: float | None) -> str:
    if pct is None:
        return f'<div class="market-metric"><span class="market-metric-label">{label}</span><span class="market-metric-value">—</span></div>'
    direction_class = "market-up" if pct >= 0 else "market-down"
    sign = "+" if pct >= 0 else ""
    return (
        f'<div class="market-metric"><span class="market-metric-label">{label}</span>'
        f'<span class="market-metric-value {direction_class}">{sign}{pct:.2f}%</span></div>'
    )


def render():
    st.markdown('<div class="page-title page-title-markets">Markets</div>', unsafe_allow_html=True)

    status = market_yf_client.market_status()
    instruments = STATUS_INSTRUMENTS[status] + MARKET_INSTRUMENTS_ALWAYS

    cols = st.columns(len(instruments))
    for i, inst in enumerate(instruments):
        quote = market_yf_client.quote_for(inst["symbol"])
        with cols[i]:
            if not quote or quote["intraday"] is None:
                st.markdown(
                    f"""<div class="tile">
                        <div class="tile-label">{inst['label']}</div>
                        <div class="tile-prev">data unavailable</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
                continue

            intraday = quote["intraday"]
            tone = "good" if intraday >= 0 else "bad"
            direction_class = f"market-{'up' if tone == 'good' else 'down'}"
            accent_class = f"tile-accent-{tone}"
            sign = "+" if intraday >= 0 else ""
            sparkline = tiles.sparkline_svg(quote["history"], tone)

            st.markdown(
                f"""<div class="tile {accent_class}">
                    <div class="tile-label">{inst['label']}</div>
                    <div class="tile-value market-hero-value {direction_class}">{sign}{intraday:.2f}%</div>
                    <div class="tile-prev">Intraday change</div>
                    {_metric_row("1 Month", quote["one_month"])}
                    {_metric_row("YTD", quote["ytd"])}
                    <div class="market-sparkline-wrap">{sparkline}</div>
                    <div class="severity-caption">1-year trend</div>
                </div>""",
                unsafe_allow_html=True,
            )
