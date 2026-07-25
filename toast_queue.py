"""Process-wide toast/alert queue — shared by news, commute, and sports
alerts (app.py's own _alert_priority already treats these as one merged
queue). Module-level, not st.session_state — session report: "I've
locally seen the same headline pop up... four times tonight." A
session-scoped queue meant each connected browser session (the kiosk
running alongside a phone or a second tab checking on it) got its own
separate copy of the queue, so the exact same already-deduped alert
(news.get_new_alerts is already process-wide, not per-session) could
still play out once per open connection instead of once, period.
"""

_queue: list[dict] = []


def extend(alerts: list[dict]) -> None:
    _queue.extend(alerts)


def current(now_ts: float) -> dict | None:
    """Whatever's at the front of the queue right now, stamping its
    shown_at the first time it's seen. None if the queue's empty."""
    if not _queue:
        return None
    alert = _queue[0]
    if "shown_at" not in alert:
        alert["shown_at"] = now_ts
    return alert


def advance() -> None:
    """Drops the front of the queue — call once its hold time is up."""
    if _queue:
        _queue.pop(0)
