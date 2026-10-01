"""Bank of Canada Valet API access — same fetch/cache/fallback shape as
fred_client.py, for the one real gap FRED's own Canada mirrors have.

Session request: "is there already a ten-year yield for Canada... very
important... that's the rate the markets look at." There was one
already (config.py's INDICATORS["ca"] yield_10y, FRED series
IRLTLT01CAM156N) — but confirmed live it's an OECD-sourced MONTHLY
average, two months stale (August's reading, on October 1st) when
checked. The actual Government of Canada 10-year benchmark bond yield
is published DAILY by the Bank of Canada itself (Valet series
BD.CDN.10YR.DQ.YLD, confirmed live: real day-to-day movement, e.g.
3.83 to 3.97 across a couple weeks in September — a genuinely "markets
watch this" series, not the smoothed-out monthly read FRED's mirror
gives). No API key needed, unlike FRED.
"""

import requests
import streamlit as st

import fetch_throttle
from indicators import build_reading

VALET_BASE_URL = "https://www.bankofcanada.ca/valet/observations"

_last_good_series: dict[str, list[dict]] = {}


@st.cache_data(ttl=60 * 60, show_spinner=False)
def _fetch_series_raw(series_code: str) -> list[dict]:
    # Same "generous history, still a tiny/cheap request" reasoning as
    # fred_client._fetch_series_raw's own `limit` — recent=2600 covers
    # roughly a decade of daily observations for indicators.py's own
    # percentile_rank, and Valet doesn't charge or throttle harder for
    # asking for more.
    fetch_throttle.wait_turn()
    resp = requests.get(f"{VALET_BASE_URL}/{series_code}/json", params={"recent": 2600}, timeout=10)
    resp.raise_for_status()
    raw_observations = resp.json().get("observations", [])
    observations = []
    for o in raw_observations:
        value = (o.get(series_code) or {}).get("v")
        date = o.get("d")
        if value is not None and date is not None:
            observations.append({"date": date, "value": value})
    # Valet returns newest-first (confirmed live) — same as FRED's own
    # sort_order=desc default, and fred_client._fetch_series_raw
    # reverses for the exact same reason: build_reading (indicators.py)
    # expects chronological, oldest-first order and reads series[-1] as
    # "current." Caught by a real end-to-end test here returning a 2016
    # reading as "current" before this reversal was added.
    observations.reverse()
    return observations


def fetch_series(series_code: str) -> list[dict]:
    """Return recent observations for a Bank of Canada Valet series,
    oldest first."""
    try:
        observations = _fetch_series_raw(series_code)
    except (requests.RequestException, ValueError, KeyError):
        return _last_good_series.get(series_code, [])
    _last_good_series[series_code] = observations
    return observations


def build_indicator_reading(series_code: str, transform: str) -> dict | None:
    observations = fetch_series(series_code)
    dates = [o["date"] for o in observations]
    values = [float(o["value"]) for o in observations]
    return build_reading(dates, values, transform)
