"""Full moon detection — session request: "moon phase, only show if
its a full moon or a moon worth looking at," one of the "life" badge
ideas floated alongside daylight saving and first/last frost. Reuses
astral.moon (already a dependency — seasons_client.py's own equinox/
solstice math is built on the same library's sun module), not a new
one.

astral.moon.phase() returns 0..27.99 (days since new moon in a ~29.53
day cycle) — its OWN documented buckets call anything from 14 to 20.99
"Full moon," a 7-day window far too wide for "worth looking at"
(confirmed live: that bucket would keep this badge lit for a quarter
of every month). True peak fullness is the cycle's exact midpoint,
~14.77; PEAK_WINDOW_DAYS narrows this to the real ~3-night window a
casual observer would call "full," confirmed live by scanning 90 real
days and finding exactly one ~3-day window per lunar month, correctly
spaced ~29-30 days apart.
"""

import math
from datetime import date

from astral import moon

_CYCLE_DAYS = 29.53
_PEAK_PHASE = _CYCLE_DAYS / 2  # ~14.77 — exact midpoint of the cycle, true full moon
PEAK_WINDOW_DAYS = 1.5  # ±1.5 days of peak reads as "full" to the naked eye


def full_moon_tonight(today: date) -> dict | None:
    """{"illumination_pct"} if tonight's moon is within the real "looks
    full" window, else None — a same-day flag like the UV/AQI/ice-risk
    badges, not a days-until countdown (the moon is full or it isn't,
    there's no "tomorrow" preview worth showing a day early for this).
    illumination_pct uses the standard phase-angle approximation
    (0% at new moon, 100% at true full) rather than astral's own
    discrete phase number, since "98% full" reads better on a badge
    than "phase 14.2"."""
    phase = moon.phase(today)
    distance_from_peak = abs(phase - _PEAK_PHASE)
    if distance_from_peak > PEAK_WINDOW_DAYS:
        return None
    illumination_pct = round(100 * (1 - math.cos(2 * math.pi * phase / _CYCLE_DAYS)) / 2)
    return {"illumination_pct": illumination_pct}
