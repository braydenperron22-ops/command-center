"""Physical kiosk-box hardware health — CPU/RAM/temp/network/device-count
readings pushed to Upstash by a script that runs directly on the kiosk
hardware itself (outside this repo entirely, not tracked here —
confirmed by grepping for it; app.py's own bottom-right corner tile and
pages_system_health.py are the read side of that same handoff).

Session request: "we have to be very conservative with our [Upstash]
limits... can we batch all of our uploads." The writer script used to
push three separate keys (kiosk_perf_stats, kiosk_network_test,
kiosk_watchdog_status) on two separate timers — consolidated into one
script, one timer, one key (kiosk_status) with perf/network/watchdog/
devices as sub-objects, one Upstash write per cycle instead of three.
This module is the one place that unpacks that combined shape back into
the four separate dicts every existing consumer (this file's own
hardware_headline_candidate, dashboard_score.py, pages_maintenance.py,
pages_system_health.py) already expects — none of those callers needed
to change at all, only where their data actually comes from.

Session request: "make it so if any readings are concerning it shows
up as a red headline so i know my mini pc needs work ie 'clean fans'."
The writer script's own "bad" flag is a single opaque boolean — fine
for the corner tile's dot color, but not enough to say WHAT'S actually
wrong or what to DO about it. This module ignores that flag entirely
and judges each of the 3 raw numbers independently against its own
thresholds below, so the headline can name the real metric and pair it
with concrete, metric-specific advice ("clean fans" was the user's own
example for a hot CPU) instead of a generic "something's wrong."
"""

import streamlit as st

import persisted_state


# The one real Upstash read every consumer below shares — st.cache_
# data's per-process memoization means every call site within the same
# rerun (and across reruns within the TTL) gets the same cached dict
# instead of each doing its own GET. 120s matches the writer's own
# cycle time; caching any looser would return stale data for no
# benefit, any tighter would just re-fetch data that hasn't changed.
@st.cache_data(ttl=120)
def _load_combined() -> dict | None:
    return persisted_state.load("kiosk_status", None)


def load_perf_stats() -> dict | None:
    combined = _load_combined()
    if combined is None:
        return None
    perf = dict(combined.get("perf") or {})
    perf.setdefault("at", combined.get("at"))
    return perf or None


def load_network_test() -> dict | None:
    combined = _load_combined()
    if combined is None:
        return None
    net = dict(combined.get("network") or {})
    # The network sub-reading carries its own "at" (it's only actually
    # re-tested every ~20min, not every 2min cycle like the rest of
    # this payload) -- only fall back to the outer timestamp if the
    # writer script is old enough not to have set one yet.
    net.setdefault("at", combined.get("at"))
    return net or None


def load_watchdog_status() -> dict | None:
    """Same shape pages_maintenance.py and dashboard_score.py already
    expect from the old standalone kiosk_watchdog_status key — {"at",
    "status", "issues"}."""
    combined = _load_combined()
    if combined is None:
        return None
    watchdog = dict(combined.get("watchdog") or {})
    watchdog.setdefault("at", combined.get("at"))
    return watchdog or None


def load_device_stats() -> dict | None:
    """{"count", "delta"} -- devices currently on the home network and
    the change since the last 2-minute cycle. See app.py's own arrival/
    departure toast for how `delta` turns into "someone's home" without
    claiming to know who."""
    combined = _load_combined()
    if combined is None:
        return None
    devices = dict(combined.get("devices") or {})
    devices.setdefault("at", combined.get("at"))
    return devices or None


# This repo has no visibility into whatever logic the kiosk's own
# writer script uses to set "bad" (see this module's own docstring —
# that script isn't tracked here), so these are independent,
# deliberately conservative consumer-hardware norms: most CPUs aren't
# a real concern until well past 70C, and CPU/RAM only really need
# attention once they're pegged near the ceiling, not just busy. Worth
# revisiting against the real box's own normal range if these ever
# feel wrong in practice.
TEMP_HIGH_C = 70
CPU_HIGH_PCT = 90
RAM_HIGH_PCT = 90

