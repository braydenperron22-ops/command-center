"""First/last frost of the season — session request: "first and last
frost of the season is good," one of the "life" badge ideas floated
alongside moon phase and daylight saving. Genuinely different shape
from every other hero badge: not a fixed date (holidays, TD quarter)
and not a same-day "is this true right now" flag (UV, AQI) — frost has
to be TRACKED across an entire season, because "first frost" only
means something the first time it happens each fall, and "last frost"
can only ever be known in hindsight, once enough time has passed
without another one.

Forward-looking, not a morning-after report: uses tonight's forecast
low (same weather["forecast_low_c"] field the UV/record/ice-risk
badges already read, no new fetch) rather than waiting to confirm a
frost already happened — "frost risk tonight" is the version worth
acting on (bring the plants in), not "it frosted last night, you
already know." FROST_THRESHOLD_C=0 matches road_conditions.ice_risk's
own freezing-point convention.

Watch windows are deliberately generous (Aug 15-Dec 31 for fall, Jan 1-
Jun 15 for spring) — wide enough to bracket a real Northern Ontario
frost date without having to tune a precise climatological average,
narrow enough that a genuine summer heat wave low or winter cold snap
never gets mistaken for "the" seasonal frost event.
"""

from datetime import date

import persisted_state

FROST_THRESHOLD_C = 0.0
FALL_WATCH_START = (8, 15)  # (month, day)
SPRING_WATCH_END = (6, 15)
# Gardeners' own real-world rule of thumb for declaring a frost "the
# last one" — confirmed live this is the standard practical heuristic,
# not an arbitrary number.
LAST_FROST_CONFIRM_DAYS = 10

_STATE_KEY = "frost_tracker_state"
_DEFAULT_STATE = {
    "fall_year": None, "first_frost_date": None, "first_frost_shown": False,
    "spring_year": None, "last_sub_zero_date": None, "last_frost_shown": False,
}
_state: dict = {**_DEFAULT_STATE, **persisted_state.load(_STATE_KEY, {})}


def _in_fall_watch(today: date) -> bool:
    return today >= date(today.year, *FALL_WATCH_START)


def _in_spring_watch(today: date) -> bool:
    return today <= date(today.year, *SPRING_WATCH_END)


def first_frost_badge(today: date, forecast_low_c: float | None) -> dict | None:
    """{"date"} the one day a genuine first-frost-of-the-fall risk is
    detected, else None. Call once per rerun, unconditionally — resets
    its own tracked year automatically, same "no external scheduler
    needed" shape as every other seasonal tracker in this app."""
    global _state
    if _state["fall_year"] != today.year and _in_fall_watch(today):
        _state["fall_year"] = today.year
        _state["first_frost_date"] = None
        _state["first_frost_shown"] = False
        persisted_state.save(_STATE_KEY, _state)
    if not _in_fall_watch(today) or _state["fall_year"] != today.year:
        return None
    if forecast_low_c is not None and forecast_low_c <= FROST_THRESHOLD_C and _state["first_frost_date"] is None:
        _state["first_frost_date"] = today.isoformat()
        persisted_state.save(_STATE_KEY, _state)
    if _state["first_frost_date"] != today.isoformat() or _state["first_frost_shown"]:
        return None
    _state["first_frost_shown"] = True
    persisted_state.save(_STATE_KEY, _state)
    return {"date": today}


def last_frost_badge(today: date, forecast_low_c: float | None) -> dict | None:
    """{"date"} the one day LAST_FROST_CONFIRM_DAYS have passed since
    the most recent sub-zero forecast low this spring, else None —
    "last frost was probably {date}," confirmed only in hindsight, same
    real-world heuristic gardeners already use."""
    global _state
    if _state["spring_year"] != today.year and _in_spring_watch(today):
        _state["spring_year"] = today.year
        _state["last_sub_zero_date"] = None
        _state["last_frost_shown"] = False
        persisted_state.save(_STATE_KEY, _state)
    if not _in_spring_watch(today) or _state["spring_year"] != today.year:
        return None
    if forecast_low_c is not None and forecast_low_c <= FROST_THRESHOLD_C:
        if _state["last_sub_zero_date"] != today.isoformat():
            _state["last_sub_zero_date"] = today.isoformat()
            _state["last_frost_shown"] = False
            persisted_state.save(_STATE_KEY, _state)
        return None
    last_date = _state["last_sub_zero_date"]
    if last_date is None or _state["last_frost_shown"]:
        return None
    days_since = (today - date.fromisoformat(last_date)).days
    if days_since < LAST_FROST_CONFIRM_DAYS:
        return None
    _state["last_frost_shown"] = True
    persisted_state.save(_STATE_KEY, _state)
    return {"date": date.fromisoformat(last_date)}
