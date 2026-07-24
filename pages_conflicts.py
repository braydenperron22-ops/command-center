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
REASONING model (see GPT_OSS_MODEL's own comment for the practical
consequences of that — it needed real, deliberately-computed token
headroom to actually finish instead of silently returning nothing).
Still goes through groq_client's full primary -> failsafe -> gemini
fallback chain (see groq_client.generate's own docstring) — a bad day
on both Groq accounts degrades to Gemini's own model instead, not to
nothing, since that's still meaningfully better than the empty state.

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

HEADLINES_FED_TO_AI = 150  # comfortably covers a week's real pool without an unbounded prompt
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
GPT_OSS_MODEL = "openai/gpt-oss-120b"
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
    referenced numbers) — or None on any failure (missing key, rate
    limit, network, or a response that didn't come back as valid JSON)
    with nothing usable already cached. Real calls throttled to once
    per REFRESH_SECONDS regardless of how often this is called — see
    groq_client.generate_periodic. See this module's own docstring
    for the full design rationale, including why this is routed to
    gpt-oss-120b specifically."""
    texts = [h["headline"] for h in headlines[:HEADLINES_FED_TO_AI]]
    if not texts:
        return None
    headline_block = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    prompt = (
        "You are a sharp, decisive geopolitical analyst building one tile-based overview for a "
        f"home dashboard. Below are {len(texts)} real news headlines from the last "
        f"{CONFLICT_WINDOW_DAYS} days (numbered; many will be unrelated to conflicts at all — "
        "ignore those).\n\n"
        "From these, identify the most significant distinct ongoing armed conflicts, wars, or "
        f"serious military/civil crises currently active in the world — up to {MAX_CONFLICTS_SHOWN} "
        "of them, ranked by how significant/active each currently is. If fewer than "
        f"{MAX_CONFLICTS_SHOWN} genuine conflicts are actually represented in the headlines, "
        "return fewer — don't pad the list with minor or borderline cases just to fill it.\n\n"
        "For each conflict, determine:\n"
        "- countries: the real ISO 3166-1 alpha-2 lowercase country codes and English names for "
        "each side/party involved (a country, not an organization — e.g. for Gaza use 'ps'/"
        "'Gaza/Palestine', not 'Hamas')\n"
        "- status: exactly one of ACTIVE_WAR, ESCALATING, STALEMATE, DEESCALATING, CEASEFIRE, "
        "PEACE_TALKS\n"
        "- overview: a real 2-4 sentence overview covering what's actually happening right now, "
        "whether it's escalating, holding steady, or winding down, whether there are peace "
        "negotiations underway, and what effect it's having on the wider world (markets, "
        "refugees, regional stability, energy/food prices, etc. — only mention a global effect "
        "if there genuinely is one, don't force it). Write with real analytical judgment — a "
        "clear, specific, intentful read on where this is actually headed, not a vague, hedgy "
        "summary that could describe any conflict\n"
        "- severity: HIGH, MEDIUM, or LOW\n"
        "- headline_numbers: which of the numbered headlines above (list the numbers) actually "
        "relate to this specific conflict\n\n"
        "You may use your own general knowledge for background/historical context on a conflict "
        "you recognize, but your assessment of its CURRENT status and trajectory must be "
        "grounded in the headlines above, not assumed from memory — your training knowledge may "
        "be outdated about how a given conflict has evolved since then; the headlines above are "
        "genuinely current and take priority whenever they conflict with what you'd otherwise "
        "assume.\n\n"
        f"{headline_block}\n\n"
        "Respond with ONLY a JSON array, no markdown code fences, no other text, in exactly this "
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
    result = groq_client.generate_periodic(
        "conflicts_overview", REFRESH_SECONDS, prompt, temperature=0.2, max_output_tokens=max_output_tokens, model=GPT_OSS_MODEL
    )
    if result is None:
        return None

    raw = result.strip()
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


def render():
    st.markdown('<div class="page-title page-title-conflicts">Ongoing Conflicts — AI Overview</div>', unsafe_allow_html=True)

    headline_pool = conflict_news.fetch_conflict_headlines()
    try:
        entries = _ai_overview(headline_pool)
    except Exception:
        entries = None

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
        headlines_html = "".join(
            f'<div class="conflict-headline">{html.escape(h["headline"])}</div>' for h in entry["headlines"][:3]
        )

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
                    <div class="conflict-headlines">{headlines_html}</div>
                </div>""",
                unsafe_allow_html=True,
            )
