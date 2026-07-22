"""Google's Gemini API — free tier, used to turn structured facts or raw
headlines into natural short text (see morning_briefing.py's
_ai_sentence and pages_conflicts.py's _ai_summary). Session request:
"free... and somewhat competent" AI to revamp the morning brief and
conflicts pages.

Uses the "gemini-flash-lite-latest" alias rather than a pinned model
version — Google moves the free tier's default model forward over time
and retires older ones (confirmed live against the actual key: gemini-
1.5-flash 404s, gemini-2.0-flash comes back with a hard 0-quota free-
tier error, gemini-2.5-flash is "no longer available to new users").
The floating alias always resolves to whichever lightweight model is
currently supported, so this doesn't need manual bumping every time
Google reshuffles its lineup — same reasoning as sports_client's own
headshot/logo CDN URLs needing no upkeep.

Every caller MUST treat a None return as "the AI's unavailable right
now" and fall back to its own non-AI behavior. This is a free-tier
third-party call on a 24/7 kiosk — rate limits, network hiccups, and
model deprecations are all things that will happen sooner or later, and
none of them should ever be able to take a page down.
"""

import requests
import streamlit as st

GEMINI_MODEL = "gemini-flash-lite-latest"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
REQUEST_TIMEOUT_SECONDS = 20  # generous enough for a long structured response (see max_output_tokens); short calls finish well under this anyway
# Free tier is rate-limited (requests/minute and requests/day both), and
# nothing this feeds on (weather, commute, conflict headlines) actually
# changes fast enough to need calling any more often than this — see
# generate()'s own docstring for how this TTL turns into "call once per
# distinct prompt, not once per 5s rerun".
GENERATE_CACHE_TTL_SECONDS = 20 * 60


@st.cache_data(ttl=GENERATE_CACHE_TTL_SECONDS, show_spinner=False)
def _generate_or_raise(prompt: str, temperature: float, max_output_tokens: int) -> str:
    """Real request, real exception on any failure — st.cache_data only
    ever caches a genuine successful return, never a raised exception,
    so a transient failure (rate limit, network blip) is never what
    gets cached here. See generate() below for why that split matters."""
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("no GEMINI_API_KEY configured")
    resp = requests.post(
        GEMINI_URL,
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_output_tokens},
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    candidates = resp.json().get("candidates") or []
    if not candidates:
        raise RuntimeError("empty candidates in Gemini response")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError("empty text in Gemini response")
    return text


def generate(prompt: str, temperature: float = 0.7, max_output_tokens: int = 200) -> str | None:
    """One short piece of AI-written text for `prompt`, or None if the
    key's missing, the request fails, or the free tier's rate-limited
    right now — never raises. Cached by the exact prompt string AND
    temperature/max_output_tokens, but ONLY on success (see
    _generate_or_raise) — confirmed live this matters: a plain
    @st.cache_data on a function that itself returns None on failure
    caches that None for the full TTL too, meaning one transient rate
    limit hit made the Conflicts page show "no overview available" for
    a full 20 minutes even though the very next real attempt, seconds
    later, would have succeeded. Splitting the raise-on-failure request
    out from this thin try/except wrapper means only genuine successes
    ever get cached, so a transient failure is retried on the very next
    call instead of being stuck for the rest of the TTL window.

    Build prompts from already-rounded/bucketed values (this
    dashboard's other templated text already does this — see morning_
    briefing's *_LINES format calls), not raw floats or timestamps, so
    the same real-world situation reuses one cached call across the
    ~5s reruns it actually spans, rather than missing the cache (and
    burning a real API call) on every rerun's tiny jitter.

    `temperature` defaults to 0.7 — good for callers doing creative
    prose (morning_briefing's sentence-weaving, pages_conflicts' plain-
    English summaries), where some real variety is fine. A caller doing
    a judgment call instead of writing prose (news.py's decide/
    _ai_judge — keep-or-reject, which category) should pass something
    much lower: confirmed live that 0.7 made the exact same headline
    flip between two different verdicts across repeat calls, which is
    fine for phrasing but not for a decision that's supposed to be
    final once made.

    `max_output_tokens` defaults to 200 — plenty for one sentence or a
    short paragraph. A caller asking for something structurally bigger
    (pages_conflicts' multi-conflict JSON overview) needs to raise this
    explicitly, or the response silently truncates mid-output."""
    try:
        return _generate_or_raise(prompt, temperature, max_output_tokens)
    except Exception:
        return None
