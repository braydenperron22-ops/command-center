"""Groq's inference API — used to turn structured facts or raw headlines
into natural short text (see morning_briefing.py's _ai_sentence,
pages_conflicts.py's _ai_overview, news.py's _run_individual_decide). Session
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
_generate_or_raise: an overnight pause window (see _in_pause_window,
synced to the bedroom monitor's own smart-plug schedule) and a hard
daily token budget (DAILY_TOKEN_BUDGET) — see each one's own comment. Session request, after a day of
testing discovered Groq's real cap is 100k tokens/day (not just the
12k/min the response headers had already surfaced): "make everything
cheaper by lowering how often theyre pulled... completely pause AI
pulls overnight and gracefully start it back up around 3am... make
sure we will never hit the 100k limit." Per-feature cadences alone
can't promise that (headline volume on a busy news day is out of this
app's control), so the daily budget is the actual guarantee; the pause
window and slower cadences just keep usage smooth across the day
instead of front-loaded.

generate() now tries two independent Groq accounts before giving up —
see GROQ_ACCOUNTS ("primary" then "failsafe", each its own real key and
its own real 100k/day quota, tracked as two separate rolling ledgers).
Session request: "what if i use my burner gmail account to make a
second unrelated groq key that acts as our failsafe, same exact
instructions same model no hiccups." Only after both are exhausted does
it fall back to gemini_client (same public interface by design — see
that module's own docstring). Session request: "can we handoff and
delegate to a shittier model elsewhere when we hit the quota."
Deliberately NOT triggered by the overnight pause — that's checked once
up front and short-circuits before either Groq account or gemini_client
is even tried, since the pause is a chosen quiet period to conserve
budget, not a capacity problem to route around; a real None during
those hours, not a shifted call. Gemini has no equivalent daily-budget
guard of its own here — a full day of both Groq accounts being
genuinely exhausted would mean every one of those calls lands on
Gemini's quota instead, which could exhaust that too. Acceptable for
now since the failure mode is still graceful either way (a caller never
gets anything worse than the None it already has to handle), not a
third copy of Groq's guardrails.
"""

import datetime
import json
import os
import time
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from astral import LocationInfo
from astral.sun import sun

import gemini_client
import ntfy_client
import persisted_state
from config import TIMEZONE, WEATHER_LAT, WEATHER_LON

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
# gracefully start it back up around 3am" — refined further to "ai
# sleep period should be from 10pm to 4am no need for it pulling while
# screen is off... sync it with the smart plug turning off." The
# bedroom monitor's own smart plug (govee_lighting.sync_plug) already
# goes off at last light and on at first light — real civil-twilight
# dawn/dusk, not a fixed clock window, so it drifts with the actual
# season rather than being wrong by up to an hour either side of
# solstice. Reusing the exact same astral calculation here (not
# weather_client._first_last_light — that's the weather module's own
# cached, network-dependent reading; this needs a cheap, local,
# dependency-free calculation groq_client can run on its own) keeps
# the two genuinely in sync instead of two hand-picked clock times that
# could quietly drift apart from each other and from the actual screen
# state over the year.
_LOCATION = LocationInfo(latitude=WEATHER_LAT, longitude=WEATHER_LON, timezone=TIMEZONE)


