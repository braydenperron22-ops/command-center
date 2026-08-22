"""Spaces out real (cache-miss) outbound API calls across the whole app
process, so a cold start — nothing cached yet — issues each external
request one at a time with a breathing gap, instead of every client's
raw fetch firing in the same instant. This is specifically what was
crashing the app: a fresh process has ~20 different external calls
(weather, air quality, EC alerts, calendar, commute, gas price, local
news' several feeds, FRED's many series, yfinance's several tickers,
...) with nothing cached yet to short-circuit any of them, all trying
to fire within the same second or two.

A cache HIT never reaches this: st.cache_data short-circuits before the
wrapped function body (where wait_turn() is called) ever runs, so warm
reruns — the overwhelming majority of them — pay nothing here. Only a
genuine cache-miss fetch waits.

Module-level state, not st.session_state — multiple concurrent viewer
sessions share one server process, and the point is serializing every
real network call app-wide, not just within one session's own cold
start.
"""

import threading
import time

from streamlit.runtime.scriptrunner import add_script_run_ctx

MIN_GAP_SECONDS = 0.5

_lock = threading.Lock()
_last_call_ts = 0.0


def wait_turn() -> None:
    global _last_call_ts
    with _lock:
        remaining = MIN_GAP_SECONDS - (time.time() - _last_call_ts)
        if remaining > 0:
            time.sleep(remaining)
        _last_call_ts = time.time()


# Live bug, seen twice: app.py's toast-check loop calls a roster of
# per-source warm_cache()/get_new_alerts()-shaped functions every single
# rerun, regardless of which page is showing (see each such function's
# own module docstring — Portfolio/Predictions/Market-Internals/Email/
# Conflicts/Weather-Hourly all independently confirmed to block their
# own page's render() past app.py's 5s st_autorefresh window on a cold
# cache — Portfolio alone measured 14s, Conflicts 13s, Predictions
# 14s). Moving those calls into this shared loop only relocates the
# risk unless the loop itself is bounded: any ONE of them going cold
# still blocks the whole loop, and by extension whichever page happens
# to be rendering that rerun, corrupting the in-flight Streamlit rerun
# (screen shows two pages' content blended together — reconfirmed live
# as Market Internals rendering twice right after a first attempt at
# this added five more unbounded calls to the loop).
#
# First attempt at fixing this used a bare threading.Thread with no
# ScriptRunContext attached — Streamlit does NOT propagate a script's
# context to threads you spawn yourself, and code running without one
# can raise (confirmed live: AttributeError right at this call site,
# not reproducible in a local bare-mode test, which doesn't exercise
# Streamlit's real per-session context machinery at all). The fix,
# per Streamlit's own docs: attach the context explicitly with
# add_script_run_ctx(thread) before starting it.
_in_flight: set[str] = set()
_in_flight_lock = threading.Lock()


def run_bounded(key: str, fn, budget_start: float, budget_seconds: float = 2.5, default=None):
    """Runs fn() (a warm_cache()/get_new_alerts()-shaped callable, no
    arguments) in a background thread and waits for it — but only for
    whatever's left of `budget_seconds` counted from `budget_start`,
    shared across every call in the same loop, never longer. Returns
    `default` immediately, without even starting fn(), once that
    shared budget is already spent. A call still running when the
    budget runs out is left to finish on its own in the background (it
    still updates whatever module-level cache it was populating — just
    too late to matter this rerun; the next rerun, 5s later, sees the
    fresh cache) rather than being allowed to hold up the script. At
    most one real call per `key` runs at a time — a call for a key
    that's already in flight from a prior rerun is skipped outright
    rather than piling up a second overlapping attempt against the
    same upstream API.

    Every step here — attaching the ScriptRunContext, starting the
    thread, joining it — is wrapped so this function itself can never
    raise: whatever fn() needs from Streamlit (st.cache_data, st.secrets)
    should work fine with the context attached, but if anything in this
    dispatch mechanism still fails for a reason not anticipated here, a
    dropped refresh is a far smaller problem than crashing the entire
    toast-check loop and taking every other source down with it."""
    remaining = budget_seconds - (time.time() - budget_start)
    if remaining <= 0:
        return default
    with _in_flight_lock:
        if key in _in_flight:
            return default
        _in_flight.add(key)

    result = [default]

    def _run():
        try:
            result[0] = fn()
        except Exception:
            pass
        finally:
            with _in_flight_lock:
                _in_flight.discard(key)

    try:
        thread = threading.Thread(target=_run, daemon=True, name=f"refresh-{key}")
        add_script_run_ctx(thread)
        thread.start()
        thread.join(remaining)
    except Exception:
        with _in_flight_lock:
            _in_flight.discard(key)
        return default
    return result[0]
