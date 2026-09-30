"""Municipality of East Ferris garbage/recycling pickup schedule (Route
#1 — Wednesday, Center: Corbeil Road, East area, Quae-Quae Road,
Guillemette Road, Big Moose Road, Bertha Road).

Garbage (every Monday) is a simple enough recurring rule to compute.
Recycling isn't: session correction 2026-09-30 found the real cadence
is a continuous 14-day cycle that carries over month boundaries — a
computed "2nd/4th Wednesday of the calendar month" rule looked right
but silently drops a real pickup in any month with 5 Wednesdays
(September 2026 has one, which was the actual live bug that day).
Rather than re-deriving that cycle with a second anchor-date formula
that could just as easily hide its own edge case, this is hand-
maintained straight from the municipality's own 2026 Route #1 calendar
— same "verified real data beats a plausible-looking computed rule"
choice cpp_payment_dates.py already made for the identical reason.

_2026_RECYCLING_DATES needs a real annual update once East Ferris
publishes next year's calendar (circularmaterials.ca/eastferris, or
the municipality's own site — both blocked non-browser fetches when
checked live, so this has to be read off the calendar image/PDF
directly, not scraped). next_pickup falls back to garbage once
today is past the last recycling date listed here rather than
guessing — see coverage_status/COVERAGE_WARNING_DAYS, surfaced on the
Maintenance page the same way cpp_payment_dates' own coverage warning
is."""

from datetime import date, timedelta

MONDAY = 0

_2026_RECYCLING_DATES = [
    date(2026, 1, 7), date(2026, 1, 21),
    date(2026, 2, 4), date(2026, 2, 18),
    date(2026, 3, 4), date(2026, 3, 18),
    date(2026, 4, 1), date(2026, 4, 15), date(2026, 4, 29),
    date(2026, 5, 13), date(2026, 5, 27),
    date(2026, 6, 10), date(2026, 6, 24),
    date(2026, 7, 8), date(2026, 7, 22),
    date(2026, 8, 5), date(2026, 8, 19),
    date(2026, 9, 2), date(2026, 9, 16), date(2026, 9, 30),
    date(2026, 10, 14), date(2026, 10, 28),
    date(2026, 11, 11), date(2026, 11, 25),
    date(2026, 12, 9), date(2026, 12, 23),
]
_KNOWN_RECYCLING_DATES = sorted(_2026_RECYCLING_DATES)


def next_weekday(today: date, weekday: int) -> date:
    """Next date (today included) landing on `weekday` (Monday=0 ... Sunday=6).
    Public — household_reminders.py's own simple day-of-week reminders
    (Laundry, Groceries) reuse this exact date math rather than a
    second copy of it."""
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def _next_recycling_date(today: date) -> date | None:
    upcoming = [d for d in _KNOWN_RECYCLING_DATES if d >= today]
    return upcoming[0] if upcoming else None


def next_pickup(today: date) -> dict:
    """Whichever of garbage (every Monday, computed) or recycling
    (hand-maintained real dates) comes next from `today` —
    {"kind", "date", "days_until"}. `today` counts as "next" if it's
    itself a pickup day. Falls back to garbage-only once recycling
    coverage has run out (see coverage_status) rather than guessing at
    a continued cycle."""
    garbage_date = next_weekday(today, MONDAY)
    recycling_date = _next_recycling_date(today)
    if recycling_date is None or garbage_date <= recycling_date:
        kind, pickup_date = "Garbage", garbage_date
    else:
        kind, pickup_date = "Recycling", recycling_date
    return {"kind": kind, "date": pickup_date, "days_until": (pickup_date - today).days}


# Same reasoning and shape as cpp_payment_dates.COVERAGE_WARNING_DAYS —
# a real, visible warning once the hand-maintained list is actually
# running low, so next year's update doesn't depend on someone
# noticing the recycling badge quietly stopped appearing on its own.
COVERAGE_WARNING_DAYS = 60


def coverage_status(today: date) -> dict:
    """{"last_date", "days_remaining"} — days_remaining goes negative
    once today is already past the last known recycling date (next_pickup
    would already have silently fallen back to garbage-only by then)."""
    last_date = _KNOWN_RECYCLING_DATES[-1]
    return {"last_date": last_date, "days_remaining": (last_date - today).days}
