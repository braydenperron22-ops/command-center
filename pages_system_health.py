"""Rotating "how is the whole system doing" page — session request:
"a page that rotates through, shows all the maintenance stats, for the
kiosk and the dashboard itself, and derives one score on how the
dashboard is doing, and has historical performance, that way I know if
something is falling off." Joins the normal ambient rotation (see
config.PAGES) on the same footing as Today/Weather/Sports/etc.

Distinct from pages_maintenance.py's own "D" hotkey diagnostics grid,
which stays exactly as it is (an exhaustive, tile-per-signal deep dive,
reached on demand) — this page is the glanceable rotation-page version:
one score, a trend so degradation shows up over days instead of only
ever being visible one signal at a time, and a compact set of the
physical-kiosk vitals that don't appear ANYWHERE else in this app
outside the tiny rotating corner status badge (see kiosk_hardware.py).
Reads the same already-tracked state dashboard_score.py rolls up (data_
health, groq_client, dashboard_health, persisted_state, kiosk_hardware)
— no new network call, no new Upstash read beyond dashboard_score's own
throttled history recording, which app.py drives separately from this
page's own render (see app.py's own call to dashboard_score.record_if_
due, right alongside dashboard_health's per-rerun bookkeeping) so the
trend keeps getting sampled even during the ~75-80 minutes per rotation
this page isn't the one showing.
"""

import time

import streamlit as st

import dashboard_health
import dashboard_score
import data_health
import kiosk_hardware
import tiles


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


def _row(label: str, status: str = "", tone: str = "", meta: str = "") -> str:
    """Same shape as pages_maintenance.py's own _row (not imported from
    there — CSS classes are shared app-wide, but per-page HTML-building
    helpers are kept page-local by convention, same as every other page
    in this app). `tone` empty means no pill — for purely informational
    rows (a plain duration, a plain count) pass `meta` instead of
    `status`."""
    pill_html = f'<span class="maint-pill maint-pill-{tone}">{status}</span>' if tone else ""
    meta_html = f'<span class="maint-row-meta">{meta}</span>' if meta else ""
    return f'<div class="maint-row"><span class="maint-row-label">{label}</span>{pill_html}{meta_html}</div>'


def _tile(title: str, rows_html: str) -> str:
    return f'<div class="tile maint-tile"><div class="tile-label compact">{title}</div>{rows_html}</div>'


def _score_hero_html(result: dict, hist: list[dict]) -> str:
    score, grade, tone = result["score"], result["grade"], result["tone"]
    scores = [h["score"] for h in hist]
    if len(scores) >= 2:
        span_days = (hist[-1]["ts"] - hist[0]["ts"]) / 86400
        span_text = f"{span_days:.1f}d" if span_days < 2 else f"{span_days:.0f}d"
        sparkline = tiles.sparkline_svg(
            scores, tone, width=280, height=54,
            color={"good": "#32D74B", "medium": "#FF9F0A", "low": "#FF6961"}.get(tone, "#9BA0AC"),
            stroke_width=2.25,
        )
        history_html = (
            f'<div class="system-health-history">{sparkline}'
            f'<div class="system-health-history-caption">'
            f"low {min(scores):.0f} · avg {sum(scores) / len(scores):.0f} · over the last {span_text}"
            "</div></div>"
        )
    else:
        history_html = '<div class="system-health-history-caption">Building history — check back in a bit.</div>'
    return f"""<div class="tile system-health-hero">
        <div class="system-health-score-row">
            <div class="system-health-score-number system-health-score-{tone}">{score}</div>
            <div class="system-health-score-meta">
                <div class="maint-pill maint-pill-{tone}">{grade}</div>
                <div class="tile-prev">updated {_relative_time(hist[-1]["ts"] if hist else None)}</div>
            </div>
        </div>
        {history_html}
    </div>"""


def _issues_html(issues: list[dict]) -> str:
    if not issues:
        return _tile("Current Issues", _row("All systems healthy", "Good", "good"))
    rows = "".join(_row(issue["text"], "!", issue["tone"]) for issue in issues[:8])
    return _tile(f"Current Issues ({len(issues)})", rows)


def _kiosk_hardware_rows() -> str:
    perf = kiosk_hardware.load_perf_stats()
    if perf is None:
        return _row("Status", "No reports yet", "neutral")
    return (
        _row("CPU", f"{perf['cpu_pct']}%", "low" if perf["cpu_pct"] >= kiosk_hardware.CPU_HIGH_PCT else "good")
        + _row("RAM", f"{perf['ram_pct']}%", "low" if perf["ram_pct"] >= kiosk_hardware.RAM_HIGH_PCT else "good")
        + _row("Temp", f"{perf['temp_c']}°C", "low" if perf["temp_c"] >= kiosk_hardware.TEMP_HIGH_C else "good")
    )


def _kiosk_network_rows() -> str:
    net = kiosk_hardware.load_network_test()
    if net is None:
        return _row("Status", "No reports yet", "neutral")
    tone = "low" if net.get("bad") else "good"
    return (
        _row("Speed", f"{net.get('mbps')} Mbps", tone)
        + _row("Latency", f"{net.get('latency_ms')}ms", tone)
    )


def _dashboard_pulse_rows() -> str:
    last = dashboard_health.last_rerun()
    if last is None:
        return _row("Status", "No data yet", "neutral")
    age = time.time() - last["ts"]
    if age >= 180:
        tone, label = "low", "Stalled"
    elif age >= 90:
        tone, label = "medium", "Slow"
    else:
        tone, label = "good", "Live"
    rows = _row("Status", label, tone, _relative_time(last["ts"])) + _row("Last rerun", meta=f"{last['duration']:.1f}s")
    hist = dashboard_health.history()
    if hist:
        avg = sum(h["duration"] for h in hist) / len(hist)
        rows += _row(f"Avg (last {len(hist)})", meta=f"{avg:.1f}s")
    return rows


def _data_sources_rows() -> str:
    statuses = data_health.all_status()
    fresh = sum(1 for s in statuses if s["status"] == "fresh")
    stale = [s for s in statuses if s["status"] == "stale"]
    tone = "good" if not stale else "low"
    rows = _row("Fresh", f"{fresh}/{len(statuses)}", tone)
    for s in stale[:3]:
        rows += _row(s["label"], f'{s["hours_since"]:.0f}h', "low")
    return rows


def render() -> None:
    st.markdown('<div class="page-title page-title-system-health">System Health</div>', unsafe_allow_html=True)
    result = dashboard_score.compute()
    hist = dashboard_score.history()
    st.markdown(_score_hero_html(result, hist), unsafe_allow_html=True)

    cols = st.columns(4)
    with cols[0]:
        st.markdown(_tile("Kiosk Hardware", _kiosk_hardware_rows()), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(_tile("Kiosk Network", _kiosk_network_rows()), unsafe_allow_html=True)
    with cols[2]:
        st.markdown(_tile("Dashboard Pulse", _dashboard_pulse_rows()), unsafe_allow_html=True)
    with cols[3]:
        st.markdown(_tile("Data Sources", _data_sources_rows()), unsafe_allow_html=True)

    st.markdown(_issues_html(result["issues"]), unsafe_allow_html=True)
