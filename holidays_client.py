"""Canadian/Ontario statutory holidays — same locale the rest of this
app already assumes (CPI, GDP, BoC rate are all Canada-focused), and
banks observe these exact dates, matching TD's own closure schedule.
Session request: "how can i get all of the holidays to be fed to the
AI." Uses the `holidays` package rather than hand-computing dates —
several of these are movable (Good Friday is Easter-based; Family Day/
Victoria Day/Labour Day/Thanksgiving are all "Nth weekday of month"
rules) and some shift to the next business day when they land on a
weekend (see BOXING_DAY/CHRISTMAS "(observed)" — confirmed live,
2026's real Boxing Day falls on a Saturday and correctly observes the
following Monday instead) — exactly the class of date math worth a
real, maintained library instead of reinventing.

No fixed year range: `holidays.Canada(subdiv="ON")` resolves any date
dynamically on lookup (confirmed live for dates decades out either
direction), so this never goes stale the way a hardcoded year list
would.
"""

from datetime import date, timedelta

import holidays

_CA_ON_HOLIDAYS = holidays.Canada(subdiv="ON")

# How many days ahead to flag an upcoming holiday — short enough that
# it's still "worth planning around" news (a long weekend coming up),
# not a standing fixture repeated every single morning for a week.
UPCOMING_WINDOW_DAYS = 3


def holiday_clause(now) -> tuple[int, str] | None:
    """(priority, text) for morning_briefing.py's own clause list —
    highest priority when today itself is a statutory holiday (real,
    actionable "no mail/banks closed today" news), lower when one's
    coming up within UPCOMING_WINDOW_DAYS. None most days, same as
    every other clause here."""
    today = now.date()
    if today in _CA_ON_HOLIDAYS:
        return 6, f"today is a statutory holiday: {_CA_ON_HOLIDAYS[today]}"
    for offset in range(1, UPCOMING_WINDOW_DAYS + 1):
        d = today + timedelta(days=offset)
        if d in _CA_ON_HOLIDAYS:
            day_word = "day" if offset == 1 else "days"
            return 3, f"{_CA_ON_HOLIDAYS[d]} is in {offset} {day_word} ({d.strftime('%A')})"
    return None
