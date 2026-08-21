"""Financial-plumbing monitor: is the short-term funding/money-market
system behaving normally, or drifting into something worth noticing —
the same "how far from its own recent normal" question this app's
VIX/16 market-move band (market_yf_client.volatility_band_status) and
the Market Internals ratio tiles (market_internals.price_ratio's own
z-score) already answer for other domains, applied here to the
funding side of the financial system instead of asset prices.

Session request: "financial-system monitoring layer... CORRA, SOFR,
repo/funding conditions, treasury bill yields, money-market rates,
commercial paper, bank funding conditions, credit spreads, liquidity
measures, financial conditions, Canadian and U.S. financial-system
indicators... identify whether financial plumbing is behaving normally
or becoming unusual." Follow-up: "use CORRA for the Bank of Canada."

Every series below already has a real, live, free source: FRED_API_KEY
is already configured in this app (the Home page's own CPI/GDP/
unemployment tiles use it) and covers every US series; Bank of
Canada's own Valet API (no key needed) covers CORRA.

No bespoke "crisis level" cutoff is hand-picked per series here — I
don't have well-grounded stress thresholds memorized for eight
different series, and a hand-picked number risks being quietly wrong
for years until it's actually tested. Instead every series is judged
the same way the rest of this app already judges "is this reading
actually notable": how many standard deviations it currently sits from
its OWN recent trailing behavior (config.SIGNIFICANT_Z, the same bar
tiles.py's macro-indicator tiles and this session's Market Internals
z-score upgrade already use) — a real jump specific to THAT series is
what counts as unusual, not a fixed number that means something
different in a high-rate era than a low-rate one.

Three buckets, matching the session's own example mockup exactly
("Funding conditions... Money-market conditions... Liquidity"):
  - Funding: SOFR, IORB (the Fed's own floor rate — SOFR trading well
    above IORB is the textbook repo-stress signal, Sept 2019), CORRA.
  - Money market: T-bill yields, commercial paper.
  - Liquidity: the Fed's own overnight reverse-repo facility usage
    (a direct gauge of where "parked" cash is sitting), high-yield and
    investment-grade credit spreads, and the Chicago Fed's National
    Financial Conditions Index (a real, published "financial
    conditions" composite — the literal name of the session's own
    category)."""

import statistics
from datetime import datetime

import requests
import streamlit as st

import fetch_throttle
import fred_client
import persisted_state
from config import SIGNIFICANT_Z

BOC_VALET_URL = "https://www.bankofcanada.ca/valet/observations/{series}/json"

# ~3 months of daily readings — long enough to smooth routine day-to-
# day noise (a quarter-end technical SOFR blip, say) without waiting a
# full year like market_internals.py's own 252-day window, which is
# tuned for equity-market cycles; funding rates move on a faster,
# policy-driven cadence than stock prices do.
ZSCORE_WINDOW = 60

_BUCKETS = {
    "funding": {
        "label": "Funding conditions",
        "series": [
            {"label": "SOFR", "source": "fred", "series_id": "SOFR"},
            {"label": "IORB", "source": "fred", "series_id": "IORB"},
            {"label": "CORRA", "source": "boc", "series_id": "AVG.INTWO"},
        ],
    },
    "money_market": {
        "label": "Money-market conditions",
        "series": [
            {"label": "3-Month T-Bill", "source": "fred", "series_id": "DTB3"},
            {"label": "4-Week T-Bill", "source": "fred", "series_id": "DTB4WK"},
            {"label": "3-Month Commercial Paper", "source": "fred", "series_id": "CPF3M"},
        ],
    },
    "liquidity": {
        "label": "Liquidity",
        "series": [
            {"label": "Fed Reverse Repo Usage", "source": "fred", "series_id": "RRPONTSYD"},
            {"label": "High-Yield Credit Spread", "source": "fred", "series_id": "BAMLH0A0HYM2"},
            {"label": "Investment-Grade Credit Spread", "source": "fred", "series_id": "BAMLC0A0CM"},
            {"label": "Financial Conditions Index", "source": "fred", "series_id": "NFCI"},
        ],
    },
}

_last_good_boc: dict[str, list[float]] = {}


