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
REQUEST_TIMEOUT_SECONDS = 12
# Free tier is rate-limited (requests/minute and requests/day both), and
# nothing this feeds on (weather, commute, conflict headlines) actually
# changes fast enough to need calling any more often than this — see
# generate()'s own docstring for how this TTL turns into "call once per
# distinct prompt, not once per 5s rerun".
GENERATE_CACHE_TTL_SECONDS = 20 * 60


@st.cache_data(ttl=GENERATE_CACHE_TTL_SECONDS, show_spinner=False)
def generate(prompt: str) -> str | None:
    """One short piece of AI-written text for `prompt`, or None if the
    key's missing, the request fails, or the free tier's rate-limited
    right now — never raises. Cached by the exact prompt string: build
    prompts from already-rounded/bucketed values (this dashboard's
    other templated text already does this — see morning_briefing's
    *_LINES format calls), not raw floats or timestamps, so the same
    real-world situation reuses one cached call across the ~5s reruns
    it actually spans, rather than missing the cache (and burning a
    real API call) on every rerun's tiny jitter."""
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        resp = requests.post(
            GEMINI_URL,
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 200},
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        candidates = resp.json().get("candidates") or []
        if not candidates:
            return None
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        return text or None
    except Exception:
        return None
