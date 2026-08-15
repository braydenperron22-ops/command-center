"""Compares today's forecast high/low against the TRUE all-time
historical extreme for this exact calendar date, back to ARCHIVE_START_
YEAR — same free Open-Meteo historical archive already used elsewhere
in this app, no new vendor/key. One wide-range request (a full
calendar-year-aligned span, not one call per year — confirmed live the
archive API has no "same date across many years" batch mode, but
happily returns the whole archive's daily data in one request) filtered
client-side for entries matching today's month/day. Refreshed once a
day: the underlying history doesn't change more often than that, and a
year-aligned range naturally still contains any Feb 29s that fall in it.

Session report: "27 degrees in 2025... that is not a record high, it
is a year ago" — this used to look back only RECORD_LOOKBACK_YEARS (10)
years and label the result "Near record," which was real but genuinely
misleading: it's the warmest in a decade, not the warmest ever. Follow-
up, once that was made honest with a "(10y)" label instead: "the
hottest August 7th ever recorded... why don't you just say that?"
Checked live what the archive API can actually support before
committing to that — it hard-floors at 1940-01-01 (anything earlier is
a 400), so ARCHIVE_START_YEAR=1940 is the true earliest "ever" this
data source can honestly claim, not an arbitrary round number. Real
consequence, confirmed live: the true all-time high for Aug 7 turned
out to be 31.2°C in 2001, not 27.0°C in 2025 — 2025 wasn't even in the
top 5 hottest Aug 7s on record. This is a real trade-off the badge now
carries: it fires far less often (a much bigger true extreme is a
harder bar to get near) and the underlying fetch is genuinely heavier
(86 years of daily data, ~14s confirmed live) — both accepted knowingly
rather than discovered by surprise, since the request size only grows
with wall-clock time regardless.
"""

from datetime import date, timedelta

import requests
import streamlit as st

import data_health
import fetch_throttle
from config import WEATHER_LAT, WEATHER_LON

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
# Open-Meteo's archive hard-floors here — confirmed live, any start_date
# before this gets a 400 ("out of allowed range from 1940-01-01"). Not a
# chosen window; this is as far back as "ever recorded" can honestly go
# with this data source.
ARCHIVE_START_YEAR = 1940
# Only worth a badge when today's forecast is genuinely close to (or
# past) the historical extreme for this date — most days aren't close,
# and showing "18° vs record 24.8°" every single day would be noise,
# not signal (same "only show when it crosses a real threshold"
# convention as the UV/AQI hero badges).
RECORD_MARGIN_C = 2.0

_last_good_records: dict | None = None


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def _fetch_records_raw(today: date) -> dict | None:
    start = date(ARCHIVE_START_YEAR, 1, 1)
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
        # 86 years of daily data takes genuinely longer than a 10-year
        # slice did (~14s confirmed live) — the old 15s timeout was
        # already close to that; bumped for real headroom, not guessed.
        timeout=30,
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


def record_context(current_temp_c: float | None) -> dict | None:
    """{"kind": "high"|"low", "value", "record", "year"} once the
    CURRENT actual temperature — not the day's forecast high/low — is
    within RECORD_MARGIN_C of (or past) the historical extreme for this
    date. Gated on the live reading on purpose: the day's forecast low
    might be a genuine near-record 8am reading, but showing "Record
    low" all afternoon while it's actually 24° out would be describing
    a moment that's already over (or hasn't happened yet). None on the
    (large majority of) days when nothing's record-worthy right now, or
    the archive fetch itself is unavailable with no prior good copy to
    fall back on yet."""
    global _last_good_records
    today = date.today()
    try:
        records = _fetch_records_raw(today)
    except Exception:
        records = _last_good_records
    if records is not None:
        _last_good_records = records
    if not records or current_temp_c is None:
        return None

    if records.get("record_high_c") is not None and current_temp_c >= records["record_high_c"] - RECORD_MARGIN_C:
        return {
            "kind": "high", "value": current_temp_c,
            "record": records["record_high_c"], "year": records["record_high_year"],
        }
    if records.get("record_low_c") is not None and current_temp_c <= records["record_low_c"] + RECORD_MARGIN_C:
        return {
            "kind": "low", "value": current_temp_c,
            "record": records["record_low_c"], "year": records["record_low_year"],
        }
    return None


# Session request: "it should also learn things about my environment...
# is the weather warming up, or is the weather cooling off." The daily
# brief's own weather fact (morning_briefing._weather_clause) only ever
# carries TODAY's live reading — a genuine multi-day trend needs real
# day-by-day history, from the same Open-Meteo archive endpoint
# _fetch_records_raw above already proves reachable, just a short
# recent window instead of the full 86-year span (a handful of days,
# not tens of thousands — genuinely fast, nothing like that fetch's own
# confirmed ~14s).
RECENT_HIGHS_LOOKBACK_DAYS = 10

_last_good_recent_highs: list[dict] | None = None


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def _fetch_recent_highs_raw(today: date) -> list[dict]:
    # end_date is yesterday, not today — the archive only has FINALIZED
    # days; today's own reading belongs to the live weather fetch
    # instead (_weather_clause), not this historical source, so the two
    # never double up on the same day.
    end = today - timedelta(days=1)
    start = end - timedelta(days=RECENT_HIGHS_LOOKBACK_DAYS - 1)
    fetch_throttle.wait_turn()
    resp = requests.get(
        ARCHIVE_URL,
        params={
            "latitude": WEATHER_LAT, "longitude": WEATHER_LON,
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "daily": "temperature_2m_max",
            "timezone": "America/Toronto",
        },
        timeout=15,
    )
    resp.raise_for_status()
    daily = resp.json().get("daily", {})
    return [
        {"date": t, "high_c": hi}
        for t, hi in zip(daily.get("time", []), daily.get("temperature_2m_max", []))
        if hi is not None
    ]


def recent_daily_highs() -> list[dict]:
    """Last RECENT_HIGHS_LOOKBACK_DAYS real daily highs, oldest first —
    {"date" (ISO string), "high_c"} — ending yesterday. For
    morning_briefing._environment_trends_block's own genuine weather-
    trend tracking, not this module's own record-badge use above. []
    if the archive fetch fails with no prior good copy yet, same last-
    good-copy convention as record_context."""
    global _last_good_recent_highs
    today = date.today()
    try:
        result = _fetch_recent_highs_raw(today)
    except Exception:
        result = None
    if result:
        _last_good_recent_highs = result
        data_health.record_success("weather_trends")
    return result if result is not None else (_last_good_recent_highs or [])
