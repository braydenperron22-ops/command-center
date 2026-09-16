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
    `status`. Only used by _issues_html below now — the vitals tiles
    switched to _stat/_stat_row (see their own comment) after "make it
    visible and digestible from a distance... I don't have to read.\""""
    pill_html = f'<span class="maint-pill maint-pill-{tone}">{status}</span>' if tone else ""
    meta_html = f'<span class="maint-row-meta">{meta}</span>' if meta else ""
    return f'<div class="maint-row"><span class="maint-row-label">{label}</span>{pill_html}{meta_html}</div>'


def _tile(title: str, rows_html: str) -> str:
    return f'<div class="tile maint-tile"><div class="tile-label compact">{title}</div>{rows_html}</div>'


def _stat(value: str, label: str, tone: str = "neutral") -> str:
    """One big number + a small caption underneath — session request:
    "make it visible and digestible from a distance... I don't have to
    read." Color alone (good/medium/low) carries whether it's fine,
    same as every dot/pill elsewhere in this app, so a glance doesn't
    need to parse a status word to know something's off."""
    return (
        f'<div class="system-health-stat">'
        f'<div class="system-health-stat-value system-health-stat-{tone}">{value}</div>'
        f'<div class="system-health-stat-label">{label}</div>'
        "</div>"
    )


def _stat_row(*stats: str) -> str:
    return f'<div class="system-health-stat-row">{"".join(stats)}</div>'


def _short_age(seconds: float) -> str:
    """Compact duration for a big-stat value — "12s"/"3m"/"1.4h", no
    "ago" (the tile's own LAST REFRESH label already says that)."""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    return f"{seconds / 3600:.1f}h"


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


def _dashboard_stats() -> str:
    last = dashboard_health.last_rerun()
    if last is None:
        return _stat_row(_stat("—", "LAST REFRESH"))
    age = time.time() - last["ts"]
    if age >= 180:
        tone = "low"
    elif age >= 90:
        tone = "medium"
    else:
        tone = "good"
    return _stat_row(_stat(_short_age(age), "LAST REFRESH", tone))


def _kiosk_stats() -> str:
    perf = kiosk_hardware.load_perf_stats()
    if perf is None:
        return _stat_row(_stat("—", "NO DATA"))
    return _stat_row(
        _stat(f"{perf['cpu_pct']}%", "CPU", "low" if perf["cpu_pct"] >= kiosk_hardware.CPU_HIGH_PCT else "good"),
        _stat(f"{perf['ram_pct']}%", "RAM", "low" if perf["ram_pct"] >= kiosk_hardware.RAM_HIGH_PCT else "good"),
        _stat(f"{perf['temp_c']}°", "TEMP", "low" if perf["temp_c"] >= kiosk_hardware.TEMP_HIGH_C else "good"),
    )


def _network_stats() -> str:
    net = kiosk_hardware.load_network_test()
    if net is None:
        return _stat_row(_stat("—", "NO DATA"))
    tone = "low" if net.get("bad") else "good"
    return _stat_row(
        _stat(f"{net.get('mbps')}", "MBPS", tone),
        _stat(f"{net.get('latency_ms')}", "MS PING", tone),
    )


def render() -> None:
    st.markdown('<div class="page-title page-title-system-health">System Health</div>', unsafe_allow_html=True)
    result = dashboard_score.compute()
    hist = dashboard_score.history()
    st.markdown(_score_hero_html(result, hist), unsafe_allow_html=True)

    # Session request: "make it so like dashboard and then time since
    # last refresh, in a bigger font. And then kiosk CPU RAM temp,
    # internet speed and how fast it is... visible and digestible from
    # a distance." Same order requested, each its own big-stat tile
    # (see _stat's own comment) instead of the small label+pill rows
    # this row used to be. Data Sources' own tile was dropped from here
    # — a real stale source still surfaces below in Current Issues
    # (same as it always did, via dashboard_score's own penalty), a
    # healthy "N/14 fresh" count just wasn't part of what was asked for
    # and this row reads cleaner with 3 tiles, not 4.
    cols = st.columns(3)
    with cols[0]:
        st.markdown(_tile("Dashboard", _dashboard_stats()), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(_tile("Kiosk", _kiosk_stats()), unsafe_allow_html=True)
    with cols[2]:
        st.markdown(_tile("Internet", _network_stats()), unsafe_allow_html=True)

    st.markdown(_issues_html(result["issues"]), unsafe_allow_html=True)
