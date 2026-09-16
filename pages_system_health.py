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
— no new network call anywhere in that chain. dashboard_score.compute()
itself does read a handful of persisted_state keys directly (kiosk
watchdog status, the toast/scenery/Govee error logs) every time this
page is on screen, which is a real Upstash cost this docstring used to
claim didn't exist — audited and left as-is on purpose rather than
adding a cache layer: at ~72 renders/day (5 of every ~85 rotation
minutes) it's on the order of a few hundred commands/day, negligible
against the 500k/month budget, not worth the extra complexity of
throttling something already this cheap. The actual throttled write is
dashboard_score's own history recording, which app.py drives
separately from this page's own render (see app.py's own call to
dashboard_score.record_if_due, right alongside dashboard_health's
per-rerun bookkeeping) so the trend keeps getting sampled even during
the ~75-80 minutes per rotation this page isn't the one showing.
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
    # A real word, not a glyph — every other status pill on this page
    # (and pages_maintenance.py's own _row, the pattern this mirrors)
    # uses a word ("Good", "Active", "Failed"); a bare "!" was a one-off
    # that didn't match either that convention or the app's separate
    # ▲/▼/● glyph vocabulary used elsewhere for directional movement.
    rows = "".join(_row(issue["text"], "Issue", issue["tone"]) for issue in issues[:8])
    return _tile(f"Current Issues ({len(issues)})", rows)


def dashboard_stats() -> str:
    """Public (not underscore-prefixed) — session follow-up: "I liked
    how you had it formatted with the other page where you had all
    three... with their stats in the bar big and visible," reused
    directly by app.py's corner widget so the two surfaces can never
    drift out of formatting sync (the corner wraps this in its own
    small title, same as render() does below)."""
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


def kiosk_stats() -> str:
    """Public — see dashboard_stats' own comment, same reason. No-data
    case keeps the real 3-stat shape (dash per value, same CPU/RAM/TEMP
    labels) instead of collapsing to one generic placeholder — audit
    finding: the old single "NO DATA" stat made this tile a visibly
    different width/shape than its two siblings the moment any one of
    the three tiles lost its data, since dashboard_stats() never did
    that collapse to begin with. All three now degrade the same way."""
    perf = kiosk_hardware.load_perf_stats()
    if perf is None:
        return _stat_row(_stat("—", "CPU"), _stat("—", "RAM"), _stat("—", "TEMP"))
    return _stat_row(
        _stat(f"{perf['cpu_pct']}%", "CPU", "low" if perf["cpu_pct"] >= kiosk_hardware.CPU_HIGH_PCT else "good"),
        _stat(f"{perf['ram_pct']}%", "RAM", "low" if perf["ram_pct"] >= kiosk_hardware.RAM_HIGH_PCT else "good"),
        _stat(f"{perf['temp_c']}°", "TEMP", "low" if perf["temp_c"] >= kiosk_hardware.TEMP_HIGH_C else "good"),
    )


def network_stats() -> str:
    """Public — see dashboard_stats' own comment, same reason. Same
    no-data fix as kiosk_stats() above — keeps the real 2-stat shape."""
    net = kiosk_hardware.load_network_test()
    if net is None:
        return _stat_row(_stat("—", "MBPS"), _stat("—", "MS PING"))
    tone = "low" if net.get("bad") else "good"
    return _stat_row(
        _stat(f"{net.get('mbps')}", "MBPS", tone),
        _stat(f"{net.get('latency_ms')}", "MS PING", tone),
    )


def household_stats() -> str:
    """Public — see dashboard_stats' own comment, same reason. Session
    request: "could we have somewhere that shows how many devices are
    online." Same no-data fix as its siblings (kiosk_stats/network_
    stats) — keeps the real 1-stat shape instead of collapsing to a
    placeholder. No tone threshold the way CPU/RAM/temp have one —
    there's no "bad" device count, just a number."""
    devices = kiosk_hardware.load_device_stats()
    if devices is None:
        return _stat_row(_stat("—", "DEVICES"))
    return _stat_row(_stat(str(devices.get("count", "—")), "DEVICES", "good"))


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
    cols = st.columns(4)
    with cols[0]:
        st.markdown(_tile("Dashboard", dashboard_stats()), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(_tile("Kiosk", kiosk_stats()), unsafe_allow_html=True)
    with cols[2]:
        st.markdown(_tile("Internet", network_stats()), unsafe_allow_html=True)
    with cols[3]:
        st.markdown(_tile("Household", household_stats()), unsafe_allow_html=True)

    st.markdown(_issues_html(result["issues"]), unsafe_allow_html=True)
