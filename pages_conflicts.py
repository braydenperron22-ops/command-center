"""Conflicts page: fully dynamic, no fixed list.

Used to identify conflicts by scanning Google News headlines for a
tracked country name alongside a conflict-indicator keyword — brittle
(a headline like "South Sudan..." could get misparsed as "Sudan",
"stress test" and other unrelated matches slipped through elsewhere in
the app before similar keyword lists got tightened over many rounds)
and required maintaining CONFLICT_COUNTRIES/CONFLICT_TERMS by hand.
Session request: "make conflicts feed directly from gemini instead of
looking for headlines with specific names... remove the RSS keyword
searching for different countries... it should build the entire
overview on itself."

_ai_overview (below) is now the only detection/summarization step: it's
handed the whole real headline pool from conflict_news.fetch_
conflict_headlines (still a real, freshly-fetched RSS pool — that part
is unchanged) and asked to identify the most significant distinct
ongoing conflicts represented in it, classify each one's current
trajectory (active war / escalating / stalemate / de-escalating /
ceasefire / peace talks), and write a real overview covering what's
happening, where it's headed, and its effect on the wider world.

Important honesty note baked into the prompt itself: plain chat-
completions calls (what groq_client.generate uses, whichever provider
it ends up serving from) do NOT have live web search — that's a
different capability no provider's plain chat endpoint offers as
called here, so this is NOT the model browsing the internet in real
time. It's genuinely current in the parts that matter most — which
headlines exist, what they say — because those are real headlines
fetched this session, in the prompt. Where the prompt asks for
background/context beyond the last 7 days (is this conflict long-
running, who the parties historically are), that part does lean on the
model's own training knowledge, which is explicitly called out as
potentially outdated in the prompt so the model weighs the fresh
headlines over stale recall for anything about the CURRENT state. This
was reconfirmed directly rather than assumed — session request: "I
want our Llama model to do a research on active conflicts" was
declined in that literal form (no live search exists to actually do
that) in favor of what this already does: real headlines for current
state, the model's own knowledge only for background.

Routed through groq_client with an explicit non-default `model` —
session history: first switched to gemini_client entirely ("crack the
whip... it's not giving me a whole lot"), then a live side-by-side
test against a specific alternative found something sharper still —
session request: "Meta is losing the AI race... is there a better...
option through Grok" — openai/gpt-oss-120b, OpenAI's own open-weight
model hosted on Groq, confirmed live to write noticeably more decisive
overviews than both Llama and Gemini on this exact prompt. It's a
REASONING model (see groq_client.GPT_OSS_MODEL's own comment for the
practical consequences of that — it needed real, deliberately-computed
token headroom to actually finish instead of silently returning
nothing). Routed through its own dedicated Groq account (see
groq_client's _MODEL_ACCOUNT — a separate account from the one Llama
uses, not a shared pair to fall back between), falling to Gemini's own
model if that account fails — a bad day on it degrades to Gemini
instead of nothing, since that's still meaningfully better than the
empty state.

No keyword fallback if the AI call fails (unlike news.py, which keeps
its old keyword pipeline as a safety net) — that fallback is exactly
what an earlier session asked to remove, not preserve as a shadow
system. The page just doesn't render new content on a failure and
effectively shows last-run's data via groq_client.generate's own
20-minute cache, or the empty state if there's truly nothing cached
yet."""

import html
import json

import streamlit as st

import conflict_news
import groq_client
from config import CONFLICT_WINDOW_DAYS, MAX_CONFLICTS_SHOWN
from flags import flag_for

# (label, badge tone) — trajectory is the main signal now (this used to
# be a separate coverage-count badge plus a rising/falling/steady arrow
# derived from headline timestamp density; the AI's own status verdict
# already captures that same idea more directly, so there's no separate
# trend calculation to maintain anymore).
_STATUS_DISPLAY = {
    "ACTIVE_WAR": ("Active War", "bad"),
    "ESCALATING": ("Escalating ↑", "bad"),
    "STALEMATE": ("Stalemate →", "neutral"),
    "DEESCALATING": ("De-escalating ↓", "good"),
    "CEASEFIRE": ("Ceasefire", "good"),
    "PEACE_TALKS": ("Peace Talks", "good"),
}
_SEVERITY_FILL_PCT = {"HIGH": 100, "MEDIUM": 65, "LOW": 35}

