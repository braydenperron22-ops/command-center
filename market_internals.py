"""Market Internals: risk-appetite and credit-market gauges built from
free index/ETF data via yfinance.

Four metrics:
  - Market Confidence Index: a 0-99 composite from two VIX-based
    exponential decay formulas (current VIX and its 30-day average,
    each clamped 0-99), averaged — the exact formula requested, not a
    reinterpretation of it.
  - VIXEQ/VIX: Cboe's equal-weighted constituent volatility vs the
    standard (effectively cap-weighted, mega-cap-dominated) VIX. Yahoo
    only exposes a live snapshot for ^VIXEQ (no historical series is
    available — period='max' isn't even a valid request for that
    symbol), so its trend is built by accumulating one real daily
    snapshot per day into a local file as this app runs continuously,
    rather than faking a chart from data that doesn't exist.
  - HYG/LQD: high-yield vs investment-grade corporate bond ETFs — a
    classic credit-market risk-appetite ratio.
  - RSP/SPY: equal-weight vs cap-weight S&P 500 ETFs — a classic
    breadth ratio (is the rally broad, or a handful of mega-caps).
"""

import json
import os
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from config import MARKET_DATA_TTL_SECONDS

VIXEQ_HISTORY_PATH = os.path.join(os.path.dirname(__file__), "vixeq_history.json")
TREND_LOOKBACK_DAYS = 21  # ~1 trading month

_last_good_history: dict[str, pd.DataFrame] = {}
_last_good_snapshot: dict[str, float] = {}


@st.cache_data(ttl=MARKET_DATA_TTL_SECONDS, show_spinner=False)
def _fetch_history_raw(symbol: str, period: str) -> pd.DataFrame:
    hist = yf.Ticker(symbol).history(period=period, interval="1d")
    if hist.empty:
        raise ValueError(f"no price history returned for {symbol}")
    return hist


def _fetch_history(symbol: str, period: str = "1y") -> pd.DataFrame | None:
    cache_key = f"{symbol}:{period}"
    try:
        hist = _fetch_history_raw(symbol, period)
    except Exception:
        return _last_good_history.get(cache_key)
    _last_good_history[cache_key] = hist
    return hist


@st.cache_data(ttl=MARKET_DATA_TTL_SECONDS, show_spinner=False)
def _fetch_snapshot_raw(symbol: str) -> float:
    hist = yf.Ticker(symbol).history(period="5d")
    if hist.empty:
        raise ValueError(f"no snapshot data for {symbol}")
    return float(hist["Close"].iloc[-1])


def _fetch_snapshot(symbol: str) -> float | None:
    try:
        value = _fetch_snapshot_raw(symbol)
    except Exception:
        return _last_good_snapshot.get(symbol)
    _last_good_snapshot[symbol] = value
    return value


def trend(current: float, prior: float, higher_is_good: bool) -> tuple[str, str]:
    """(arrow label, tone) comparing current to a value ~1 month ago —
    shared by every metric on this page so "which way is this trending"
    always means the same lookback and the same "good/bad" framing
    logic, applied with each metric's own direction of preference."""
    if prior == 0:
        return "→ Flat", "neutral"
    pct_diff = (current - prior) / abs(prior)
    if abs(pct_diff) < 0.005:
        return "→ Flat", "neutral"
    rising = pct_diff > 0
    tone = "good" if (rising == higher_is_good) else "bad"
    return ("↑ Rising" if rising else "↓ Falling"), tone


def confidence_index() -> dict | None:
    vix_hist = _fetch_history("^VIX", period="1y")
    if vix_hist is None or len(vix_hist) < 35:
        return None

    closes = vix_hist["Close"]
    vix_30dma_series = closes.rolling(30).mean()

    comp_now = (100 * np.exp(-(0.08 * (closes - 15)))).clip(0, 99)
    comp_ma = (100 * np.exp(-(0.08 * (vix_30dma_series - 14)))).clip(0, 99)
    confidence_series = ((comp_now + comp_ma) / 2).dropna()
    if confidence_series.empty:
        return None

    current = float(confidence_series.iloc[-1])
    prior = float(confidence_series.iloc[-TREND_LOOKBACK_DAYS]) if len(confidence_series) > TREND_LOOKBACK_DAYS else current

    return {
        "value": current,
        "prior_value": prior,
        "current_vix": float(closes.iloc[-1]),
        "vix_30dma": float(vix_30dma_series.iloc[-1]),
        "history": [float(v) for v in confidence_series.tail(90)],
    }


def _load_vixeq_history() -> dict:
    try:
        with open(VIXEQ_HISTORY_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _record_vixeq_ratio(today: str, ratio: float) -> None:
    history = _load_vixeq_history()
    if today in history:
        return
    history[today] = ratio
    if len(history) > 730:  # keep a rolling ~2 years, file shouldn't grow forever
        for old_key in sorted(history.keys())[: len(history) - 730]:
            del history[old_key]
    try:
        with open(VIXEQ_HISTORY_PATH, "w") as f:
            json.dump(history, f)
    except OSError:
        pass


def vixeq_vix_ratio() -> dict | None:
    """Yahoo only exposes a live snapshot for ^VIXEQ, not a historical
    series, so the trend here is real accumulated history — one genuine
    daily data point recorded the first time this runs each day — not a
    reconstruction. Starts with no trend and fills in over the following
    weeks as this app keeps running."""
    vixeq = _fetch_snapshot("^VIXEQ")
    vix = _fetch_snapshot("^VIX")
    if not vixeq or not vix:
        return None

    ratio = vixeq / vix
    today_str = date.today().isoformat()
    _record_vixeq_ratio(today_str, ratio)

    stored = _load_vixeq_history()
    sorted_dates = sorted(stored.keys())
    history_values = [stored[d] for d in sorted_dates]
    if len(history_values) > TREND_LOOKBACK_DAYS:
        prior = history_values[-TREND_LOOKBACK_DAYS]
    elif history_values:
        prior = history_values[0]
    else:
        prior = ratio

    return {
        "value": ratio,
        "prior_value": prior,
        "vixeq": vixeq,
        "vix": vix,
        "history": history_values[-90:],
        "history_days": len(history_values),
    }


def price_ratio(symbol_a: str, symbol_b: str) -> dict | None:
    hist_a = _fetch_history(symbol_a, period="1y")
    hist_b = _fetch_history(symbol_b, period="1y")
    if hist_a is None or hist_b is None:
        return None

    # Align on shared trading days only — two different ETFs occasionally
    # miss a day here or there (holidays, data gaps).
    combined = pd.concat([hist_a["Close"], hist_b["Close"]], axis=1, keys=["a", "b"]).dropna()
    if combined.empty:
        return None

    ratio_series = combined["a"] / combined["b"]
    current = float(ratio_series.iloc[-1])
    prior = float(ratio_series.iloc[-TREND_LOOKBACK_DAYS]) if len(ratio_series) > TREND_LOOKBACK_DAYS else current

    return {
        "value": current,
        "prior_value": prior,
        "history": [float(v) for v in ratio_series.tail(252)],
    }
