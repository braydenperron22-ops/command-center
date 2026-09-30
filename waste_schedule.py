"""Municipality of East Ferris garbage/recycling pickup schedule (Route
#1 — Wednesday, Center: Corbeil Road, East area, Quae-Quae Road,
Guillemette Road, Big Moose Road, Bertha Road) — not sourced from a
live feed since the real schedule is a simple recurring rule, confirmed
against the municipality's own 2026 recycling calendar.

Session correction 2026-09-30: this used to assume "2nd and 4th
Wednesday of the calendar month," which reset every month — wrong.
Real East Ferris recycling runs on a continuous 14-day cycle that
carries over month boundaries, confirmed against the real 2026
calendar: Route #1's own highlighted Wednesdays are Sept 16, Sept 30,
Oct 14, Oct 28, Nov 11, Nov 25 — each exactly 14 days apart. A
calendar-month-relative rule only happens to match a continuous
cycle in a month with exactly 4 Wednesdays; September 2026 has 5,
which is exactly what silently dropped a real Sept 30 pickup off the
old rule. RECYCLING_ANCHOR is a real, confirmed Route #1 date; the fix
is a straight (date - anchor) % 14 == 0 check, immune to month
boundaries and to month Wednesday-count.
"""

from datetime import date, timedelta

MONDAY = 0
WEDNESDAY = 2
RECYCLING_ANCHOR = date(2026, 9, 30)
RECYCLING_INTERVAL_DAYS = 14


def next_weekday(today: date, weekday: int) -> date:
    """Next date (today included) landing on `weekday` (Monday=0 ... Sunday=6).
    Public — household_reminders.py's own simple day-of-week reminders
    (Laundry, Groceries) reuse this exact date math rather than a
    second copy of it."""
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def _next_recycling_wednesday(today: date) -> date:
    candidate = next_weekday(today, WEDNESDAY)
    while (candidate - RECYCLING_ANCHOR).days % RECYCLING_INTERVAL_DAYS != 0:
        candidate += timedelta(days=7)
    return candidate


def next_pickup(today: date) -> dict:
    """Whichever of garbage (every Monday) or recycling (2nd/4th
    Wednesday) comes next from `today` — {"kind", "date", "days_until"}.
    `today` counts as "next" if it's itself a pickup day."""
    garbage_date = next_weekday(today, MONDAY)
    recycling_date = _next_recycling_wednesday(today)
    if garbage_date <= recycling_date:
        kind, pickup_date = "Garbage", garbage_date
    else:
        kind, pickup_date = "Recycling", recycling_date
    return {"kind": kind, "date": pickup_date, "days_until": (pickup_date - today).days}
