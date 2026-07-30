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

Session request: "both of the simulated forecasts go to the markets
page — SPY takes over Bitcoin for the weekend, in the S&P spot, and
crude oil takes over in the crude oil spot" -> follow-up: "push crypto
over — since we only have Ethereum, Solana, and Dogecoin, we should
have Bitcoin, Ethereum, and Solana, because we're taking over the
Bitcoin spot with the S&P 500 derived." The SPY forecast
(prediction_markets_client.close_forecast_return) is now its own
leading tile on weekends rather than overriding "btc" in place, so
Bitcoin moved back into the real crypto lineup shown alongside it —
Dogecoin dropped from config.py's MARKET_INSTRUMENTS_WEEKEND to keep
the same 4-tile weekend count. The "oil" slot still swaps its live
CL=F intraday move for the same forecast treatment against WTI.
1-month/YTD/the sparkline still come from the real instrument's own
price history (still meaningful over a weekend) for oil; the SPY tile
uses SPY's own real history for the same reason. Only the hero
"intraday" number and its caption become the forecast, labeled as such
rather than passed off as an observed live move.
"""

import streamlit as st

import market_yf_client
import prediction_markets_client
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

# A synthetic leading tile, not a real yfinance instrument — prepended
# ahead of the real weekend crypto lineup rather than overriding one of
# its slots, so Bitcoin/Ethereum/Solana all stay genuinely themselves.
_SPY_FORECAST_INSTRUMENT = {"key": "spy_forecast", "label": "S&P 500 (SPY forecast)"}

# key -> (yfinance symbol for real price history, CLOSE_SERIES key,
# label override) for the weekend slots that get a Polymarket forecast
# instead of their usual quote. The label override keeps this reading
# as a forecast rather than an observed live move even for "oil",
# which otherwise keeps its plain config.py label.
_WEEKEND_FORECAST_SLOTS = {
    "spy_forecast": ("SPY", "spy", None),
    "oil": ("CL=F", "wti", "Crude Oil (forecast)"),
}


def _weekend_forecast_quote(symbol: str, series: str) -> dict | None:
    """The normal quote_for() shape, but with `intraday` replaced by
    Polymarket's own expected-close return against this instrument's
    real last close — 1-month/YTD/the sparkline stay real, since that
    history is still meaningful over a weekend; only the hero number
    (which would otherwise just show a stale ~0% from Friday's already-
    priced-in close) becomes a forward-looking forecast."""
    quote = market_yf_client.quote_for(symbol)
    if not quote or not quote.get("history"):
        return quote
    forecast = prediction_markets_client.close_forecast_return(series, quote["history"][-1])
    if not forecast:
        return quote
    return {**quote, "intraday": forecast["pct_return"]}


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
    if status == "weekend":
        instruments = [_SPY_FORECAST_INSTRUMENT] + STATUS_INSTRUMENTS[status] + MARKET_INSTRUMENTS_ALWAYS
    else:
        instruments = STATUS_INSTRUMENTS[status] + MARKET_INSTRUMENTS_ALWAYS

    cols = st.columns(len(instruments))
    for i, inst in enumerate(instruments):
        forecast_slot = _WEEKEND_FORECAST_SLOTS.get(inst["key"]) if status == "weekend" else None
        if forecast_slot:
            symbol, series, label_override = forecast_slot
            label = label_override or inst["label"]
            quote = _weekend_forecast_quote(symbol, series)
        else:
            label = inst["label"]
            quote = market_yf_client.quote_for(inst["symbol"])
        with cols[i]:
            if not quote or quote["intraday"] is None:
                st.markdown(
                    f"""<div class="tile">
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
            caption = "Market-implied forecast" if forecast_slot else "Intraday change"

            st.markdown(
                f"""<div class="tile {accent_class}">
                    <div class="tile-label">{label}</div>
                    <div class="tile-value market-hero-value {direction_class}">{sign}{intraday:.2f}%</div>
                    <div class="tile-prev">{caption}</div>
                    {_metric_row("1 Month", quote["one_month"])}
                    {_metric_row("YTD", quote["ytd"])}
                    <div class="market-sparkline-wrap">{sparkline}</div>
                    <div class="severity-caption">1-year trend</div>
                </div>""",
                unsafe_allow_html=True,
            )
