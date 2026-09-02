"""Diagnostics/status page — session request: "add a maintenance tab...
by pressing D... that shows stats on how everything is updating, our
models their state and when their last answer was, dashboard
performance metrics and anything you can think of... all colour coded
to show how the board is performing." Not part of the normal PAGES
rotation (see config.py) — reached only via the D hotkey (app.py) or
an explicit mobile-nav link, same "hidden unless asked for" treatment
as the jumbotron's own J hotkey.

Every number here is read from state other modules already maintain
for their own real work (AI status, token budgets, data-source health,
cloud-cache reachability) — nothing on this page triggers a new API
call or a new Upstash round trip of its own. That matters specifically
for persisted_state's Upstash backing: this page could plausibly be
left open on a phone or the kiosk itself for a long stretch, and with
the app rerunning every 5s, anything that made a live network call
inside render() would reintroduce the exact per-rerun cost problem
this session already found and fixed elsewhere (see groq_client.py's
_outage_episode and its siblings) — "be command conscious" applies
here too, not just to the things it was first said about.
"""

import resource
import sys
import time
from datetime import date

import streamlit as st

import cpp_payment_dates
import dashboard_health
import data_health
import gemini_client
import groq_client
import persisted_state

_STARTED_AT = time.time()


def _relative_time(ts: float | None) -> str:
    if ts is None:
        return "never yet"
    elapsed = time.time() - ts
    if elapsed < 5:
        return "just now"
    if elapsed < 3600:
        return f"{int(elapsed // 60)}m ago"
    if elapsed < 86400:
        return f"{elapsed / 3600:.1f}h ago"
    return f"{elapsed / 86400:.1f}d ago"


def _format_duration(seconds: float) -> str:
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _row(label: str, status: str = "", tone: str = "", meta: str = "") -> str:
    """A label + optional colored status pill + optional right-aligned
    meta text. `tone` empty means "no pill" — for purely informational
    rows (uptime, memory) that aren't really a health state, a colored
    pill just for the sake of one reads as a status claim that isn't
    actually there."""
    pill_html = f'<span class="maint-pill maint-pill-{tone}">{status}</span>' if tone else ""
    meta_html = f'<span class="maint-row-meta">{meta}</span>' if meta else ""
    return f'<div class="maint-row"><span class="maint-row-label">{label}</span>{pill_html}{meta_html}</div>'


def _tile(title: str, rows_html: str) -> str:
    return f'<div class="tile maint-tile"><div class="tile-label compact">{title}</div>{rows_html}</div>'


def _ai_models_rows() -> str:
    return "".join(
        _row(m["label"], m["status"], m["tone"], _relative_time(m["at"])) for m in groq_client.ai_status_by_model()
    )


def _ai_features_rows() -> str:
    groq_cache = groq_client.periodic_cache_status()
    gemini_cache = gemini_client.periodic_cache_status()
    features = [
        ("Conflicts Overview", groq_cache.get("conflicts_overview")),
        ("Morning Brief", gemini_cache.get("morning_briefing_sentence")),
    ]
    return "".join(
        _row(label, "Generated" if at else "Never yet", "good" if at else "neutral", _relative_time(at))
        for label, at in features
    )


# account identifier -> display label — plain .title() renders the
# "chatgpt" account (see groq_client._MODEL_ACCOUNT) as "Chatgpt", not
# the name it's actually known by.
_ACCOUNT_DISPLAY_NAMES = {"chatgpt": "ChatGPT"}


def _budget_rows() -> str:
    rows = []
    for b in groq_client.account_budgets():
        pct_used = 100.0 - b["remaining_pct"]
        tone = "good" if b["remaining_pct"] >= 50 else "medium" if b["remaining_pct"] >= 20 else "low"
        label = _ACCOUNT_DISPLAY_NAMES.get(b["account"], b["account"].title())
        rows.append(
            f'<div class="maint-row"><span class="maint-row-label">{label}</span>'
            f'<span class="maint-row-meta">{b["used"]:,}/{b["budget"]:,} (24h)</span></div>'
            f'<div class="severity-track"><div class="severity-fill severity-fill-{tone}" '
            f'style="left:0;width:{pct_used:.0f}%;"></div></div>'
        )
    return "".join(rows)


