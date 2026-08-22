"""Predictions: rolling, per-meeting rate-decision odds for every central
bank prediction_markets_client.BANKS actually covers. Session history:
"make it its own page for just prediction market things. start by doing
this for the biggest central banks" (shipped first as big Fed/BoC/BoJ
hero tiles) -> "I want all of the rate odds as many as you can find...
I want them all on the side with the country name and then the most
likely outcome and the percentage" (added the compact all-bank side
list alongside those tiles) -> "don't make the BoC, Fed, and the other
one big, make them fit into the same row... leave an open spot on the
right side, we're gonna put some other things there... nice, clean
format, like a list almost" (dropped the separate hero-tile row
entirely) -> "what other markets are there... pull the consensus...
build a forecast... estimate if it's gonna be coming in cooler or
hotter than expected" (added a fixed CPI + unemployment pair) -> "make
it a big number... put it in a box, make it all fancy... instead of
having two of them that are kinda random... find data for Canada as
well... have the next closest event show up automatically... across
Canada and the US" (added Canada, one hero box for whichever series is
soonest) -> "is there anything more outside of just the basic stuff...
if so, for the US, add it" — DATA_SERIES now also covers Core PCE, ISM
Manufacturing/Services PMI, Non-Farm Payrolls, UMich Consumer
Sentiment, and GDP growth. Not all of those have an honest "last
actual" baseline available in this app (see _EXTRA_FRED_SERIES and
prediction_markets_client.DATA_SERIES's own reading_key/fred_series
fields) — those render as a plain forecast box instead of faking a
hotter/cooler call against a baseline that isn't real.
"""

import html
from datetime import datetime

import streamlit as st

import fred_client
import prediction_markets_client as pmc
from flags import flag_for

_DIRECTION_TONE = {"cooler": "good", "hotter": "bad", "in-line": "neutral"}
_DIRECTION_WORD = {"cooler": "COOLER", "hotter": "HOTTER", "in-line": "IN LINE"}

# A few DATA_SERIES entries (Core PCE, UMich Sentiment) have a real FRED
# series backing them but aren't in config.py's INDICATORS — adding them
# there would also grow the Home page's tile grid and the ticker, well
# beyond what was actually asked for here. Fetched directly instead,
# independent of the `readings` dict pages_home.py already builds.
_EXTRA_FRED_SERIES = {
    "us_core_pce": ("PCEPILFE", "yoy"),
    "us_umich_sentiment": ("UMCSENT", "level"),
}


def _last_actual_for_series(series: str, cfg: dict, readings: dict, fred_api_key: str | None) -> float | None:
    reading_key = cfg.get("reading_key")
    if reading_key:
        reading = readings.get(reading_key)
        return reading.get("current") if reading else None
    extra = _EXTRA_FRED_SERIES.get(series)
    if not extra or not fred_api_key:
        return None
    series_id, transform = extra
    if transform == "yoy":
        reading = fred_client.build_indicator_reading(series_id, fred_api_key, "yoy")
        return reading.get("current") if reading else None
    return fred_client.fetch_latest_value(series_id, fred_api_key)


def _format_release_date(iso_date: str | None) -> str:
    if not iso_date:
        return ""
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%B %-d, %Y")
    except (ValueError, TypeError):
        return ""


def _side_list_html() -> str:
    rows = []
    entries = []
    for bank in pmc.BANKS:
        odds = pmc.current_odds(bank)
        if not odds:
            continue
        bucket, prob = pmc.most_likely_outcome(odds)
        entries.append((odds.get("end_date") or "", bank, bucket, prob))
    # Soonest meeting first — draws the eye to whatever's actually
    # coming up next, not an arbitrary or alphabetical order.
    entries.sort(key=lambda e: e[0])
    for end_date, bank, bucket, prob in entries:
        country = pmc.BANK_COUNTRIES[bank]
        direction = pmc.bucket_direction(bucket)
        # Session request: "instead of central banks, I just want the
        # flags. And then what's projected for each central bank" — the
        # country name is replaced by its flag (title attribute keeps
        # the name available on hover/screen readers), same bank ->
        # percentage -> outcome column order as before.
        #
        # Session follow-up: "find a way to make it known when a
        # contract is almost up or when that decision is due... a
        # number next to the odds in brackets... or have it dynamically
        # colored." Both: a plain day count, plus an escalating color as
        # the decision actually approaches (see days_until_urgency).
        days = pmc.days_until(end_date)
        days_html = ""
        if days is not None:
            urgency = pmc.days_until_urgency(days)
            day_text = "today" if days == 0 else f"{days}d"
            days_html = f'<span class="prediction-row-days prediction-row-days-{urgency}">{day_text}</span>'
        rows.append(
            f'<div class="prediction-row">'
            f'<span class="prediction-row-country" title="{html.escape(country)}">{flag_for(pmc.BANK_FLAG_CODES[bank])}</span>'
            f'<span class="prediction-row-pct">{prob * 100:.0f}%</span>'
            f'<span class="prediction-row-outcome prediction-direction-{direction}">{html.escape(pmc.BUCKET_LABELS[bucket])}</span>'
            f'{days_html}'
            f"</div>"
        )
    if not rows:
        return '<div class="tile-prev">data unavailable</div>'
    return "".join(rows)


