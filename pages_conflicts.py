"""Conflicts page: fully dynamic, no fixed list.

Scans Google News (via its `when:7d` date-scoped RSS search — no key, and
gives genuine week-old history directly rather than needing to accumulate
today's snapshots locally over several days) for any headline mentioning a
tracked country alongside a conflict-indicator term, groups by which
countries co-occur, and ranks by hit count — whatever's most documented
over the last week surfaces automatically, so this gives a genuine sense
of what's heating up vs. going quiet, rather than a static watchlist.

Each tile also gets a one-sentence AI summary of its own matched
headlines (_ai_summary, session request: "revamp... the conflict
pages" with a free AI) — the raw headlines are individually often
clickbait-y or narrowly framed, so a synthesized line reads better at
a glance than any single one of them. Purely additive: the raw
headlines still render underneath exactly as before, and the tile
looks and works the same as ever if the AI call fails (see
gemini_client.generate's own docstring on why that must always be an
option)."""

import html
import re
from datetime import datetime, timezone

import streamlit as st

import conflict_news
import gemini_client
from config import CONFLICT_COUNTRIES, CONFLICT_TERMS, FLAG_CODE_NAME, MAX_CONFLICTS_SHOWN
from flags import flag_for

RECENT_WINDOW_SECONDS = 24 * 60 * 60
_MIN_DATETIME = datetime.min.replace(tzinfo=timezone.utc)

# Coverage-trend arrow: same idea as air_quality_client's rising/falling
# trend, but doesn't need to accumulate samples over time — the 7-day
# headline pool already carries real `published` timestamps, so a
# recent-vs-older split is available on the very first render. The two
# windows are different widths (3 days vs. 4), so raw counts are
# compared as a per-day RATE, not a raw count — otherwise the wider
# "older" bucket would always out-count the narrower "recent" one for
# genuinely steady coverage and read as false "de-escalating".
TREND_RECENT_DAYS = 3
TREND_OLDER_DAYS = 4  # covers days 4-7 back
TREND_MIN_SAMPLE = 4  # fewer dated headlines than this isn't enough to call a direction from
TREND_RATIO_THRESHOLD = 1.4  # rate must differ by at least this factor to read as a real move, not noise


def _coverage_trend(headlines: list[dict], now_utc: datetime) -> str | None:
    """"rising" / "falling" / "steady", or None if there's too little
    dated coverage to judge a trend from."""
    recent = older = 0
    for h in headlines:
        published = h["published"]
        if published is None:
            continue
        age_days = (now_utc - published).total_seconds() / 86400
        if age_days < TREND_RECENT_DAYS:
            recent += 1
        elif age_days < TREND_RECENT_DAYS + TREND_OLDER_DAYS:
            older += 1

    if recent + older < TREND_MIN_SAMPLE:
        return None
    recent_rate = recent / TREND_RECENT_DAYS
    older_rate = older / TREND_OLDER_DAYS
    if older_rate == 0:
        return "rising"
    ratio = recent_rate / older_rate
    if ratio >= TREND_RATIO_THRESHOLD:
        return "rising"
    if ratio <= 1 / TREND_RATIO_THRESHOLD:
        return "falling"
    return "steady"


def _word_in(term: str, text: str) -> bool:
    """Whole-word match — plain substring matching let "war" match inside
    "warm", "Ukraine" phrasing aside terms like these need real boundaries.

    Tolerates an optional trailing "s": "militant" alone used to silently
    miss the far more common "militants attack" plural phrasing (strict
    word-boundary matching means \\bmilitant\\b does not match
    "militants" — there's no boundary between "t" and "s")."""
    return re.search(r"\b" + re.escape(term) + r"s?\b", text) is not None


def _country_codes_in(text: str) -> set[str]:
    """Every CONFLICT_COUNTRIES code mentioned in `text`, checking longer
    (multi-word) names first and skipping any shorter name whose match
    falls entirely inside a longer one's already-claimed span — a plain
    "does this name appear anywhere" check per name (the previous
    approach) let "sudan" match inside "south sudan" (a genuine whole
    word there too, separated by a space), silently merging two
    distinct conflicts into one inflated group any time a South-Sudan-
    only headline appeared. Longer-name-wins mirrors how a human reader
    would parse "south sudan" as naming one country, not two."""
    codes = set()
    claimed_spans = []
    for name in sorted(CONFLICT_COUNTRIES, key=len, reverse=True):
        pattern = r"\b" + re.escape(name) + r"s?\b"
        for m in re.finditer(pattern, text):
            if any(m.start() >= s and m.end() <= e for s, e in claimed_spans):
                continue
            codes.add(CONFLICT_COUNTRIES[name])
            claimed_spans.append((m.start(), m.end()))
    return codes


