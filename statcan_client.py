"""Statistics Canada WDS API access, used where FRED's Canada mirrors are stale."""

import requests
import streamlit as st

from indicators import build_reading

STATCAN_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods"


@st.cache_data(ttl=60 * 60, show_spinner=False)
def fetch_vector(vector_id: int, latest_n: int = 30) -> list[dict]:
    """Return recent observations for a StatCan vector, oldest first."""
    body = [{"vectorId": vector_id, "latestN": latest_n}]
    resp = requests.post(STATCAN_URL, json=body, timeout=10)
    resp.raise_for_status()
    payload = resp.json()[0]["object"]["vectorDataPoint"]
    return [{"date": p["refPer"], "value": p["value"]} for p in payload]


def build_indicator_reading(vector_id: int, transform: str) -> dict | None:
    observations = fetch_vector(vector_id)
    dates = [o["date"] for o in observations]
    values = [float(o["value"]) for o in observations]
    return build_reading(dates, values, transform)
