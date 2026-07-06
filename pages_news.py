"""News page: general market/finance headlines from the free RSS feeds.

Uses `news.is_market_relevant` — the same filter that drives the
breaking-news bar, so that bar is effectively this page's feed surfaced
the moment each headline first appears rather than something separately
and more strictly curated.
"""

import hashlib
import time

import streamlit as st

import news

WINDOW_SECONDS = 24 * 60 * 60
MAX_SHOWN = 10


def _relative_time(seconds_ago: float) -> str:
    minutes = int(seconds_ago / 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    return f"{hours}h ago"


def _meta_text(entry: dict, now_ts: float) -> str:
    relative = _relative_time(now_ts - entry["first_seen"])
    source = entry.get("source")
    return f"{source} · {relative}" if source else relative


def render():
    st.markdown('<div class="page-title page-title-news">Market News — Last 24 Hours</div>', unsafe_allow_html=True)

    seen_at = st.session_state.setdefault("news_feed_seen_at", {})
    now_ts = time.time()

    for item in news.fetch_headlines():
        if not news.is_market_relevant(item["headline"]):
            continue
        h = hashlib.sha1(item["headline"].encode()).hexdigest()
        if h not in seen_at:
            category = news.classify(item["headline"]) or "Market News"
            seen_at[h] = {
                "headline": item["headline"],
                "first_seen": now_ts,
                "category": category,
                "source": item.get("source", ""),
            }

    # Age out old entries, AND re-check every remaining one against
    # today's is_market_relevant() — this kiosk keeps the same browser
    # session open for hours/days, so a headline that qualified under a
    # since-tightened filter would otherwise just sit here, correctly
    # filtered out for every *new* headline but never swept from what's
    # already stored, until its 24h window happened to expire on its own.
    for h in [
        h for h, entry in seen_at.items()
        if now_ts - entry["first_seen"] > WINDOW_SECONDS or not news.is_market_relevant(entry["headline"])
    ]:
        del seen_at[h]

    entries = sorted(seen_at.values(), key=lambda e: e["first_seen"], reverse=True)[:MAX_SHOWN]

    if not entries:
        st.markdown(
            '<div class="tile"><div class="tile-prev">No market headlines in the last 24 hours.</div></div>',
            unsafe_allow_html=True,
        )
        return

    rows = "".join(
        f"""<div class="news-feed-row {news.category_class(e.get('category', 'Market News'))}">
            <div class="news-feed-headline">{e['headline']}</div>
            <div class="news-feed-meta">{_meta_text(e, now_ts)}</div>
        </div>"""
        for e in entries
    )
    st.markdown(f'<div class="news-feed-list">{rows}</div>', unsafe_allow_html=True)
