"""Live "how is the dashboard actually running" signal — session
request: "do we have a system that shows how the dashboard is running,
when it's being hung up, and when it's running smoothly, like an
actual heart rate monitor." Two separate signals, deliberately not one:

- A FAST pulse (the "heart rate" part): the toast fragment's own 10s
  st.fragment(run_every=...) tick already runs unconditionally,
  regardless of which page is showing (see app.py's own toast-fragment
  docstring) — every tick, it stamps a plain client-visible timestamp
  marker, and a small always-on client-side JS watchdog (same pattern
  already proven for #kiosk-client-heartbeat's own staleness detector,
  see app.py's kiosk-stale-watchdog) compares that against the
  browser's own clock every couple seconds. This is the thing that can
  actually go stale and freeze on screen if the whole process wedges —
  the correct, honest way to show "hung": nothing updates, same as a
  real flatlined monitor.

- A slower duration HISTORY (the "how hard is it working" part): the
  OUTER script's own real end-to-end rerun cost — the exact thing this
  session spent tonight measuring by hand with temporary AUDIT_TIMING
  print statements (see git history for that investigation) — recorded
  permanently now instead of only during an ad-hoc debugging pass, so
  a future slow patch is visible on the Maintenance page without
  needing to re-instrument anything.

Module-level, not persisted_state — this is specifically NOT meant to
survive a restart. A process that just restarted is, definitionally,
no longer hung; the whole point is showing what THIS running process
is doing right now, and Upstash round trips have no business being
anywhere near the mechanism whose entire job is proving the app hasn't
gotten stuck (see fetch_throttle.py's own docstring on why the
heartbeat.beat() file write is a plain local write for the same
reason). Deliberately works identically wherever app.py itself runs —
this Mac's local test copy, or the real Streamlit Cloud kiosk — since
it's plain Python state inside the app, not a separate OS-level script
like watchdog_kiosk.sh."""

import time

MAX_HISTORY = 30

# {"ts": float, "duration": float}, newest last
_rerun_history: list[dict] = []


def record_rerun(duration: float) -> None:
    _rerun_history.append({"ts": time.time(), "duration": duration})
    del _rerun_history[:-MAX_HISTORY]


def history() -> list[dict]:
    return list(_rerun_history)


def last_rerun() -> dict | None:
    return _rerun_history[-1] if _rerun_history else None