def _global_consensus_html() -> str:
    """One big number below the full bank list — session request: "I'm
    a guy who likes simplicity... a clear, easy to see signal... take
    the implied odds of every single outcome of every single central
    bank and make a single number, which is like the central bank of
    the world, and what the world is doing on average." Same big-
    number-in-a-colored-box shape as the NEXT PRINT hero (_macro_hero_
    html) below, but toned by rate direction (cut/hold/hike, the same
    ice/fire palette .prediction-direction-cut/-hike already use) —
    good/bad/neutral doesn't apply to a rate direction the way it does
    to a hotter/cooler CPI surprise (see that box's own comment).
    "" whenever pmc.global_consensus() itself has nothing (no bank
    anywhere has live data), same "just omit it" rule every other
    optional tile in this app already follows."""
    consensus = pmc.global_consensus()
    if not consensus:
        return ""
    direction, prob, count = consensus["direction"], consensus["probability"], consensus["bank_count"]
    tag_text = pmc.DIRECTION_LABELS[direction].upper()
    return (
        f'<div class="tile prediction-global-tile">'
        f'<div class="tile-label">GLOBAL CENTRAL BANK</div>'
        f'<div class="prediction-macro-box prediction-macro-box-{direction}">'
        f'<div class="prediction-macro-number">{prob * 100:.0f}<span class="prediction-macro-unit">%</span></div>'
        f'<div class="prediction-macro-tag prediction-macro-tag-{direction}">{html.escape(tag_text)}</div>'
        f"</div>"
        f'<div class="internals-context">Average across all {count} tracked banks — real money\'s own '
        f"combined lean on what's coming next, not this app's own forecast.</div>"
        f"</div>"
    )


def _macro_hero_html(readings: dict, fred_api_key: str | None) -> str:
    # cached_next_data_series()/cached_data_forecast(), not the real
    # next_data_series()/current_data_forecast() — this page render
    # must never be the thing that triggers a real (a Polymarket search
    # per tracked series, ~10s+ cold) fetch; see prediction_markets_
    # client's own module comment for the live bug this caused.
    series = pmc.cached_next_data_series()
    if series is None:
        return '<div class="tile-prev">data unavailable</div>'
    cfg = pmc.DATA_SERIES[series]
    forecast_data = pmc.cached_data_forecast(series)
    if not forecast_data:
        return '<div class="tile-prev">data unavailable</div>'
    unit = cfg["unit"]
    decimals = cfg.get("decimals", 2)
    release = _format_release_date(forecast_data.get("end_date"))
    release_line = f" &middot; releases {html.escape(release)}" if release else ""
    last_actual = _last_actual_for_series(series, cfg, readings, fred_api_key)
    result = pmc.forecast_vs_last_actual(series, last_actual) if last_actual is not None else None
    if result:
        tone = _DIRECTION_TONE[result["direction"]]
        tag_text = _DIRECTION_WORD[result["direction"]]
        context = f'Market-implied vs. last actual {result["last_actual"]:.{decimals}f}{unit}{release_line}'
    else:
        # No honest baseline to compare against (ISM's own data is
        # proprietary, no free FRED series; Non-Farm Payrolls/GDP would
        # need a diff/annualized transform this app doesn't otherwise
        # use) — show the market's own number plainly rather than
        # faking a hotter/cooler call.
        tone = "neutral"
        tag_text = "MARKET FORECAST"
        context = f"Market-implied next print{release_line}"
    return (
        f'<div class="prediction-macro-heading">{html.escape(cfg["label"].upper())} &mdash; {html.escape(cfg["country"].upper())}</div>'
        f'<div class="prediction-macro-box prediction-macro-box-{tone}">'
        f'<div class="prediction-macro-number">{forecast_data["forecast"]:.{decimals}f}<span class="prediction-macro-unit">{html.escape(unit)}</span></div>'
        f'<div class="prediction-macro-tag prediction-macro-tag-{tone}">{tag_text}</div>'
        f"</div>"
        f'<div class="internals-context">{context}</div>'
    )


def render(readings: dict | None = None, fred_api_key: str | None = None) -> None:
    readings = readings or {}
    st.markdown('<div class="page-title page-title-predictions">Predictions</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="prediction-source-note">Market-implied odds from Polymarket — '
        "not this app's own forecast, just what real money is currently pricing in.</div>",
        unsafe_allow_html=True,
    )

    list_col, open_col = st.columns([3, 2])
    with list_col:
        st.markdown(
            f'<div class="tile prediction-side-tile">'
            f'<div class="tile-label">ALL CENTRAL BANKS</div>'
            f'<div class="prediction-side-list">{_side_list_html()}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
        global_html = _global_consensus_html()
        if global_html:
            st.markdown(global_html, unsafe_allow_html=True)
    with open_col:
        st.markdown(
            f'<div class="tile prediction-macro-tile">'
            f'<div class="tile-label">NEXT PRINT</div>'
            f"{_macro_hero_html(readings, fred_api_key)}"
            f"</div>",
            unsafe_allow_html=True,
        )
