"""Physical kiosk-box hardware health — CPU/RAM/temp readings pushed to
Upstash by a script that runs directly on the kiosk hardware itself
(outside this repo entirely, not tracked here — confirmed by grepping
for it; app.py's own bottom-right corner tile is the read side of that
same handoff, see its "Kiosk: ..." row and kiosk_perf_stats key).

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

import persisted_state

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
    perf = persisted_state.load("kiosk_perf_stats", None)
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