def _first_last_light(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    s = sun(_LOCATION.observer, date=day, tzinfo=ZoneInfo(TIMEZONE))
    return s["dawn"].replace(tzinfo=None), s["dusk"].replace(tzinfo=None)

# Two genuinely separate Groq accounts, tried in order — session
# request: "what if i use my burner gmail account to make a second
# unrelated groq key that acts as our failsafe, same exact
# instructions same model no hiccups... small risk small reward." Each
# has its own real 100k/day quota, so each gets its own independent
# rolling ledger below — "primary" being exhausted says nothing about
# "failsafe"'s own budget. Tried before gemini_client since same-model
# Groq output is the real thing, not a step down in quality the way
# Gemini is.
GROQ_ACCOUNTS = ("primary", "failsafe")
_GROQ_SECRET_NAMES = {"primary": "GROQ_API_KEY", "failsafe": "GROQ_API_KEY_FAILSAFE"}
# account -> list of mutable [timestamp, tokens] pairs for that
# account's own real calls — a list, not a tuple, so _reconcile_budget
# can update a call's token count in place once the real usage is
# known (see _reserve_budget's return value). Only ever holds entries
# from the trailing ROLLING_WINDOW_SECONDS; anything older is pruned in
# _rolling_used every time it's read, so neither log grows unbounded
# across a long server uptime. Each log can only ever know about calls
# THIS process has made on that account — a redeploy starts both
# empty, with no way to recover what Groq's own server-side ledger says
# happened before that (Groq doesn't expose current daily usage on a
# successful call, only inside a 429's error body when something's
# actually already blocked) — see ai_status's own docstring.
_usage_logs: dict[str, list] = {account: [] for account in GROQ_ACCOUNTS}


def _local_now() -> datetime.datetime:
    return datetime.datetime.now(ZoneInfo(TIMEZONE))


def _in_pause_window(now: datetime.datetime) -> bool:
    """True outside today's first_light..last_light window — same
    civil-twilight bounds the smart plug uses, so "screen off" and "AI
    paused" are the same real condition, not two schedules that happen
    to roughly agree. Uses `now`'s own calendar date for both bounds:
    dawn and dusk both fall later the same day, so unlike the old fixed
    23:00-03:00 range this never needs a midnight-wraparound check.

    `now` is expected timezone-aware (see _local_now — kept that way
    since _reserve_budget's .timestamp() call needs it), but
    _first_last_light returns naive datetimes (same convention
    weather_client's own version and govee_lighting.sync_plug already
    use). Stripped to naive here, locally, just for this comparison —
    confirmed live this matters: comparing aware against naive raises
    TypeError, which app.py's blanket try/except around the badge's
    render call was silently swallowing, making the whole badge vanish
    with no visible error at all rather than a wrong-but-visible one."""
    first_light, last_light = _first_last_light(now.date())
    naive_now = now.replace(tzinfo=None)
    return not (first_light <= naive_now < last_light)


def ai_pulls_paused() -> bool:
    """Public wrapper on _in_pause_window/_local_now — the "screen off,
    no need for AI to be pulling" schedule isn't specific to Groq, so
    any other provider a feature routes to directly (e.g. gemini_client,
    for morning_briefing.py's own "gemini's one and only responsibility"
    routing) should still respect the same quiet hours rather than
    ignoring them just because the call bypasses this module's own
    generate()/generate_periodic()."""
    return _in_pause_window(_local_now())


def _rolling_used(account: str, now_ts: float) -> int:
    log = _usage_logs[account]
    cutoff = now_ts - ROLLING_WINDOW_SECONDS
    log[:] = [entry for entry in log if entry[0] > cutoff]
    return sum(entry[1] for entry in log)


def _reserve_budget(account: str, now: datetime.datetime, estimated_tokens: int) -> list | None:
    """The new log entry (provisionally reserved at this call's rough
    estimate — see _reconcile_budget below) if it still fits inside
    this account's trailing 24h remaining budget, for the caller to
    hold onto and reconcile once the real usage is known. None means:
    don't even attempt the network call, same graceful "nothing new
    right now" fallback a real 429 already causes."""
    now_ts = now.timestamp()
    if _rolling_used(account, now_ts) + estimated_tokens > DAILY_TOKEN_BUDGET:
        return None
    entry = [now_ts, estimated_tokens]
    _usage_logs[account].append(entry)
    return entry


def _reconcile_budget(entry: list, actual_tokens: int | None) -> None:
    """Swaps the pre-call estimate already reserved in `entry` for what
    Groq actually reports using (or zero on a failed call, since a
    rejected request isn't billed) — so a call whose ceiling
    (max_output_tokens) was high but whose real output was short
    doesn't permanently over-charge the rolling window. Updates the
    same entry already sitting in that account's usage log in place,
    keeping its original timestamp so it still ages out on the schedule
    it actually happened on, not when it was reconciled."""
    entry[1] = actual_tokens or 0


# Which tier actually served the most recent real generate() call,
# system-wide (not per-feature — same framing ai_status() already
# used for "primary" specifically). "not_attempted" is the fresh-
# process default, distinct from "none" (attempted, and every tier —
# primary, failsafe, AND gemini — genuinely failed) since those are
# different situations worth telling apart. Session request, after the
# budget-estimate percentage alone caused real confusion ("thought we
# rate limited main?? ... badge said 100%" — the estimate can't see a
# real failure the way an actual observed outcome can): "can you just
# change the badge to say AI: Active or AI: Rate Limited or any an all
# other statuses it may have."
_last_served_by = "not_attempted"

# model -> {"ok": bool, "via": "primary"|"failsafe"|None} for the last
# real attempt on that specific model, across every caller — session
# request, now that this app routes different features to genuinely
# different models (news.py's default llama-3.3-70b-versatile,
# pages_conflicts.py's openai/gpt-oss-120b): "since we have a bunch of
# different models now... show what models are active and what ones
# are not responding." The old single _last_served_by above only ever
# reflected whichever call happened most recently, system-wide — a
# gpt-oss success (once/day, see pages_conflicts' REFRESH_SECONDS)
# could read "Active" while llama was actually failing every call that
# hour, or vice versa. See ai_status_by_model below.
_model_status: dict[str, dict] = {}

# Display names + fixed slot order for the badge (ai_status_by_model).
# Coupled to pages_conflicts.GPT_OSS_MODEL's actual string value by
# convention, not by import (that module already imports this one;
# importing back would be circular) — if that constant's model ever
# changes, update the key here too. Fixed rather than "whatever's been
# attempted so far this process" so the badge doesn't grow/shrink or
# reorder itself as different features' own cadences happen to fire —
# GPT-OSS in particular only runs once a day, so "only show what's
# been attempted" would leave it missing from the badge most of the
# time.
MODEL_DISPLAY_NAMES = {GROQ_MODEL: "Llama", "openai/gpt-oss-120b": "GPT-OSS"}
_MODEL_SLOTS = [GROQ_MODEL, "openai/gpt-oss-120b"]


def ai_status() -> dict:
    """{"label": str, "tone": "good"|"medium"|"low"|"neutral"} for a
    small live status badge. Grounded in what actually just happened
    (see _last_served_by), not only the budget estimate — that
    estimate has real blind spots of its own (a redeploy resets it
    optimistically; input-token guesses can run a hair over) that a
    real observed outcome doesn't share. Statuses, in priority order:

    - "Asleep" (neutral): the overnight pause window — deliberately not
      attempting anything, not a failure.
    - "Rate Limited" (low): the most recent real attempt failed on
      every tier — primary, failsafe, AND gemini. Nothing is currently
      getting through.
    - "On Failsafe" / "On Gemini" (medium): primary's most recent real
      attempt failed, but a fallback tier covered it — output is still
      flowing, just not from the primary account.
    - "Low" (medium): primary's own rolling budget has under 20%
      remaining, even though its last real attempt succeeded (or
      nothing's been attempted yet this process) — a heads-up that
      Rate Limited may be coming.
    - "Active" (good): primary healthy, most recent attempt (if any)
      succeeded on primary."""
    now = _local_now()
    if _in_pause_window(now):
        return {"label": "Asleep", "tone": "neutral"}
    if _last_served_by == "none":
        return {"label": "Rate Limited", "tone": "low"}
    if _last_served_by == "failsafe":
        return {"label": "On Failsafe", "tone": "medium"}
    if _last_served_by == "gemini":
        return {"label": "On Gemini", "tone": "medium"}
    # _last_served_by is "primary" or "not_attempted" — primary's own
    # remaining budget still decides between a Low warning and Active.
    used = max(0, min(_rolling_used("primary", now.timestamp()), DAILY_TOKEN_BUDGET))
    remaining_pct = 100.0 * (DAILY_TOKEN_BUDGET - used) / DAILY_TOKEN_BUDGET
    if remaining_pct < 20:
        return {"label": "Low", "tone": "medium"}
    return {"label": "Active", "tone": "good"}


def ai_status_by_model() -> list[dict]:
    """{"label", "status", "tone"} for each model this app actually
    uses — Llama and GPT-OSS on Groq (see _MODEL_SLOTS), plus Gemini —
    so the badge shows each one's own real status instead of one line
    for whichever happened to run most recently (see _model_status's
    own comment for why that was misleading with more than one model
    in play). notify_if_outage/ai_status above are untouched and still
    drive the actual outage push — this is purely for the on-screen
    glance.

    Per slot, in priority order:
    - "Asleep" (neutral): the overnight pause window, same as
      ai_status() — nothing's being attempted for ANY model right now.
    - "Idle" (neutral): this model hasn't had a real attempt yet this
      process — a fresh redeploy, or, for GPT-OSS specifically given
      its once-a-day cadence, simply hasn't been that model's turn yet
      today. Not a failure, just nothing observed.
    - "Rate Limited" (low): its last real attempt failed everywhere
      available to it (both Groq accounts for Llama/GPT-OSS; Gemini
      itself for Gemini).
    - "Failsafe" (medium): Llama/GPT-OSS only — primary failed but the
      failsafe account covered it.
    - "Active" (good): last real attempt succeeded on the account/
      provider it's actually supposed to run on."""
    asleep = _in_pause_window(_local_now())
    entries = []
    for model in _MODEL_SLOTS:
        label = MODEL_DISPLAY_NAMES.get(model, model)
        info = _model_status.get(model)
        if asleep:
            entries.append({"label": label, "status": "Asleep", "tone": "neutral"})
        elif info is None:
            entries.append({"label": label, "status": "Idle", "tone": "neutral"})
        elif not info["ok"]:
            entries.append({"label": label, "status": "Rate Limited", "tone": "low"})
        elif info["via"] == "failsafe":
            entries.append({"label": label, "status": "Failsafe", "tone": "medium"})
        else:
            entries.append({"label": label, "status": "Active", "tone": "good"})
    gemini_outcome = gemini_client.last_outcome()
    if asleep:
        entries.append({"label": "Gemini", "status": "Asleep", "tone": "neutral"})
    elif gemini_outcome is None:
        entries.append({"label": "Gemini", "status": "Idle", "tone": "neutral"})
    elif gemini_outcome:
        entries.append({"label": "Gemini", "status": "Active", "tone": "good"})
    else:
        entries.append({"label": "Gemini", "status": "Rate Limited", "tone": "low"})
    return entries


# "Rate Limited" has to hold for this long before it's worth a push —
# a single failed attempt (one transient network blip, one call that
# happened to land right as the rolling budget was momentarily tight)
# isn't a real outage, and every tier already retries on its own next
# cycle regardless. Session request: "add meaningful outage alerts...
# if [the AI] goes dark for a meaningful period of time" — this is that
# "meaningful period" gate, the AI-outage equivalent of data_health's
# own per-source THRESHOLDS_SECONDS.
AI_OUTAGE_ALERT_AFTER_SECONDS = 20 * 60

def notify_if_outage() -> None:
    """Pushes a phone notification once per outage episode once "Rate
    Limited" (see ai_status — every tier failed on the most recent real
    attempt) has held continuously for AI_OUTAGE_ALERT_AFTER_SECONDS,
    not on the first failed attempt. Tracks the episode's start time and
    whether it's already been notified via persisted_state, not
    st.session_state or a plain module global — a session reset or a
    process restart (a redeploy, a Cloud sleep/wake) must never look
    like "nothing sent yet" for an outage still genuinely in progress.
    Any status other than "Rate Limited" clears the episode, so a
    later, separate outage gets its own fresh alert rather than being
    permanently suppressed because one already fired once before."""
    status = ai_status()
    episode = persisted_state.load("ai_outage", {"since": None, "notified": False})
    if status["label"] != "Rate Limited":
        if episode["since"] is not None:
            persisted_state.save("ai_outage", {"since": None, "notified": False})
        return
    now = time.time()
    if episode["since"] is None:
        episode = {"since": now, "notified": False}
        persisted_state.save("ai_outage", episode)
    if now - episode["since"] < AI_OUTAGE_ALERT_AFTER_SECONDS or episode["notified"]:
        return
    persisted_state.save("ai_outage", {"since": episode["since"], "notified": True})
    ntfy_client.send(
        title="AI outage",
        message=f"Primary, failsafe, and Gemini have all been failing for over {AI_OUTAGE_ALERT_AFTER_SECONDS // 60} minutes.",
        priority="high",
        tags="warning",
    )


@st.cache_data(ttl=GENERATE_CACHE_TTL_SECONDS, show_spinner=False)
def _generate_or_raise(account: str, prompt: str, temperature: float, max_output_tokens: int, model: str) -> str:
    """Real request against the given GROQ_ACCOUNTS entry, real
    exception on any failure — st.cache_data only ever caches a genuine
    successful return, never a raised exception, so a transient failure
    (rate limit, network blip, daily budget exhausted) is never what
    gets cached here. See generate() below for why that split matters,
    and for the overnight pause — that's checked once by the caller
    before either account is tried, not per-account here, since both
    accounts share the same pause window.

    `model` defaults to GROQ_MODEL for every existing caller (see
    generate()'s own default) — only a caller that explicitly asks for
    something else (see pages_conflicts.py's use of "openai/gpt-oss-
    120b") pays attention to this at all. Only reads choices[0].message
    ["content"], never "reasoning" — a reasoning-family model (like
    that one) puts its actual answer in content and its hidden chain-
    of-thought in a separate reasoning field this already ignores by
    construction, no special-casing needed here for that."""
    api_key = st.secrets.get(_GROQ_SECRET_NAMES[account])
    if not api_key:
        raise RuntimeError(f"no {_GROQ_SECRET_NAMES[account]} configured")
    now = _local_now()
    estimated_tokens = len(prompt) // 4 + max_output_tokens
    reservation = _reserve_budget(account, now, estimated_tokens)
    if reservation is None:
        raise RuntimeError(f"{account} Groq account's daily token budget exhausted for today")
    try:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
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


def generate(prompt: str, temperature: float = 0.7, max_output_tokens: int = 200, model: str = GROQ_MODEL) -> str | None:
    """One short piece of AI-written text for `prompt`, or None if the
    key's missing, the request fails, or the free tier's rate-limited
    right now — never raises. Cached by the exact prompt string AND
    temperature/max_output_tokens/model, but ONLY on success (see
    _generate_or_raise) — same reasoning as gemini_client.generate's
    own docstring: a transient failure must be retried on the very next
    call, not stuck showing "unavailable" for the rest of the TTL
    window.

    `model` defaults to GROQ_MODEL — only pass something else if a
    feature specifically needs a different model's characteristics
    (see pages_conflicts.py's use of "openai/gpt-oss-120b" for real
    reasoning depth on a low-frequency call; session request: "Meta is
    losing the AI race... is there a better... option through Grok").
    Only ever applies to the two Groq accounts — if both fail and this
    falls through to gemini_client, that's always Gemini's own model,
    since Gemini doesn't host Groq's catalog.

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
    something much lower, for the same consistency reasons documented
    in gemini_client's own docstring.

    `max_output_tokens` defaults to 200 — plenty for one sentence or a
    short paragraph. A caller asking for something structurally bigger
    (pages_conflicts' multi-conflict JSON overview) needs to raise this
    explicitly, or the response silently truncates mid-output.

    During the overnight pause, returns None immediately without
    attempting anything — neither Groq account nor gemini_client, since
    the pause is a deliberate quiet period, not a capacity problem (see
    this module's own docstring). Otherwise tries "primary", then
    "failsafe" (see GROQ_ACCOUNTS — two genuinely separate Groq
    accounts/quotas), then falls back to gemini_client before finally
    giving up and returning None. Records which tier actually served
    this call (or that none did) in _last_served_by for ai_status() —
    left untouched during the pause itself, since that's a separate
    status, not a failure to record."""
    global _last_served_by
    if _in_pause_window(_local_now()):
        return None
    for account in GROQ_ACCOUNTS:
        try:
            result = _generate_or_raise(account, prompt, temperature, max_output_tokens, model)
            _last_served_by = account
            _model_status[model] = {"ok": True, "via": account}
            return result
        except Exception:
            continue
    _model_status[model] = {"ok": False, "via": None}
    result = gemini_client.generate(prompt, temperature=temperature, max_output_tokens=max_output_tokens)
    _last_served_by = "gemini" if result is not None else "none"
    return result


# feature_key -> (generated_at, text) — see generate_periodic below.
# Plain module state (same convention as sports_client.py's own
# _last_good_* / _delay_buffers, gemini_client's own _periodic_cache)
# rather than st.session_state: the rate limit is shared across every
# browser session hitting this one server process, so the throttle has
# to be too, not per-tab.
#
# Session request: "can you improve the cache so that conflicts cant
# fail during an outage." Mid-process, an outage already falls back to
# the last good value correctly (see generate_periodic's own
# docstring) — the actual gap is a fresh process: a redeploy wipes this
# dict back to empty, so the very first call for each feature has
# nothing to fall back to if Groq happens to be down right then. Below
# persists every successful result to a small local JSON file and
# reloads it at import time, so a restart starts from "whatever last
# worked" instead of from nothing. Best-effort, not a guarantee — a
# platform that gives this app a genuinely fresh filesystem on every
# deploy (not just every restart) would still start empty; there's no
# external database here to survive that, only this local file.
_PERIODIC_CACHE_PATH = os.path.join(os.path.dirname(__file__), ".periodic_cache.json")


def _load_periodic_cache() -> dict[str, tuple[float, str]]:
    try:
        with open(_PERIODIC_CACHE_PATH) as f:
            raw = json.load(f)
        return {
            str(k): (float(v[0]), str(v[1]))
            for k, v in raw.items()
            if isinstance(v, list) and len(v) == 2
        }
    except Exception:
        return {}


def _save_periodic_cache() -> None:
    try:
        with open(_PERIODIC_CACHE_PATH, "w") as f:
            json.dump(_periodic_cache, f)
    except Exception:
        pass  # best-effort — a failed write just means no persistence this time, never a crash


_periodic_cache: dict[str, tuple[float, str]] = _load_periodic_cache()


# Deterministic per-feature delay (0-90s) applied only to a feature's
# very first-ever call after a fresh deploy/restart (empty cache) — so
# a cold start doesn't fire every periodic feature's real Groq call in
# the same rerun. Ordinary steady-state cadence is untouched; this only
# spreads out the cold-start moment itself. Session request: "layer
# them so it doesnt pull them all at once."
_STARTUP_JITTER_SECONDS = 90


def generate_periodic(feature_key: str, refresh_seconds: int, prompt: str, temperature: float = 0.7, max_output_tokens: int = 200, model: str = GROQ_MODEL) -> str | None:
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
    there's truly nothing cached yet at all — which the on-disk
    persistence above (see _load_periodic_cache) makes much rarer:
    a feature that's ever succeeded once, on any past run this
    filesystem has seen, skips the startup jitter below entirely and
    already has real fallback content from the moment this process
    starts."""
    now = time.time()
    cached = _periodic_cache.get(feature_key)
    if cached is None:
        # First time this feature_key has EVER succeeded, on this
        # filesystem, period — not just this process. Stagger its real
        # first pull instead of firing immediately.
        jitter = hash(feature_key) % _STARTUP_JITTER_SECONDS
        _periodic_cache[feature_key] = (now - refresh_seconds + jitter, "")
        return None
    if now - cached[0] < refresh_seconds:
        return cached[1] or None
    text = generate(prompt, temperature=temperature, max_output_tokens=max_output_tokens, model=model)
    if text is not None:
        _periodic_cache[feature_key] = (now, text)
        _save_periodic_cache()
        return text
    return cached[1] or None