# Session request: "make the prompt lighter on tokens" — was 150.
# Real volume checked live: 94 headlines for a typical 7-day window, so
# 100 still comfortably covers a normal week and only trims the
# worst-case (a genuinely heavy news week) rather than typical days —
# directly shrinks input tokens, which is also what determines how much
# of GPT_OSS_TPM_LIMIT is left over for the model's own reasoning +
# answer (see max_output_tokens' own comment below).
HEADLINES_FED_TO_AI = 100
# openai/gpt-oss-120b — see this module's own docstring for why this
# specific model. It's a REASONING model: it spends real completion
# tokens on hidden chain-of-thought before ever writing the visible
# answer, and those reasoning tokens count against the SAME max_tokens
# ceiling as the answer itself — confirmed live: at the old flat 2,200
# cap it silently returned nothing (reasoning ate the whole budget
# before reaching real output), and this model's own per-minute budget
# (8,000 tokens — tighter than the 12,000 the other Groq model this
# app uses gets) is tight enough that the ~2,600-token prompt plus a
# fixed output cap can blow the limit outright depending on how many
# headlines happen to be pending that day (real 413 hit during
# testing: "Requested 8555... Limit 8000"). GPT_OSS_MAX_OUTPUT_TOKENS
# below is computed per call from the ACTUAL prompt size instead of a
# fixed number, so it scales down automatically on a heavy headline
# day and up on a light one, always leaving real room for both
# reasoning and the answer under the real ceiling.
# The model string itself now lives in groq_client.py (GPT_OSS_MODEL)
# — it needs it regardless to route a gpt-oss call to its own
# dedicated account (see that module's docstring: "primary" only runs
# Llama, a separate account is dedicated to this one). Referenced from
# there instead of kept as a second copy here.
GPT_OSS_TPM_LIMIT = 8_000
GPT_OSS_SAFETY_MARGIN = 700  # slack for the input-token estimate being a rough len(prompt)//4, not an exact tokenization
GPT_OSS_MIN_OUTPUT_TOKENS = 1_500  # floor — below this there isn't real room to both reason and write a useful answer
# Session request history: "for conflicts I don't need second by
# second updates... update that hourly" -> widened to 3h for cost
# reasons -> "honestly, have it run once a day, but make it intentful."
# Conflict trajectories don't shift minute to minute the way commute/
# market numbers do, so once daily is still a real, current read —
# just one considered pass instead of several shallow ones.
REFRESH_SECONDS = 24 * 60 * 60


