"""Tiny JSON-file-backed persistence for small pieces of state that
must survive an actual process restart (a redeploy, a Streamlit Cloud
sleep/wake) — not just multiple browser sessions within one running
process, which module-level globals alone already solve. Session
discovery: "I also got my morning brief twice" and a duplicate Brent
oil push — earlier today's fix moved push-notification dedup from
st.session_state (scoped per browser connection) to plain module-level
globals (scoped per process), which fixed duplicate pushes across
reconnects within one running app, but this session's own several
redeploys in a row kept resetting those globals right back to "nothing
sent yet," reproducing the same symptom from a different cause.

One JSON file per key, not one shared file — matches this app's
existing convention of small standalone state files (todo.json,
commute_history.json, groq_client's own .periodic_cache.json) rather
than one shared blob every module reaches into.

Deliberately NOT a general-purpose cache — no TTL, no size limits,
callers own their own value shape and any pruning it needs (e.g. a
bounded recent-headline-hash list). Best-effort: a failed read/write
never raises, same "must never take a page down" rule every other
client in this app already follows.
"""

import json
import os

_STATE_DIR = os.path.dirname(__file__)


def load(key: str, default):
    """Whatever was last saved under `key`, or `default` if nothing has
    ever been saved (first run on this filesystem) or the read fails
    for any reason (corrupt file, permissions, whatever)."""
    path = os.path.join(_STATE_DIR, f".notify_{key}.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save(key: str, value) -> None:
    """Best-effort — a failed write just means this particular update
    doesn't survive the next restart, not a crash. `value` must be
    JSON-serializable as-is; callers own converting anything else
    (dates, sets) to/from a JSON-friendly shape themselves."""
    path = os.path.join(_STATE_DIR, f".notify_{key}.json")
    try:
        with open(path, "w") as f:
            json.dump(value, f)
    except Exception:
        pass
