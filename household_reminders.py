"""Simple day-of-the-week household reminders — Laundry (Wednesday and
Saturday) and Groceries (every Sunday). Session request: "add my
laundry day on Wednesday... groceries on Sunday," later "add Saturday
as a laundry day as well." Same "fixed weekly rule" pattern
waste_schedule.py's own garbage/recycling reminder already established
(see that module's own docstring) — reuses its public next_weekday
helper rather than a second copy of the same date math. No nth-week-of-
month complexity needed here (unlike recycling): every rule below is
just "every [weekday(s)]."
"""

from datetime import date, timedelta

import waste_schedule

WEDNESDAY = 2
SATURDAY = 5
SUNDAY = 6
MONDAY = 0

# Ordered by label for readability only — due_reminders below re-sorts
# by actual days_until, since which one is genuinely "next" changes
# with the day it's asked from. `weekdays` is a list (not a single day)
# so a reminder that fires more than once a week — Laundry, now Wed AND
# Sat — surfaces as ONE entry counting down to whichever of its days is
# genuinely closest, not two separate "Laundry" entries on screen at once.
REMINDERS = [
    {"label": "Laundry", "weekdays": [WEDNESDAY, SATURDAY]},
    {"label": "Groceries", "weekdays": [SUNDAY]},
]

# Session correction: originally shipped as a single ONE_OFF_REMINDERS
# date ("two weeks from now"), but the real request was ongoing —
# "water the P-trap, biweekly on Monday." Same continuous-cycle shape
# waste_schedule.py's own recycling fix already uses (a real anchor
# date + 14-day modulo, immune to month boundaries) rather than a
# fixed "2nd/4th week" rule — this is the exact same class of bug that
# one had. Oct 12, 2026 — the original one-off date — is itself a real
# Monday, so it's kept as the anchor rather than picking a new one.
BIWEEKLY_REMINDERS = [
    {"label": "Water the P-trap", "weekday": MONDAY, "anchor": date(2026, 10, 12)},
]


def _next_biweekly(today: date, weekday: int, anchor: date, interval_days: int = 14) -> date:
    candidate = waste_schedule.next_weekday(today, weekday)
    while (candidate - anchor).days % interval_days != 0:
        candidate += timedelta(days=7)
    return candidate


def due_reminders(today: date) -> list[dict]:
    """{"label", "days_until"} for every reminder above (weekly and
    biweekly alike), soonest first. Plural (a list, not just "the next
    one") — app.py's own hero-badge gating (see the garbage/payday
    badges it already shows) checks each independently against
    "today, morning only" / "tomorrow, evening only," and more than
    one of these can legitimately be in that window on the same day."""
    out = [
        {
            "label": r["label"],
            "days_until": min((waste_schedule.next_weekday(today, w) - today).days for w in r["weekdays"]),
        }
        for r in REMINDERS
    ]
    out.extend(
        {
            "label": r["label"],
            "days_until": (_next_biweekly(today, r["weekday"], r["anchor"]) - today).days,
        }
        for r in BIWEEKLY_REMINDERS
    )
    out.sort(key=lambda r: r["days_until"])
    return out
