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
Canada and the US" — the reserved right column is now a single hero box
for whichever tracked series (US or Canada, CPI or unemployment) has the
soonest still-open print (see
prediction_markets_client.next_data_series()), not a fixed pair.
"""

import html
from datetime import datetime

import streamlit as st

import prediction_markets_client as pmc

_DIRECTION_TONE = {"cooler": "good", "hotter": "bad", "in-line": "neutral"}
_DIRECTION_WORD = {"cooler": "COOLER", "hotter": "HOTTER", "in-line": "IN LINE"}


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
    for _, bank, bucket, prob in entries:
        country = pmc.BANK_COUNTRIES[bank]
        direction = pmc.bucket_direction(bucket)
        # Session request: bank on the left, then the percentage, then
        # the outcome — reordered from the original country/outcome/
        # percentage layout.
        rows.append(
            f'<div class="prediction-row">'
            f'<span class="prediction-row-country">{html.escape(country)}</span>'
            f'<span class="prediction-row-pct">{prob * 100:.0f}%</span>'
            f'<span class="prediction-row-outcome prediction-direction-{direction}">{html.escape(pmc.BUCKET_LABELS[bucket])}</span>'
            f"</div>"
        )
    if not rows:
        return '<div class="tile-prev">data unavailable</div>'
    return "".join(rows)


def _macro_hero_html(readings: dict) -> str:
    series = pmc.next_data_series()
    if series is None:
        return '<div class="tile-prev">data unavailable</div>'
    cfg = pmc.DATA_SERIES[series]
    reading = readings.get(cfg["reading_key"])
    last_actual = reading.get("current") if reading else None
    result = pmc.forecast_vs_last_actual(series, last_actual)
    if not result:
        return '<div class="tile-prev">data unavailable</div>'
    tone = _DIRECTION_TONE[result["direction"]]
    word = _DIRECTION_WORD[result["direction"]]
    unit = cfg["unit"]
    release = _format_release_date(result.get("end_date"))
    release_line = f" &middot; releases {html.escape(release)}" if release else ""
    return (
        f'<div class="prediction-macro-heading">{html.escape(cfg["label"].upper())} &mdash; {html.escape(cfg["country"].upper())}</div>'
        f'<div class="prediction-macro-box prediction-macro-box-{tone}">'
        f'<div class="prediction-macro-number">{result["forecast"]:.2f}<span class="prediction-macro-unit">{html.escape(unit)}</span></div>'
        f'<div class="prediction-macro-tag prediction-macro-tag-{tone}">{word}</div>'
        f"</div>"
        f'<div class="internals-context">Market-implied vs. last actual {result["last_actual"]:.2f}{unit}{release_line}</div>'
    )


def render(readings: dict | None = None) -> None:
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
    with open_col:
        st.markdown(
            f'<div class="tile prediction-macro-tile">'
            f'<div class="tile-label">NEXT PRINT</div>'
            f"{_macro_hero_html(readings)}"
            f"</div>",
            unsafe_allow_html=True,
        )
