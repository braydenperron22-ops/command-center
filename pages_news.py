"""News page: general market/finance headlines from the free RSS feeds.

Uses `news.decide` — the same AI-first verdict that drives the
breaking-news bar, so that bar is effectively this page's feed surfaced
the moment each headline first appears rather than something separately
and more strictly curated.
"""

import hashlib
import html
import time

import streamlit as st

import headline_tickers
import news
import news_market_reaction

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
        h = hashlib.sha1(item["headline"].encode()).hexdigest()
        if h in seen_at:
            continue
        decision = news.decide(item["headline"], item.get("description", ""))
        if decision is None:
            continue
        # Captured once, at first sight, and locked in from then on:
        # the instrument (index/futures) and its price at the moment
        # this headline broke, so the reaction badge always measures
        # "since this happened" against a single consistent price
        # series — not a moving target, and not a comparison across
        # two different instruments if market status changes while
        # the headline is still showing. None for anything outside
        # Fed/BoC or Macro Shock, where "the market's" reaction
        # isn't a meaningful causal claim.
        reaction_symbol = (
            news_market_reaction.reaction_symbol()
            if decision["category"] in news_market_reaction.REACTION_CATEGORIES
            else None
        )
        seen_at[h] = {
            "headline": decision["headline"],
            "first_seen": now_ts,
            "category": decision["category"],
            # Captured once, at first sight — "was breaking," not
            # re-evaluated fresh on every render (see decide()'s own
            # docstring: an AI verdict is trusted as final once made).
            "important": decision["important"],
            "source": item.get("source", ""),
            "reaction_symbol": reaction_symbol,
            "baseline_spx": news_market_reaction.price_for(reaction_symbol) if reaction_symbol else None,
        }

    # Age out entries past their 24h window. Used to also re-check every
    # remaining one against a live filter call in case a keyword-list
    # edit mid-session changed its answer — decide()'s AI verdict is
    # trusted as final once made (see its own docstring), so there's
    # nothing left to re-validate here, and re-asking would mean a real
    # AI call for every stored entry, every render.
    for h in [h for h, entry in seen_at.items() if now_ts - entry["first_seen"] > WINDOW_SECONDS]:
        del seen_at[h]

    entries = sorted(seen_at.values(), key=lambda e: e["first_seen"], reverse=True)[:MAX_SHOWN]

    if not entries:
        st.markdown(
            '<div class="tile"><div class="tile-prev">No market headlines in the last 24 hours.</div></div>',
            unsafe_allow_html=True,
        )
        return

    def _row_class(e: dict) -> str:
        if e.get("important"):
            return "news-feed-row-breaking"
        return news.category_class(e.get("category", "Market News"))

    rows = "".join(
        f"""<div class="news-feed-row {_row_class(e)}">
            <div class="news-feed-headline">{html.escape(e['headline'])}{headline_tickers.ticker_badge_html(e['headline'])}"""
        f"""{news_market_reaction.reaction_badge_html(e.get('reaction_symbol'), e.get('baseline_spx'))}</div>
            <div class="news-feed-meta">{_meta_text(e, now_ts)}</div>
        </div>"""
        for e in entries
    )
    st.markdown(f'<div class="news-feed-list">{rows}</div>', unsafe_allow_html=True)
