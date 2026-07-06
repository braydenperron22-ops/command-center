"""Markets page: intraday / 1-month / YTD % change for indices/FX/commodities.

Intraday gets the same hero-value treatment as the macro tiles' current
reading, with 1M/YTD as secondary rows below — matches the Home page's
visual hierarchy instead of treating all three timeframes equally.
"""

import streamlit as st

import twelvedata_client
from config import MARKET_INSTRUMENTS


def _metric_row(label: str, pct: float | None) -> str:
    if pct is None:
        return f'<div class="market-metric"><span class="market-metric-label">{label}</span><span class="market-metric-value">—</span></div>'
    direction_class = "market-up" if pct >= 0 else "market-down"
    sign = "+" if pct >= 0 else ""
    return (
        f'<div class="market-metric"><span class="market-metric-label">{label}</span>'
        f'<span class="market-metric-value {direction_class}">{sign}{pct:.2f}%</span></div>'
    )


def render(api_key: str):
    st.markdown('<div class="page-title">Markets</div>', unsafe_allow_html=True)

    symbols = tuple(inst["symbol"] for inst in MARKET_INSTRUMENTS)
    quotes = twelvedata_client.fetch_quotes(symbols, api_key)

    cols = st.columns(len(MARKET_INSTRUMENTS))
    for i, inst in enumerate(MARKET_INSTRUMENTS):
        quote = quotes.get(inst["symbol"])
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
            direction_class = "market-up" if intraday >= 0 else "market-down"
            sign = "+" if intraday >= 0 else ""

            st.markdown(
                f"""<div class="tile">
                    <div class="tile-label">{inst['label']}</div>
                    <div class="tile-value {direction_class}">{sign}{intraday:.2f}%</div>
                    <div class="tile-prev">Intraday change</div>
                    {_metric_row("1 Month", quote["one_month"])}
                    {_metric_row("YTD", quote["ytd"])}
                </div>""",
                unsafe_allow_html=True,
            )
