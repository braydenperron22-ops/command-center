"""Detects a stock ticker or company name referenced in a headline and
resolves it to that company's trailing 1-year return, shown as a small
inline badge on the News page — reuses the same yfinance + last-known-
good resilience pattern as every other market data client in this app,
just with a longer cache TTL since a 1-year return doesn't need
Markets-page-level freshness.
"""

import functools
import re

import streamlit as st
import yfinance as yf

import fetch_throttle
from news import EARNINGS_COMPANIES

TICKER_PATTERN = re.compile(r"\(([A-Z]{2,5})\)")
CACHE_TTL_SECONDS = 60 * 60

_last_good_return: dict[str, float] = {}


@functools.lru_cache(maxsize=2048)
def detect_ticker(headline: str) -> str | None:
    """An explicit "(TICKER)" parenthetical wins if present; otherwise
    falls back to a company-name mention via the same map classify()
    uses for its Earnings category, so "Apple" resolves to AAPL even
    without the ticker spelled out."""
    match = TICKER_PATTERN.search(headline)
    if match:
        return match.group(1)
    h = headline.lower()
    for name, ticker in EARNINGS_COMPANIES.items():
        if re.search(r"\b" + re.escape(name) + r"s?\b", h):
            return ticker
    return None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_one_year_return_raw(ticker: str) -> float:
    fetch_throttle.wait_turn()
    hist = yf.Ticker(ticker).history(period="1y", interval="1d")
    if hist.empty or len(hist) < 2:
        raise ValueError(f"no history for {ticker}")
    closes = hist["Close"]
    return float((closes.iloc[-1] / closes.iloc[0] - 1) * 100)


def one_year_return(ticker: str) -> float | None:
    try:
        value = _fetch_one_year_return_raw(ticker)
    except Exception:
        return _last_good_return.get(ticker)
    _last_good_return[ticker] = value
    return value


def ticker_badge_html(headline: str) -> str:
    """A small inline pill like "AAPL 1Y +34.2%" for the first ticker or
    company detected in the headline, or "" if none detected or the
    return isn't available (e.g. a too-recent IPO with <1y of history)."""
    ticker = detect_ticker(headline)
    if not ticker:
        return ""
    ret = one_year_return(ticker)
    if ret is None:
        return ""
    direction = "market-up" if ret >= 0 else "market-down"
    sign = "+" if ret >= 0 else ""
    return f'<span class="headline-ticker-badge {direction}">{ticker} 1Y {sign}{ret:.1f}%</span>'
