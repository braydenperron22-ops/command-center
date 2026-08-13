"""Daily North Bay gas prices from AffordableEnergy.ca — a real update
every day, unlike fuel_price_client.py's own government CSV source
(weekly only). Session request: "I wanna find a better way to pull live
gas prices... update day after day... that's the one I kinda want to
use." Confirmed live: fetches cleanly (200, no bot-block — unlike
canada.ca's real 403 seen elsewhere this session) and the page publishes
Yesterday/Today/Tomorrow Regular/Premium/Diesel prices specifically for
North Bay, as three `<h3>Gas Prices for {date}</h3>` blocks each
followed by a `grid-cols-3` price grid — confirmed via a real saved
fetch + BeautifulSoup inspection, not just a WebFetch summary.

This does NOT replace fuel_price_client.py's own weekly CSV: that feed
is still the only source with the 10-year depth _real_price_floor()
needs (real North Bay data back to 1990). This module only supplies a
fresher "today's price" input — fuel_price_client.eco_mode_status()
prefers this over the CSV's own latest row when it's reachable, falling
back to the CSV otherwise, same "never let one source's failure blank
the feature" pattern as weather_records_client/cpp_payment_dates.
"""

import re
from datetime import date, datetime

import requests
import streamlit as st
from bs4 import BeautifulSoup

import fetch_throttle

SOURCE_URL = "https://www.affordableenergy.ca/gas-prices/north-bay/"
FUEL_LABEL = "Regular"
# The site never discloses an update schedule — "Today" just reflects
# whatever's current whenever the page is loaded. An hour catches a
# same-day change quickly without hammering someone else's commercial
# site the way a static government CSV can be polled more casually.
CACHE_TTL_SECONDS = 60 * 60

_last_good_reading: dict | None = None


def _parse_heading_date(text: str) -> date:
    # "Thursday, August 13, 2026" — matches this specific site's own
    # heading format, not a general date parser.
    return datetime.strptime(text, "%A, %B %d, %Y").date()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_raw() -> dict | None:
    fetch_throttle.wait_turn()
    resp = requests.get(SOURCE_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")

    # Matched by the actual calendar date rather than DOM position
    # (Tomorrow/Today/Yesterday order) — the heading text itself never
    # says "Today", only a date, and trusting position would silently
    # mislabel a reading if the site ever reorders its own blocks.
    for h in soup.find_all("h3", string=re.compile(r"Gas Prices for", re.I)):
        date_text = h.get_text(strip=True).replace("Gas Prices for ", "").strip()
        try:
            heading_date = _parse_heading_date(date_text)
        except ValueError:
            continue
        if heading_date != date.today():
            continue
        price_grid = h.find_parent().find("div", class_=re.compile(r"grid-cols-3"))
        if price_grid is None:
            continue
        for block in price_grid.find_all("div", recursive=False):
            label_span = block.find("span", class_="block")
            if not label_span or label_span.get_text(strip=True) != FUEL_LABEL:
                continue
            value_span = block.find("span", class_=re.compile(r"text-2xl"))
            if value_span is None:
                continue
            try:
                price = float(value_span.get_text(strip=True))
            except ValueError:
                continue
            return {"price_cents_per_litre": price, "date": heading_date}
    return None


def today_price() -> dict | None:
    """{"price_cents_per_litre", "date"} for today's real North Bay
    Regular price, the last good reading if the page's briefly
    unreachable or today's block isn't found yet, or None if there's
    never been a good reading — matches fuel_price_client.fetch_readings'
    own last-good-copy convention."""
    global _last_good_reading
    try:
        result = _fetch_raw()
    except Exception:
        return _last_good_reading
    if result:
        _last_good_reading = result
    return result or _last_good_reading
