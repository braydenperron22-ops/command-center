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

Every date block on the page is kept (not just today's) — the site
already carries yesterday's real price on the same fetch, no second
request needed, which is what makes a genuine day-over-day change
(session request: "add a little arrow that shows how much higher or
lower it is from the day prior") a real reading instead of something
this app would have to start tracking on its own from scratch.
"""

import re
from datetime import date, datetime, timedelta

import requests
import streamlit as st
from bs4 import BeautifulSoup

import fetch_throttle
import persisted_state

SOURCE_URL = "https://www.affordableenergy.ca/gas-prices/north-bay/"
FUEL_LABEL = "Regular"
# The site never discloses an update schedule — "Today" just reflects
# whatever's current whenever the page is loaded. An hour catches a
# same-day change quickly without hammering someone else's commercial
# site the way a static government CSV can be polled more casually.
CACHE_TTL_SECONDS = 60 * 60


# Session request: "cache the results so it doesn't die on refreshes" —
# a plain module-level dict here didn't survive a real Streamlit
# process restart (a redeploy, a crash, Streamlit Cloud's own idle
# sleep/wake cycle): the very first today_price() call after one, if it
# happened to land before the site had published today's own block yet
# (real, confirmed live — see today_price's own comment below), had
# nothing to fall back to at all and returned None outright. Persisted
# now, same "survive a restart, not just a rerun" fix this app's other
# last-good-copy fallbacks already got (see e.g. commute_reminder.
# _shown_state's own comment on the identical class of bug). JSON can't
# key a dict by a real date object — save()'s own docstring: callers
# convert dates/sets to/from a JSON-friendly shape themselves — so this
# is stored as {iso_date_string: price}, converted to/from real date
# keys only at the two places that actually need them.
def _load_last_good() -> dict[date, float]:
    raw = persisted_state.load("daily_gas_last_good", {})
    out = {}
    for k, v in raw.items():
        try:
            out[date.fromisoformat(k)] = float(v)
        except (ValueError, TypeError):
            continue
    return out


_last_good_prices: dict[date, float] = _load_last_good()


def _parse_heading_date(text: str) -> date:
    # "Thursday, August 13, 2026" — matches this specific site's own
    # heading format, not a general date parser.
    return datetime.strptime(text, "%A, %B %d, %Y").date()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_raw() -> dict[date, float]:
    """{date: price_cents_per_litre} for every date block the page
    currently shows (real Yesterday/Today/Tomorrow, whatever dates
    those actually resolve to) — matched by each heading's own parsed
    calendar date rather than DOM position, so it can't be silently
    mislabeled if the site ever reorders its own blocks."""
    fetch_throttle.wait_turn()
    resp = requests.get(SOURCE_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")

    prices: dict[date, float] = {}
    for h in soup.find_all("h3", string=re.compile(r"Gas Prices for", re.I)):
        date_text = h.get_text(strip=True).replace("Gas Prices for ", "").strip()
        try:
            heading_date = _parse_heading_date(date_text)
        except ValueError:
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
                prices[heading_date] = float(value_span.get_text(strip=True))
            except ValueError:
                continue
    return prices


def today_price() -> dict | None:
    """{"price_cents_per_litre", "date", "change"} for the most recent
    real North Bay Regular price the site has actually published —
    "change" is that date's price minus the day before it, in
    cents/litre, or None if that prior day's block wasn't there (never
    invented, same "no number beats a guessed one" rule as this app's
    other real-data sources). Falls back to the last successfully-
    fetched set of prices if the page's briefly unreachable, matching
    fuel_price_client.fetch_readings' own last-good-copy convention;
    None if there's never been a good reading.

    Session report, once real live data existed to check this against:
    "our daily gas source... only works sometimes." Two real, separate
    causes, both fixed here. First: _last_good_prices used to be a
    plain in-memory dict, wiped on every process restart — see this
    module's own _load_last_good comment. Second, this function itself
    used to require date.today() to be an EXACT key in `prices`,
    returning None otherwise — confirmed live that the site's own
    published dates aren't always a clean, consecutive Yesterday/Today/
    Tomorrow set (a real fetch here came back {Aug 16, Aug 18, Aug 19}
    — Aug 17 genuinely missing from the site's own page that day), and
    the site "never discloses an update schedule" for when "Today"
    actually flips over either. Now uses whichever date is genuinely
    the LATEST one actually available, instead of insisting on an exact
    match — still a real, honestly-dated price (never backdated or
    invented), just no longer silently returning nothing over a gap
    that isn't this app's own fault."""
    global _last_good_prices
    try:
        prices = _fetch_raw()
    except Exception:
        prices = None
    if prices and prices != _last_good_prices:
        _last_good_prices = prices
        persisted_state.save("daily_gas_last_good", {d.isoformat(): p for d, p in prices.items()})
    prices = prices or _last_good_prices
    if not prices:
        return None
    latest = max(prices)
    prior_price = prices.get(latest - timedelta(days=1))
    change = (prices[latest] - prior_price) if prior_price is not None else None
    return {"price_cents_per_litre": prices[latest], "date": latest, "change": change}
