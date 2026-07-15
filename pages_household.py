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
import local_news_client


def _render_fuel_price(now: datetime) -> None:
    """North Bay gas price vs. its own recent trend (see
    fuel_price_client.eco_mode_status) — built specifically to answer
    "should I bother driving in eco mode today," not just to display a
    number. Silent if the feed hasn't returned anything yet rather than
    an empty tile."""
    status = fuel_price_client.eco_mode_status()
    if not status:
        return
    if status["eco_recommended"]:
        badge_class, badge_text = "badge-bad", "Eco mode recommended"
    else:
        badge_class, badge_text = "badge-good", "Eco mode not needed"
    as_of = f"{status['as_of'].strftime('%b')} {status['as_of'].day}"
    # Day-granularity only, not a specific time — the survey publishes
    # "before end of business" on its update day, not at a fixed hour,
    # so anything more precise than "today" would be a made-up promise.
    days_until_update = (status["next_update"] - now.date()).days
    update_text = "updates today" if days_until_update <= 0 else f"next update in {days_until_update}d"
    st.markdown(
        f"""<div class="tile compact">
            <div class="tile-label compact">NORTH BAY GAS</div>
            <div class="tile-value">{status['price']:.1f}¢/L</div>
            <div class="tile-prev">vs {status['baseline']:.1f}¢ 12wk avg · as of {as_of} · {update_text}</div>
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


def render(now: datetime) -> None:
    st.markdown('<div class="page-title page-title-household">Household</div>', unsafe_allow_html=True)
    _render_fuel_price(now)
    st.markdown('<div style="height: 0.5rem;"></div>', unsafe_allow_html=True)
    _render_local_news()
