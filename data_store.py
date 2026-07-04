"""Read/write helpers for the JSON-backed dashboard state and task list."""
import json
import uuid
from datetime import datetime, timezone

from config import STATE_PATH, TASKS_PATH

EMPTY_STATE = {
    "last_synced": None,
    "weather": None,
    "calendar_events": [],
    "email_highlights": [],
    "alerts": [],
    "commute": None,
}


def load_state() -> dict:
    if not STATE_PATH.exists():
        return dict(EMPTY_STATE)
    with open(STATE_PATH) as f:
        data = json.load(f)
    return {**EMPTY_STATE, **data}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)


def load_tasks() -> list:
    if not TASKS_PATH.exists():
        return []
    with open(TASKS_PATH) as f:
        return json.load(f)


def save_tasks(tasks: list) -> None:
    TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TASKS_PATH, "w") as f:
        json.dump(tasks, f, indent=2, default=str)


def add_task(text: str, due: str | None = None) -> list:
    tasks = load_tasks()
    tasks.append({
        "id": str(uuid.uuid4()),
        "text": text,
        "due": due,
        "done": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    save_tasks(tasks)
    return tasks


def toggle_task(task_id: str) -> list:
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == task_id:
            t["done"] = not t["done"]
    save_tasks(tasks)
    return tasks


def delete_task(task_id: str) -> list:
    tasks = load_tasks()
    tasks = [t for t in tasks if t["id"] != task_id]
    save_tasks(tasks)
    return tasks
