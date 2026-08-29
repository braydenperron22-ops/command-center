"""Liveness signal for the external watchdog (watchdog_kiosk.sh) —
launchd's own KeepAlive only restarts com.brayden.commandcenter if the
PROCESS actually exits; it has no way to notice a process that's still
alive but wedged (a genuine deadlock, or this machine's own real
memory pressure — confirmed live, 8GB total RAM with ~1.9GB already
swapped out even at idle, real Swapins/Swapouts in the millions —
which can stall the interpreter for extended stretches without ever
killing it). Session report: "it only freezes sometimes but the freeze
is persistent through refreshes" — a symptom a browser refresh can
never fix on its own, since the browser is just asking the same stuck
server for the same thing again.

beat() is called once, as the literal last statement in app.py, after
every page/side-effect block for that rerun has already finished. A
script that's stuck partway through a rerun never reaches it, so a
stale file here is a real signal that a rerun genuinely hasn't
completed — not a guess.

Deliberately a plain local file write, not persisted_state.save() —
this has to stay cheap and dependency-free (no Upstash round trip, no
chance of blocking on a degraded cloud store) so the heartbeat itself
can never become the thing that hangs.
"""

import os
import time

HEARTBEAT_PATH = os.path.join(os.path.dirname(__file__), "data", "heartbeat.txt")


def beat() -> None:
    try:
        os.makedirs(os.path.dirname(HEARTBEAT_PATH), exist_ok=True)
        with open(HEARTBEAT_PATH, "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass
