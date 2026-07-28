"""Renders the weather-statement banner: an active Environment Canada
alert takes priority — pulled from two genuinely separate EC products,
its general weather-warnings feed (ec_alerts) and its AQHI air quality
observations (ec_aqhi), confirmed live to not overlap at all — and our
own extreme-heat/extreme-cold fallback only ever shows when neither
has anything active for the region."""

import html
import time
from datetime import datetime

import streamlit as st

import ec_alerts
import ec_aqhi
import ec_storm_timing
import persisted_state
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


def render(weather: dict | None) -> bool:
    """Returns whether a banner was actually rendered — session report:
    "our heat warning just popped up and its kinda colliding with the
    leave in timer." The banner is now position: fixed (theme.py's own
    comment on .weather-statement-bar has the full story), which took
    it out of document flow entirely — app.py uses this return value to
    reserve the same real space in flow (a spacer before .hero-row)
    only on a rerun where there's actually a banner to clear, rather
    than a permanent gap on every ordinary alert-free day."""
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
            return False
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
    return True


# Session request: "a recent special weather statement just came in but
# it didnt show as a toast alert, make sure they show up." render()
# above already surfaces whatever's currently active in the persistent
# banner, but that banner is suppressed during a jumbotron takeover
# (app.py) — with nothing else picking up the slack, a new alert issued
# while a game's on screen went completely unseen, which is exactly what
# happened here. get_new_alerts below mirrors news.get_new_alerts's own
# shape so app.py's existing toast queue (which DOES still run during a
# takeover) can carry this too, resolving from the exact same
# _combined_alerts/_selection_score logic render() uses so the toast and
# the banner always agree on which alert currently wins.
#
# Persisted (not a plain module-level set) so a redeploy/restart can't
# re-toast an alert this process already showed — same reasoning as
# news.py's own news_seen_headlines. Deliberately has NO "first call
# just establishes a baseline, don't alert yet" step the way news.
# get_new_alerts has: that exists there to avoid flooding dozens of
# already-old headlines on a fresh restart, but the failure mode here
# is the opposite and far worse — silently suppressing the one toast
# that matters most (a warning already active the moment a redeploy
# happens to land) is not an acceptable trade for a life-safety feed
# that's supposed to "work consistently."
MAX_SEEN_ALERTS = 200
_seen_alert_keys: dict = dict(persisted_state.load("weather_seen_alerts", {}))


def get_new_alerts() -> list[dict]:
    """New weather alerts since the last check — {"kind": "weather",
    "severity", "label", "headline"}, the toast queue's own generic
    shape (see news.get_new_alerts/sports_alerts.get_new_alerts).
    Keyed by the winning alert's own stable id (ec_alerts.fetch_alerts's
    "id" field for a real EC alert — genuinely unique per issuance,
    embeds the issue timestamp — or its title for the AQHI-synthesized
    alert, which has no id of its own) so a genuinely new issuance
    always toasts even if an alert with the same hazard/title was seen
    before, while an alert that's merely still active from a prior
    rerun never re-toasts. The manual heat/cold fallback (render()'s
    own else branch) is deliberately NOT included — it's a slow-moving
    daily forecast threshold, not a discrete "just came in" moment, and
    current_severity() already treats it as not a real alert for the
    same reason."""
    alerts = _combined_alerts()
    if not alerts:
        return []
    alert = max(alerts, key=_selection_score)
    key = alert.get("id") or alert["title"]
    if key in _seen_alert_keys:
        return []
    _seen_alert_keys[key] = True
    if len(_seen_alert_keys) > MAX_SEEN_ALERTS:
        _seen_alert_keys.pop(next(iter(_seen_alert_keys)))
    persisted_state.save("weather_seen_alerts", _seen_alert_keys)
    return [
        {
            "kind": "weather",
            "severity": _severity(alert["title"]),
            "label": "Environment Canada",
            "headline": alert["title"],
        }
    ]


def render_alert_bar(alert: dict, elapsed: float, variant: str = "a") -> None:
    """Bottom-strip toast for a brand-new weather alert — same stretch-
    then-slide intro as news.render_alert_bar/commute_reminder.
    render_bar (theme.py's toast-*-anim keyframes), colored by severity
    via .weather-alert-bar-* (theme.py), the same palette render()'s own
    .weather-statement-* modifiers use so the toast and the persistent
    banner never disagree about how urgent this looks."""
    delay = f"animation-delay: -{elapsed:.2f}s;"
    bar_class = f"weather-alert-bar weather-alert-bar-{alert['severity']}"
    st.markdown(
        f"""<div class="{bar_class}">
            <span class="news-breaking-label toast-label-anim-{variant}" style="{delay}">{html.escape(alert['label'])}</span>
            <span class="news-alert-headline toast-headline-anim-{variant}" style="{delay}">{html.escape(alert['headline'])}</span>
        </div>""",
        unsafe_allow_html=True,
    )


def _current_alert_and_severity() -> tuple[dict, str] | None:
    alerts = _combined_alerts()
    if not alerts:
        return None
    alert = max(alerts, key=_selection_score)
    return alert, _severity(alert["title"])


