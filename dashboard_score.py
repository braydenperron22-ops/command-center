"""One composite "how is the whole system doing" number, plus a
persisted history of it over time — session request: "a page that
rotates through, shows all the maintenance stats... derives one score
on how the dashboard is doing, and has historical performance, that
way I know if something is falling off."

pages_maintenance.py (the "D" hotkey diagnostics grid) already surfaces
every individual signal this reads — this module doesn't duplicate any
of that tracking, it just rolls the same already-maintained state up
into one number: data source staleness (data_health), AI model/budget/
outage health (groq_client), dashboard rerun health (dashboard_health),
cloud-cache reachability (persisted_state), and the physical kiosk box
itself (kiosk_hardware — CPU/RAM/temp/network, which pages_maintenance
doesn't even show, only the always-on corner status bar does). No new
network call anywhere in compute() — same "be command conscious"
discipline pages_maintenance.py's own docstring establishes, since this
also needs to be safe to compute every single outer rerun.

Scoring is a flat 100-point budget with a deduction per real issue
found, clamped to [0, 100] — deliberately simple and legible (every
deduction below has one line saying what it's for) over something
"smarter" a future degradation would be harder to reason about.
Thresholds reuse whatever threshold the underlying module already
defines as "not fine" (kiosk_hardware.TEMP_HIGH_C, groq_client's own
budget tone cutoffs, dashboard_health's own stalled/slow cutoffs from
pages_maintenance._pulse_bar_tone) rather than inventing new ones, so
this never disagrees with what the Maintenance page itself already
calls a problem.

History is recorded at most once every RECORD_INTERVAL_SECONDS,
regardless of which page happens to be showing — app.py calls
record_if_due() unconditionally, right alongside dashboard_health's own
per-rerun bookkeeping, specifically so the trend keeps getting sampled
even while the rotation is sitting on a completely different page for
hours. The "due" check itself is a plain in-process module global, not
a persisted_state.load() on every rerun — this module is a normal
`import`ed module (unlike app.py itself), so that global genuinely
survives across reruns via Python's own sys.modules cache, the same
reasoning persisted_state.save_throttled's own docstring lays out in
detail after an earlier bug in this app where a dedup global was
mistakenly placed directly in app.py instead."""

import time
from datetime import date

import cpp_payment_dates
import dashboard_health
import data_health
import groq_client
import kiosk_hardware
import persisted_state

HISTORY_KEY = "dashboard_score_history"
RECORD_INTERVAL_SECONDS = 30 * 60  # ~10 days of trend at MAX_HISTORY_POINTS below
MAX_HISTORY_POINTS = 480

# Recent-failure tiles (app.py's toast/scenery render errors, Govee
# control errors) only count against the score for a day — an error
# from last week shouldn't permanently keep the score down once
# whatever it was has long since been resolved or forgotten; that's
# what the *history* line is for, not an ongoing deduction here.
_RECENT_FAILURE_WINDOW_SECONDS = 24 * 60 * 60
_RECENT_FAILURE_KEYS = [
    ("toast_render_error", "Toast render"),
    ("scenery_render_error", "Background render"),
    ("govee_control_error", "Govee control"),
]


def _deduct(issues: list[dict], score: float, points: float, text: str, tone: str = "low") -> float:
    issues.append({"text": text, "tone": tone})
    return score - points


