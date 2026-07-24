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

Two entry points, pick based on what the caller actually needs:
- generate() — de-dupes by exact prompt text (news.py's per-headline
  classification: each headline gets its own real call, once, ever).
- generate_periodic() — throttled by an explicit cadence instead
  (morning_briefing, pages_conflicts: session request, "I don't need
  second by second updates... by limiting the amount of calls we have
  per minute, we can add Gemini a little all over the dashboard
  instead of exacerbating all our resources" — this is the one to
  reach for by default whenever a new feature gets added here, since
  the free tier's request-per-minute limit is shared across every
  feature calling into this module, not per-caller).
"""

import time

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

# Last real observed outcome for this process — True (succeeded),
# False (failed), or None (never attempted yet) — across every caller,
# direct (morning_briefing) or via groq_client's own fallback tier.
# See groq_client.ai_status_by_model, which reads this through
# last_outcome() below for its multi-model status badge.
_last_outcome: bool | None = None


def last_outcome() -> bool | None:
    return _last_outcome


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
    a judgment call instead of writing prose (news.py's
    _run_individual_decide — keep-or-reject, which category) should pass
    something much lower: confirmed live that 0.7 made the exact same
    headline flip between two different verdicts across repeat calls,
    which is fine for phrasing but not for a decision that's supposed
    to be final once made.

    `max_output_tokens` defaults to 200 — plenty for one sentence or a
    short paragraph. A caller asking for something structurally bigger
    (pages_conflicts' multi-conflict JSON overview) needs to raise this
    explicitly, or the response silently truncates mid-output."""
    global _last_outcome
    try:
        text = _generate_or_raise(prompt, temperature, max_output_tokens)
        _last_outcome = True
        return text
    except Exception:
        _last_outcome = False
        return None


# feature_key -> (generated_at, text) — see generate_periodic below.
# Plain module state (same convention as sports_client.py's own
# _last_good_* / _delay_buffers) rather than st.session_state: the free
# tier's rate limit is shared across every browser session hitting this
# one server process, so the throttle has to be too, not per-tab.
_periodic_cache: dict[str, tuple[float, str]] = {}


def generate_periodic(feature_key: str, refresh_seconds: int, prompt: str, temperature: float = 0.7, max_output_tokens: int = 200) -> str | None:
    """Same as generate(), but throttled by a caller-chosen cadence
    instead of by exact-prompt-text matching. Session request: "I don't
    need second by second updates... by limiting the amount of calls we
    have per minute, we can add Gemini a little all over the dashboard
    instead of exacerbating all our resources" — with several features
    now sharing one free-tier quota (15 req/min on this model),
    "recompute whenever the prompt text changes" isn't tight enough on
    its own: morning_briefing's picked facts can shift every few
    minutes just from live commute/market numbers ticking, and
    pages_conflicts' AI overview reruns on every 5s rerun a page is
    open, both far more often than that content actually needs
    refreshing.

    This is the one dial each feature sets for itself: pass a stable
    `feature_key` unique to that feature (not derived from the prompt)
    and the cadence it actually needs (pages_conflicts: 3600, hourly —
    conflict trajectories don't shift minute to minute; morning_
    briefing: 300, 5 minutes — commute/market numbers do move faster
    than that but don't need second-by-second phrasing). Whatever was
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
