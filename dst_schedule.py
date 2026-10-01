"""Daylight Saving Time changes — Ontario follows the same rule as most
of North America: clocks spring forward the 2nd Sunday in March, fall
back the 1st Sunday in November. Session request: "daylight savings
time is good" (one of the "life" badge ideas floated alongside moon
phase and first/last frost) — a real twice-a-year routine disruption
nothing else on the dashboard flags, distinct from the season-start
badge (astronomical, not clock-rule) it sits next to.

Computed directly, same "no API needed, the real-world rule is simple
and fixed" reasoning as td_quarter_schedule.py/payday_schedule.py —
not expected to change without an act of Parliament.
"""

from datetime import date, timedelta

MARCH = 3
NOVEMBER = 11
SUNDAY = 6


def _nth_sunday(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    first_sunday = d + timedelta(days=(SUNDAY - d.weekday()) % 7)
    return first_sunday + timedelta(weeks=n - 1)


def next_change(today: date) -> dict:
    """Next DST transition on/after `today` — {"label", "date",
    "days_until"}. `today` counts as "next" if it's itself the change
    date. "label" is "Spring forward" or "Fall back" — built from this
    year's and next year's own two dates rather than walking forward,
    same reasoning as next_quarter_start's own docstring."""
    candidates = [
        ("Spring forward", _nth_sunday(today.year, MARCH, 2)),
        ("Fall back", _nth_sunday(today.year, NOVEMBER, 1)),
        ("Spring forward", _nth_sunday(today.year + 1, MARCH, 2)),
        ("Fall back", _nth_sunday(today.year + 1, NOVEMBER, 1)),
    ]
    label, candidate = min((c for c in candidates if c[1] >= today), key=lambda c: c[1])
    return {"label": label, "date": candidate, "days_until": (candidate - today).days}
