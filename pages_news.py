"""News page: general market/finance headlines from the free RSS feeds.

Deliberately looser than the breaking-news alert bar — that requires a
topic AND a surprise/magnitude qualifier together (right for something
worth interrupting the screen for), but this just needs one real finance
signal, since these feeds mix genuine market content with lifestyle pieces.
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


def render():
    st.markdown('<div class="page-title">Market News — Last 24 Hours</div>', unsafe_allow_html=True)

    seen_at = st.session_state.setdefault("news_feed_seen_at", {})
    now_ts = time.time()

    for item in news.fetch_headlines():
        if not news.is_market_relevant(item["headline"]):
            continue
        h = hashlib.sha1(item["headline"].encode()).hexdigest()
        if h not in seen_at:
            seen_at[h] = {"headline": item["headline"], "first_seen": now_ts}

    for h in [h for h, entry in seen_at.items() if now_ts - entry["first_seen"] > WINDOW_SECONDS]:
        del seen_at[h]

    entries = sorted(seen_at.values(), key=lambda e: e["first_seen"], reverse=True)[:MAX_SHOWN]

    if not entries:
        st.markdown(
            '<div class="tile"><div class="tile-prev">No market headlines in the last 24 hours.</div></div>',
            unsafe_allow_html=True,
        )
        return

    rows = "".join(
        f"""<div class="news-feed-row">
            <div class="news-feed-headline">{e['headline']}</div>
            <div class="news-feed-meta">{_relative_time(now_ts - e['first_seen'])}</div>
        </div>"""
        for e in entries
    )
    st.markdown(f'<div class="news-feed-list">{rows}</div>', unsafe_allow_html=True)
