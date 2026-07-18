"""Renders the weather-statement banner: an active Environment Canada
alert takes priority — pulled from two genuinely separate EC products,
its general weather-warnings feed (ec_alerts) and its AQHI air quality
observations (ec_aqhi), confirmed live to not overlap at all — and our
own extreme-heat/extreme-cold fallback only ever shows when neither
has anything active for the region."""

import streamlit as st

import ec_alerts
import ec_aqhi
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
    # Ranked above heat/cold, not with fog/frost: by the time
    # ec_aqhi.aqhi_alert() ever produces a title at all, it's already
    # filtered to High Risk or worse (see ec_aqhi._HIGH_RISK_AQHI) —
    # a genuinely serious condition, not the routine end of the
    # "air quality" bucket the old rank of 15 (tied with fog) assumed.
    "air quality": 35,
    "heat": 30, "cold": 30, "frost": 20, "fog": 15,
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


def _combined_alerts() -> list[dict]:
    """EC's general weather-warnings feed plus, separately, a
    synthesized alert for a genuinely elevated AQHI reading (see
    ec_aqhi.aqhi_alert) — confirmed live these are two real,
    independent EC products with no overlap (the weather feed does not
    carry air quality at all), so both need fetching and both need to
    participate in the same selection/severity logic below. Each
    guarded separately so a failure fetching one doesn't also hide the
    other."""
    try:
        alerts = list(ec_alerts.fetch_alerts())
    except Exception:
        alerts = []
    try:
        aqhi = ec_aqhi.aqhi_alert()
    except Exception:
        aqhi = None
    if aqhi is not None:
        alerts.append(aqhi)
    return alerts


def current_severity() -> str | None:
    """The same alert render() below would show, resolved to just its
    severity tier — for callers elsewhere in the app (the Govee light)
    that need to react to real EC alerts without duplicating the
    fetch/selection logic. None if nothing's active, or if the only
    thing showing is our own manual heat/cold fallback (that's a
    self-generated heuristic, not a genuine EC alert, and shouldn't
    trigger a real-alert response anywhere)."""
    alerts = _combined_alerts()
    if not alerts:
        return None
    alert = max(alerts, key=_selection_score)
    return _severity(alert["title"])


def render(weather: dict | None) -> None:
    alerts = _combined_alerts()
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
