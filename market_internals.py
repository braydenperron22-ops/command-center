"""Market Internals: a real Fear & Greed Index, plus two supporting
credit/breadth ratios and the Shiller CAPE ratio.

fear_greed_index() pulls the actual live index from feargreedmeter.com
— confirmed live it embeds its full computed state as structured JSON
in a standard Next.js `__NEXT_DATA__` script tag, no scraping-fragile
HTML parsing needed. CNN's own site was tried first and blocks
non-browser requests outright (its backend API returned a literal
"418 I'm a teapot. You're a bot." to a plain request). If
feargreedmeter.com is ever unreachable, this falls back to a
self-computed approximation (_computed_fear_greed_index) built from
four of CNN's own seven documented components, since three of the
seven need data that isn't freely available at all (NYSE 52-week
high/low counts, McClellan-style advance/decline breadth, and CBOE
put/call ratios — confirmed live, CBOE's own endpoint also returns 403
Access Denied without a paid feed):
  - Market Momentum: S&P 500 vs its own 125-day moving average.
  - Market Volatility: VIX, inverted (low VIX -> greed).
  - Junk Bond Demand: HYG/LQD ratio (high-yield vs investment-grade credit).
  - Safe Haven Demand: SPY's 20-day return vs IEF's (stocks vs Treasurys).
Each scored by how far it's deviated from its own recent average
relative to how much it normally deviates (a rolling z-score, mapped
to 0-100) — the same real methodology CNN's own index uses, just on a
narrower set of inputs.

Deliberately no local-file-accumulated history anywhere in this module
(the previous version's VIXEQ tile did exactly that, one snapshot/day
written to a JSON file) — Streamlit Cloud's filesystem is not
persistent across redeploys, so that tile was very likely stuck
re-accumulating from scratch on every single push and never actually
reaching a real trend in production. Every metric here is instead
computed from yfinance's own real daily history (or fetched live), so
nothing needs to accumulate over weeks of this app happening to stay
up.

HYG/LQD and RSP/SPY stay as their own supporting tiles (real, working,
already useful on their own) even though only HYG/LQD feeds the
computed fallback gauge — RSP/SPY (breadth: equal-weight vs cap-weight
S&P 500) isn't one of CNN's own seven components, it's kept because
it's a genuinely useful, well-understood metric in its own right.
"""

import json
import re

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

import fetch_throttle
from config import MARKET_DATA_TTL_SECONDS

FEARGREED_URL = "https://feargreedmeter.com/"
CAPE_URL = "https://www.multpl.com/shiller-pe"
# Shiller's own widely-cited long-run mean for the full series back to
# 1881 — a fixed reference point rather than a locally-accumulated
# trend, for the same reason the rest of this module avoids that
# pattern (see module docstring).
CAPE_HISTORICAL_AVERAGE = 17.1

# How many trading days of history each z-score is measured against —
# ~1 trading year, matching how long CNN's own "recent average" window
# is generally described as being.
ZSCORE_WINDOW = 252
TREND_LOOKBACK_DAYS = 21  # ~1 trading month

_last_good_history: dict[str, pd.DataFrame] = {}
_last_good_cape: float | None = None


@st.cache_data(ttl=MARKET_DATA_TTL_SECONDS, show_spinner=False)
def _fetch_history_raw(symbol: str, period: str) -> pd.DataFrame:
    fetch_throttle.wait_turn()
    hist = yf.Ticker(symbol).history(period=period, interval="1d")
    if hist.empty:
        raise ValueError(f"no price history returned for {symbol}")
    return hist


def _fetch_history(symbol: str, period: str = "2y") -> pd.DataFrame | None:
    cache_key = f"{symbol}:{period}"
    try:
        hist = _fetch_history_raw(symbol, period)
    except Exception:
        return _last_good_history.get(cache_key)
    _last_good_history[cache_key] = hist
    return hist


def trend(current: float, prior: float, higher_is_good: bool) -> tuple[str, str]:
    """(arrow label, tone) comparing current to a value ~1 month ago —
    shared by every ratio metric on this page so "which way is this
    trending" always means the same lookback and the same "good/bad"
    framing logic, applied with each metric's own direction of
    preference."""
    if prior == 0:
        return "→ Flat", "neutral"
    pct_diff = (current - prior) / abs(prior)
    if abs(pct_diff) < 0.005:
        return "→ Flat", "neutral"
    rising = pct_diff > 0
    tone = "good" if (rising == higher_is_good) else "bad"
    return ("↑ Rising" if rising else "↓ Falling"), tone


def _rolling_zscore(series: pd.Series) -> pd.Series:
    """How far each point sits from its own trailing average, in units
    of its own trailing standard deviation — CNN's own stated method
    ("how far each indicator has deviated from its own recent average,
    relative to how much it normally deviates")."""
    mean = series.rolling(ZSCORE_WINDOW).mean()
    std = series.rolling(ZSCORE_WINDOW).std()
    return (series - mean) / std.replace(0, np.nan)


def _zscore_to_scale(z: pd.Series) -> pd.Series:
    """Maps a z-score to a bounded 0-100 scale — 50 is "right at the
    recent norm"; +/-2.5 standard deviations reaches close to the
    0/100 ends without a hard clip suddenly flattening a genuinely
    extreme reading."""
    return (50 + z * 20).clip(0, 100)


def _momentum_series() -> pd.Series | None:
    hist = _fetch_history("^GSPC")
    if hist is None:
        return None
    close = hist["Close"]
    ma125 = close.rolling(125).mean()
    pct_above = (close - ma125) / ma125 * 100
    return _zscore_to_scale(_rolling_zscore(pct_above.dropna()))


