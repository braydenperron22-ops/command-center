"""Shared trend/classification logic used by every data source."""

import statistics
from datetime import date

from config import HOT_COOL_THRESHOLD

TREND_WINDOW = 6  # months of history used to build the trailing trend band
SPARKLINE_POINTS = 12  # readings shown in each tile's trend sparkline


def _percentile_rank(current: float, history: list[float]) -> int:
    """Where `current` sits among `history` (0-100) — e.g. 73 means
    today's reading is higher than 73% of everything in that window.
    Deliberately a separate, much longer lookback than TREND_WINDOW
    above: that one asks "hot or cold vs the last 6 readings," this asks
    "high or low vs as much real history as we actually have.\""""
    if not history:
        return 50
    below = sum(1 for v in history if v < current)
    return round(100 * below / len(history))


def _years_span(dates: list[str]) -> float:
    if len(dates) < 2:
        return 0.0
    first, last = date.fromisoformat(dates[0]), date.fromisoformat(dates[-1])
    return (last - first).days / 365.25


def _yoy_series(values: list[float], periods_per_year: int) -> list[float]:
    if len(values) <= periods_per_year:
        return []
    return [
        (values[i] / values[i - periods_per_year] - 1) * 100
        for i in range(periods_per_year, len(values))
    ]


def looks_quarterly(dates: list[str]) -> bool:
    if len(dates) < 2:
        return False
    months = sorted({int(d[5:7]) for d in dates[-8:]})
    return len(months) <= 4


def build_reading(dates: list[str], values: list[float], transform: str) -> dict | None:
    """Turn a chronological (date, value) series into a current/previous/classification reading."""
    if len(values) < 3:
        return None

    if transform == "yoy":
        periods_per_year = 4 if looks_quarterly(dates) else 12
        series = _yoy_series(values, periods_per_year)
        series_dates = dates[periods_per_year:]
        if len(series) < 3:
            return None
    else:
        series = values
        series_dates = dates

    current = series[-1]
    previous = series[-2]
    trend_window = series[-(TREND_WINDOW + 1):-1] or series[:-1]
    trend_mean = statistics.fmean(trend_window)
    trend_stdev = statistics.pstdev(trend_window) if len(trend_window) > 1 else 0.0

    # Direction-neutral: "above"/"below" trend, no judgment of good/bad here.
    # Whether "above" is favorable depends on the indicator (e.g. above-trend
    # GDP is good, above-trend unemployment is bad) — that mapping lives in
    # tiles.py via each indicator's configured good_direction.
    z = 0.0
    classification = "in-line"
    if trend_stdev > 0:
        z = (current - trend_mean) / trend_stdev
        if z >= HOT_COOL_THRESHOLD:
            classification = "above"
        elif z <= -HOT_COOL_THRESHOLD:
            classification = "below"

    return {
        "current": current,
        "previous": previous,
        "classification": classification,
        "as_of": series_dates[-1],
        "z_score": z,
        "history": series[-SPARKLINE_POINTS:],
        "percentile": _percentile_rank(current, series[:-1]),
        "history_years": _years_span(series_dates),
    }