def compute() -> dict:
    """{"score", "grade", "tone", "issues": [{"text", "tone"}, ...]} —
    issues is empty exactly when score == 100 (nothing currently
    deducting)."""
    score = 100.0
    issues: list[dict] = []

    stale = data_health.check()
    # Capped rather than one deduction per source without limit — a
    # single shared root cause (Upstash itself down, say) can plausibly
    # stale out several sources at once, and letting that alone drag
    # the score to 0 would hide whether anything ELSE is also wrong.
    for s in stale[:5]:
        score = _deduct(issues, score, 5, f"{s['label']} stale ({s['hours_stale']:.0f}h)")

    episode = groq_client.outage_episode()
    if episode["since"] is not None:
        score = _deduct(issues, score, 15, "AI outage in progress")

    for b in groq_client.account_budgets():
        if b["remaining_pct"] < 20:
            score = _deduct(issues, score, 5, f"{b['account'].title()} token budget low ({b['remaining_pct']:.0f}% left)", "low")
        elif b["remaining_pct"] < 50:
            score = _deduct(issues, score, 2, f"{b['account'].title()} token budget getting used ({b['remaining_pct']:.0f}% left)", "medium")

    for m in groq_client.ai_status_by_model():
        if m["tone"] == "low":
            score = _deduct(issues, score, 4, f"{m['label']} rate limited")

    last = dashboard_health.last_rerun()
    if last is not None:
        age = time.time() - last["ts"]
        if age >= 180:
            score = _deduct(issues, score, 20, "Dashboard rerun stalled")
        elif age >= 90:
            score = _deduct(issues, score, 8, "Dashboard rerun running slow")
        hist = dashboard_health.history()
        if hist:
            avg = sum(h["duration"] for h in hist) / len(hist)
            if avg >= 40:
                score = _deduct(issues, score, 10, f"Reruns averaging {avg:.0f}s")

    cache_status = persisted_state.upstash_status()
    if cache_status["configured"] and cache_status["last_ok"] is False:
        score = _deduct(issues, score, 10, "Cloud cache (Upstash) unreachable")

    perf = kiosk_hardware.load_perf_stats()
    if perf is not None:
        temp = perf.get("temp_c")
        if temp is not None and temp >= kiosk_hardware.TEMP_HIGH_C:
            score = _deduct(issues, score, 8, f"Kiosk running hot ({temp}°C)")
        cpu = perf.get("cpu_pct")
        if cpu is not None and cpu >= kiosk_hardware.CPU_HIGH_PCT:
            score = _deduct(issues, score, 5, f"Kiosk CPU pegged ({cpu}%)")
        ram = perf.get("ram_pct")
        if ram is not None and ram >= kiosk_hardware.RAM_HIGH_PCT:
            score = _deduct(issues, score, 5, f"Kiosk RAM pegged ({ram}%)")

    net = kiosk_hardware.load_network_test()
    if net is not None and net.get("bad"):
        score = _deduct(issues, score, 6, f"Kiosk network slow ({net.get('mbps')} Mbps, {net.get('latency_ms')}ms)")

    watchdog = persisted_state.load("kiosk_watchdog_status", None)
    if watchdog is not None:
        at = watchdog.get("at")
        age = time.time() - at if at else None
        if age is not None and age > 600:
            score = _deduct(issues, score, 5, "Kiosk watchdog not reporting")
        else:
            for issue in (watchdog.get("issues") or [])[:3]:
                score = _deduct(issues, score, 4, f"Kiosk: {issue}", "medium")

    now_ts = time.time()
    for key, label in _RECENT_FAILURE_KEYS:
        err = persisted_state.load(key, None)
        if err and (now_ts - err.get("at", 0)) < _RECENT_FAILURE_WINDOW_SECONDS:
            score = _deduct(issues, score, 4, f"{label} failed recently", "medium")

    coverage = cpp_payment_dates.coverage_status(date.today())
    if coverage["days_remaining"] < cpp_payment_dates.COVERAGE_WARNING_DAYS:
        score = _deduct(issues, score, 3, "CPP/OAS schedule needs updating", "medium")

    score = max(0, min(100, round(score)))
    if score >= 90:
        grade, tone = "Healthy", "good"
    elif score >= 70:
        grade, tone = "Minor issues", "medium"
    elif score >= 40:
        grade, tone = "Degraded", "low"
    else:
        grade, tone = "Critical", "low"
    return {"score": score, "grade": grade, "tone": tone, "issues": issues}


# See this module's own docstring for why this is a plain module
# global rather than a persisted_state.load() on every rerun.
_last_recorded_ts: float | None = None


def record_if_due(now_ts: float | None = None) -> None:
    """Call unconditionally, once per outer rerun, regardless of which
    page is showing. A no-op the overwhelming majority of the time (a
    plain float comparison) — only actually loads/computes/saves once
    every RECORD_INTERVAL_SECONDS."""
    global _last_recorded_ts
    now_ts = now_ts if now_ts is not None else time.time()
    if _last_recorded_ts is not None and (now_ts - _last_recorded_ts) < RECORD_INTERVAL_SECONDS:
        return
    hist = persisted_state.load(HISTORY_KEY, [])
    hist.append({"ts": now_ts, "score": compute()["score"]})
    del hist[:-MAX_HISTORY_POINTS]
    persisted_state.save(HISTORY_KEY, hist)
    _last_recorded_ts = now_ts


def history() -> list[dict]:
    """{"ts", "score"} points, oldest first — a fresh process before
    its first RECORD_INTERVAL_SECONDS tick, or before persisted_state
    has ever been written to at all, returns an empty list rather than
    guessing at a baseline."""
    return persisted_state.load(HISTORY_KEY, [])
