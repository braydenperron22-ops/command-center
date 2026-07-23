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

Two guardrails live here, applied uniformly to every caller regardless
of which throttle wrapper they use (generate_periodic's cadence cache
or news.py's own hand-rolled one) since both eventually call
_generate_or_raise: an overnight pause window (AI_PAUSE_START_HOUR/
AI_PAUSE_END_HOUR) and a hard daily token budget (DAILY_TOKEN_BUDGET) —
see each constant's own comment. Session request, after a day of
testing discovered Groq's real cap is 100k tokens/day (not just the
12k/min the response headers had already surfaced): "make everything
cheaper by lowering how often theyre pulled... completely pause AI
pulls overnight and gracefully start it back up around 3am... make
sure we will never hit the 100k limit." Per-feature cadences alone
can't promise that (headline volume on a busy news day is out of this
app's control), so the daily budget is the actual guarantee; the pause
window and slower cadences just keep usage smooth across the day
instead of front-loaded.
"""

import datetime
import time
from zoneinfo import ZoneInfo

import requests
import streamlit as st

from config import TIMEZONE

GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 20  # generous enough for a long structured response (see max_output_tokens); short calls finish well under this anyway
# Groq's free tier is far less tight than Gemini's turned out to be in
# practice, but this still exists for the same reason gemini_client's
# did: nothing this feeds on actually changes fast enough to need
# calling any more often than this — see generate()'s own docstring.
GENERATE_CACHE_TTL_SECONDS = 20 * 60

# Session discovery: Groq's free tier caps this model at 100,000 tokens
# PER DAY — separate from, and far tighter than, the 12k/min bucket
# (which refills almost instantly). A single busy day of testing burned
# through the whole daily allowance. This is that real cap, used
# directly — no safety margin held back below it. Session request:
# "remove the 85k hard cap, 100% should mean literally nothing can go
# through" — 0% remaining now means the same thing as Groq's own limit,
# not an earlier, artificial cutoff. The tradeoff: the pre-call
# estimate (input tokens are guessed from prompt length, not tokenized
# exactly) can occasionally run a hair over, causing a real 429 right
# at the edge — already handled gracefully (falls back to cached/None,
# see generate()), same as any other rate-limit response.
DAILY_TOKEN_BUDGET = 100_000
# Confirmed live: this is a ROLLING 24h window, not a fixed daily
# reset — a 429 at ~9:54pm reporting "Used 97025/100000... try again in
# 1h10m" for a ~7,838-token request, followed by a trivial 5-token call
# going through fine 25 minutes later (needing only a sliver of the
# same headroom), only makes sense if capacity frees up continuously as
# each real call's usage ages out 24h after it happened — not all at
# once at midnight. _usage_log below mirrors that shape directly rather
# than approximating it with a fixed reset. Session request: "does it
# go down gracefully as time passes... does the badge know this."
ROLLING_WINDOW_SECONDS = 24 * 60 * 60
# Session request: "we can completely pause AI pulls overnight and
# gracefully start it back up around 3am." Local time (America/
# Toronto — see config.TIMEZONE), same basis morning_briefing.py's own
# 5am-10am window already uses, so the two windows agree with each
# other instead of one being UTC and one being local.
AI_PAUSE_START_HOUR = 23
AI_PAUSE_END_HOUR = 3

# Each entry is a mutable [timestamp, tokens] pair for one real call —
# a list, not a tuple, so _reconcile_budget can update a call's token
# count in place once the real usage is known (see _reserve_budget's
# return value). Only ever holds entries from the trailing
# ROLLING_WINDOW_SECONDS; anything older is pruned in _rolling_used
# every time it's read, so it never grows unbounded across a long
# server uptime. This can only ever know about calls THIS process has
# actually made — a redeploy starts it empty, with no way to recover
# what Groq's own server-side ledger says happened before that (Groq
# doesn't expose current daily usage on a successful call, only inside
# a 429's error body when something's actually already blocked) — see
# budget_status's own docstring.
_usage_log: list[list] = []


def _local_now() -> datetime.datetime:
    return datetime.datetime.now(ZoneInfo(TIMEZONE))


def _in_pause_window(now: datetime.datetime) -> bool:
    # Wraps past midnight (23 -> 3), so this is "hour >= start OR hour <
    # end", not a plain range check.
    return now.hour >= AI_PAUSE_START_HOUR or now.hour < AI_PAUSE_END_HOUR


def _rolling_used(now_ts: float) -> int:
    global _usage_log
    cutoff = now_ts - ROLLING_WINDOW_SECONDS
    _usage_log = [entry for entry in _usage_log if entry[0] > cutoff]
    return sum(entry[1] for entry in _usage_log)


def _reserve_budget(now: datetime.datetime, estimated_tokens: int) -> list | None:
    """The new log entry (provisionally reserved at this call's rough
    estimate — see _reconcile_budget below) if it still fits inside the
    trailing 24h's remaining budget, for the caller to hold onto and
    reconcile once the real usage is known. None means: don't even
    attempt the network call, same graceful "nothing new right now"
    fallback a real 429 already causes."""
    now_ts = now.timestamp()
    if _rolling_used(now_ts) + estimated_tokens > DAILY_TOKEN_BUDGET:
        return None
    entry = [now_ts, estimated_tokens]
    _usage_log.append(entry)
    return entry


def _reconcile_budget(entry: list, actual_tokens: int | None) -> None:
    """Swaps the pre-call estimate already reserved in `entry` for what
    Groq actually reports using (or zero on a failed call, since a
    rejected request isn't billed) — so a call whose ceiling
    (max_output_tokens) was high but whose real output was short
    doesn't permanently over-charge the rolling window. Updates the
    same entry already sitting in _usage_log in place, keeping its
    original timestamp so it still ages out on the schedule it actually
    happened on, not when it was reconciled."""
    entry[1] = actual_tokens or 0


def budget_status() -> dict:
    """{"used": int, "budget": DAILY_TOKEN_BUDGET, "remaining_pct": float
    0-100, "paused": bool} for a small live usage indicator — session
    request: "a little ai usage bar that shows the health bar for groq
    ie how many credits we have left shown as a percentage." Tracks the
    same rolling 24h window Groq's own limit actually uses (see
    ROLLING_WINDOW_SECONDS), so it recovers gradually through the day
    the same way the real thing does, rather than jumping to 100% at a
    fixed reset instant that doesn't match reality. Still only knows
    about calls this process has made itself — right after a redeploy
    this reads optimistic (starts at 100% even if the real account is
    still constrained) until either 24h passes or enough real calls
    happen to start reflecting it; there's no way to backfill Groq's
    own server-side history into a fresh process. "paused" reflects the
    overnight window, not the budget — shown separately since "0% left"
    and "asleep until 3am" are different situations worth telling apart
    at a glance."""
    now = _local_now()
    used = max(0, min(_rolling_used(now.timestamp()), DAILY_TOKEN_BUDGET))
    remaining_pct = max(0.0, 100.0 * (DAILY_TOKEN_BUDGET - used) / DAILY_TOKEN_BUDGET)
    return {
        "used": used,
        "budget": DAILY_TOKEN_BUDGET,
        "remaining_pct": remaining_pct,
        "paused": _in_pause_window(now),
    }


@st.cache_data(ttl=GENERATE_CACHE_TTL_SECONDS, show_spinner=False)
def _generate_or_raise(prompt: str, temperature: float, max_output_tokens: int) -> str:
    """Real request, real exception on any failure — st.cache_data only
    ever caches a genuine successful return, never a raised exception,
    so a transient failure (rate limit, network blip, paused overnight,
    daily budget exhausted) is never what gets cached here. See
    generate() below for why that split matters."""
    api_key = st.secrets.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("no GROQ_API_KEY configured")
    now = _local_now()
    if _in_pause_window(now):
        raise RuntimeError("AI pulls paused overnight")
    estimated_tokens = len(prompt) // 4 + max_output_tokens
    reservation = _reserve_budget(now, estimated_tokens)
    if reservation is None:
        raise RuntimeError("daily Groq token budget exhausted for today")
    try:
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
    except Exception:
        _reconcile_budget(reservation, 0)  # rejected/failed calls aren't billed — release the reservation
        raise
    body = resp.json()
    _reconcile_budget(reservation, (body.get("usage") or {}).get("total_tokens"))
    choices = body.get("choices") or []
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


# Deterministic per-feature delay (0-90s) applied only to a feature's
# very first-ever call after a fresh deploy/restart (empty cache) — so
# a cold start doesn't fire every periodic feature's real Groq call in
# the same rerun. Ordinary steady-state cadence is untouched; this only
# spreads out the cold-start moment itself. Session request: "layer
# them so it doesnt pull them all at once."
_STARTUP_JITTER_SECONDS = 90


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
    if cached is None:
        # First time this feature_key has ever been seen this process —
        # stagger its real first pull instead of firing immediately.
        jitter = hash(feature_key) % _STARTUP_JITTER_SECONDS
        _periodic_cache[feature_key] = (now - refresh_seconds + jitter, "")
        return None
    if now - cached[0] < refresh_seconds:
        return cached[1] or None
    text = generate(prompt, temperature=temperature, max_output_tokens=max_output_tokens)
    if text is not None:
        _periodic_cache[feature_key] = (now, text)
        return text
    return cached[1] or None
