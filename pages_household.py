"""Household page: gas price and nearby incident news — split out from
the Today page, which was overrunning the screen once this joined
agenda + commute there. Garbage/recycling day used to live here too;
moved to a hero-row badge (see app.py) so it reads as a same-day alert
alongside rain/AQI/UV instead of a page you'd only see on its own
5-minute rotation slot.
"""

import time
from datetime import datetime

import streamlit as st

import fuel_price_client
import golf_client
import local_news_client
import tiles

# Deliberately just a recent-trend window, decoupled from whatever
# window eco mode's own floor is judged against (see
# fuel_price_client.FLOOR_LOOKBACK_YEARS — 10 years of weekly points
# would be unreadable noise compressed into a tile this small). This is
# only ever "which way has it been moving lately," not the reference
# the badge below is actually comparing against.
SPARKLINE_WEEKS = 16


def _render_fuel_price(now: datetime) -> None:
    """North Bay gas price vs. its own inflation-adjusted long-run
    median (see fuel_price_client.eco_mode_status) — built specifically
    to answer "should I bother driving in eco mode today," not just to
    display a number. Silent if the feed hasn't returned anything yet
    rather than an empty tile."""
    status = fuel_price_client.eco_mode_status()
    if not status:
        return
    if status["eco_recommended"]:
        badge_class, badge_text, tone = "badge-bad", "Eco mode recommended", "bad"
    else:
        badge_class, badge_text, tone = "badge-good", "Eco mode not needed", "good"
    as_of = f"{status['as_of'].strftime('%b')} {status['as_of'].day}"
    # Day-granularity only, not a specific time — the survey publishes
    # "before end of business" on its update day, not at a fixed hour,
    # so anything more precise than "today" would be a made-up promise.
    days_until_update = (status["next_update"] - now.date()).days
    update_text = "updates today" if days_until_update <= 0 else f"next update in {days_until_update}d"
    history = [r["price_cents_per_litre"] for r in fuel_price_client.fetch_readings()[-SPARKLINE_WEEKS:]]
    sparkline = tiles.sparkline_svg(history, tone)
    # Session request: "add a little arrow that shows how much higher or
    # lower it is from the day prior" — same bold-triangle pattern
    # pages_internals.py's Fear & Greed tile already uses, but colored
    # on this tile's own already-established meaning (badge-bad/-good
    # above: pricier is bad, cheaper is good), not the directional
    # green-for-up convention that tile uses for a score. Omitted
    # entirely when there's no real prior-day reading to compare
    # against (see daily_gas_price.today_price's own "change" field),
    # same as that tile omits its own arrow when the week-ago reading
    # isn't available.
    change = status.get("change")
    if change is not None:
        if change > 0:
            change_arrow, change_color = "▲", "#FF6961"
        elif change < 0:
            change_arrow, change_color = "▼", "#32D74B"
        else:
            change_arrow, change_color = "●", "#ECECF1"
        change_html = (
            f'<span style="color:{change_color};font-size:0.85em;margin-left:0.35em;">'
            f"{change_arrow} {abs(change):.1f}¢</span>"
        )
    else:
        change_html = ""
    st.markdown(
        f"""<div class="tile compact">
            <div class="tile-label compact">NORTH BAY GAS</div>
            <div class="tile-value-row">
                <div class="tile-value">{status['price']:.1f}¢/L{change_html}</div>{sparkline}
            </div>
            <div class="tile-prev">vs {status['baseline']:.1f}¢ 10yr real median · as of {as_of} · {update_text}</div>
            <div class="badge {badge_class}">{badge_text}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def _relative_time(seconds_ago: float) -> str:
    minutes = int(seconds_ago / 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


NEARBY_ROTATION_SECONDS = 10


def _render_local_news() -> None:
    """Real, nearby stuff only — police/OPP incident beats and
    road-closure/construction items (see local_news_client), not
    general local news. One headline at a time, rotating — same
    time-based pattern pages_home.py uses for its country rotation
    (int(time.time() // interval) % n, so it's driven by wall-clock
    time and needs nothing stored in session state). Silent if nothing
    currently qualifies rather than an empty-state tile — a quiet day
    locally isn't worth taking up space to announce."""
    items = local_news_client.fetch_items()
    if not items:
        return
    now_ts = time.time()
    index = int(now_ts // NEARBY_ROTATION_SECONDS) % len(items)
    item = items[index]
    st.markdown(f'<div class="tile-label compact">NEARBY · {index + 1}/{len(items)}</div>', unsafe_allow_html=True)
    meta = item["source"]
    if item["published"]:
        meta += f' · {_relative_time(now_ts - item["published"].timestamp())}'
    row = f"""<div class="news-feed-row news-cat-local compact">
        <div class="news-feed-headline">{item['headline']}</div>
        <div class="news-feed-meta">{meta}</div>
    </div>"""
    # Normal news-feed-list sizing, not agenda-feed-list — that scoping
    # is tuned for the agenda's 1-3 short calendar-event titles, and
    # blows real headline-length text up to one word per line.
    st.markdown(f'<div class="news-feed-list">{row}</div>', unsafe_allow_html=True)


# Session request: "Add a golf intelligence layer... PLAYABILITY...
# BUSYNESS... combine them into an overall GOLFABILITY." Same compact-
# tile styling as the gas price tile above — this page already is
# "local conditions I'd otherwise have to check myself," which is
# exactly what this is too.
def _render_golf(now: datetime) -> None:
    # cached_golfability(), not golfability() — this page render must
    # never be the thing that triggers a real (possibly ~5s, cold-
    # cache) fetch; see golf_client's own module-level comment for the
    # live bug this caused.
    result = golf_client.cached_golfability()
    if not result or result["golfability"] is None:
        return
    weather = result["weather"] or {}
    status = result["course_status"]
    status_class = "badge-good" if status == "OPEN" else "badge-bad" if status == "FULLY BOOKED" else "badge-neutral"
    demand_class = {"LOW": "badge-good", "MODERATE": "badge-neutral", "HIGH": "badge-bad"}.get(
        result["demand"], "badge-neutral"
    )
    detail_lines = []
    if weather.get("temp_c") is not None:
        detail_lines.append(f"{weather['temp_c']:.0f}°C")
    if weather.get("wind_kmh") is not None:
        detail_lines.append(f"Wind {weather['wind_kmh']:.0f} km/h")
    if weather.get("precip_probability") is not None:
        detail_lines.append(f"Rain {weather['precip_probability']:.0f}%")
    if result["occupancy_pct"] is not None:
        detail_lines.append(f"Tee-sheet occupancy {result['occupancy_pct']:.0f}%")
    detail_html = "".join(f'<div class="tile-prev">{line}</div>' for line in detail_lines)
    sub_scores = []
    if result["playability"] is not None:
        sub_scores.append(f"Playability: {result['playability']}/10")
    if result["busyness"] is not None:
        sub_scores.append(f"Busyness: {result['busyness']}/10")
    st.markdown(
        f"""<div class="tile compact">
            <div class="tile-label compact">⛳ HIGHVIEW GOLF · TODAY</div>
            <div class="tile-value">{result['golfability']} / 10</div>
            <div class="tile-prev">{" · ".join(sub_scores)}</div>
            {detail_html}
            <div class="badge {status_class}">{status or "—"}</div>
            <div class="badge {demand_class}">DEMAND: {result["demand"] or "—"}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def render(now: datetime) -> None:
    st.markdown('<div class="page-title page-title-household">Household</div>', unsafe_allow_html=True)
    _render_fuel_price(now)
    st.markdown('<div style="height: 0.5rem;"></div>', unsafe_allow_html=True)
    _render_golf(now)
    st.markdown('<div style="height: 0.5rem;"></div>', unsafe_allow_html=True)
    _render_local_news()
