"""Persists the to-do list to a local JSON file rather than
st.session_state — session state is per-browser-session, so an edit
from your laptop wouldn't show up on the always-on kiosk display, a
separate session entirely. A shared file on disk is visible to every
session hitting this one running app.

Gitignored: this file changes at runtime (via the page's own inputs),
it isn't part of the deployed code baseline.
"""

import json
import os

STORE_PATH = os.path.join(os.path.dirname(__file__), "todo.json")


def load() -> list[dict]:
    """Each item: {"text": str, "done": bool}."""
    try:
        with open(STORE_PATH) as f:
            data = json.load(f)
        items = data.get("items")
        return items if items is not None else []
    except (FileNotFoundError, json.JSONDecodeError, OSError, KeyError):
        return []


def save(items: list[dict]) -> None:
    try:
        with open(STORE_PATH, "w") as f:
            json.dump({"items": items}, f)
    except OSError:
        pass  # a failed save just means the edit doesn't stick — not worth crashing the page over
