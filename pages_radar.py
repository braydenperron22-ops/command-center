"""Radar page: RainViewer's animated radar (see radar_client.py for
why RainViewer over Environment Canada's own imagery), centered on
Corbeil, with a small dot for "you." Split out as its own page — a
live map deserves real screen space of its own, matching this app's
prior Radar page (see git log around 100fddd) before it was swapped
for Hourly; reinstated at the user's later request now that a nicer-
animated source exists, this time alongside Hourly rather than instead
of it.

Deliberately just the map: no storm-motion tracking, nearby-city
markers, or arrival prediction the old page used to have — those were
built around Environment Canada's own raw WMS pixel data, which
RainViewer's pre-rendered tiles don't expose, and were in any case
already removed once at the user's own request as "too inconsistent to
trust." This time the request was explicit: "that's it."
"""

import html

import streamlit as st

import radar_client


def render() -> None:
    st.markdown('<div class="page-title page-title-radar">Live Radar — Corbeil</div>', unsafe_allow_html=True)

    urls = radar_client.frame_urls()
    if not urls:
        st.markdown(
            '<div class="tile weather-radar-tile-large"><div class="tile-prev">Radar unavailable right now.</div></div>',
            unsafe_allow_html=True,
        )
        return

    # One flat line, no embedded newlines/indentation — pages_today.py/
    # pages_weather.py/the old pages_radar.py all independently hit the
    # same CommonMark bug: a multi-line indented f-string reads fine to
    # the markdown parser as long as every line has real content, but a
    # blank line in the middle of it ends that raw-HTML block early and
    # reparses everything after as an indented code block (literal
    # escaped text instead of the actual map). Nothing interpolated
    # here is ever empty at this point (urls is already guarded above),
    # so it's not currently at risk — kept flat anyway so it never can
    # be, without needing to re-derive this each time something here
    # changes.
    frames_html = "".join(
        f'<img class="weather-radar-frame-img" id="weather-radar-frame-{i}" src="{html.escape(url)}" />'
        for i, url in enumerate(urls)
    )
    st.markdown(
        '<div class="tile weather-radar-tile-large">'
        + f'<div class="weather-radar-frame weather-radar-frame-large">{frames_html}<div class="weather-radar-marker"></div></div>'
        + '<div class="weather-radar-credit">Radar data by RainViewer</div>'
        + "</div>",
        unsafe_allow_html=True,
    )
