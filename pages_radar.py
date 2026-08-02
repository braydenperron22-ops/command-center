"""Radar page: Environment Canada's own live radar reflectivity,
centered on Corbeil (see ec_radar.py) — split out from the Weather page
since a live map deserves real screen space of its own, not a shared
column next to the 7-day forecast.

No arrival/severity prediction here anymore — removed at the user's own
request after judging the lookahead-forecasting layer too inconsistent
to trust. Just the live map (a short animated loop of the last several
real frames), nearby city reference points, and a plain readout of the
dominant echo's own currently-measured drift, for reading manually.
"""

import streamlit as st

import ec_forecast
import ec_radar


def _city_markers_html(cities: list[dict]) -> str:
    """Small neutral-gray dots + labels for real nearby towns (see
    ec_radar.nearby_city_markers) — deliberately much quieter than the
    "you" marker, since these are just reference points for reading
    the map, not something to react to."""
    return "".join(
        f'<div class="weather-radar-city-marker" style="left:{c["x_pct"]:.1f}%; top:{c["y_pct"]:.1f}%;"></div>'
        f'<div class="weather-radar-city-label" style="left:{c["x_pct"]:.1f}%; top:{c["y_pct"]:.1f}%;">{c["label"]}</div>'
        for c in cities
    )


def render() -> None:
    st.markdown('<div class="page-title page-title-radar">Live Radar — Corbeil</div>', unsafe_allow_html=True)

    current = ec_forecast.current_conditions()
    kind = "snow" if current and current.get("category") == "snow" else "rain"

    city_markers_html = _city_markers_html(ec_radar.nearby_city_markers())

    # A short looping GIF of the last few real radar pulls, backfilled
    # straight from EC's own TIME dimension rather than waited-for
    # organically (session request: cache and play the last few so
    # storm motion is actually visible; then "pull previous radar
    # images directly from the source without having to build the
    # cache manually") — falls back to the plain static frame only in
    # the rare case that backfill hasn't produced 2+ real frames yet.
    loop_uri = ec_radar.radar_loop_data_uri(kind)
    image_src = loop_uri if loop_uri is not None else ec_radar.radar_image_url(kind)

    # Plain "moving NE at 32 km/h" readout of the real measured
    # trajectory (see ec_radar.storm_motion) — purely descriptive of
    # already-observed movement, not a prediction of whether/when it'll
    # reach here; that call is now made by reading the map itself. ""
    # when there's no measured motion to report yet.
    motion_label = ec_radar.storm_motion_label(kind)
    motion_html = f'<div class="tile-prev">{motion_label}</div>' if motion_label else ""

    # Session investigation: "[radar]... slow / laggy / freezes" led to
    # a real finding (image_src above is a multi-megabyte base64 data:
    # URI, 2MB+ confirmed live even at just 2 cached frames, re-sent on
    # every single 5s rerun regardless of whether it actually changed)
    # and a first attempt at fixing it via st.empty() + only calling
    # .markdown() on a genuine change — reverted after live testing
    # caught a real regression: Streamlit's own rerun model doesn't
    # "leave whatever was there" when a positionally-stable element
    # isn't touched in a given script run, it clears it, so that
    # approach made the radar tile blank on every unchanged rerun
    # instead of merely re-transmitting it (confirmed via MutationObserver
    # + get_page_text: the tile's own text content was gone entirely a
    # few reruns after a real "cache_key unchanged" cycle). A correct
    # fix needs Streamlit's actual media-serving mechanism (st.image's
    # own real, browser-cacheable /media/ URL instead of an inline data:
    # URI) rather than this trick — left as a real, separate follow-up
    # rather than shipped half-broken in this pass. Back to a plain
    # st.markdown() every rerun, same as before this investigation.
    #
    # One flat line, no embedded newlines/indentation — same bug class
    # already documented in pages_weather.py/pages_today.py: a
    # multi-line indented f-string reads fine to the markdown parser
    # AS LONG AS every line has content, but motion_html is "" whenever
    # there's no measured storm motion, which leaves a blank line in
    # the middle of what CommonMark treats as one continuous raw-HTML
    # block. A blank line ends that block, and everything after gets
    # reparsed as a NEW block — indented, which CommonMark reads as an
    # indented code block, rendering the whole radar frame as literal
    # escaped text instead of the actual map.
    st.markdown(
        f'<div class="tile weather-radar-tile weather-radar-tile-large">'
        f'<div class="tile-label compact">LIVE RADAR · {kind.upper()} · CORBEIL</div>'
        f'{motion_html}'
        f'<div class="weather-radar-frame weather-radar-frame-large">'
        f'<img class="weather-radar-image" src="{image_src}" />'
        f'{city_markers_html}'
        f'<div class="weather-radar-marker"></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
