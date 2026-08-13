"""CPP/OAS payment dates — the days Service Canada deposits pension
payments, which reliably brings a real wave of branch traffic (seniors
coming in to withdraw/deposit) the same day or the day after. Session
request: "flag pension days so i know when the branch will be a zoo."

Hand-maintained from Service Canada's own official published schedule,
not computed from the general "third-to-last business day" rule —
checked live, that rule does NOT reliably reproduce the real schedule:
December is a confirmed exception (2026's real payment is Dec 22, a
full week before what that rule would compute, Dec 29 — Service Canada
pays out early ahead of the holiday period). Same "verified real data
beats a plausible-looking computed rule" reasoning as payday_schedule.
py's own anchor-date approach, not a generic formula.

2026_DATES needs a real annual update once Service Canada publishes
next year's schedule (typically published in advance — check canada.ca
CPP/OAS payment dates). next_payment_date returns None past what's
listed here rather than falling back to the unverified generic rule,
since a wrong guess is worse than no badge at all.
"""

from datetime import date

_2026_DATES = [
    date(2026, 1, 28), date(2026, 2, 25), date(2026, 3, 27), date(2026, 4, 28),
    date(2026, 5, 27), date(2026, 6, 26), date(2026, 7, 29), date(2026, 8, 27),
    date(2026, 9, 25), date(2026, 10, 28), date(2026, 11, 26), date(2026, 12, 22),
]
_KNOWN_DATES = sorted(_2026_DATES)


def next_payment_date(today: date) -> dict | None:
    """Next CPP/OAS payment date on/after `today` — {"date",
    "days_until"}, or None once `today` is past the last date this
    module actually has real data for (see this module's own docstring
    on why that's a hard stop, not a computed fallback)."""
    upcoming = [d for d in _KNOWN_DATES if d >= today]
    if not upcoming:
        return None
    candidate = upcoming[0]
    return {"date": candidate, "days_until": (candidate - today).days}


# Session follow-up: "is there a way to automatically update the cpp/
# oas schedule" — checked live: no real government API for this exists
# (only statistical CSVs, not the payment-date schedule itself), and
# the one real HTML calendar page (canada.ca/en/services/benefits/
# calendar.html) returned a 403 on a real fetch attempt, meaning a
# scraper here would be genuinely fragile. User's own call: manual
# annual update instead of a scraper that could silently break. This
# is the other half of that choice — a real signal on the Maintenance
# page (pages_maintenance.py) so the once-a-year update doesn't get
# silently forgotten once _KNOWN_DATES actually runs out, rather than
# relying on someone noticing the hero badge quietly stopped appearing.
COVERAGE_WARNING_DAYS = 60


def coverage_status(today: date) -> dict:
    """{"last_date", "days_remaining"} — days_remaining goes negative
    once today is already past the last known date (next_payment_date
    would already be returning None by then)."""
    last_date = _KNOWN_DATES[-1]
    return {"last_date": last_date, "days_remaining": (last_date - today).days}
