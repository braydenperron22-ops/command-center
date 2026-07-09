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


def current_country() -> str:
    rotation_index = int(time.time() // ROTATION_SECONDS) % 2
    return "us" if rotation_index == 0 else "ca"


def fetch_readings(fred_api_key: str) -> tuple[dict, dict]:
    """Every country's every indicator — needed regardless of which page is
    active, since the release-calendar ticker at the bottom is global."""
    seen_as_of = st.session_state.setdefault("seen_as_of", {})
    readings = {}
    new_flags = {}
    for c, indicators in INDICATORS.items():
        for ind in indicators:
            if ind.get("source") == "statcan":
                reading = statcan_client.build_indicator_reading(ind["vector_id"], ind["transform"])
            else:
                reading = fred_client.build_indicator_reading(ind["series_id"], fred_api_key, ind["transform"])
            key = (c, ind["key"])
            readings[key] = reading

            # Flag as "new" only if this session already had a prior value for
            # this indicator and it just changed — first-ever load establishes
            # the baseline instead of flashing everything as new.
            is_new = False
            if reading:
                prior = seen_as_of.get(key)
                if prior is not None and prior != reading["as_of"]:
                    is_new = True
                seen_as_of[key] = reading["as_of"]
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
