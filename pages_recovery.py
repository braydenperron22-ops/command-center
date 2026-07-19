"""Temporary page: wisdom teeth recovery timer. Self-contained HTML/CSS/JS
(see recovery_timer.html) rendered via components.html rather than
st.markdown — it runs its own setInterval clock tick every second, which
needs a real isolated document rather than sharing the dashboard's DOM
(this app's own 5s autorefresh would otherwise tear it down and reset
the interval constantly).

Added at the user's request while actually recovering — stays in the
rotation (see PAGES/PAGE_DURATION_OVERRIDES in config.py) until they ask
for it to come back out, at which point delete this file, recovery_timer.html,
and the "recovery" entries in config.py/app.py/theme.py.
"""

from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_HTML_PATH = Path(__file__).with_name("recovery_timer.html")

# Must match recovery_timer.html's own `start` — that file is the single
# source of truth for the full day-by-day detail (pain/swelling levels,
# diet, "what to expect," the surgeon watch-list); this is only enough
# duplicated here to label the always-visible badge below, since a
# global badge (see app.py's page-independent hero row) can't reach
# into that file's own embedded JS.
_START = datetime(2026, 7, 17, 12, 0, 0)

# (hours since start, short stage title) — mirrors recovery_timer.html's
# own `stages` array (title field only). Keep in sync if that file's
# schedule ever changes.
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


def render() -> None:
    st.markdown('<div class="page-title page-title-recovery">Recovery</div>', unsafe_allow_html=True)
    components.html(_HTML_PATH.read_text(), height=980, scrolling=False)


def _current_stage_title(hours_elapsed: float) -> str:
    title = _STAGE_TITLES[0][1]
    for hours, stage_title in _STAGE_TITLES:
        if hours_elapsed > hours or hours_elapsed == hours:
            title = stage_title
        else:
            break
    return title


def status_badge_html(now: datetime) -> str | None:
    """A small pill for app.py's page-independent hero row (same
    always-visible spot as the AQI/Wildfire/Payday badges) — the full
    render() page above only shows during its own rotation slot, but
    the whole point of a recovery tracker is glancing at it no matter
    which page happens to be up, so this is a second, minute-precision
    view of the same schedule that doesn't need its own live-ticking
    iframe. None before surgery's start time (nothing to show yet).
    """
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
