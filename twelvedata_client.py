"""Twelve Data for the Markets page — intraday / 1-month / YTD % change for
indices/FX/commodities, computed from one batched daily time-series call.

Free tier caps at 8 credits/minute. Everything is fetched in a single
batched request per refresh (one call regardless of instrument count),
cached for TWELVEDATA_TTL_SECONDS so repeat reruns never re-hit the API.
"""

import requests
import streamlit as st

from config import TWELVEDATA_TTL_SECONDS

TIME_SERIES_URL = "https://api.twelvedata.com/time_series"
ONE_MONTH_TRADING_DAYS = 21
SPARKLINE_TRADING_DAYS = 12  # matches the Home page tiles' trend sparkline length

# Same reasoning as fred_client: never let a transient hiccup blank the
# Markets page — fall back to the last successfully fetched batch.
_last_good_quotes: dict = {}


def _pct_change(latest: float, base: float | None) -> float | None:
    if not base:
        return None
    return (latest - base) / base * 100


def _compute_metrics(values: list[dict]) -> dict | None:
    """values are newest-first, one entry per trading day."""
    if not values:
        return None

    closes = [(v["datetime"], float(v["close"])) for v in values]
    latest_date, latest_close = closes[0]
    latest_open = float(values[0]["open"])

    intraday = _pct_change(latest_close, latest_open)

    one_month_base = closes[ONE_MONTH_TRADING_DAYS][1] if len(closes) > ONE_MONTH_TRADING_DAYS else None
    one_month = _pct_change(latest_close, one_month_base)

    year_start = f"{latest_date[:4]}-01-01"
    ytd_base = next((c for d, c in closes if d < year_start), None)
    ytd = _pct_change(latest_close, ytd_base)

    # closes is newest-first; the sparkline (like tiles.py's) wants
    # oldest-first so it reads left-to-right as it would on a chart.
    history = [c for _, c in closes[:SPARKLINE_TRADING_DAYS]][::-1]

    return {"intraday": intraday, "one_month": one_month, "ytd": ytd, "history": history}


@st.cache_data(ttl=TWELVEDATA_TTL_SECONDS, show_spinner=False)
def _fetch_quotes_raw(symbols: tuple, api_key: str) -> dict:
    """{symbol: {"intraday": float, "one_month": float, "ytd": float} | None}"""
    resp = requests.get(TIME_SERIES_URL, params={
        "symbol": ",".join(symbols),
        "interval": "1day",
        "outputsize": 260,  # comfortably covers a full year of trading days
        "apikey": api_key,
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # A single-symbol request returns one flat object instead of {symbol: {...}}.
    if len(symbols) == 1:
        data = {symbols[0]: data}

    results = {}
    for symbol in symbols:
        entry = data.get(symbol)
        if not entry or entry.get("status") == "error" or "values" not in entry:
            results[symbol] = None
            continue
        try:
            results[symbol] = _compute_metrics(entry["values"])
        except (KeyError, TypeError, ValueError):
            results[symbol] = None
    return results


def fetch_quotes(symbols: tuple, api_key: str) -> dict:
    try:
        results = _fetch_quotes_raw(symbols, api_key)
    except (requests.RequestException, ValueError, KeyError):
        return _last_good_quotes.get(symbols, {symbol: None for symbol in symbols})
    _last_good_quotes[symbols] = results
    return results