def _ai_overview(headlines: list[dict]) -> list[dict] | None:
    """Up to MAX_CONFLICTS_SHOWN entries, each {"countries": [{"code",
    "name"}, ...], "status", "overview", "severity", "headlines": [...]}
    (headlines re-attached below, matched back from the AI's own
    referenced numbers — kept on the returned entry even though render()
    no longer displays them, see its own comment; still real, still fed
    to the AI in full either way, this only changes what's shown on
    screen) — or None on any failure (missing key, rate limit, network,
    or a response that didn't come back as valid JSON) with nothing
    usable already cached. Real calls throttled to once per
    REFRESH_SECONDS regardless of how often this is called — see
    groq_client.generate_periodic. See this module's own docstring
    for the full design rationale, including why this is routed to
    gpt-oss-120b specifically."""
    texts = [h["headline"] for h in headlines[:HEADLINES_FED_TO_AI]]
    if not texts:
        return None
    headline_block = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    # Session request: "make the prompt lighter on tokens" — same
    # instructions, same output contract, just said in fewer words.
    # Cut the scaffolding (everything except the headline block itself)
    # from ~2,170 chars to ~1,270, roughly 225 fewer estimated input
    # tokens — real headroom back for the model's own reasoning + answer
    # under GPT_OSS_TPM_LIMIT (see max_output_tokens' own comment
    # below), on top of the HEADLINES_FED_TO_AI cut above.
    prompt = (
        "You are a sharp, decisive geopolitical analyst building a tile-based overview for a "
        f"home dashboard. Below are {len(texts)} real headlines from the last "
        f"{CONFLICT_WINDOW_DAYS} days (numbered; many are unrelated to conflicts — ignore "
        "those).\n\n"
        "Identify the most significant distinct ongoing armed conflicts/wars/serious military "
        f"or civil crises represented, up to {MAX_CONFLICTS_SHOWN}, ranked by how active each "
        "currently is. Return fewer if fewer genuinely qualify — don't pad with minor/"
        "borderline cases.\n\n"
        "For each, give:\n"
        "- countries: real ISO 3166-1 alpha-2 codes + English names for each side (a country, "
        "not an organization — Gaza is 'ps'/'Gaza/Palestine', not 'Hamas')\n"
        "- status: ACTIVE_WAR | ESCALATING | STALEMATE | DEESCALATING | CEASEFIRE | PEACE_TALKS\n"
        "- overview: 2-3 decisive, specific sentences, 40 words maximum — what's happening now, "
        "its trajectory, and (only if there's real room left in that cap) peace talks or effects "
        "on markets/refugees/regional stability/prices. No vague hedging that could describe any "
        "conflict. Prioritize what's happening now and its trajectory over the rest if the cap "
        "forces a choice — never pad to fill it, never run past it.\n"
        "- severity: HIGH | MEDIUM | LOW\n"
        "- headline_numbers: which numbers above relate to this conflict\n\n"
        "Use your own knowledge for historical background, but trust the headlines over memory "
        "for current status/trajectory — your training may be outdated.\n\n"
        f"{headline_block}\n\n"
        "Respond with ONLY a JSON array, no markdown fences, no other text, in exactly this "
        "shape:\n"
        '[{"countries": [{"code": "ua", "name": "Ukraine"}, {"code": "ru", "name": "Russia"}], '
        '"status": "ACTIVE_WAR", "overview": "...", "severity": "HIGH", "headline_numbers": [3, 7]}]'
    )
    # gpt-oss-120b is a reasoning model — hidden chain-of-thought tokens
    # count against the same max_tokens budget as the visible answer, and
    # this model's own per-minute limit (8,000) is tighter than the
    # primary Llama model's (12,000). A fixed cap silently starves the
    # visible output (confirmed live: 2,200 came back empty) or blows the
    # per-minute ceiling outright (confirmed live: a 6,000 cap 413'd once
    # input tokens were added in). Sizing this from the real prompt each
    # call, instead of guessing a constant, is what keeps this correct as
    # the headline pool (and therefore prompt length) drifts day to day.
    estimated_input_tokens = len(prompt) // 4
    max_output_tokens = max(
        GPT_OSS_MIN_OUTPUT_TOKENS, GPT_OSS_TPM_LIMIT - GPT_OSS_SAFETY_MARGIN - estimated_input_tokens
    )
    def _parse(raw_text: str) -> list[dict] | None:
        """Turns one raw AI response into real entries, or None if it's
        not usable — shared by the validate= callback below (which only
        cares whether this succeeds) and the real parse after a
        generate_periodic call returns, so there's exactly one place
        that knows what a valid response looks like."""
        raw = raw_text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            raw = raw.rsplit("```", 1)[0]
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return None
        if not isinstance(parsed, list):
            return None

        entries = []
        for item in parsed:
            try:
                countries = [
                    {"code": str(c["code"]).lower(), "name": str(c["name"])}
                    for c in item["countries"]
                    if c.get("code") and c.get("name")
                ]
                status = str(item["status"]).upper()
                overview = str(item["overview"]).strip()
                severity = str(item.get("severity", "MEDIUM")).upper()
                numbers = item.get("headline_numbers") or []
            except (KeyError, TypeError):
                continue
            if not countries or status not in _STATUS_DISPLAY or not overview:
                continue
            matched = [headlines[n - 1] for n in numbers if isinstance(n, int) and 1 <= n <= len(texts)]
            entries.append(
                {
                    "countries": countries,
                    "status": status,
                    "overview": overview,
                    "severity": severity if severity in _SEVERITY_FILL_PCT else "MEDIUM",
                    "headlines": matched,
                }
            )
        return entries or None

    result = groq_client.generate_periodic(
        "conflicts_overview",
        REFRESH_SECONDS,
        prompt,
        temperature=0.2,
        max_output_tokens=max_output_tokens,
        model=groq_client.GPT_OSS_MODEL,
        # Explicit, not just relying on Groq's own default (also
        # "medium") — this was a real, considered choice, not an
        # oversight. Session request: "make sure GPT doesn't run out of
        # credits halfway through" led to trying "low" here first — it
        # never truncates, but a live side-by-side on the same headline
        # pool showed it isn't just terser, it under-scans: "low" found
        # 1 conflict where "medium" correctly separated out 3 distinct
        # ones (US-Iran, Yemen-Saudi, Ukraine-Russia) from the exact
        # same headlines. Asked directly which mattered more given that
        # tradeoff — kept "medium" for the real analytical coverage,
        # since the `validate` retry-on-invalid fix below already turns
        # an occasional truncation into a same-day retry instead of a
        # broken page for the rest of the 24h window.
        reasoning_effort="medium",
        # Session report: "generated eleven hours ago, yet no conflict
        # overview available right now" — see generate_periodic's own
        # comment on `validate`. A malformed/truncated response (a real
        # risk for this reasoning model under a tight token budget, see
        # this module's own docstring) used to sit in the cache reading
        # as "fresh" for the entire 24h window with nothing to show for
        # it; this makes "fresh" also mean "actually parses."
        validate=lambda text: _parse(text) is not None,
    )
    if result is None:
        return None
    return _parse(result)


