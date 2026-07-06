"""Conflicts page: fully dynamic, no fixed list.

Scans Google News (via its `when:7d` date-scoped RSS search — no key, and
gives genuine week-old history directly rather than needing to accumulate
today's snapshots locally over several days) for any headline mentioning a
tracked country alongside a conflict-indicator term, groups by which
countries co-occur, and ranks by hit count — whatever's most documented
over the last week surfaces automatically, so this gives a genuine sense
of what's heating up vs. going quiet, rather than a static watchlist.
"""

import re

import streamlit as st

import conflict_news
from config import CONFLICT_COUNTRIES, CONFLICT_TERMS, FLAG_CODE_NAME, MAX_CONFLICTS_SHOWN
from flags import flag_for


def _word_in(term: str, text: str) -> bool:
    """Whole-word match — plain substring matching let "war" match inside
    "warm", "Ukraine" phrasing aside terms like these need real boundaries.

    Tolerates an optional trailing "s": "militant" alone used to silently
    miss the far more common "militants attack" plural phrasing (strict
    word-boundary matching means \\bmilitant\\b does not match
    "militants" — there's no boundary between "t" and "s")."""
    return re.search(r"\b" + re.escape(term) + r"s?\b", text) is not None


def _coverage_level(count: int) -> tuple[str, str]:
    """(label, badge tone) for how much coverage a conflict is getting."""
    if count == 1:
        return "Limited Coverage", "neutral"
    if count <= 3:
        return "Some Coverage", "neutral"
    return "Highly Covered", "bad"


@st.cache_data(ttl=60 * 60, show_spinner=False)
def _detect_conflicts(headlines: list[dict]) -> list[dict]:
    """Cached at the same TTL as conflict_news.fetch_conflict_headlines()
    (its only real input) — without this, the whole headline pool got
    rescanned against every conflict term and every tracked country name
    (thousands of regex checks) every single second this page is showing,
    even though the pool itself only changes once an hour."""
    groups = {}  # frozenset(codes) -> [headlines]
    for item in headlines:
        h = item["headline"].lower()
        if not any(_word_in(term, h) for term in CONFLICT_TERMS):
            continue
        codes = {code for name, code in CONFLICT_COUNTRIES.items() if _word_in(name, h)}
        if not codes:
            continue
        key = frozenset(codes)
        groups.setdefault(key, []).append(item["headline"])

    entries = []
    for codes, matched_headlines in groups.items():
        names = [FLAG_CODE_NAME.get(c, c.upper()) for c in sorted(codes)]
        entries.append({
            "codes": sorted(codes),
            "label": " – ".join(names),
            "headlines": matched_headlines,
        })

    entries.sort(key=lambda e: len(e["headlines"]), reverse=True)
    return entries[:MAX_CONFLICTS_SHOWN]


def render():
    st.markdown('<div class="page-title page-title-conflicts">Ongoing Conflicts — Last 7 Days</div>', unsafe_allow_html=True)

    headline_pool = conflict_news.fetch_conflict_headlines()
    entries = _detect_conflicts(headline_pool)

    if not entries:
        st.markdown(
            '<div class="tile"><div class="tile-prev">No conflict-related coverage detected right now.</div></div>',
            unsafe_allow_html=True,
        )
        return

    cols = st.columns(len(entries))
    for i, entry in enumerate(entries):
        count = len(entry["headlines"])
        label, tone = _coverage_level(count)
        badge_class = f"badge-{tone}"
        fill_class = f"severity-fill-{tone}"
        fill_pct = min(count / 5, 1.0) * 100

        flags_html = "".join(f'<span class="conflict-flag">{flag_for(code)}</span>' for code in entry["codes"])
        headlines_html = "".join(f'<div class="conflict-headline">{h}</div>' for h in entry["headlines"][:3])

        with cols[i]:
            st.markdown(
                f"""<div class="tile tile-accent-{tone}">
                    <div class="conflict-flags">{flags_html}</div>
                    <div class="tile-label">{entry['label']}</div>
                    <div class="badge {badge_class}">{label}</div>
                    <div class="severity-track">
                        <div class="severity-fill {fill_class}" style="left: 0; width: {fill_pct:.0f}%;"></div>
                    </div>
                    <div class="conflict-headlines">{headlines_html}</div>
                </div>""",
                unsafe_allow_html=True,
            )
