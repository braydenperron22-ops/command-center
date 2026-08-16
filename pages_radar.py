"""Radar page: RainViewer's animated radar (see radar_client.py for
why RainViewer over Environment Canada's own imagery), centered on
Corbeil, with a small dot for "you," plus a minute-by-minute rain
nowcast beside it (see precip_nowcast_client.py — session request:
"does RainViewer have a future forecast... similar to Apple?" — no,
discontinued; "look into other sources... xweather"). Split out as its
own page — a live map deserves real screen space of its own, matching
this app's prior Radar page (see git log around 100fddd) before it was
swapped for Hourly; reinstated at the user's later request now that a
nicer-animated source exists, this time alongside Hourly rather than
instead of it.

No storm-motion tracking, nearby-city markers, or arrival prediction
the old page used to have — those were built around Environment
Canada's own raw WMS pixel data, which RainViewer's pre-rendered tiles
don't expose, and were in any case already removed once at the user's
own request as "too inconsistent to trust." The minute-cast isn't a
repeat of that removed feature — it's a real, separate Xweather product
built specifically for exactly this "when does it start/stop" question,
not a home-grown projection off the radar's own pixels.

Side by side, not stacked: confirmed live that stacking the two tiles
vertically meant they were competing for the one dimension a kiosk
screen is actually short on (height, with a fixed header above and a
fixed ticker below both eating into it) — and that budget isn't even a
fixed number, since the header's own height varies with the morning-
briefing sentence's real length from one day to the next, so a stacked
layout kept finding new ways to overlap the ticker no matter how far
each tile's own spacing got trimmed. A kiosk screen is landscape, so
horizontal space is the dimension actually going unused; placing the
nowcast tile beside the radar instead of under it spends that instead.
"""

import html

import streamlit as st

import precip_nowcast_client
import radar_client


def _nowcast_summary(forecast: list[dict] | None) -> str:
    if not forecast:
        return "Rain forecast unavailable."
    starting = precip_nowcast_client.rain_starting_in_minutes(forecast)
    ending = precip_nowcast_client.rain_ending_in_minutes(forecast)
    if starting is not None:
        return "Rain starting now." if starting == 0 else f"Rain in {starting} min."
    if ending is not None:
        return f"Rain easing in {ending} min." if ending > 0 else "Rain easing now."
    if forecast[0]["precip_rate_mm"] > 0:
        return "Rain continuing."
    return "No rain expected."


def _nowcast_bars_svg(forecast: list[dict], width: int = 400, height: int = 44) -> str:
    values = [p["precip_rate_mm"] for p in forecast]
    peak = max(values) or 1.0
    n = len(values)
    bar_w = width / n
    bars = "".join(
        f'<rect x="{i * bar_w:.1f}" y="{height - max(1.5, (v / peak) * height):.1f}" '
        f'width="{max(bar_w - 1, 1):.1f}" height="{max(1.5, (v / peak) * height):.1f}" rx="1"/>'
        for i, v in enumerate(values)
    )
    return f'<svg class="precip-nowcast-bars" viewBox="0 0 {width} {height}" preserveAspectRatio="none">{bars}</svg>'


def _nowcast_html() -> str:
    forecast = precip_nowcast_client.minutely_forecast()
    summary = html.escape(_nowcast_summary(forecast))
    bars_html = _nowcast_bars_svg(forecast, width=400, height=44) if forecast else ""
    return (
        '<div class="tile precip-nowcast-tile">'
        + f'<div class="precip-nowcast-summary">{summary}</div>'
        + bars_html
        + '<div class="weather-radar-credit">Minute forecast by Xweather</div>'
        + "</div>"
    )


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
    radar_html = (
        '<div class="tile weather-radar-tile-large">'
        + f'<div class="weather-radar-frame weather-radar-frame-large">{frames_html}<div class="weather-radar-marker"></div></div>'
        + '<div class="weather-radar-credit">Radar data by RainViewer</div>'
        + "</div>"
    )
    # Both tiles built into ONE flat string and rendered in a single
    # st.markdown call, wrapped in .weather-radar-row (theme.py) — has
    # to be one real parent element for display:flex to lay them out
    # side by side; two separate st.markdown calls would just be two
    # unrelated sibling divs in normal block flow, stacked regardless
    # of any CSS on either one individually.
    st.markdown(f'<div class="weather-radar-row">{radar_html}{_nowcast_html()}</div>', unsafe_allow_html=True)
