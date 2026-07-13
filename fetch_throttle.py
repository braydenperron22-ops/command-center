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
