"""Temporary: wisdom teeth recovery status. Used to be its own rotating
page (a full HTML/CSS/JS timer embedded via components.html) plus this
badge; the dedicated page was dropped in favor of just this badge shown
on every page at all times (session request: "less invasive," and
"fully in line with the other pills" — see its call site in app.py,
folded into the same `extras` list as AQI/Wildfire/Payday rather than a
separate element).

Once recovery's done, delete this file and the `status_badge_html` call
in app.py.
"""

from datetime import datetime

# (hours since start, short stage title) — a condensed version of a
# fuller day-by-day recovery schedule (pain/swelling levels, diet,
# "what to expect," a surgeon watch-list), trimmed down to just enough
# to label this badge once the fuller page-based view was dropped.
_START = datetime(2026, 7, 17, 12, 0, 0)

_STAGE_TITLES = [
    (0, "Anesthesia Wearing Off"),
    (3, "Feeling Returning"),
    (6, "First Soreness Sets In"),
    (12, "Settling Into Night One"),
    (24, "Day 2 — Swelling Building"),
    (36, "Swelling Continues Climbing"),
    (48, "Day 3 — Peak Swelling Window"),
    (60, "Peak Plateau"),
    (72, "Day 4 — Corner Turning"),
    (96, "Day 4-5 — Continued Improvement"),
    (120, "Day 6 — Stitches & Tissue Closing"),
    (144, "Day 7 — Nearly Settled"),
    (168, "Week 2 — Surface Healing Complete"),
    (336, "Weeks 3-4 — Deeper Healing Continues"),
    (840, "Months 2-3 — Bone Remodeling"),
]


def _current_stage_title(hours_elapsed: float) -> str:
    title = _STAGE_TITLES[0][1]
    for hours, stage_title in _STAGE_TITLES:
        if hours_elapsed >= hours:
            title = stage_title
        else:
            break
    return title


def status_badge_html(now: datetime) -> str | None:
    """A `.weather-extra`-styled pill for app.py's hero-row `extras` list
    (same row as AQI/Wildfire/Payday). None before surgery's start time
    (nothing to show yet)."""
    hours_elapsed = (now - _START).total_seconds() / 3600
    if hours_elapsed < 0:
        return None
    hours = int(hours_elapsed)
    minutes = int(round((hours_elapsed - hours) * 60))
    if minutes == 60:
        hours, minutes = hours + 1, 0
    title = _current_stage_title(hours_elapsed)
    return (
        f'<span class="weather-extra" style="color:#c9a876; '
        f'background:rgba(201,168,118,0.22); border-color:#c9a876;">'
        f"{hours}h {minutes:02d}m · {title}</span>"
    )
