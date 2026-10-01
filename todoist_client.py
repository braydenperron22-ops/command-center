"""Todoist read-only task list — session request: "I found a second use
for Todoist... a wireless way for me to make a to-do list and it gets
shipped to the dashboard... can we make it so the dashboard can
actually read that stuff." Explicitly read-only (the request was "read
what the thing is," not create/edit) — tasks still get added from the
Todoist app itself, same shape as pages_shopping.py's own "write from
your phone, read on the kiosk" idea, just with Todoist as the writer
instead of this app's own text box.

A personal API token (Settings -> Integrations -> Developer in the
Todoist app) is all auth needs — no OAuth, confirmed live against the
real API before any of this was written (see the project_id/task
field names below, which came from a real GET /api/v1/tasks response,
not docs alone — the docs page's own task-schema section didn't render
through automated fetching, every field name here was confirmed live).

"idk how to differentiate them [groceries vs to-do]" — two real
Todoist projects (Groceries, To-Do) were created via the API for this
specifically; TODOIST_GROCERIES_PROJECT_ID/TODOIST_TODO_PROJECT_ID
point at them. Adding a task to either list, from any device with the
Todoist app, is what "ships to the dashboard" from here on.
"""

import requests
import streamlit as st

import fetch_throttle

API_BASE = "https://api.todoist.com/api/v1"
CACHE_TTL_SECONDS = 5 * 60

_last_good_tasks: dict[str, list[dict]] = {}


def _configured() -> bool:
    return bool(st.secrets.get("TODOIST_API_TOKEN"))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_tasks_raw(project_id: str) -> list[dict]:
    token = st.secrets.get("TODOIST_API_TOKEN")
    fetch_throttle.wait_turn()
    tasks: list[dict] = []
    cursor = None
    # Cursor-based pagination (confirmed live: GET /api/v1/tasks
    # returns {"results": [...], "next_cursor": ...|null}) — a real
    # personal list is very unlikely to need a second page, but a
    # single plain request would silently truncate if it ever did.
    for _ in range(10):  # hard cap — never loop forever on a weird API response
        params = {"project_id": project_id}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(
            f"{API_BASE}/tasks", headers={"Authorization": f"Bearer {token}"}, params=params, timeout=10
        )
        resp.raise_for_status()
        payload = resp.json()
        tasks.extend(payload.get("results") or [])
        cursor = payload.get("next_cursor")
        if not cursor:
            break
    return tasks


def fetch_tasks(project_id: str) -> list[dict]:
    """Real Todoist fields only, not the full raw response — {"id",
    "content", "description", "priority" (1-4, 4=highest, confirmed
    live), "due" (None or a real due object), "checked"}. Active tasks
    only; Todoist's own /tasks endpoint already excludes completed
    ones by default (confirmed live), so no checked==True filtering
    needed here."""
    if not _configured():
        return []
    try:
        raw = _fetch_tasks_raw(project_id)
    except Exception:
        return _last_good_tasks.get(project_id, [])
    tasks = [
        {
            "id": t["id"],
            "content": t["content"],
            "description": t.get("description") or "",
            "priority": t.get("priority", 1),
            "due": t.get("due"),
            "checked": t.get("checked", False),
        }
        for t in raw
        if not t.get("is_deleted") and not t.get("checked")
    ]
    _last_good_tasks[project_id] = tasks
    return tasks


def groceries() -> list[dict]:
    project_id = st.secrets.get("TODOIST_GROCERIES_PROJECT_ID")
    return fetch_tasks(project_id) if project_id else []


def todo() -> list[dict]:
    project_id = st.secrets.get("TODOIST_TODO_PROJECT_ID")
    return fetch_tasks(project_id) if project_id else []