def _data_source_rows() -> str:
    tone_map = {"fresh": "good", "stale": "low", "unknown": "neutral"}
    rows = []
    for s in data_health.all_status():
        meta = "never yet" if s["hours_since"] is None else f'{s["hours_since"]:.1f}h ago (limit {s["threshold_hours"]:.0f}h)'
        rows.append(_row(s["label"], s["status"].title(), tone_map[s["status"]], meta))
    return "".join(rows)


def _cloud_cache_rows() -> str:
    status = persisted_state.upstash_status()
    if not status["configured"]:
        return _row("Upstash", "Not configured", "neutral", "using local file only")
    if status["last_ok"] is None:
        return _row("Upstash", "Configured", "neutral", "not attempted yet")
    tone = "good" if status["last_ok"] else "low"
    text = "Reachable" if status["last_ok"] else "Unreachable"
    return _row("Upstash", text, tone, _relative_time(status["last_at"]))


def _toast_health_rows() -> str:
    """Session report: "the GoVi lights are going red... but the toast
    is not there." app.py now catches a toast-render failure instead of
    letting it vanish inside a bare except, and records it here — the
    next time this happens, this tile shows exactly what broke instead
    of leaving it a mystery."""
    err = persisted_state.load("toast_render_error", None)
    if not err:
        return _row("Last render failure", "None recorded", "good")
    return (
        _row(f"{err['kind']} alert", "Failed", "low", _relative_time(err["at"]))
        + f'<div class="maint-row-meta">{err["error"]}</div>'
        + f'<div class="maint-row-meta">{(err.get("headline") or "")[:80]}</div>'
    )


def _govee_health_rows() -> str:
    """Session report: "the smart plug didn't turn on automatically this
    morning like it was supposed to." Same shape as _toast_health_rows
    above, for the same reason — govee_client.py now records a control
    failure (device offline, an expired key, a bad response from Govee
    itself) instead of just returning False and vanishing, so the next
    time this happens, this tile shows what actually broke instead of
    it being a silent mystery again."""
    err = persisted_state.load("govee_control_error", None)
    if not err:
        return _row("Last control failure", "None recorded", "good")
    return (
        _row(f"{err['device']} {err['capability']}", "Failed", "low", _relative_time(err["at"]))
        + f'<div class="maint-row-meta">{err["error"]}</div>'
    )


def _system_rows() -> str:
    rows = [_row("Process uptime", meta=_format_duration(time.time() - _STARTED_AT))]
    try:
        raw_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # ru_maxrss's units differ by platform: KB on Linux (the actual
        # deploy target — Streamlit Community Cloud), bytes on macOS
        # (confirmed live while testing this locally: without this
        # branch, the same raw value read as "56192 MB" instead of the
        # real ~55 MB).
        peak_mb = raw_maxrss / 1024 / 1024 if sys.platform == "darwin" else raw_maxrss / 1024
        rows.append(_row("Peak memory", meta=f"{peak_mb:.0f} MB"))
    except Exception:
        pass
    paused = groq_client.ai_pulls_paused()
    rows.append(_row("AI calls", "Paused (overnight)" if paused else "Active", "neutral" if paused else "good"))
    episode = groq_client.outage_episode()
    if episode["since"] is not None:
        rows.append(_row("AI outage", "Notified" if episode["notified"] else "In progress", "low", _relative_time(episode["since"])))
    else:
        rows.append(_row("AI outage", "None", "good"))
    # Session follow-up: "is there a way to automatically update the
    # cpp/oas schedule" — real answer was no (see cpp_payment_dates.py's
    # own docstring: no usable government API, and a real fetch to the
    # one HTML calendar page came back 403). User's own call was a
    # manual annual update instead of a fragile scraper — this is the
    # other half of that choice: a real, visible warning here once the
    # hardcoded list is actually running low, so the update doesn't
    # depend on someone noticing the hero badge quietly stopped
    # appearing on its own.
    coverage = cpp_payment_dates.coverage_status(date.today())
    if coverage["days_remaining"] < cpp_payment_dates.COVERAGE_WARNING_DAYS:
        rows.append(_row(
            "CPP/OAS schedule", "Needs update", "low",
            f'covers through {coverage["last_date"].strftime("%b %Y")}',
        ))
    else:
        rows.append(_row(
            "CPP/OAS schedule", "Current", "good",
            f'covers through {coverage["last_date"].strftime("%b %Y")}',
        ))
    return "".join(rows)


