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


# Session follow-up: "feed all that info to the morning brief LLM" —
# holiday_clause above only ever reaches the AI when it wins a spot in
# render()'s top-3 stats bar (a real, correctly narrow window for what
# actually gets a bullet on screen), which could silently starve the
# model of holiday awareness entirely on a busy day. This is a
# separate, wider feed specifically for _ai_sentence's own prompt
# context — not gated by stats-bar priority at all, same spirit as the
# weekday/USER_PROFILE context that's already unconditionally given
# regardless of what's visible in the bar.
UPCOMING_HOLIDAYS_COUNT = 4


def upcoming_holidays_block(now) -> str:
    """Next UPCOMING_HOLIDAYS_COUNT statutory holidays on/after today,
    oldest first, as a compact "Name: Weekday, Month Day" list — "" is
    never actually returned (Canada always has more holidays coming),
    but kept Optional-shaped for consistency with this file's other
    block-builder."""
    today = now.date()
    found = []
    d = today
    # Bounded scan, not an unbounded while-True — 800 days comfortably
    # covers UPCOMING_HOLIDAYS_COUNT even across the sparsest real gap
    # in the Canadian calendar (Boxing Day to New Year's Day aside, the
    # actual widest gap is Thanksgiving to Christmas, ~2.5 months), so
    # this always terminates even if the count were ever raised well
    # past what a single year could satisfy.
    for _ in range(800):
        if d in _CA_ON_HOLIDAYS:
            # d.day as a plain int, not %d/%-d — the same "avoid a non-
            # portable strftime flag" convention pages_household.py's
            # own as_of formatting already uses, rather than %-d (a
            # GNU/BSD-only extension Windows strftime doesn't support).
            found.append(f"{_CA_ON_HOLIDAYS[d]}: {d.strftime('%A, %B')} {d.day}")
            if len(found) >= UPCOMING_HOLIDAYS_COUNT:
                break
        d += timedelta(days=1)
    return "; ".join(found)
