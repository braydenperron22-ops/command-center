"""Predictions: rolling, per-meeting rate-decision odds for every central
bank prediction_markets_client.BANKS actually covers. Session history:
"make it its own page for just prediction market things. start by doing
this for the biggest central banks" (shipped first for Fed/BoC/BoJ) ->
"I want all of the rate odds as many as you can find... I want them all
on the side with the country name and then the most likely outcome and
the percentage. So it's like, what is expected of them?"

Two-part layout: FEATURED_BANKS keep the original detailed tile (full
verdict + the whole outcome breakdown, same "readable from across the
room" verdict-first shape pages_internals.py already established) in
the wider main column; every bank in BANKS — featured ones included, so
the side list is genuinely complete on its own — gets one compact row
(country, most likely outcome, probability) in a side list, sorted by
whichever meeting is coming up soonest.
"""

import html
from datetime import datetime

import streamlit as st

import prediction_markets_client as pmc

# The original three, kept as the detailed hero tiles — every other
# bank BANKS covers gets the compact side-list treatment only, since a
# full 5-way breakdown tile per bank wouldn't fit for a roster this
# size (see the session request behind this file's own docstring: "as
# many as you can find," not "in this much detail for all of them").
FEATURED_BANKS = ["fed", "boc", "boj"]


def _format_meeting_date(iso_date: str | None) -> str:
    if not iso_date:
        return ""
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%B %-d, %Y")
    except (ValueError, TypeError):
        return ""


def _bank_tile_html(bank: str) -> str:
    label = pmc.BANK_LABELS[bank]
    odds = pmc.current_odds(bank)
    if not odds:
        return (
            f'<div class="tile prediction-tile">'
            f'<div class="tile-label">{html.escape(label.upper())}</div>'
            f'<div class="tile-prev">data unavailable</div>'
            f"</div>"
        )

    bucket, prob = pmc.most_likely_outcome(odds)
    # Cutting rates reads as the market anticipating a weaker economy —
    # the classic "good news is bad news" market read isn't something
    # this tile should try to arbitrate, so tone stays neutral for every
    # bucket rather than picking a winner/loser color the way a plain %
    # change tile would. Consistent with pages_internals.py's own
    # ratio tiles, which use the same neutral treatment for numbers that
    # aren't inherently good or bad.
    meeting_date = _format_meeting_date(odds.get("end_date"))
    meeting_line = f"Next meeting: {html.escape(meeting_date)}" if meeting_date else ""

    rows = []
    for b in pmc.BUCKET_ORDER:
        if b not in odds["outcomes"]:
            continue
        pct = odds["outcomes"][b] * 100
        leading = " prediction-bar-row-leading" if b == bucket else ""
        rows.append(
            f'<div class="prediction-bar-row{leading}">'
            f'<span class="prediction-bar-label">{html.escape(pmc.BUCKET_LABELS[b])}</span>'
            f'<span class="prediction-bar-track"><span class="prediction-bar-fill" style="width:{pct:.1f}%"></span></span>'
            f'<span class="prediction-bar-pct">{pct:.1f}%</span>'
            f"</div>"
        )

    return (
        f'<div class="tile prediction-tile">'
        f'<div class="tile-label">{html.escape(label.upper())}</div>'
        f'<div class="internals-verdict internals-verdict-neutral">{html.escape(pmc.BUCKET_LABELS[bucket])} · {prob * 100:.0f}%</div>'
        f'<div class="internals-context">{meeting_line}</div>'
        f'<div class="prediction-breakdown">{"".join(rows)}</div>'
        f"</div>"
    )


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
        rows.append(
            f'<div class="prediction-row">'
            f'<span class="prediction-row-country">{html.escape(country)}</span>'
            f'<span class="prediction-row-outcome">{html.escape(pmc.BUCKET_LABELS[bucket])}</span>'
            f'<span class="prediction-row-pct">{prob * 100:.0f}%</span>'
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

    main_col, side_col = st.columns([3, 2])
    with main_col:
        tile_cols = st.columns(len(FEATURED_BANKS))
        for col, bank in zip(tile_cols, FEATURED_BANKS):
            with col:
                st.markdown(_bank_tile_html(bank), unsafe_allow_html=True)
    with side_col:
        st.markdown(
            f'<div class="tile prediction-side-tile">'
            f'<div class="tile-label">ALL CENTRAL BANKS</div>'
            f'<div class="prediction-side-list">{_side_list_html()}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