def current_storm_phase(now: datetime) -> dict | None:
    """{"phase": "approaching"|"here"|"leaving", "minutes": float,
    "target": datetime} for whichever alert render() would currently
    show, or None — for govee_lighting.sync_lights (session request:
    "red govee flashes for when the storm is approaching... solid red
    at like 30% for when its here... same thing for when the storm is
    leaving") and render_storm_headline below. Thin wrapper around
    ec_storm_timing.storm_phase using the exact same alert selection
    render()/get_new_alerts() already use, so the light, the toast, the
    banner, and the headline never disagree about which alert is "the"
    current one."""
    resolved = _current_alert_and_severity()
    if resolved is None:
        return None
    alert, severity = resolved
    return ec_storm_timing.storm_phase(now, alert["title"], severity)


# "every like 5-10 mins" — the middle of the requested range. Keyed per
# alert id (not persisted — a restart just resets the cadence once,
# acceptable for a repeating reminder rather than a one-shot safety
# notice like get_new_alerts's own persisted dedup) so a brand new storm
# always gets an immediate fresh cycle rather than inheriting whatever's
# left of a previous, unrelated alert's timer.
STORM_PROXIMITY_INTERVAL_SECONDS = 7 * 60
_last_storm_toast: dict[str, float] = {}


def _format_clock(remaining_seconds: float) -> str:
    """H:MM:SS (or MM:SS under an hour) — first-frame value only; the
    element's own data-target-ms/data-format drive the real per-second
    tick from there via app.py's global live-countdown ticker. Same
    shape as commute_reminder._format_clock, duplicated rather than
    imported — this app's own established convention for a small,
    module-specific first-frame formatter (see also pages_jumbotron.
    _fmt_countdown's own copy)."""
    total = max(0, int(remaining_seconds))
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def render_storm_headline(now: datetime) -> None:
    """A standalone bright countdown headline — session request: "can
    we make an APPROACHING: and CLEARING: timer using these values
    pulled from the EC alert for ultimate transparency," modeled
    directly on commute_reminder.render_leave_headline (see
    .storm-headline in theme.py for why it's colored differently).
    "CLEARING" is the user's own word, used for both "here" and
    "leaving" — session correction: "it should say clearing in and
    then a timer to [event_end_datetime] since thats when the message
    actually clears," not only once that instant has already passed
    (the original, narrower "leaving"-only behavior). "APPROACHING"
    still only ever shows for "approaching". Either way the target is
    whatever ec_storm_timing.storm_phase's own "target" says for the
    current phase — "here"'s target IS event_end_datetime itself, so
    this is always counting down to something real and current, never
    a stale or made-up value.

    Ticks for real once a second via app.py's global live-countdown
    ticker, exactly like the leave headline — the text rendered here is
    only ever the first frame's value; data-target-ms drives everything
    after that, straight off ec_storm_timing.storm_phase's own
    "target" datetime (the actual EC-sourced validity_datetime/
    event_end_datetime instant, not a value re-derived from "minutes"
    and therefore never out of sync with it)."""
    resolved = _current_alert_and_severity()
    if resolved is None:
        return
    alert, severity = resolved
    info = ec_storm_timing.storm_phase(now, alert["title"], severity)
    if info is None:
        return
    target_ms = int(info["target"].timestamp() * 1000)
    label = "APPROACHING" if info["phase"] == "approaching" else "CLEARING"
    tier = "extreme" if severity == "extreme" else "warning"
    remaining = max(0.0, info["minutes"] * 60)
    st.markdown(
        f'<div class="storm-headline storm-headline-{tier}"><span class="live-countdown" '
        f'data-target-ms="{target_ms}" data-format="clock" data-template="{label}: {{}}">'
        f'{label}: {_format_clock(remaining)}</span></div>',
        unsafe_allow_html=True,
    )


def get_storm_proximity_alerts(now: datetime) -> list[dict]:
    """Periodic toasts while a storm-grade alert is approaching or
    leaving — session request: "toast alerts for when the storm gets
    closer every like 5-10 mins... same thing for when the storm is
    leaving." Distinct from get_new_alerts's own one-shot "a new alert
    just came in" toast: this repeats on a fixed cadence for as long as
    ec_storm_timing.storm_phase keeps returning "approaching" or
    "leaving" for the current alert, giving a running sense of how
    close it is rather than a single notice. Nothing fires during
    "here" — the steady red light (govee_lighting.sync_lights) is the
    ambient signal for that; a toast every few minutes for something
    already overhead would just be noise, not news."""
    resolved = _current_alert_and_severity()
    if resolved is None:
        return []
    alert, severity = resolved
    phase_info = ec_storm_timing.storm_phase(now, alert["title"], severity)
    if phase_info is None or phase_info["phase"] not in ("approaching", "leaving"):
        return []
    key = alert.get("id") or alert["title"]
    last = _last_storm_toast.get(key, 0.0)
    if time.time() - last < STORM_PROXIMITY_INTERVAL_SECONDS:
        return []
    _last_storm_toast[key] = time.time()
    minutes = round(phase_info["minutes"])
    verb = "expected to arrive in about" if phase_info["phase"] == "approaching" else "expected to clear in about"
    return [
        {
            "kind": "weather",
            "severity": severity,
            "label": "Environment Canada",
            "headline": f"{alert['title']} — {verb} {minutes} min",
        }
    ]
