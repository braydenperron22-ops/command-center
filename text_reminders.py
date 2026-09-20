"""Fixed-clock-time text reminders — a good-morning text and a
goodnight text to Chloe, each firing twice: a 15-minute heads-up, then
again right at the actual time. Session request: "these should not get
the whole like leave in thing. It's just a reminder" — deliberately NOT
built on commute_reminder's shift/commute machinery (no calendar event,
no travel-time math, no widening milestone ladder): just two plain
clock times, one heads-up stage and one at-time stage, same
append-to-the-queue shape every other toast source in this app uses
(see kiosk_hardware.device_change_toast for the simplest existing
example of that shape).
"""

from datetime import datetime, time as dtime

import ntfy_client
import persisted_state

# Session-specified times. Add more reminders here later the same way —
# each just needs a "key" (for dedup), a "label" (what shows on the
# toast/push), and a "time" (when the actual, non-heads-up stage fires).
REMINDERS = [
    {"key": "chloe_morning", "label": "Send Chloe a good morning text", "time": dtime(8, 0)},
    {"key": "chloe_goodnight", "label": "Send Chloe a goodnight text", "time": dtime(22, 0)},
]
HEADS_UP_MINUTES = 15
# A window, not an exact-minute match — same reasoning every other
# clock-time-gated feature in this app already uses (the outer rerun's
# own ~65-75s cadence can't guarantee landing on the literal minute).
FIRE_WINDOW_MINUTES = 5

# Loaded once at import, saved only on a genuine new fire (see get_new_
# alerts below) — same discipline as commute_reminder's own _shown_state:
# re-loading this from persisted_state on every rerun would be a real,
# ongoing drain on the shared Upstash command budget for a value that
# only this process ever writes.
_STATE_KEY = "chloe_text_reminders_fired"
_state: dict = persisted_state.load(_STATE_KEY, {"date": None, "fired": []})


def get_new_alerts(now: datetime) -> list[dict]:
    """news_queue-shaped alert dicts (see app.py's _gather_new_alerts)
    for whichever reminder stage just became due, if any. Also pushes a
    phone notification for the same stage. Both stages of both
    reminders are tracked per calendar day, so a stage fires exactly
    once per day even across many reruns."""
    global _state
    today = now.date().isoformat()
    if _state["date"] != today:
        _state = {"date": today, "fired": []}

    now_minutes = now.hour * 60 + now.minute
    out: list[dict] = []
    for reminder in REMINDERS:
        target_minutes = reminder["time"].hour * 60 + reminder["time"].minute
        for stage_key, offset_minutes, phrase in (
            ("heads_up", HEADS_UP_MINUTES, f"in {HEADS_UP_MINUTES} minutes"),
            ("now", 0, "now"),
        ):
            fire_at = target_minutes - offset_minutes
            fire_key = f"{reminder['key']}|{stage_key}"
            if fire_key in _state["fired"]:
                continue
            if not (fire_at <= now_minutes < fire_at + FIRE_WINDOW_MINUTES):
                continue

            _state["fired"].append(fire_key)
            persisted_state.save(_STATE_KEY, _state)

            headline = f"{reminder['label']} — {phrase}"
            out.append({
                "kind": "household",
                "category": "Household",
                "headline": headline,
                "summary": headline,
                "important": False,
            })
            try:
                ntfy_client.send(
                    title=reminder["label"],
                    message=phrase.capitalize(),
                    priority="default",
                    tags="speech_balloon",
                )
            except Exception:
                pass
    return out
