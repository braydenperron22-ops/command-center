"""North Bay regular-unleaded gasoline prices from Ontario's official
Fuels Price Survey (data.ontario.ca) — weekly, government-published,
Open Government Licence. Not GasBuddy: that source has real-time
crowd-sourced pricing, but its Terms of Service explicitly prohibit
automated access. This is the legitimate alternative — a week stale at
most rather than live, but genuine North Bay data (the survey tracks
it by name), not some bigger city standing in for it.
"""

import csv
import io
from datetime import date, timedelta

import requests
import streamlit as st

import fetch_throttle
import statcan_client

FUEL_PRICES_URL = "https://ontario.ca/v1/files/fuel-prices/fueltypesall.csv"
CITY_COLUMN = "North Bay"
FUEL_TYPE = "Regular Unleaded Gasoline"
# The survey itself only updates weekly, but not at a fixed time —
# it's published "before end of business" on the update day, not
# necessarily first thing. 12h meant a process whose first fetch of the
# day landed before that publish (very plausible, e.g. an early-morning
# fetch) wouldn't see the new price until 12h later, making a genuine
# same-day update look like it "never happened" for most of the day.
# 2h catches the actual publish within a couple hours either way, and
# costs nothing extra — this is a static government CSV, not a
# rate-limited API.
CACHE_TTL_SECONDS = 2 * 60 * 60

# Session feedback: comparing today's price to a trailing 12-week
# average just measures whether prices are drifting up or down lately —
# gas that's "below its own recent average" during a slow multi-year
# climb still reads as "cheap" right up until it isn't. Real (inflation-
# adjusted) North Bay prices go back to 1990 in this same feed, so
# instead this compares today's price, in real terms, against the
# *median* real price over a long trailing window — a genuinely fixed
# reference (doesn't chase whatever the last few weeks happened to do),
# recomputed in nominal cents/litre every time using the latest CPI
# print rather than a number that quietly goes stale as inflation
# accumulates. 10 years is long enough to smooth past a single price
# shock (2022's spike, say) without reaching back before Canada's
# federal carbon-pricing backstop (2019) into an era that isn't really
# comparable to today's regulatory/tax structure.
FLOOR_LOOKBACK_YEARS = 10
CPI_VECTOR_ID = 41690973  # StatCan All-Items CPI (Canada) — same series config.py's own CPI (YoY) indicator tracks

_last_good_readings: list[dict] | None = None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_readings_raw() -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(FUEL_PRICES_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig")))
    readings = []
    for row in reader:
        if row.get("Fuel Type") != FUEL_TYPE:
            continue
        price_text = row.get(CITY_COLUMN)
        date_text = row.get("Date")
        if not price_text or not date_text:
            continue
        try:
            price = float(price_text)
            day = date.fromisoformat(date_text)
        except ValueError:
            continue
        if price <= 0:  # the survey uses 0 for "not collected that week" rather than omitting the cell
            continue
        readings.append({"date": day, "price_cents_per_litre": price})
    readings.sort(key=lambda r: r["date"])
    return readings


def fetch_readings() -> list[dict]:
    """Oldest first — {"date", "price_cents_per_litre"}, or the last
    good copy if the feed's briefly unreachable."""
    global _last_good_readings
    try:
        result = _fetch_readings_raw()
    except Exception:
        return _last_good_readings or []
    if result:
        _last_good_readings = result
    return result or (_last_good_readings or [])


def _cpi_value_at(cpi_obs: list[dict], target: date) -> float | None:
    """Latest CPI observation on or before `target` — CPI is a monthly
    series being matched against weekly gas readings, so most dates
    fall between two prints; the most recent one actually published as
    of that date is the correct real-world deflator, not a same-month
    or nearest one. `cpi_obs` must be sorted oldest first."""
    value = None
    for obs in cpi_obs:
        if obs["date"] <= target:
            value = obs["value"]
        else:
            break
    return value


def _real_price_floor(readings: list[dict]) -> float | None:
    """Median North Bay price over the trailing FLOOR_LOOKBACK_YEARS,
    each historical reading re-expressed in today's dollars via
    StatCan's CPI (see CPI_VECTOR_ID) — see the module docstring above
    FLOOR_LOOKBACK_YEARS for why this replaced a trailing-weeks nominal
    average. None if CPI data isn't reachable or there's too little
    history to mean anything — silently wrong is worse than silent."""
    latest_date = readings[-1]["date"]
    cutoff = latest_date - timedelta(days=365 * FLOOR_LOOKBACK_YEARS)
    pool = [r for r in readings if r["date"] >= cutoff]
    if len(pool) < 52:  # under a year of weekly readings isn't a real long-run reference
        return None

    try:
        raw_cpi = statcan_client.fetch_vector(CPI_VECTOR_ID, latest_n=(FLOOR_LOOKBACK_YEARS + 1) * 12)
    except Exception:
        return None
    if not raw_cpi:
        return None
    cpi_obs = []
    for o in raw_cpi:
        try:
            cpi_obs.append({"date": date.fromisoformat(str(o["date"])[:10]), "value": float(o["value"])})
        except (ValueError, TypeError):
            continue
    cpi_obs.sort(key=lambda o: o["date"])
    if not cpi_obs:
        return None
    cpi_today = cpi_obs[-1]["value"]
    if not cpi_today:
        return None

    real_prices = []
    for r in pool:
        cpi_then = _cpi_value_at(cpi_obs, r["date"])
        if not cpi_then:
            continue
        real_prices.append(r["price_cents_per_litre"] * (cpi_today / cpi_then))
    if len(real_prices) < 52:
        return None
    real_prices.sort()
    return real_prices[len(real_prices) // 2]


def eco_mode_status() -> dict | None:
    """{"price", "baseline", "eco_recommended", "as_of", "next_update"}
    — eco mode is recommended when today's price, in real terms, is
    above the median real North Bay price over the last
    FLOOR_LOOKBACK_YEARS (see _real_price_floor) — a fixed, inflation-
    adjusted reference rather than a trailing-weeks average that just
    tracks whatever prices happened to do recently. `next_update` is
    the latest reading's own date plus 7 days — derived from the actual
    weekly cadence observed in the data rather than assumed to always
    land on a specific weekday, so it self-corrects if the survey's
    publish day ever shifts. None if there isn't enough price history
    or CPI data to judge a real floor from."""
    readings = fetch_readings()
    if not readings:
        return None
    latest = readings[-1]
    floor = _real_price_floor(readings)
    if floor is None:
        return None
    return {
        "price": latest["price_cents_per_litre"],
        "baseline": floor,
        "eco_recommended": latest["price_cents_per_litre"] > floor,
        "as_of": latest["date"],
        "next_update": latest["date"] + timedelta(days=7),
    }
