"""Markets page data via yfinance — replaces the earlier Twelve Data
integration, which needed ETF proxies (SPY/DIA/QQQ/EWC) since its free
tier didn't include raw index symbols or crypto. yfinance gives the real
indices directly during market hours, live futures outside those hours,
and crypto on weekends — no key, no rate-limit tier to design around.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import yfinance as yf

import fetch_throttle
from config import (
    MARKET_DATA_TTL_SECONDS,
    MARKET_INSTRUMENTS_CLOSED,
    MARKET_INSTRUMENTS_OPEN,
    MARKET_INSTRUMENTS_WEEKEND,
    MARKET_SPARKLINE_PERIOD,
)

ONE_MONTH_TRADING_DAYS = 21

# Same open/closed/weekend swap the Markets page itself uses (real index /
# futures / crypto) — "sp500" is the headline instrument in the first two,
# "btc" in the weekend set, since no equity index is trading then.
_PRIMARY_KEY_BY_STATUS = {"open": "sp500", "closed": "sp500", "weekend": "btc"}
_INSTRUMENTS_BY_STATUS = {
    "open": MARKET_INSTRUMENTS_OPEN,
    "closed": MARKET_INSTRUMENTS_CLOSED,
    "weekend": MARKET_INSTRUMENTS_WEEKEND,
}


def primary_symbol(status: str) -> str:
    """The one instrument that best represents 'the market' right now,
    for callers (like the Govee light) that just want a single headline
    direction rather than the Markets page's full grid."""
    key = _PRIMARY_KEY_BY_STATUS[status]
    return next(i["symbol"] for i in _INSTRUMENTS_BY_STATUS[status] if i["key"] == key)

# Never let one bad/rate-limited ticker crash the page — same reasoning
# as every other data client in this app: fall back to the last
# successfully fetched history for that specific symbol.
_last_good_history: dict[str, pd.DataFrame] = {}


def market_status(now: datetime | None = None) -> str:
    """'open' (real indices), 'closed' (futures), or 'weekend' (crypto)
    — 'open' is NYSE/TSX cash-market hours (9:30am-4:00pm ET, Mon-Fri).
    'weekend' is meant to mean "nothing but crypto is actually trading",
    which isn't the same as "it's Saturday or Sunday": CME Globex
    reopens equity index futures Sunday at 6:00pm ET for the new
    week (through Friday 5:00pm ET) — Saturday and Sunday-before-6pm
    are the only genuinely all-crypto window, not the whole weekend as
    a block. No holiday calendar: a market holiday just falls under
    "closed" and shows futures, a reasonable stand-in rather than a
    stale index quote — not worth the complexity of a full holiday
    calendar for that edge case alone.
    """
    eastern = (now or datetime.now(ZoneInfo("UTC"))).astimezone(ZoneInfo("America/New_York"))
    weekday = eastern.weekday()  # Monday=0 ... Saturday=5, Sunday=6
    if weekday == 6 and eastern.hour >= 18:  # Sunday, futures already reopened for the week
        return "closed"
    if weekday >= 5:  # all of Saturday, and Sunday before 6pm
        return "weekend"
    open_time = eastern.replace(hour=9, minute=30, second=0, microsecond=0)
    close_time = eastern.replace(hour=16, minute=0, second=0, microsecond=0)
    return "open" if open_time <= eastern < close_time else "closed"


@st.cache_data(ttl=MARKET_DATA_TTL_SECONDS, show_spinner=False)
def _fetch_history_raw(symbol: str) -> pd.DataFrame:
    fetch_throttle.wait_turn()
    hist = yf.Ticker(symbol).history(period=MARKET_SPARKLINE_PERIOD, interval="1d")
    if hist.empty:
        raise ValueError(f"no price history returned for {symbol}")
    return hist


def _fetch_history(symbol: str) -> pd.DataFrame | None:
    try:
        hist = _fetch_history_raw(symbol)
    except Exception:
        return _last_good_history.get(symbol)
    _last_good_history[symbol] = hist
    return hist


def _pct_change(latest: float, base: float | None) -> float | None:
    if not base:
        return None
    return (latest - base) / base * 100


def quote_for(symbol: str) -> dict | None:
    """Intraday / 1-month / YTD % change plus a full year of closes for
    the sparkline, from one cached yfinance history call per symbol."""
    hist = _fetch_history(symbol)
    if hist is None or hist.empty:
        return None

    closes = hist["Close"]
    latest_close = float(closes.iloc[-1])
    latest_open = float(hist["Open"].iloc[-1])
    intraday = _pct_change(latest_close, latest_open)

    one_month_base = float(closes.iloc[-ONE_MONTH_TRADING_DAYS]) if len(closes) > ONE_MONTH_TRADING_DAYS else None
    one_month = _pct_change(latest_close, one_month_base)

    year_start = hist.index[-1].replace(month=1, day=1)
    ytd_series = closes[hist.index < year_start]
    ytd_base = float(ytd_series.iloc[-1]) if len(ytd_series) else None
    ytd = _pct_change(latest_close, ytd_base)

    return {
        "intraday": intraday,
        "one_month": one_month,
        "ytd": ytd,
        "history": [float(v) for v in closes],
    }
