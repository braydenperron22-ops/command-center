"""FRED API access: fetch series history and classify readings vs trend."""

from datetime import date

import requests
import streamlit as st

import fetch_throttle
from indicators import build_reading

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_RELEASE_DATES_URL = "https://api.stlouisfed.org/fred/release/dates"

# This runs 24/7 unattended — a transient network hiccup or a FRED outage
# must never crash a page (blank screen until the next rerun happens to
# succeed). The raw fetch stays cached-and-raising (so Streamlit doesn't
# cache a failure and a fresh retry happens on the very next rerun); the
# public function catches that and falls back to the last value that DID
# fetch successfully, so a tile keeps showing slightly-stale data instead
# of nothing. Module-level rather than st.session_state since this
# process serves one continuously-running display, not per-user sessions.
_last_good_series: dict[str, list[dict]] = {}
_last_good_release_date: dict[int, str | None] = {}


@st.cache_data(ttl=60 * 60, show_spinner=False)
def _fetch_series_raw(series_id: str, api_key: str) -> list[dict]:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        # Deliberately generous rather than just enough for the trend
        # window/sparkline — indicators.py's percentile_rank wants as
        # much real history as it can get, and these series aren't all
        # the same frequency: 2600 covers ~10 years even for a DAILY
        # series like the 10-year yield, while monthly/quarterly series
        # (CPI, unemployment, GDP) just get their entire available
        # history back, since none of them have that many observations
        # to begin with. Still a tiny request either way — FRED doesn't
        # charge or meaningfully slow down for the extra rows, and it's
        # cached for an hour regardless.
        "limit": 2600,
    }
    fetch_throttle.wait_turn()
    resp = requests.get(FRED_BASE_URL, params=params, timeout=10)
    resp.raise_for_status()
    observations = resp.json().get("observations", [])
    observations = [o for o in observations if o.get("value") not in (None, ".")]
    observations.reverse()
    return observations


def fetch_series(series_id: str, api_key: str) -> list[dict]:
    """Return recent observations for a FRED series, oldest first."""
    try:
        observations = _fetch_series_raw(series_id, api_key)
    except (requests.RequestException, ValueError, KeyError):
        return _last_good_series.get(series_id, [])
    _last_good_series[series_id] = observations
    return observations


def build_indicator_reading(series_id: str, api_key: str, transform: str) -> dict | None:
    observations = fetch_series(series_id, api_key)
    dates = [o["date"] for o in observations]
    values = [float(o["value"]) for o in observations]
    return build_reading(dates, values, transform)


def fetch_latest_value(series_id: str, api_key: str) -> float | None:
    """Most recent value of a series that's already exactly what it claims
    to be (e.g. T10Y2Y is already the 10Y-2Y spread, not a raw yield)."""
    observations = fetch_series(series_id, api_key)
    return float(observations[-1]["value"]) if observations else None


@st.cache_data(ttl=12 * 60 * 60, show_spinner=False)
def _fetch_next_release_date_raw(release_id: int, api_key: str) -> str | None:
    params = {
        "release_id": release_id,
        "api_key": api_key,
        "file_type": "json",
        "realtime_start": date.today().isoformat(),
        "include_release_dates_with_no_data": "true",
        "sort_order": "asc",
        "limit": 1,
    }
    fetch_throttle.wait_turn()
    resp = requests.get(FRED_RELEASE_DATES_URL, params=params, timeout=10)
    resp.raise_for_status()
    dates = resp.json().get("release_dates", [])
    return dates[0]["date"] if dates else None


def fetch_next_release_date(release_id: int, api_key: str) -> str | None:
    """The next confirmed date on FRED's official release calendar for this release."""
    try:
        result = _fetch_next_release_date_raw(release_id, api_key)
    except (requests.RequestException, ValueError, KeyError):
        return _last_good_release_date.get(release_id)
    _last_good_release_date[release_id] = result
    return result
