"""Statistics Canada WDS API access, used where FRED's Canada mirrors are stale."""

import requests
import streamlit as st

from indicators import build_reading

STATCAN_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods"

# Same reasoning as fred_client: never let a transient StatCan hiccup
# crash the page — fall back to the last successfully fetched value.
_last_good_vector: dict[int, list[dict]] = {}


@st.cache_data(ttl=60 * 60, show_spinner=False)
def _fetch_vector_raw(vector_id: int, latest_n: int = 200) -> list[dict]:
    body = [{"vectorId": vector_id, "latestN": latest_n}]
    resp = requests.post(STATCAN_URL, json=body, timeout=10)
    resp.raise_for_status()
    payload = resp.json()[0]["object"]["vectorDataPoint"]
    return [{"date": p["refPer"], "value": p["value"]} for p in payload]


def fetch_vector(vector_id: int, latest_n: int = 200) -> list[dict]:
    """Return recent observations for a StatCan vector, oldest first."""
    try:
        observations = _fetch_vector_raw(vector_id, latest_n)
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return _last_good_vector.get(vector_id, [])
    _last_good_vector[vector_id] = observations
    return observations


def build_indicator_reading(vector_id: int, transform: str) -> dict | None:
    observations = fetch_vector(vector_id)
    dates = [o["date"] for o in observations]
    values = [float(o["value"]) for o in observations]
    return build_reading(dates, values, transform)
