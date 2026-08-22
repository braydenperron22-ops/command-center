"""Markets page: intraday / 1-month / YTD % change for indices/FX/
commodities/crypto, via yfinance (market_yf_client.py).

Which instruments show swaps by market status: real indices during
NYSE/TSX hours, futures outside those hours (still live), crypto on
weekends (the only thing actually moving when nothing else is open).
Gold/crude/USD-CAD are always shown via their own always-appropriate
quote (futures for commodities, spot for FX) regardless of status.
Intraday gets the same hero-value treatment as the macro tiles' current
reading, with 1M/YTD as secondary rows and a full year of daily closes
as a trend chart below — matches the Home page's visual hierarchy
instead of treating all three timeframes (or the trend) equally.

A Polymarket-derived weekend forecast (a synthetic SPY tile, plus an
override of the oil tile) briefly lived here — session request: "get
rid of the market implied weekend moves and just resort to Bitcoin,
Ethereum, whatever, the main cryptos." Removed; weekend now shows the
same plain crypto lineup (config.py's MARKET_INSTRUMENTS_WEEKEND) every
other status shows its own instruments, no forecast tile, no special
casing for oil.
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
        label = inst["label"]
        quote = market_yf_client.quote_for(inst["symbol"])
        with cols[i]:
            if not quote or quote["intraday"] is None:
                st.markdown(
                    f"""<div class="tile market-tile">
                        <div class="tile-label">{label}</div>
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
            caption = "Intraday change"

            # Session request: "change the three standard deviation
            # rule... if the market is trading outside of that band...
            # this should be flagged on the markets page." VIX/16 (see
            # market_yf_client.volatility_band_status) only really means
            # anything for the S&P itself — no equivalent band exists
            # for Dow/Nasdaq/TSX/commodities/FX here — so this only ever
            # fires on the "sp500" tile (real index or its futures,
            # whichever this slot is currently showing). Reuses
            # .tile-significant, the same quiet widened-accent-strip cue
            # the macro indicator tiles already use for "significant
            # move vs trend" rather than inventing a second visual
            # language for "this number is notable."
            band = market_yf_client.volatility_band_status(intraday) if inst["key"] == "sp500" else None
            significant_class = "tile-significant" if band and band["outside_band"] else ""
            trend_caption = "1-year trend"
            if band and band["outside_band"]:
                trend_caption += f' · outside priced-in range (±{band["expected_move_pct"]:.2f}%)'

            st.markdown(
                f"""<div class="tile market-tile {accent_class} {significant_class}">
                    <div class="tile-label">{label}</div>
                    <div class="tile-value market-hero-value {direction_class}">{sign}{intraday:.2f}%</div>
                    <div class="tile-prev">{caption}</div>
                    {_metric_row("1 Month", quote["one_month"])}
                    {_metric_row("YTD", quote["ytd"])}
                    <div class="market-sparkline-wrap">{sparkline}</div>
                    <div class="severity-caption">{trend_caption}</div>
                </div>""",
                unsafe_allow_html=True,
            )
