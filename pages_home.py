"""Home page: rotating US/Canada macro dashboard."""

import time

import streamlit as st

import fred_client
import market_client
import regime_bar
import statcan_client
from config import COUNTRY_META, INDICATORS, MARKET_INDEX, ROTATION_SECONDS, YIELD_SPREAD_SERIES_ID
from flags import flag_for
from tiles import render_tile

NEW_BADGE_SECONDS = 24 * 60 * 60  # how long a freshly detected release stays flagged "NEW"

# Module-level (not st.session_state) so a freshly detected release
# stays flagged across every session/reconnect for the full window
# below, not just within one browser session — a kiosk reconnecting
# (network hiccup, tab reload, autorefresh's own websocket churn, ...)
# used to silently reset the old session-scoped tracking and lose the
# badge entirely, which is almost certainly why a real release never
# visibly triggered it.
_last_as_of: dict[tuple, str] = {}
_detected_at: dict[tuple, float] = {}


def current_country() -> str:
    rotation_index = int(time.time() // ROTATION_SECONDS) % 2
    return "us" if rotation_index == 0 else "ca"


def fetch_readings(fred_api_key: str) -> tuple[dict, dict]:
    """Every country's every indicator — needed regardless of which page is
    active, since the release-calendar ticker at the bottom is global."""
    readings = {}
    new_flags = {}
    now = time.time()
    for c, indicators in INDICATORS.items():
        for ind in indicators:
            if ind.get("source") == "statcan":
                reading = statcan_client.build_indicator_reading(ind["vector_id"], ind["transform"])
            else:
                reading = fred_client.build_indicator_reading(ind["series_id"], fred_api_key, ind["transform"])
            key = (c, ind["key"])
            readings[key] = reading

            # "New" for a full NEW_BADGE_SECONDS from the moment WE
            # first notice the latest observation change, not from the
            # observation's own as_of date — for a monthly series like
            # CPI, as_of is dated the 1st of the month it *covers*, not
            # when it was actually published (BLS/StatCan typically
            # report ~2 weeks after month-end), so comparing that date
            # against wall-clock time would almost never land within 24h
            # even right after a real release. The first time this
            # process ever sees a given indicator, its value just
            # establishes the baseline (no detection timestamp set) so
            # a fresh redeploy doesn't flash every tile "NEW" at once.
            is_new = False
            if reading:
                as_of = reading["as_of"]
                if key not in _last_as_of:
                    _last_as_of[key] = as_of
                elif _last_as_of[key] != as_of:
                    _last_as_of[key] = as_of
                    _detected_at[key] = now
                detected_at = _detected_at.get(key)
                is_new = detected_at is not None and (now - detected_at) <= NEW_BADGE_SECONDS
            new_flags[key] = is_new
    return readings, new_flags


def render(fred_api_key: str, readings: dict, new_flags: dict):
    # Own try/except rather than relying on _safe_render's page-wide
    # catch in app.py — a regime bug should lose just the banner, not
    # blank the whole page's indicator tiles behind the generic error
    # message.
    try:
        regime_bar.render(readings)
    except Exception:
        pass

    country = current_country()
    meta = COUNTRY_META[country]

    market_html = ""
    market = market_client.fetch_ytd_return(MARKET_INDEX[country]["series_id"], fred_api_key)
    if market:
        direction_class = "market-up" if market["ytd_pct"] >= 0 else "market-down"
        sign = "+" if market["ytd_pct"] >= 0 else ""
        market_html = (
            f'<div class="market-pill"><span class="market-pill-label">{MARKET_INDEX[country]["label"]} YTD</span>'
            f'<span class="market-pill-value {direction_class}">{sign}{market["ytd_pct"]:.1f}%</span></div>'
        )

    st.markdown(
        f"""<div style="text-align:center; margin: 0.8rem 0 1.2rem;">
            <div class="flag-badge">{flag_for(country)}</div>
            <div class="country-name">{meta['name']}</div>{market_html}
        </div>""",
        unsafe_allow_html=True,
    )

    yield_spread = None
    if country == "us":
        yield_spread = fred_client.fetch_latest_value(YIELD_SPREAD_SERIES_ID, fred_api_key)

    cols = st.columns(len(INDICATORS[country]))
    for i, ind in enumerate(INDICATORS[country]):
        key = (country, ind["key"])
        extra_line = None
        if ind["key"] == "yield_10y" and yield_spread is not None:
            extra_line = f"10Y–2Y spread: {yield_spread:+.2f}pp"
        with cols[i]:
            render_tile(
                ind["label"], ind["unit"], readings[key],
                good_direction=ind.get("good_direction"), is_new=new_flags[key],
                extra_line=extra_line,
            )