def _volatility_series() -> pd.Series | None:
    hist = _fetch_history("^VIX")
    if hist is None:
        return None
    # Inverted: a low VIX relative to its own recent norm is greed, a
    # high one is fear.
    return _zscore_to_scale(-_rolling_zscore(hist["Close"]))


def _junk_bond_series() -> pd.Series | None:
    hyg, lqd = _fetch_history("HYG"), _fetch_history("LQD")
    if hyg is None or lqd is None:
        return None
    combined = pd.concat([hyg["Close"], lqd["Close"]], axis=1, keys=["hyg", "lqd"]).dropna()
    if combined.empty:
        return None
    return _zscore_to_scale(_rolling_zscore(combined["hyg"] / combined["lqd"]))


def _safe_haven_series() -> pd.Series | None:
    spy, ief = _fetch_history("SPY"), _fetch_history("IEF")
    if spy is None or ief is None:
        return None
    combined = pd.concat([spy["Close"], ief["Close"]], axis=1, keys=["spy", "ief"]).dropna()
    if combined.empty:
        return None
    spread = combined["spy"].pct_change(20) - combined["ief"].pct_change(20)
    return _zscore_to_scale(_rolling_zscore(spread.dropna()))


@st.cache_data(ttl=15 * 60, show_spinner=False)
def _fetch_feargreedmeter_raw() -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(FEARGREED_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp.text, re.DOTALL)
    if not match:
        raise ValueError("feargreedmeter.com's page structure changed — __NEXT_DATA__ not found")
    payload = json.loads(match.group(1))
    return payload["props"]["pageProps"]["data"]["fgi"]["latest"]


def _external_fear_greed_index() -> dict | None:
    """{"value", "prior_value", "yesterday", "one_week_ago",
    "one_year_ago", "source": "external"} from feargreedmeter.com's own
    live computed index (see module docstring for why this specific
    source). `prior_value` uses their own "one month ago" figure to
    keep the trend arrow's ~1-month lookback consistent with every
    other metric on this page, rather than switching to a noisier
    day-over-day comparison just because one happens to be available."""
    try:
        latest = _fetch_feargreedmeter_raw()
    except Exception:
        return None
    now = latest.get("now")
    if now is None:
        return None
    return {
        "value": float(now),
        "prior_value": float(latest.get("one_month_ago", now)),
        "yesterday": latest.get("previous_close"),
        "one_week_ago": latest.get("one_week_ago"),
        "one_year_ago": latest.get("one_year_ago"),
        "source": "external",
    }


def _computed_fear_greed_index() -> dict | None:
    """{"value", "prior_value", "components": {name: score}, "history",
    "source": "computed"} — the four-component fallback gauge described
    in the module docstring, used only when feargreedmeter.com itself
    isn't reachable. Degrades gracefully on its own too: computed from
    whichever components actually came back (a single symbol failing,
    e.g. IEF briefly unreachable, doesn't take down the whole gauge),
    returning None only once fewer than half of the four are
    available."""
    series_by_component = {
        "Momentum": _momentum_series(),
        "Volatility": _volatility_series(),
        "Junk Bond Demand": _junk_bond_series(),
        "Safe Haven Demand": _safe_haven_series(),
    }
    valid = {k: v for k, v in series_by_component.items() if v is not None and not v.dropna().empty}
    if len(valid) < 2:
        return None

    combined = pd.concat(valid.values(), axis=1, keys=valid.keys()).ffill().dropna()
    if combined.empty:
        return None
    composite = combined.mean(axis=1)

    current = float(composite.iloc[-1])
    prior = float(composite.iloc[-TREND_LOOKBACK_DAYS]) if len(composite) > TREND_LOOKBACK_DAYS else current
    yesterday = float(composite.iloc[-2]) if len(composite) > 1 else current

    return {
        "value": current,
        "prior_value": prior,
        "yesterday": yesterday,
        "components": {k: float(v.iloc[-1]) for k, v in combined.items()},
        "component_count": len(valid),
        "history": [float(v) for v in composite.tail(90)],
        "source": "computed",
    }


def fear_greed_index() -> dict | None:
    """The real live Fear & Greed Index when feargreedmeter.com is
    reachable; falls back to _computed_fear_greed_index (a narrower
    self-computed approximation) when it isn't. See module docstring
    for the reasoning behind both. Check result["source"] ("external"
    vs "computed") to know which one came back."""
    external = _external_fear_greed_index()
    if external is not None:
        return external
    return _computed_fear_greed_index()


def price_ratio(symbol_a: str, symbol_b: str) -> dict | None:
    hist_a = _fetch_history(symbol_a)
    hist_b = _fetch_history(symbol_b)
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


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def _fetch_cape_raw() -> float:
    fetch_throttle.wait_turn()
    resp = requests.get(CAPE_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    match = re.search(r'id="current"[\s\S]*?</b>\s*([\d.]+)', resp.text)
    if not match:
        raise ValueError("multpl.com's page structure changed — CAPE value not found")
    return float(match.group(1))


def shiller_cape() -> dict | None:
    """Current Shiller CAPE (cyclically-adjusted P/E) — scraped from
    multpl.com's own simple "current value" block (data ultimately
    sourced from Robert Shiller's own published series). No free
    structured API for this exists: FRED doesn't carry it, and
    Shiller's own site only publishes a raw Excel workbook. Compared
    against CAPE_HISTORICAL_AVERAGE, a fixed reference point, rather
    than a locally-accumulated trend (see module docstring for why)."""
    global _last_good_cape
    try:
        value = _fetch_cape_raw()
    except Exception:
        return {"value": _last_good_cape} if _last_good_cape is not None else None
    _last_good_cape = value
    return {"value": value}
