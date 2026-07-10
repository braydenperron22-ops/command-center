"""A short rolling log of commute-time readings, persisted to disk (not
session state) so the trend survives a browser reload or Streamlit
Cloud sleep/wake — same reasoning as market_internals.py's VIXEQ
history file, just a much shorter retention window since "how has the
commute changed in the last half hour" doesn't need months of data.
"""

import json
import os
import time

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "commute_history.json")
RETENTION_SECONDS = 2 * 60 * 60  # comfortably more than any lookback window this app asks for


def _load() -> list[dict]:
    try:
        with open(HISTORY_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save(history: list[dict]) -> None:
    try:
        with open(HISTORY_PATH, "w") as f:
            json.dump(history, f)
    except OSError:
        pass  # a failed save just means the trend has a gap — not worth crashing the page over


def record(duration_seconds: float) -> None:
    """Appends a fresh reading and prunes anything older than
    RETENTION_SECONDS. Call this only when a genuinely new reading was
    fetched (not every rerun) — commute_client hooks it into the
    cached fetch itself, so it naturally only fires once per real
    TomTom call."""
    now = time.time()
    history = _load()
    history.append({"timestamp": now, "duration_seconds": duration_seconds})
    history = [h for h in history if now - h["timestamp"] <= RETENTION_SECONDS]
    _save(history)


def reading_from_before(seconds_ago: float) -> dict | None:
    """The most recent recorded reading from at least `seconds_ago` in
    the past — {"timestamp", "duration_seconds"} — or None if nothing
    that old has been recorded yet (e.g. right after a fresh deploy)."""
    threshold = time.time() - seconds_ago
    candidates = [h for h in _load() if h["timestamp"] <= threshold]
    if not candidates:
        return None
    return max(candidates, key=lambda h: h["timestamp"])
