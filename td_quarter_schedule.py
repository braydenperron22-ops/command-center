"""TD Bank Group's fiscal quarters — Nov 1, Feb 1, May 1, Aug 1, one
calendar quarter ahead of the regular Jan/Apr/Jul/Oct year. Session
confirmation: Brayden's own sales targets reset on TD's real fiscal
quarters, not the calendar ones — same "no API exists for this, but
the real-world rule is simple and fixed" reasoning as payday_schedule.
py/waste_schedule.py, computed directly rather than needing an anchor
date the way payday's biweekly cadence does (a fiscal quarter start is
just a fixed month/day repeating every year, not a rolling interval).
"""

from datetime import date

_QUARTER_START_MONTHS = (2, 5, 8, 11)


def next_quarter_start(today: date) -> dict:
    """Next TD fiscal quarter start on/after `today` — {"date",
    "days_until"}. `today` counts as "next" if it's itself a quarter
    start. Built from this year's and next year's own 4 quarter-start
    dates rather than walking forward from a reference date — simpler
    and correct by construction, since the month/day pair is fixed and
    never drifts the way a biweekly cadence could."""
    candidates = [date(today.year, m, 1) for m in _QUARTER_START_MONTHS]
    candidates += [date(today.year + 1, m, 1) for m in _QUARTER_START_MONTHS]
    candidate = min(c for c in candidates if c >= today)
    return {"date": candidate, "days_until": (candidate - today).days}
