"""Compares today's forecast high/low against the historical extreme for
this exact calendar date, going back RECORD_LOOKBACK_YEARS years — same
free Open-Meteo historical archive already used elsewhere in this app,
no new vendor/key. One wide-range request (a full calendar-year-aligned
span, not RECORD_LOOKBACK_YEARS separate per-year calls — confirmed live
the archive API has no "same date across many years" batch mode, but
happily returns a decade of daily data in one ~75KB response) filtered
client-side for entries matching today's month/day. Refreshed once a
day: the underlying history doesn't change more often than that, and a
year-aligned range naturally still contains any Feb 29s that fall in it.
"""

from datetime import date

import requests
import streamlit as st

import fetch_throttle
from config import WEATHER_LAT, WEATHER_LON

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
RECORD_LOOKBACK_YEARS = 10
# Only worth a badge when today's forecast is genuinely close to (or
# past) the historical extreme for this date — most days aren't close,
# and showing "18° vs record 24.8°" every single day would be noise,
# not signal (same "only show when it crosses a real threshold"
# convention as the UV/AQI hero badges).
RECORD_MARGIN_C = 2.0

_last_good_records: dict | None = None


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def _fetch_records_raw(today: date) -> dict | None:
    start = date(today.year - RECORD_LOOKBACK_YEARS, 1, 1)
    end = date(today.year - 1, 12, 31)
    fetch_throttle.wait_turn()
    resp = requests.get(
        ARCHIVE_URL,
        params={
            "latitude": WEATHER_LAT, "longitude": WEATHER_LON,
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": "America/Toronto",
        },
        timeout=15,
    )
    resp.raise_for_status()
    daily = resp.json().get("daily", {})
    suffix = f"-{today.month:02d}-{today.day:02d}"
    highs, lows = [], []
    for t, hi, lo in zip(daily.get("time", []), daily.get("temperature_2m_max", []), daily.get("temperature_2m_min", [])):
        if not t.endswith(suffix):
            continue
        if hi is not None:
            highs.append((hi, int(t[:4])))
        if lo is not None:
            lows.append((lo, int(t[:4])))
    if not highs and not lows:
        return None
    record_high = max(highs) if highs else None
    record_low = min(lows) if lows else None
    return {
        "record_high_c": record_high[0] if record_high else None,
        "record_high_year": record_high[1] if record_high else None,
        "record_low_c": record_low[0] if record_low else None,
        "record_low_year": record_low[1] if record_low else None,
    }


def record_context(forecast_high_c: float | None, forecast_low_c: float | None) -> dict | None:
    """{"kind": "high"|"low", "value", "record", "year"} once today's
    forecast is within RECORD_MARGIN_C of (or past) the historical
    extreme for this date — None on the (large majority of) days when
    there's nothing record-worthy to flag, or the archive fetch itself
    is unavailable with no prior good copy to fall back on yet."""
    global _last_good_records
    today = date.today()
    try:
        records = _fetch_records_raw(today)
    except Exception:
        records = _last_good_records
    if records is not None:
        _last_good_records = records
    if not records:
        return None

    if forecast_high_c is not None and records.get("record_high_c") is not None:
        if forecast_high_c >= records["record_high_c"] - RECORD_MARGIN_C:
            return {
                "kind": "high", "value": forecast_high_c,
                "record": records["record_high_c"], "year": records["record_high_year"],
            }
    if forecast_low_c is not None and records.get("record_low_c") is not None:
        if forecast_low_c <= records["record_low_c"] + RECORD_MARGIN_C:
            return {
                "kind": "low", "value": forecast_low_c,
                "record": records["record_low_c"], "year": records["record_low_year"],
            }
    return None
