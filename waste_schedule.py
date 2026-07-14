"""North Bay garbage/recycling pickup schedule — a fixed weekly rule
(garbage every Monday, recycling the 2nd and 4th Wednesday of each
month), not sourced from a live feed since the city's schedule is
exactly this simple recurring rule. "Typically" per the person who
gave me this rule — a stat holiday can shift a real pickup day by
one, which this doesn't account for; worth revisiting if that ever
causes a wrong reminder.
"""

from datetime import date, timedelta

MONDAY = 0
WEDNESDAY = 2
RECYCLING_WEEKS = (2, 4)


def _nth_weekday_of_month(d: date) -> int:
    """1 for the first occurrence of d's weekday in d's month, 2 for the second, ..."""
    return (d.day - 1) // 7 + 1


def _next_weekday(today: date, weekday: int) -> date:
    """Next date (today included) landing on `weekday` (Monday=0 ... Sunday=6)."""
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def _next_recycling_wednesday(today: date) -> date:
    candidate = _next_weekday(today, WEDNESDAY)
    while _nth_weekday_of_month(candidate) not in RECYCLING_WEEKS:
        candidate += timedelta(days=7)
    return candidate


def next_pickup(today: date) -> dict:
    """Whichever of garbage (every Monday) or recycling (2nd/4th
    Wednesday) comes next from `today` — {"kind", "date", "days_until"}.
    `today` counts as "next" if it's itself a pickup day."""
    garbage_date = _next_weekday(today, MONDAY)
    recycling_date = _next_recycling_wednesday(today)
    if garbage_date <= recycling_date:
        kind, pickup_date = "Garbage", garbage_date
    else:
        kind, pickup_date = "Recycling", recycling_date
    return {"kind": kind, "date": pickup_date, "days_until": (pickup_date - today).days}
