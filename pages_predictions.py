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
format, like a list almost" — dropped the separate hero-tile row
entirely; every bank (Fed/BoC/BoJ included) is just a row in the one
list now, and the freed-up space is a deliberately empty column
reserved for future widgets.
"""

import html

import streamlit as st

import prediction_markets_client as pmc


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


def render() -> None:
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
        # Deliberately empty — reserved for whatever goes here next.
        pass
