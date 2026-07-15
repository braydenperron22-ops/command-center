"""Renders the weather-statement banner: an active Environment Canada
alert takes priority; our own extreme-heat/extreme-cold fallback only
ever shows when EC has nothing active for the region."""

import streamlit as st

import ec_alerts
from config import EXTREME_COLD_THRESHOLD_C, EXTREME_HEAT_THRESHOLD_C


# Tornado/hurricane/tsunami are categorically more dangerous than any
# other hazard EC issues for this region — a Tornado Watch still
# deserves to look scarier than a routine Heat Warning, so hazard type
# has to weigh in alongside EC's warning/watch/statement tier wording,
# not just tier alone. Heat/cold/fog-family hazards are real but
# generally less sudden/life-threatening than storm/wind/flood/ice
# ones, so a Warning for one of these is visually subordinate to a
# storm-type Warning at the same tier (Tornado > Thunderstorm > Heat,
# as requested).
_EXTREME_HAZARD_TERMS = ("tornado", "hurricane", "tsunami")
_MODERATE_HAZARD_TERMS = ("heat", "cold", "frost", "fog", "rainfall", "snowfall", "air quality")

# Which hazard actually wins when several alerts are active at once —
# deliberately separate from _severity()'s tier-first coloring below.
# Tier (warning/watch/statement) reflects confidence/imminence, not
# danger, so a low-confidence Thunderstorm Watch still has to outrank a
# certain Heat Warning here: Tornado > Thunderstorm > Heat holds
# regardless of which one currently has the more definite tier wording.
_HAZARD_RANK = {
    "tornado": 100, "hurricane": 95, "tsunami": 95,
    "thunderstorm": 80, "tropical storm": 75, "flood": 70,
    "blizzard": 65, "winter storm": 65, "ice storm": 63, "freezing rain": 60,
    "wind": 55, "rainfall": 50, "snowfall": 45,
    "heat": 30, "cold": 30, "frost": 20, "fog": 15, "air quality": 15,
}
_DEFAULT_HAZARD_RANK = 40  # an unrecognized hazard — assume moderate rather than trivial or extreme
_TIER_TIEBREAK = {"warning": 2, "watch": 1, "statement": 0}


def _tier(title: str) -> str:
    t = title.lower()
    if "warning" in t:
        return "warning"
    if "watch" in t:
        return "watch"
    return "statement"


def _hazard_rank(title: str) -> int:
    t = title.lower()
    matches = [rank for hazard, rank in _HAZARD_RANK.items() if hazard in t]
    return max(matches) if matches else _DEFAULT_HAZARD_RANK


def _selection_score(alert: dict) -> tuple[int, int]:
    """Which single alert wins when several are active — hazard type
    first (Tornado > Thunderstorm > Heat, full stop, regardless of
    tier), EC's warning/watch/statement wording only as a tiebreak
    between two alerts for the *same* hazard (a Thunderstorm Warning
    still outranks a Thunderstorm Watch)."""
    title = alert["title"]
    return (_hazard_rank(title), _TIER_TIEBREAK[_tier(title)])


def _severity(title: str) -> str:
    """One of "extreme" (tornado/hurricane/tsunami, any tier) >
    "warning" > "warning-moderate" (a Warning-tier heat/cold/fog-family
    hazard) > "watch" > "statement". EC's own title text always
    contains a tier word (e.g. "YELLOW WARNING - HEAT...", "Severe
    Thunderstorm Warning", "Special Weather Statement") and the hazard
    name itself, so this needs no separate fields from the feed. Drives
    how hard the bar visually pulls attention for whichever alert
    _selection_score picked — tier still decides the color/intensity
    honestly (a Watch shouldn't look as certain as a Warning) even
    though it's hazard type that decided which alert got shown."""
    t = title.lower()
    if any(term in t for term in _EXTREME_HAZARD_TERMS):
        return "extreme"
    tier = _tier(title)
    if tier == "warning":
        return "warning-moderate" if any(term in t for term in _MODERATE_HAZARD_TERMS) else "warning"
    return tier


def _fallback_text(weather: dict | None) -> str | None:
    if not weather:
        return None
    high = weather.get("forecast_high_c")
    low = weather.get("forecast_low_c")
    if high is not None and high >= EXTREME_HEAT_THRESHOLD_C:
        return f"Extreme Heat Advisory — today's high near {high:.0f}°C"
    if low is not None and low <= EXTREME_COLD_THRESHOLD_C:
        return f"Extreme Cold Advisory — today's low near {low:.0f}°C"
    return None


def render(weather: dict | None) -> None:
    alerts = ec_alerts.fetch_alerts()
    if alerts:
        # Several alerts can technically be active at once (e.g. a Heat
        # Warning alongside a Severe Thunderstorm Watch) — showing just
        # the most severe one keeps the bar readable rather than
        # concatenating everything, and means a genuinely more dangerous
        # alert is never buried under whatever the feed happened to list
        # first. A "+N more" suffix at least surfaces that there's more
        # to know.
        alert = max(alerts, key=_selection_score)
        # Used to append " — {summary}" too, but EC's summary field is
        # just "Issued: <timestamp>" (confirmed live) — roughly doubled
        # the banner's height for a kiosk that already refreshes
        # automatically and has no use for a manual staleness check.
        # Title alone (hazard + region) is the part actually worth
        # reading from across the room.
        text = alert["title"]
        if len(alerts) > 1:
            text += f" (+{len(alerts) - 1} more alert{'s' if len(alerts) > 2 else ''})"
        label = "Environment Canada"
        # A real EC alert earns the bold, high-contrast treatment
        # (theme.py's weather-statement-{severity} modifiers) — our own
        # manual heat/cold fallback below deliberately keeps the
        # original muted styling instead, since it's a self-generated
        # heuristic, not an official warning, and shouldn't visually
        # compete with a genuine one.
        bar_class = f"weather-statement-bar weather-statement-{_severity(alert['title'])}"
    else:
        text = _fallback_text(weather)
        if not text:
            return
        label = "Weather Advisory"
        bar_class = "weather-statement-bar"

    st.markdown(
        f"""<div class="{bar_class}">
            <span class="weather-statement-dot"></span>
            <span class="weather-statement-label">{label}</span>
            <span class="weather-statement-text">{text}</span>
        </div>""",
        unsafe_allow_html=True,
    )