@st.cache_data(ttl=60 * 60, show_spinner=False)
def _fetch_boc_raw(series: str) -> list[float]:
    fetch_throttle.wait_turn()
    resp = requests.get(BOC_VALET_URL.format(series=series), params={"recent": 400}, timeout=10)
    resp.raise_for_status()
    observations = resp.json().get("observations", [])
    return [
        float(o[series]["v"])
        for o in observations
        if series in o and o[series].get("v") not in (None, "")
    ]


def _fetch_boc_series(series: str) -> list[float]:
    try:
        values = _fetch_boc_raw(series)
    except Exception:
        return _last_good_boc.get(series, [])
    _last_good_boc[series] = values
    return values


def _series_values(source: str, series_id: str) -> list[float] | None:
    if source == "boc":
        values = _fetch_boc_series(series_id)
        return values or None
    key = st.secrets.get("FRED_API_KEY")
    if not key:
        return None
    observations = fred_client.fetch_series(series_id, key)
    return [float(o["value"]) for o in observations] if observations else None


def _zscore(values: list[float]) -> float | None:
    """Same math as indicators.build_reading's own z-score (current vs
    a trailing window's mean/stdev) — a fresh, locally-tuned window
    rather than reusing that function directly, since its TREND_WINDOW
    (6 readings) is sized for monthly/quarterly macro releases, not a
    daily-frequency funding rate."""
    if len(values) < ZSCORE_WINDOW + 1:
        return None
    window = values[-(ZSCORE_WINDOW + 1):-1]
    mean = statistics.fmean(window)
    stdev = statistics.pstdev(window)
    if stdev == 0:
        return 0.0
    return (values[-1] - mean) / stdev


def _series_reading(item: dict) -> dict | None:
    values = _series_values(item["source"], item["series_id"])
    if not values:
        return None
    z = _zscore(values)
    return {
        "label": item["label"],
        "value": values[-1],
        "z_score": z,
        "significant": z is not None and abs(z) >= SIGNIFICANT_Z,
    }


def plumbing_status() -> dict | None:
    """{"overall": "NORMAL"|"UNUSUAL", "buckets": [{"key", "label",
    "status", "detail", "readings": [...]}]} — None only if every
    single series failed to fetch (FRED and Bank of Canada both
    unreachable at once, same all-sources-down fallback shape every
    other multi-source client in this app already uses)."""
    buckets = []
    any_data = False
    overall_unusual = False
    for key, bucket in _BUCKETS.items():
        readings = [r for r in (_series_reading(s) for s in bucket["series"]) if r is not None]
        if not readings:
            continue
        any_data = True
        flagged = [r for r in readings if r["significant"]]
        if flagged:
            overall_unusual = True
            worst = max(flagged, key=lambda r: abs(r["z_score"]))
            direction = "elevated" if worst["z_score"] > 0 else "easing"
            status, detail = "unusual", f"{worst['label']} {direction} vs its own recent norm"
        else:
            status, detail = "normal", f"{bucket['label']} normal"
        buckets.append({"key": key, "label": bucket["label"], "status": status, "detail": detail, "readings": readings})
    if not any_data:
        return None
    return {"overall": "UNUSUAL" if overall_unusual else "NORMAL", "buckets": buckets}


# "Only surface meaningful changes or stress" — fires once on the
# normal->unusual transition, not on every rerun while it stays
# unusual, and not on the reverse transition (a quiet "back to normal"
# isn't worth interrupting for, same reasoning every other one-shot
# toast in this app already follows). No baseline gate needed the way
# road_conditions_511's closures needed one: "is the system stressed
# RIGHT NOW" is a current fact by construction, not backlog — same
# reasoning market_volatility_alert.py's own toast already uses. Per-
# instance state, same as every other one-shot toast here.
_was_unusual: bool = persisted_state.load_per_instance("plumbing_was_unusual", False)


def get_new_alerts(now: datetime) -> list[dict]:
    global _was_unusual
    status = plumbing_status()
    if status is None:
        return []
    is_unusual = status["overall"] == "UNUSUAL"
    if is_unusual == _was_unusual:
        return []
    _was_unusual = is_unusual
    persisted_state.save_per_instance("plumbing_was_unusual", _was_unusual)
    if not is_unusual:
        return []
    flagged = next((b for b in status["buckets"] if b["status"] == "unusual"), None)
    if not flagged:
        return []
    return [
        {
            "kind": "weather",
            "severity": "warning",
            "label": "Financial Plumbing",
            "headline": f"{flagged['label']} turning unusual",
            "summary": flagged["detail"],
        }
    ]
