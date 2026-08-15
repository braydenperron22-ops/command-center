"""Astronomical season start dates (equinoxes/solstices) — session
request: "can you include the first day of each season as a hero
badge/fact the AI can use."

Computed, not hand-maintained like cpp_payment_dates.py's own real
published dates — unlike CPP's administrative schedule (confirmed live
this session to NOT follow its own "obvious" computed rule), an
equinox/solstice is pure celestial mechanics with no institutional
discretion involved, so a real astronomical formula is trustworthy
here in a way a "plausible" rule wasn't there. Reuses this app's own
already-trusted solar-position math (astral.sun — the same formulas
weather_client.py's sunrise/sunset already depend on) via a numerical
search for the exact moment the sun's apparent ecliptic longitude
crosses 0°/90°/180°/270° (spring equinox/summer solstice/fall equinox/
winter solstice), rather than a second, independent equinox-finding
algorithm this app would have no track record trusting.

Checked live against 2026's real published UTC times before trusting
this: all four computed dates matched the real published calendar date
exactly (Mar 20/Jun 21/Sep 23/Dec 21), each within about 10 minutes of
the real published UTC instant — far more precision than a "which
calendar day" fact actually needs.
"""

from datetime import date, datetime, timedelta, timezone

from astral import sun

# (label, target ecliptic longitude in degrees, approximate month/day
# to seed the numerical search on) — the search itself finds the EXACT
# date for any given year; these are just a rough starting point so the
# +/-5-day bisection window reliably contains the real crossing.
_SEASONS = [
    ("Spring", 0, 3, 20),
    ("Summer", 90, 6, 21),
    ("Fall", 180, 9, 22),
    ("Winter", 270, 12, 21),
]


def _apparent_longitude(dt: datetime) -> float:
    jd = sun.julianday(dt)
    jc = sun.julianday_to_juliancentury(jd)
    return sun.sun_apparent_long(jc) % 360


def _find_crossing(year: int, target_long: float, month: int, day: int) -> date:
    """The real UTC date the sun's apparent ecliptic longitude crosses
    target_long, found by bisection over a +/-5 day window around the
    given rough seed date — 60 iterations narrows this to a fraction of
    a minute, though only the date half of the result is actually used
    by anything in this module."""
    lo = datetime(year, month, day, tzinfo=timezone.utc) - timedelta(days=5)
    hi = lo + timedelta(days=10)
    for _ in range(60):
        mid = lo + (hi - lo) / 2
        # Signed shortest angular distance, not a plain subtraction —
        # correctly handles the 359°->0° wraparound the spring equinox
        # search crosses (target_long=0).
        delta = (_apparent_longitude(mid) - target_long + 180) % 360 - 180
        if delta < 0:
            lo = mid
        else:
            hi = mid
    return lo.date()


_cache: dict[int, list[tuple[str, date]]] = {}


def season_start_dates(year: int) -> list[tuple[str, date]]:
    """[(label, date), ...] for all four season starts in `year`, oldest
    first (Spring/Summer/Fall/Winter, already chronological). Cached
    per year — pure local computation with no I/O, but no reason to
    redo the same 240 bisection steps on every rerun either."""
    if year not in _cache:
        _cache[year] = [(label, _find_crossing(year, target, m, d)) for label, target, m, d in _SEASONS]
    return _cache[year]


def next_season_start(today: date) -> dict | None:
    """{"label", "date", "days_until"} for the next season start on or
    after `today`. Checks this year AND next — winter's own date falls
    in December, so a late-December lookup needs next year's spring/
    summer/fall to already be searchable rather than running out."""
    for year in (today.year, today.year + 1):
        for label, d in season_start_dates(year):
            if d >= today:
                return {"label": label, "date": d, "days_until": (d - today).days}
    return None


# Same "today, or coming up within a short window" shape as holidays_
# client.holiday_clause — a season change is the same kind of rare,
# genuinely worth-a-line event a statutory holiday is, just on its own
# astronomical schedule instead of a legislated one.
UPCOMING_WINDOW_DAYS = 3


def season_clause(now: datetime) -> tuple[int, str] | None:
    """(priority, text) for morning_briefing.py's own clause list —
    same priority tiers as holidays_client.holiday_clause: highest when
    today itself is a season's first day, lower when one's coming up
    within UPCOMING_WINDOW_DAYS. None most days."""
    season = next_season_start(now.date())
    if season is None:
        return None
    if season["days_until"] == 0:
        return 6, f"today is the first day of {season['label']}"
    if season["days_until"] <= UPCOMING_WINDOW_DAYS:
        day_word = "day" if season["days_until"] == 1 else "days"
        return 3, f"{season['label']} begins in {season['days_until']} {day_word} ({season['date'].strftime('%A')})"
    return None


# Same "always-given background, not gated by stats-bar priority"
# reasoning as holidays_client.upcoming_holidays_block — session
# request: "a fact the AI can use," not just something that might win a
# spot in the top-3 stats bar on the one day it fires.
def upcoming_seasons_block(now: datetime) -> str:
    """The next season change on/after today, as a compact "Label:
    Weekday, Month Day (in N days)" string, for _ai_sentence's/
    _update_learned_notes' own prompt context."""
    season = next_season_start(now.date())
    if season is None:
        return ""
    d = season["date"]
    when = "today" if season["days_until"] == 0 else f"in {season['days_until']} days"
    return f"{season['label']} begins {d.strftime('%A, %B')} {d.day} ({when})"
