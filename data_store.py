"""Read/write helpers for the JSON-backed dashboard state."""
import json

from config import STATE_PATH

EMPTY_STATE = {
    "last_synced": None,
    "weather": None,
    "calendar_events": [],
    "email_highlights": [],
    "alerts": [],
    "commute": None,
    "indices": [],
}


def load_state() -> dict:
    if not STATE_PATH.exists():
        return dict(EMPTY_STATE)
    try:
        with open(STATE_PATH) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        # A partially-written or corrupted file shouldn't crash the dashboard —
        # fall back to empty state until the next sync overwrites it cleanly.
        return dict(EMPTY_STATE)
    return {**EMPTY_STATE, **data}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)