def _pulse_bar_tone(duration: float) -> str:
    if duration >= 40:
        return "low"
    if duration >= 15:
        return "medium"
    return "good"


def _pulse_rows() -> str:
    """Session request: "a system that shows how the dashboard is
    running... when it's being hung up, and when it's running
    smoothly, like an actual heart rate monitor." See dashboard_health.py
    for the two signals this reads — a live status pill also sits
    outside this page, in the always-on corner (app.py's own
    dashboard-pulse-dot/-text, watched client-side); this tile is the
    fuller diagnostic history: how long each of the last MAX_HISTORY
    full outer reruns actually took, the same real number this session
    spent tonight measuring by hand with temporary print statements."""
    last = dashboard_health.last_rerun()
    if last is None:
        return _row("Status", "No data yet", "neutral", "process just started")
    age = time.time() - last["ts"]
    if age >= 180:
        tone, label = "low", "Stalled"
    elif age >= 90:
        tone, label = "medium", "Slow"
    else:
        tone, label = "good", "Live"
    rows = [
        _row("Status", label, tone, _relative_time(last["ts"])),
        _row("Last full rerun", meta=f"{last['duration']:.1f}s"),
    ]
    hist = dashboard_health.history()
    if hist:
        durations = [h["duration"] for h in hist]
        rows.append(_row(f"Avg (last {len(hist)})", meta=f"{sum(durations) / len(durations):.1f}s"))
        max_dur = max(durations)
        bars_html = "".join(
            f'<div class="maint-pulse-bar maint-pulse-bar-{_pulse_bar_tone(d)}" '
            f'style="height:{max(3, (d / max_dur) * 32):.0f}px" title="{d:.1f}s"></div>'
            for d in durations
        )
        rows.append(f'<div class="maint-pulse-sparkline">{bars_html}</div>')
    return "".join(rows)


def render() -> None:
    st.markdown('<div class="page-title page-title-maintenance">Maintenance</div>', unsafe_allow_html=True)
    row1 = st.columns(3)
    with row1[0]:
        st.markdown(_tile("AI Models", _ai_models_rows()), unsafe_allow_html=True)
    with row1[1]:
        st.markdown(_tile("AI Features", _ai_features_rows()), unsafe_allow_html=True)
    with row1[2]:
        st.markdown(_tile("Groq Token Budgets", _budget_rows()), unsafe_allow_html=True)
    row2 = st.columns(3)
    with row2[0]:
        st.markdown(_tile("Data Sources", _data_source_rows()), unsafe_allow_html=True)
    with row2[1]:
        st.markdown(_tile("System", _system_rows()), unsafe_allow_html=True)
    with row2[2]:
        st.markdown(_tile("Cloud Cache", _cloud_cache_rows()), unsafe_allow_html=True)
    row3 = st.columns(3)
    with row3[0]:
        st.markdown(_tile("Toast Alerts", _toast_health_rows()), unsafe_allow_html=True)
    with row3[1]:
        st.markdown(_tile("Govee", _govee_health_rows()), unsafe_allow_html=True)
    with row3[2]:
        st.markdown(_tile("Dashboard Pulse", _pulse_rows()), unsafe_allow_html=True)
