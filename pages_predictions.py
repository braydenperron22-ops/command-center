"""Predictions: rolling, per-meeting rate-decision odds for the central
banks this app tracks (Federal Reserve, Bank of Canada, Bank of Japan —
see prediction_markets_client.BANKS for why not every major central
bank; ECB/BoE don't currently have an actively-maintained version of
this same market series). Session request: "make it its own page for
just prediction market things. start by doing this for the biggest
central banks and the 'expected outcome for them.'"

One tile per bank, verdict-first — same "the meaning has to be readable
from across the room" philosophy pages_internals.py already established
for this app's other probability-flavored page: the market's single
most-likely outcome and its own probability lead each tile, the full
five-way breakdown (50+/25 bps either direction, or no change) sits
underneath as supporting context, not the headline.
"""

import html
from datetime import datetime

import streamlit as st

import prediction_markets_client as pmc


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


def render() -> None:
    st.markdown('<div class="page-title page-title-predictions">Predictions</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="prediction-source-note">Market-implied odds from Polymarket — '
        "not this app's own forecast, just what real money is currently pricing in.</div>",
        unsafe_allow_html=True,
    )

    cols = st.columns(len(pmc.BANKS))
    for col, bank in zip(cols, pmc.BANKS):
        with col:
            st.markdown(_bank_tile_html(bank), unsafe_allow_html=True)
