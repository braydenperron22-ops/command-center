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

FUEL_PRICES_URL = "https://ontario.ca/v1/files/fuel-prices/fueltypesall.csv"
CITY_COLUMN = "North Bay"
FUEL_TYPE = "Regular Unleaded Gasoline"
CACHE_TTL_SECONDS = 12 * 60 * 60  # the survey itself only updates weekly (Mondays); twice a day is plenty
BASELINE_WEEKS = 12  # trailing window "normal" is judged against, so eco mode reacts to prices actually drifting rather than a fixed cents-per-litre number going stale over time

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


def eco_mode_status() -> dict | None:
    """{"price", "baseline", "eco_recommended", "as_of", "next_update"}
    — eco mode is recommended when the latest price is above the
    trailing BASELINE_WEEKS average, i.e. gas is expensive relative to
    what it's actually been running lately, not some fixed
    cents-per-litre cutoff that would go stale as prices drift over
    months. `next_update` is the latest reading's own date plus 7 days
    — derived from the actual weekly cadence observed in the data
    rather than assumed to always land on a specific weekday, so it
    self-corrects if the survey's publish day ever shifts. None if
    there isn't enough history yet to judge a baseline from."""
    readings = fetch_readings()
    if not readings:
        return None
    latest = readings[-1]
    baseline_pool = readings[:-1][-BASELINE_WEEKS:]
    if not baseline_pool:
        return None
    baseline = sum(r["price_cents_per_litre"] for r in baseline_pool) / len(baseline_pool)
    return {
        "price": latest["price_cents_per_litre"],
        "baseline": baseline,
        "eco_recommended": latest["price_cents_per_litre"] > baseline,
        "as_of": latest["date"],
        "next_update": latest["date"] + timedelta(days=7),
    }
