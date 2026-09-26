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

from datetime import date

import waste_schedule

WEDNESDAY = 2
SATURDAY = 5
SUNDAY = 6

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


def due_reminders(today: date) -> list[dict]:
    """{"label", "days_until"} for every reminder above, soonest first.
    Plural (a list, not just "the next one") — app.py's own hero-badge
    gating (see the garbage/payday badges it already shows) checks
    each independently against "today, morning only" / "tomorrow,
    evening only," and Laundry and Groceries can both legitimately be
    in that window on the same day."""
    out = [
        {
            "label": r["label"],
            "days_until": min((waste_schedule.next_weekday(today, w) - today).days for w in r["weekdays"]),
        }
        for r in REMINDERS
    ]
    out.sort(key=lambda r: r["days_until"])
    return out
