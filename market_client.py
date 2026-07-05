"""Simple YTD return for a market index, sourced from FRED."""

from datetime import date

import requests
import streamlit as st

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def fetch_ytd_return(series_id: str, api_key: str) -> dict | None:
    """Latest value vs. the last available value from the prior year-end."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 400,
    }
    resp = requests.get(FRED_BASE_URL, params=params, timeout=10)
    resp.raise_for_status()
    observations = [o for o in resp.json().get("observations", []) if o.get("value") not in (None, ".")]
    if not observations:
        return None

    current_year = date.today().year
    latest = observations[0]
    baseline = next(
        (o for o in observations if int(o["date"][:4]) < current_year),
        None,
    )
    if baseline is None:
        return None

    latest_value = float(latest["value"])
    baseline_value = float(baseline["value"])
    ytd_pct = (latest_value / baseline_value - 1) * 100

    return {
        "value": latest_value,
        "ytd_pct": ytd_pct,
        "as_of": latest["date"],
    }
