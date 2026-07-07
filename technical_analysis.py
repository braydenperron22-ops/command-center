"""Technical analysis engine for the Watchlist page.

Price history comes from yfinance (no key, free). A composite bullish/
bearish/neutral signal is built from three independent, well-established
readings — trend (price vs. 50-day MA, and the 50/200-day relationship),
momentum (MACD vs. its signal line), and RSI overbought/oversold — a
majority vote rather than any single indicator deciding the call.

The price target is technically-derived, not an analyst consensus figure:
a *range* (not a falsely-precise single number) spanning whichever of
these agree with the overall tone —
  - the nearest real support/resistance pivot from actual price action,
  - a Fibonacci 127.2% extension off the most recent swing high/low,
  - a trend-continuation projection from the 20-day moving average's
    current slope.
A tight range means those methods agree; a wide one means they don't —
that disagreement is itself useful information, so it's shown as a range
rather than averaged away into one number.
"""

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

LOOKBACK_PERIOD = "1y"
SMA_SHORT, SMA_MEDIUM, SMA_LONG = 20, 50, 200
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
SWING_LOOKBACK = 60  # trading days used for the swing high/low and support/resistance pivots
TREND_PROJECTION_DAYS = 20
CACHE_TTL_SECONDS = 30 * 60

# Never let one bad/rate-limited/delisted ticker crash the whole page —
# same reasoning as every other data client in this app: fall back to the
# last successfully fetched history for that specific symbol.
_last_good_history: dict[str, pd.DataFrame] = {}


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_history_raw(symbol: str) -> pd.DataFrame:
    hist = yf.Ticker(symbol).history(period=LOOKBACK_PERIOD, interval="1d")
    if hist.empty:
        raise ValueError(f"no price history returned for {symbol}")
    return hist


def fetch_history(symbol: str) -> pd.DataFrame | None:
    try:
        hist = _fetch_history_raw(symbol)
    except Exception:
        return _last_good_history.get(symbol)
    _last_good_history[symbol] = hist
    return hist


def _rsi(closes: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)


def _macd(closes: pd.Series) -> tuple[pd.Series, pd.Series]:
    ema_fast = closes.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = closes.ewm(span=MACD_SLOW, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    return macd_line, signal_line


def _swing_levels(hist: pd.DataFrame, lookback: int = SWING_LOOKBACK) -> tuple[float, float]:
    window = hist.tail(lookback)
    return float(window["Low"].min()), float(window["High"].max())


def _support_resistance(hist: pd.DataFrame, current_price: float, lookback: int = SWING_LOOKBACK) -> tuple[float, float]:
    """Nearest support below / resistance above the current price, from
    local swing pivots (a 3-day-either-side high/low) over the lookback
    window — the closest meaningful level to where price actually is,
    not just the window's single min/max."""
    window = hist.tail(lookback)
    highs, lows = window["High"], window["Low"]

    pivot_highs = [
        float(highs.iloc[i]) for i in range(2, len(highs) - 2)
        if highs.iloc[i] == highs.iloc[i - 2:i + 3].max()
    ]
    pivot_lows = [
        float(lows.iloc[i]) for i in range(2, len(lows) - 2)
        if lows.iloc[i] == lows.iloc[i - 2:i + 3].min()
    ]

    resistances = [p for p in pivot_highs if p > current_price]
    supports = [p for p in pivot_lows if p < current_price]
    resistance = min(resistances) if resistances else float(highs.max())
    support = max(supports) if supports else float(lows.min())
    return support, resistance


def analyze(symbol: str) -> dict | None:
    hist = fetch_history(symbol)
    if hist is None or len(hist) < SMA_LONG + 5:
        return None

    closes = hist["Close"]
    current_price = float(closes.iloc[-1])

    sma50 = closes.rolling(SMA_MEDIUM).mean()
    sma200 = closes.rolling(SMA_LONG).mean()
    rsi = _rsi(closes)
    macd_line, signal_line = _macd(closes)

    current_rsi = float(rsi.iloc[-1])
    current_macd = float(macd_line.iloc[-1])
    current_macd_signal = float(signal_line.iloc[-1])
    current_sma50 = float(sma50.iloc[-1])
    current_sma200 = float(sma200.iloc[-1])

    # Three independent votes rather than one indicator deciding alone.
    votes = 0
    votes += 1 if current_price > current_sma50 else -1
    votes += 1 if current_sma50 > current_sma200 else -1
    votes += 1 if current_macd > current_macd_signal else -1
    if current_rsi >= 70:
        votes -= 1  # overbought tempers a bullish read
    elif current_rsi <= 30:
        votes += 1  # oversold tempers a bearish read

    if votes >= 2:
        tone = "good"
    elif votes <= -2:
        tone = "bad"
    else:
        tone = "neutral"

    support, resistance = _support_resistance(hist, current_price)
    swing_low, swing_high = _swing_levels(hist)
    swing_range = swing_high - swing_low

    sma20_valid = closes.rolling(SMA_SHORT).mean().dropna()
    if len(sma20_valid) > TREND_PROJECTION_DAYS:
        slope_per_day = (sma20_valid.iloc[-1] - sma20_valid.iloc[-TREND_PROJECTION_DAYS]) / TREND_PROJECTION_DAYS
    else:
        slope_per_day = 0.0
    trend_target = current_price + slope_per_day * TREND_PROJECTION_DAYS

    if tone == "good":
        candidates = [resistance, swing_high + swing_range * 0.272]
        if trend_target > current_price:
            candidates.append(trend_target)
    elif tone == "bad":
        candidates = [support, swing_low - swing_range * 0.272]
        if trend_target < current_price:
            candidates.append(trend_target)
    else:
        candidates = [support, resistance]

    target_low, target_high = min(candidates), max(candidates)

    return {
        "symbol": symbol,
        "price": current_price,
        "tone": tone,
        "rsi": current_rsi,
        "support": support,
        "resistance": resistance,
        "target_low": target_low,
        "target_high": target_high,
        "history": [float(v) for v in closes.tail(30)],
    }
