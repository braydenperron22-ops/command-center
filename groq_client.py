"""Groq's inference API — used to turn structured facts or raw headlines
into natural short text (see morning_briefing.py's _ai_sentence,
pages_conflicts.py's _ai_overview, news.py's _run_batch_decide). Session
request: "im sick of hitting quotas man... whats the ai api with the
highest rate limit" — Groq runs open-weight models (Meta/OpenAI/etc.'s
own releases, not Groq's own) on custom inference hardware built for
speed, with a free tier that's dramatically more generous than Gemini's
free tier was turning out to be for this app's real usage pattern.

Pinned to "llama-3.3-70b-versatile" rather than a floating "latest"
alias the way gemini_client.py used — Groq's own model catalog (see
https://api.groq.com/openai/v1/models, queried live) doesn't offer a
rolling alias the way Gemini's "gemini-flash-lite-latest" did, so this
needs a manual bump if Groq ever retires this specific model. Chosen
after a live side-by-side test against this app's own real prompts
(structured JSON classification, JARVIS-voiced creative prose) — both
came back clean and comparable in quality to what Gemini was producing.

Same public interface as gemini_client.py on purpose (generate/
generate_periodic, same signatures) — every caller in this app already
went through gemini_client, so migrating call sites is a straight
import swap, nothing else changes. Every caller MUST still treat a
None return as "the AI's unavailable right now" and fall back to its
own non-AI behavior — a different provider doesn't change that
obligation, only how rarely it should actually trigger.
"""

import time

import requests
import streamlit as st

GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 20  # generous enough for a long structured response (see max_output_tokens); short calls finish well under this anyway
# Groq's free tier is far less tight than Gemini's turned out to be in
# practice, but this still exists for the same reason gemini_client's
# did: nothing this feeds on actually changes fast enough to need
# calling any more often than this — see generate()'s own docstring.
GENERATE_CACHE_TTL_SECONDS = 20 * 60


@st.cache_data(ttl=GENERATE_CACHE_TTL_SECONDS, show_spinner=False)
def _generate_or_raise(prompt: str, temperature: float, max_output_tokens: int) -> str:
    """Real request, real exception on any failure — st.cache_data only
    ever caches a genuine successful return, never a raised exception,
    so a transient failure (rate limit, network blip) is never what
    gets cached here. See generate() below for why that split matters."""
    api_key = st.secrets.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("no GROQ_API_KEY configured")
    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    choices = resp.json().get("choices") or []
    if not choices:
        raise RuntimeError("empty choices in Groq response")
    text = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("empty text in Groq response")
    return text


def generate(prompt: str, temperature: float = 0.7, max_output_tokens: int = 200) -> str | None:
    """One short piece of AI-written text for `prompt`, or None if the
    key's missing, the request fails, or the free tier's rate-limited
    right now — never raises. Cached by the exact prompt string AND
    temperature/max_output_tokens, but ONLY on success (see
    _generate_or_raise) — same reasoning as gemini_client.generate's
    own docstring: a transient failure must be retried on the very next
    call, not stuck showing "unavailable" for the rest of the TTL
    window.

    Build prompts from already-rounded/bucketed values (this
    dashboard's other templated text already does this — see morning_
    briefing's *_LINES format calls), not raw floats or timestamps, so
    the same real-world situation reuses one cached call across the
    ~5s reruns it actually spans, rather than missing the cache (and
    burning a real API call) on every rerun's tiny jitter.

    `temperature` defaults to 0.7 — good for callers doing creative
    prose (morning_briefing's sentence-weaving, pages_conflicts' plain-
    English summaries), where some real variety is fine. A caller doing
    a judgment call instead of writing prose (news.py's
    _run_batch_decide — keep-or-reject, which category) should pass
    something much lower, for the same consistency reasons documented
    in gemini_client's own docstring.

    `max_output_tokens` defaults to 200 — plenty for one sentence or a
    short paragraph. A caller asking for something structurally bigger
    (pages_conflicts' multi-conflict JSON overview) needs to raise this
    explicitly, or the response silently truncates mid-output."""
    try:
        return _generate_or_raise(prompt, temperature, max_output_tokens)
    except Exception:
        return None


# feature_key -> (generated_at, text) — see generate_periodic below.
# Plain module state (same convention as sports_client.py's own
# _last_good_* / _delay_buffers, gemini_client's own _periodic_cache)
# rather than st.session_state: the rate limit is shared across every
# browser session hitting this one server process, so the throttle has
# to be too, not per-tab.
_periodic_cache: dict[str, tuple[float, str]] = {}


def generate_periodic(feature_key: str, refresh_seconds: int, prompt: str, temperature: float = 0.7, max_output_tokens: int = 200) -> str | None:
    """Same as generate(), but throttled by a caller-chosen cadence
    instead of by exact-prompt-text matching — see gemini_client.
    generate_periodic's own docstring for the full rationale (this is a
    straight port, same behavior, same signature).

    Pass a stable `feature_key` unique to that feature (not derived
    from the prompt) and the cadence it actually needs. Whatever was
    last generated for that key keeps being reused, no matter how much
    the prompt content drifts within the window — a real new call only
    ever fires once refresh_seconds has actually elapsed.

    On a failed real attempt, falls back to the last good value for
    this key if there is one (rather than flashing "unavailable" for a
    feature that was working moments ago), and only returns None if
    there's truly nothing cached yet at all."""
    now = time.time()
    cached = _periodic_cache.get(feature_key)
    if cached and now - cached[0] < refresh_seconds:
        return cached[1]
    text = generate(prompt, temperature=temperature, max_output_tokens=max_output_tokens)
    if text is not None:
        _periodic_cache[feature_key] = (now, text)
        return text
    return cached[1] if cached else None
