"""Biweekly payday schedule — every second Thursday, anchored to a known
real payday (July 16, 2026). Same reasoning as waste_schedule.py: no API
exists for a personal pay schedule, and biweekly-on-a-fixed-weekday is
regular enough to compute forward from one confirmed anchor date rather
than needing a live feed.
"""

from datetime import date, timedelta

REFERENCE_PAYDAY = date(2026, 7, 16)
PAY_PERIOD_DAYS = 14


def next_payday(today: date) -> dict:
    """Next payday on/after `today` — {"date", "days_until"}. `today`
    counts as "next" if it's itself a payday. Floor division handles a
    `today` before REFERENCE_PAYDAY too (walks back a period, then the
    < today check rolls it forward again), not just ones after it."""
    days_since_reference = (today - REFERENCE_PAYDAY).days
    periods_elapsed = days_since_reference // PAY_PERIOD_DAYS
    candidate = REFERENCE_PAYDAY + timedelta(days=periods_elapsed * PAY_PERIOD_DAYS)
    if candidate < today:
        candidate += timedelta(days=PAY_PERIOD_DAYS)
    return {"date": candidate, "days_until": (candidate - today).days}