# Live bug: render() used to call _ai_overview (a real Groq call on
# any REFRESH_SECONDS cache miss — confirmed live at 13.27s cold for a
# real gpt-oss-120b generation) directly, meaning whichever rerun
# happened to land on this page right as the 24h cache went stale paid
# that cost synchronously, blocking past app.py's 5s st_autorefresh
# window. That corrupts the Streamlit rerun and blends pages together
# on screen — the exact same bug class fixed this session for
# golf_client/financial_plumbing_client/portfolio_client/
# league_transactions_client/prediction_markets_client/market_internals/
# email_client (see each module's own comment) — confirmed as this
# page's own real photographed instance: duplicated conflict tiles plus
# a floating weather-statement banner mid-page. warm_cache below is
# wired into app.py's toast-check loop instead, unconditionally every
# rerun; render() now reads only cached_overview, which never calls the
# AI itself. groq_client.generate_periodic's own 24h internal cache
# means warm_cache is a fast already-cached read on every rerun except
# the one that happens to cross the daily refresh boundary.
_last_good_entries: list[dict] | None = None


def warm_cache() -> None:
    global _last_good_entries
    headline_pool = conflict_news.fetch_conflict_headlines()
    try:
        entries = _ai_overview(headline_pool)
    except Exception:
        entries = None
    if entries:
        _last_good_entries = entries


def cached_overview() -> list[dict] | None:
    return _last_good_entries


def render():
    """Session request: "hide the rss feed but let the ai see them for
    the conflict recap" — the raw sourced headlines used to be listed
    under each tile's AI-written overview (see git history's
    conflict-headlines markup); each tile is now just the AI's own
    synthesis, no visible headline list. The underlying fetch and the
    AI's own use of the full pool are both completely unchanged —
    headline_pool still goes into _ai_overview in full via warm_cache
    above, this only changes what render() puts on screen afterward."""
    st.markdown('<div class="page-title page-title-conflicts">Ongoing Conflicts — AI Overview</div>', unsafe_allow_html=True)

    entries = cached_overview()

    if not entries:
        st.markdown(
            '<div class="tile"><div class="tile-prev">No conflict overview available right now.</div></div>',
            unsafe_allow_html=True,
        )
        return

    cols = st.columns(len(entries))
    for i, entry in enumerate(entries):
        label_text, tone = _STATUS_DISPLAY[entry["status"]]
        badge_class = f"badge-{tone}"
        fill_class = f"severity-fill-{tone}"
        fill_pct = _SEVERITY_FILL_PCT[entry["severity"]]
        country_label = " – ".join(c["name"] for c in entry["countries"])

        flags_html = "".join(f'<span class="conflict-flag">{flag_for(c["code"])}</span>' for c in entry["countries"])

        with cols[i]:
            st.markdown(
                f"""<div class="tile tile-accent-{tone}">
                    <div class="conflict-flags">{flags_html}</div>
                    <div class="tile-label">{html.escape(country_label)}</div>
                    <div class="badge {badge_class}">{label_text}</div>
                    <div class="severity-track">
                        <div class="severity-fill {fill_class}" style="left: 0; width: {fill_pct}%;"></div>
                    </div>
                    <div class="conflict-ai-summary">{html.escape(entry["overview"])}</div>
                </div>""",
                unsafe_allow_html=True,
            )