def _coverage_level(count: int) -> tuple[str, str]:
    """(label, badge tone) for how much coverage a conflict is getting."""
    if count == 1:
        return "Limited Coverage", "neutral"
    if count <= 3:
        return "Some Coverage", "neutral"
    return "Highly Covered", "bad"


AI_SUMMARY_HEADLINES_SHOWN = 5


def _ai_summary(headlines: list[dict]) -> str | None:
    """One neutral sentence summarizing what this conflict's own
    matched headlines (newest AI_SUMMARY_HEADLINES_SHOWN, already
    sorted newest-first by _detect_conflicts) are actually saying,
    rather than making the tile lean on whichever single raw headline
    happened to match. None on any failure — see gemini_client.
    generate's own docstring; render() falls back to just the raw
    headline list underneath, exactly as this page worked before."""
    texts = [h["headline"] for h in headlines[:AI_SUMMARY_HEADLINES_SHOWN]]
    prompt = (
        "You summarize ongoing conflict news for a home dashboard tile. Given these recent "
        "headlines, all about the same conflict, write ONE neutral, factual sentence (25 words "
        "or fewer) capturing what's currently happening. No speculation, no opinion, no "
        "headline-style clickbait phrasing — a plain, careful summary. Start with a capital "
        "letter and end with a period. Headlines:\n" + "\n".join(f"- {t}" for t in texts)
    )
    return gemini_client.generate(prompt)


@st.cache_data(ttl=60 * 60, show_spinner=False)
def _detect_conflicts(headlines: list[dict]) -> list[dict]:
    """Cached at the same TTL as conflict_news.fetch_conflict_headlines()
    (its only real input) — without this, the whole headline pool got
    rescanned against every conflict term and every tracked country name
    (thousands of regex checks) every single second this page is showing,
    even though the pool itself only changes once an hour."""
    groups = {}  # frozenset(codes) -> [{"headline": ..., "published": ...}]
    for item in headlines:
        h = item["headline"].lower()
        if not any(_word_in(term, h) for term in CONFLICT_TERMS):
            continue
        codes = _country_codes_in(h)
        if not codes:
            continue
        key = frozenset(codes)
        groups.setdefault(key, []).append({
            "headline": item["headline"],
            "published": item.get("published"),
        })

    entries = []
    for codes, matched_headlines in groups.items():
        # Newest first — Google's own feed order isn't reliably
        # chronological (confirmed by inspection: dates come back mixed
        # within a single response), so this is a real sort, not a
        # no-op. Anything with an unparseable date sorts to the very
        # end rather than crashing the comparison.
        matched_headlines.sort(key=lambda h: h["published"] or _MIN_DATETIME, reverse=True)
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

    now_utc = datetime.now(timezone.utc)

    cols = st.columns(len(entries))
    for i, entry in enumerate(entries):
        count = len(entry["headlines"])
        label, tone = _coverage_level(count)
        trend = _coverage_trend(entry["headlines"], now_utc)
        trend_arrow = {"rising": " ↑", "falling": " ↓", "steady": " →"}.get(trend, "")
        label = f"{label}{trend_arrow}"
        badge_class = f"badge-{tone}"
        fill_class = f"severity-fill-{tone}"
        fill_pct = min(count / 5, 1.0) * 100

        flags_html = "".join(f'<span class="conflict-flag">{flag_for(code)}</span>' for code in entry["codes"])
        headlines_html = "".join(
            f'<div class="conflict-headline{" conflict-headline-recent" if h["published"] and (now_utc - h["published"]).total_seconds() < RECENT_WINDOW_SECONDS else ""}">{html.escape(h["headline"])}</div>'
            for h in entry["headlines"][:3]
        )
        try:
            summary = _ai_summary(entry["headlines"])
        except Exception:
            summary = None
        summary_html = f'<div class="conflict-ai-summary">{html.escape(summary)}</div>' if summary else ""

        with cols[i]:
            st.markdown(
                f"""<div class="tile tile-accent-{tone}">
                    <div class="conflict-flags">{flags_html}</div>
                    <div class="tile-label">{entry['label']}</div>
                    <div class="badge {badge_class}">{label}</div>
                    <div class="severity-track">
                        <div class="severity-fill {fill_class}" style="left: 0; width: {fill_pct:.0f}%;"></div>
                    </div>
                    {summary_html}
                    <div class="conflict-headlines">{headlines_html}</div>
                </div>""",
                unsafe_allow_html=True,
            )