_TEMP_ADVICE = "clean the fans/vents"
_CPU_ADVICE = "check for a runaway process"
_RAM_ADVICE = "a restart would help"


def _concerns(perf: dict) -> list[tuple[str, str]]:
    """[(short_reading, advice)] for every metric currently over its
    own threshold, worst-first — empty once the box is genuinely fine.
    Independent per-field checks (not the writer's own single "bad"
    flag) so more than one real issue at once still gets its own
    separate mention instead of collapsing into one vague warning."""
    out = []
    temp = perf.get("temp_c")
    if temp is not None and temp >= TEMP_HIGH_C:
        out.append((f"{temp}°C", _TEMP_ADVICE))
    cpu = perf.get("cpu_pct")
    if cpu is not None and cpu >= CPU_HIGH_PCT:
        out.append((f"{cpu}% CPU", _CPU_ADVICE))
    ram = perf.get("ram_pct")
    if ram is not None and ram >= RAM_HIGH_PCT:
        out.append((f"{ram}% RAM", _RAM_ADVICE))
    return out


def hardware_headline_candidate(now) -> dict | None:
    """Red-headline candidate (see headline_rotation.py's own shape),
    or None while every real reading is within its own normal range.
    rotation-warning tier — real and worth actually doing something
    about, but not the rotation-critical tier reserved for a genuine
    emergency (market_circuit_breaker) — a hot mini PC needs cleaning,
    not an ambulance. No target_ms — this isn't a countdown, just a
    standing "this is currently true" fact, same shape sports_alerts.
    live_score_headline_candidates already uses for its own non-
    countdown candidates. `now` accepted for signature symmetry with
    every other *_candidate function in this app, even though this
    reading doesn't actually need it."""
    perf = load_perf_stats()
    if perf is None:
        return None
    concerns = _concerns(perf)
    if not concerns:
        return None
    reading, advice = concerns[0]
    text = f"Kiosk running hot: {reading} — {advice}" if reading.endswith("°C") else f"Kiosk needs attention: {reading} — {advice}"
    if len(concerns) > 1:
        extra = ", ".join(r for r, _ in concerns[1:])
        text += f" (also {extra})"
    return {"text": text, "css_class": "rotation-warning", "target_ms": None, "template": "{}", "zero_text": None}


# Session request: "I want a toast alert... X amount of devices just
# came online, or people are leaving." The kiosk's own writer script
# already computes count/delta every 2-minute cycle (see its own
# comment) -- this just turns a genuine change into a one-shot toast,
# same append-to-the-queue shape as commute_reminder.check_car_prep and
# every other source app.py's _gather_new_alerts calls. Module-level
# dedup (not st.session_state) for the same reason toast_queue.py
# itself is process-wide, not per-session — this is imported once per
# process and, unlike app.py itself, is NOT re-exec'd fresh every
# rerun, so a plain global here really does survive across ticks (see
# persisted_state.py's own docstring on exactly this distinction).
_last_alerted_device_at: float | None = None


def device_change_toast() -> dict | None:
    global _last_alerted_device_at
    devices = load_device_stats()
    if devices is None:
        return None
    at = devices.get("at")
    delta = devices.get("delta", 0)
    if not at or not delta:
        return None
    if at == _last_alerted_device_at:
        return None  # already alerted for this exact 2-minute reading
    _last_alerted_device_at = at
    count = devices.get("count")
    if delta > 0:
        headline = f"{delta} more device{'s' if delta != 1 else ''} just joined the network ({count} total)"
    else:
        headline = f"{abs(delta)} device{'s' if abs(delta) != 1 else ''} just left the network ({count} total)"
    return {
        "kind": "household",
        "category": "Household",
        "headline": headline,
        "summary": headline,
        "important": False,
    }
