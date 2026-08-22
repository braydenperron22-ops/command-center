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


# Live bug, confirmed twice: app.py's toast-check loop calls a whole
# roster of per-source warm_cache()/get_new_alerts() functions
# synchronously, every single rerun, regardless of which page is
# showing — the fix (this session) for page render() itself blocking a
# slow fetch past the 5s st_autorefresh window and corrupting the
# in-flight Streamlit rerun (see golf_client/financial_plumbing_client/
# portfolio_client and friends). That only relocated the risk: ANY ONE
# of those calls going cold (confirmed live: portfolio_client.
# warm_cache alone measured 14s) already blocks the WHOLE loop, and
# by extension whichever page happens to be rendering that rerun, past
# the same 5s window — reconfirmed live as Market Internals rendering
# twice with a second page's content bleeding in underneath it, right
# after a round of fixes added five more such calls to that same loop.
#
# run_bounded is the actual fix: every call in that loop shares one
# wall-clock budget (see app.py's own _toast_budget_start) instead of
# each getting to run for as long as it wants. A call that's still
# running when the shared budget runs out is left to finish on its own
# in the background (it'll still update whatever module-level cache it
# was populating — just too late to matter this rerun; the next rerun,
# 5s later, sees the fresh cache) rather than being allowed to hold up
# the script. At most one real call per `key` runs at a time — a call
# for a key that's already in flight from a prior rerun is skipped
# outright rather than piling up a second overlapping attempt against
# the same upstream API.
_in_flight: set[str] = set()
_in_flight_lock = threading.Lock()


def run_bounded(key: str, fn, budget_start: float, budget_seconds: float = 2.5, default=None):
    """Runs fn() (a warm_cache()/get_new_alerts()-shaped callable, no
    arguments) in a background thread and waits for it — but only for
    whatever's left of `budget_seconds` counted from `budget_start`,
    shared across every call in the same loop, never longer. Returns
    `default` immediately, without even starting fn(), once that
    shared budget is already spent — see this module's own docstring
    for why a per-loop budget instead of a per-call timeout is what
    actually bounds the whole toast-check loop's wall-clock time
    regardless of how many warmers exist."""
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

    thread = threading.Thread(target=_run, daemon=True, name=f"refresh-{key}")
    thread.start()
    thread.join(remaining)
    return result[0]
