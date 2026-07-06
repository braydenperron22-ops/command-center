"""FRED API access: fetch series history and classify readings vs trend."""

from datetime import date

import requests
import streamlit as st

from indicators import build_reading

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_RELEASE_DATES_URL = "https://api.stlouisfed.org/fred/release/dates"


@st.cache_data(ttl=60 * 60, show_spinner=False)
def fetch_series(series_id: str, api_key: str) -> list[dict]:
    """Return recent observations for a FRED series, oldest first."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 36,
    }
    resp = requests.get(FRED_BASE_URL, params=params, timeout=10)
    resp.raise_for_status()
    observations = resp.json().get("observations", [])
    observations = [o for o in observations if o.get("value") not in (None, ".")]
    observations.reverse()
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
def fetch_next_release_date(release_id: int, api_key: str) -> str | None:
    """The next confirmed date on FRED's official release calendar for this release."""
    params = {
        "release_id": release_id,
        "api_key": api_key,
        "file_type": "json",
        "realtime_start": date.today().isoformat(),
        "include_release_dates_with_no_data": "true",
        "sort_order": "asc",
        "limit": 1,
    }
    resp = requests.get(FRED_RELEASE_DATES_URL, params=params, timeout=10)
    resp.raise_for_status()
    dates = resp.json().get("release_dates", [])
    return dates[0]["date"] if dates else None
