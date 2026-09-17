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

import html

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


def load_boot_status() -> dict | None:
    """{"at", "clean", "reason"} -- did the kiosk's previous boot end
    with a real shutdown/reboot sequence, or did it just stop (a crash)?
    Only actually re-evaluated on the kiosk once per boot, not every
    2-minute cycle — see the writer script's own comment."""
    combined = _load_combined()
    if combined is None:
        return None
    boot = dict(combined.get("boot") or {})
    boot.setdefault("at", combined.get("at"))
    return boot or None


def load_smart_status() -> dict | None:
    """{"reallocated_blocks", "reallocated_events", "uncorrectable",
    "crc_errors", "power_on_hours", "wear_value", "wear_thresh", "bad"}
    -- the kiosk's own SSD SMART attributes, re-checked on the kiosk
    roughly once an hour (see the writer script's own comment — wear/
    error counts don't change meaningfully minute to minute)."""
    combined = _load_combined()
    if combined is None:
        return None
    smart = dict(combined.get("smart") or {})
    smart.setdefault("at", combined.get("at"))
    return smart or None


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

# Session report: "set the alert for a threshold that actually will
# impair the ability for the kiosk to load. It's just a fucking web
# page. three point six Mbps is enough." Same move as TEMP_HIGH_C/
# CPU_HIGH_PCT/RAM_HIGH_PCT above: this used to just trust the writer
# script's own opaque "bad" flag for network, whatever threshold that
# script happens to use internally — not tracked in this repo, and
# evidently tuned for a heavier real use case than "reload a mostly-
# cached Streamlit page every ~70s." A real, locally-owned number
# instead, set well below the user's own stated "enough" reading so
# normal fluctuation around it doesn't flap the alert.
MBPS_LOW_THRESHOLD = 2.0

_TEMP_ADVICE = "clean the fans/vents"
_CPU_ADVICE = "check for a runaway process"
_RAM_ADVICE = "a restart would help"


def network_is_slow(net: dict | None) -> bool:
    """True only when the real Mbps reading is below MBPS_LOW_
    THRESHOLD — the one shared judgment _concerns(), dashboard_score.py,
    and pages_system_health.py's network_stats() all call instead of
    each separately checking the writer's own net["bad"] flag, so "is
    the network actually a problem" can never drift into disagreeing
    with itself across the headline, the score, and the page's own
    color coding."""
    if net is None:
        return False
    mbps = net.get("mbps")
    return mbps is not None and mbps < MBPS_LOW_THRESHOLD


def _concerns(perf: dict, boot: dict | None, smart: dict | None, net: dict | None) -> list[tuple[str, str]]:
    """[(short_reading, advice)] for every metric currently over its
    own threshold, worst-first — empty once the box is genuinely fine.
    Independent per-field checks (not the writer's own single "bad"
    flag) so more than one real issue at once still gets its own
    separate mention instead of collapsing into one vague warning.

    Session request: "make sure they're actionable and I know exactly
    what's going on and how to fix it" — crash detection and drive
    health join the same worst-first list, same (reading, concrete-
    advice) shape as temp/CPU/RAM, so anything genuinely worth knowing
    about the physical kiosk surfaces here, not just CPU/RAM/temp.

    Session report: "shouldn't I have a red headline? For my internet,
    it's currently reading 1.6 Mbps." Real gap, found live — network
    was already reaching dashboard_score.py's own score but never this
    function, so a genuinely bad reading dinged the score silently
    with no headline, the only one of the 5 real signals this module
    tracks that didn't. Follow-up session report: the writer script's
    own "bad" judgment this originally trusted directly was too
    aggressive for what a kiosk actually needs (see MBPS_LOW_THRESHOLD's
    own comment) — network_is_slow() above replaced it with a real,
    locally-owned threshold instead, same "don't trust an opaque
    external flag, judge the real number" move temp/CPU/RAM already
    made above."""
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
    if network_is_slow(net):
        out.append((f"{net.get('mbps')} Mbps network", "check the kiosk's WiFi signal/router"))
    if smart is not None and smart.get("bad"):
        out.append(("drive wear/errors", "back up your data soon, drive may be failing"))
    if boot is not None and boot.get("clean") is False:
        out.append(("crashed on last boot", "check the Maintenance page's Kiosk Last Boot tile"))
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
    concerns = _concerns(perf, load_boot_status(), load_smart_status(), load_network_test())
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
    """Session follow-up: "can you make it so that it shows what device
    went offline? And if it doesn't know what device went offline,
    then just say a device has left." devices["joined"]/["left"] are
    OPTIONAL lists of real device names — the writer script doesn't
    send these yet as of this comment (it only reports count/delta),
    so every real toast today still falls through to the generic
    phrasing below until that script is extended to actually capture
    hostnames/names during its own network scan (outside this repo,
    can't be done from here — see this module's own docstring). Once
    it does, this needs no further changes: a present, non-empty list
    is used automatically; an absent/empty one still falls back
    exactly as before, so a cycle where the writer only recognizes
    SOME of the devices that changed degrades gracefully to the
    generic count instead of a partial, confusing name list."""
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
        joined = [n for n in (devices.get("joined") or []) if n]
        if joined:
            headline = f"{', '.join(joined)} joined the network ({count} total)"
        else:
            headline = f"{delta} more device{'s' if delta != 1 else ''} just joined the network ({count} total)"
    else:
        left = [n for n in (devices.get("left") or []) if n]
        if left:
            headline = f"{', '.join(left)} left the network ({count} total)"
        elif abs(delta) == 1:
            headline = f"A device has left the network ({count} total)"
        else:
            headline = f"{abs(delta)} devices just left the network ({count} total)"
    return {
        "kind": "household",
        "category": "Household",
        "headline": headline,
        "summary": headline,
        "important": False,
    }


def render_alert_bar(alert: dict) -> None:
    """Bottom-strip toast, own dedicated renderer — session report: this
    was falling through to news.render_alert_bar's binary BREAKING
    NEWS/MARKET NEWS label choice (the fallback for any kind without
    its own renderer, see app.py's own dispatch), showing the
    genuinely wrong "MARKET NEWS" label for a device join/leave.
    Reuses that same function's calm, neutral bar styling (.news-alert-
    bar-market — visually exactly right for this, not urgent) with its
    own label instead, same shape as email_client.render_alert_bar."""
    headline_text = html.escape(alert.get("headline", ""))
    st.markdown(
        f'<div class="news-alert-bar-market">'
        f'<span class="news-breaking-label">HOUSEHOLD</span>'
        f'<span class="news-alert-headline">{headline_text}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
