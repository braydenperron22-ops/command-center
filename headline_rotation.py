"""Unified top-of-screen rotation for every "red headline" — the
leave-in countdown, the storm-proximity countdown, the persistent
weather-statement banner, a road-issue banner, and breaking news —
replacing the old fixed vertical stack (separate pinned slots, most
empty most of the time, stacked at fixed offsets whenever more than
one happened to be active) with one shared slot that cycles through
whichever are currently active, with a real swap animation instead of
everything just sitting there permanently reserved.

Session request: "make it so all the red headlines within the last 2
hours cycle at the top of the screen with a cool animation when it
swaps, make it hard cached in upstash so refreshes dont reset it." "2
hours" isn't a new number invented for this — it's the exact same
TOP_ALERT_HOLD_SECONDS breaking news has always used (news.py's own
render_top_alert_bar/config.py), now applied uniformly across every
source instead of just the one. The Upstash half is real too: news.
py's own top_alert lived in st.session_state until this same session
fixed it (see that module's own comment) — the rotation's own position/
timing state gets the identical treatment here, for the identical
reason: a page reload must never reset which headline is showing or
restart its swap timer.

Follow-up session request: "redesign the top bar... get a clearer
hierarchy going between what's more important" — a distant "leave in 2
hours" (calm) used to get the exact same rotation turn and screen time
as an active road closure (warning), the request's own example. Every
source already computed a real severity tier for its own color; that
tier now ALSO drives ordering (most severe shows first — see
_TIER_PRIORITY) and hold time (more severe, more airtime — see
_TIER_HOLD_SECONDS), and theme.py's own CSS scales font-size by tier
too, so the hierarchy reads at a glance, not just eventually via which
one you happen to catch mid-cycle."""

import html
import time
from datetime import datetime

import streamlit as st

import commute_reminder
import market_circuit_breaker
import persisted_state
import road_conditions_511
import weather_alerts_bar
from config import TOP_ALERT_HOLD_SECONDS

# How long a headline holds the shared slot before swapping, when more
# than one is eligible at once — fallback for a tier not in
# _TIER_HOLD_SECONDS below (shouldn't happen in practice; every real
# candidate carries a real rotation-* class).
SWAP_INTERVAL_SECONDS = 8

# Session request: "redesign the top bar... get a clearer hierarchy
# going between what's more important" — the request's own example was
# a distant "leave in 2 hours" (calm) getting the exact same rotation
# turn and screen time as an active road closure (warning). Every
# candidate already carries a real, server-computed severity class
# (calm/notice/warning/critical) — even the leave candidate's own,
# which _render_candidate below doesn't use for its ON-SCREEN color
# (that stays client-side, live-ticking from data-target-ms) but which
# IS a real, freshly-computed tier same as the other 4 sources, via
# commute_reminder._TIER_TO_ROTATION_CLASS — reused here as the one
# shared severity signal driving both ordering and hold time, instead
# of adding a second, parallel priority system.
_TIER_PRIORITY = {"rotation-critical": 3, "rotation-warning": 2, "rotation-notice": 1, "rotation-calm": 0}
# More important, more airtime — not just seen first, held longer.
# Calm/FYI items still get their turn, just briefly; critical gets
# double a calm item's hold, matching how differently urgent the two
# actually are.
_TIER_HOLD_SECONDS = {"rotation-critical": 16, "rotation-warning": 12, "rotation-notice": 8, "rotation-calm": 5}

# Loaded once at import, not re-fetched every rerun — same per-rerun-
# cost convention as every other persisted dict in this app (news.py's
# own _pushed_headlines, commute_reminder's _shown_state, etc.). Both
# mutated in place and only re-saved on a genuine change below.
_first_seen: dict[str, float] = persisted_state.load("headline_rotation_first_seen", {})
_rotation_state: dict = persisted_state.load(
    "headline_rotation_state", {"order": [], "index": 0, "swap_at": 0.0}
)


def _candidates(now: datetime, weather: dict | None) -> dict[str, dict]:
    """Every currently-active "red headline" source, keyed by a stable
    id — entries with nothing to show are simply absent. Each value:
    {"text", "css_class", "target_ms", "template", "zero_text"} — see
    each source's own *_candidate function for what those mean."""
    out = {}
    leave = commute_reminder.leave_headline_candidate(now)
    if leave is not None:
        out["leave"] = leave
    storm = weather_alerts_bar.storm_headline_candidate(now)
    if storm is not None:
        out["storm"] = storm
    statement = weather_alerts_bar.weather_statement_candidate(weather)
    if statement is not None:
        out["weather_statement"] = statement
    # Session request: "when there's an alert like this, it should
    # have the same red headline effect that a severe weather alert
    # has." Same wiring shape as every other source here.
    road_issue = road_conditions_511.road_closure_headline_candidate(now)
    if road_issue is not None:
        out["road_issue"] = road_issue
    # Session request: "market circuit breaker events... super duper
    # important if it were to happen." rotation-critical unconditionally
    # (see market_circuit_breaker.py's own docstring) — same wiring
    # shape as every other source here.
    circuit_breaker = market_circuit_breaker.circuit_breaker_headline_candidate(now)
    if circuit_breaker is not None:
        out["circuit_breaker"] = circuit_breaker
    # Session request: "breaking news should get its own toast alert"
    # — no longer a candidate here at all. news.get_new_alerts's own
    # one-shot toast (already wired independently into app.py's toast
    # queue) is breaking news's real moment now; the persistent shared
    # slot is reserved for genuinely ongoing/active hazards. See news.
    # update_top_alert's own updated docstring for the full story —
    # top_alert_candidate itself was retired, not just unwired here.
    return out


def _update_first_seen(now_epoch: float, active_keys: set[str]) -> dict[str, float]:
    """Tracks, per source key, the epoch timestamp it FIRST started
    being active — the thing that makes "within the last 2 hours" real,
    literal, and Upstash-persisted for every source uniformly (see this
    module's own docstring for the full "make it hard cached in upstash
    so refreshes dont reset it" story), including the two (weather-
    statement, breaking news) that have no inherent 2-hour bound of
    their own the way the leave/storm countdowns already do.

    Session report: "I find that they don't show for the full two
    hours that they should be, which is kind of annoying." Root cause:
    this used to delete a key from _first_seen the instant it wasn't in
    active_keys for even a single rerun — meaning any one-rerun gap in
    a source computing as "active" (a transient fetch hiccup on
    ec_alerts.fetch_alerts, for instance — nothing rare over a real
    2-hour window) reset its clock back to zero the moment it reappeared,
    even though the real underlying event (the storm, the leave-in
    countdown) never actually stopped. Only ADDS new keys now; never
    proactively removes one just because a source didn't compute as
    active this particular rerun — render()'s own eligibility filter
    already only considers keys present in THIS rerun's real candidates
    (`for key in candidates`), so a key sitting in _first_seen for a
    source that's genuinely not active right now is already inert and
    costs nothing to leave alone. Cleanup instead happens only once an
    entry is old enough that it could never be eligible again regardless
    (past its own 2-hour hold), which both prevents this dict from
    growing forever AND can never fire early."""
    global _first_seen
    changed = False
    for key in active_keys:
        if key not in _first_seen:
            _first_seen[key] = now_epoch
            changed = True
    for key in list(_first_seen):
        if now_epoch - _first_seen[key] > TOP_ALERT_HOLD_SECONDS:
            del _first_seen[key]
            changed = True
    if changed:
        persisted_state.save("headline_rotation_first_seen", _first_seen)
    return _first_seen


def _hold_seconds(candidates: dict[str, dict], key: str) -> float:
    return _TIER_HOLD_SECONDS.get(candidates[key]["css_class"], SWAP_INTERVAL_SECONDS)


def _advance_rotation(now_epoch: float, eligible_keys: list[str], candidates: dict[str, dict]) -> str:
    """Which key currently holds the shared slot — persisted so a page
    reload picks up exactly where the rotation left off instead of
    restarting at the first item with a fresh swap timer. Restarts
    fresh (index 0, a new hold timer sized to THAT item's own tier —
    see _hold_seconds) whenever the eligible SET itself changes shape
    (something new became eligible, or something aged out) — safer
    than trying to preserve an index that might no longer even be in
    range, and simple: the set changing is itself already a real,
    noticeable moment worth resetting the clock on. eligible_keys
    itself already arrives priority-sorted (render()'s own job), so
    index 0 here is always the most important currently-eligible item —
    the one that should show first on a fresh rotation."""
    global _rotation_state
    if _rotation_state.get("order") != eligible_keys:
        _rotation_state = {"order": eligible_keys, "index": 0, "swap_at": now_epoch + _hold_seconds(candidates, eligible_keys[0])}
        persisted_state.save("headline_rotation_state", _rotation_state)
    elif len(eligible_keys) > 1 and now_epoch >= _rotation_state["swap_at"]:
        new_index = (_rotation_state["index"] + 1) % len(eligible_keys)
        hold = _hold_seconds(candidates, eligible_keys[new_index])
        _rotation_state = {"order": eligible_keys, "index": new_index, "swap_at": now_epoch + hold}
        persisted_state.save("headline_rotation_state", _rotation_state)
    return eligible_keys[_rotation_state["index"]]


def render(now: datetime, weather: dict | None) -> bool:
    """Renders the unified rotating headline at the top of the screen
    if anything currently qualifies — returns whether it did, for
    app.py's own hero-row spacer (same contract weather_alerts_bar.
    render used to provide on its own, generalized to all 4 sources).
    `weather` is only needed for the weather-statement candidate's own
    manual heat/cold fallback (see weather_alerts_bar.render's own
    identical parameter)."""
    now_epoch = time.time()
    candidates = _candidates(now, weather)
    first_seen = _update_first_seen(now_epoch, set(candidates))
    # Severity first (see _TIER_PRIORITY — the real hierarchy request),
    # oldest-within-that-tier as the tiebreak — a headline that's been
    # waiting longest still gets first turn among equally-important
    # ones, just no longer outranks something genuinely more urgent
    # only for having shown up earlier.
    eligible_keys = sorted(
        (key for key in candidates if now_epoch - first_seen[key] <= TOP_ALERT_HOLD_SECONDS),
        key=lambda k: (-_TIER_PRIORITY.get(candidates[k]["css_class"], 0), first_seen[k]),
    )
    if not eligible_keys:
        return False
    current_key = _advance_rotation(now_epoch, eligible_keys, candidates)
    _render_candidate(current_key, candidates[current_key])
    return True


def _render_candidate(key: str, candidate: dict) -> None:
    # The leave countdown is the one special case: its color comes from
    # the shared live-countdown ticker's own real-time intensity-* tier
    # (recalculated every second from data-target-ms, via the closest
    # .leave-headline ancestor — a pre-existing coupling, not something
    # introduced here), not from a static server-rendered class the way
    # the other 3 sources work. Carrying BOTH .leave-headline (so that
    # existing lookup still finds it) AND a static rotation-* class
    # would leave two same-specificity color rules fighting over the
    # same element — so leave skips the rotation-* class entirely and
    # relies purely on the existing intensity system for its color,
    # exactly as it already did in its own standalone div.
    if key == "leave":
        css_class = "leave-headline"
    else:
        css_class = candidate["css_class"]
    countdown_attrs = ""
    if candidate["target_ms"] is not None:
        countdown_attrs = (
            f' data-target-ms="{candidate["target_ms"]}" data-format="clock"'
            f' data-template="{candidate["template"]}"'
        )
        if candidate["zero_text"]:
            countdown_attrs += f' data-zero-text="{candidate["zero_text"]}"'
        if key == "leave":
            countdown_attrs += " data-intensity"
    # Audit fix: the storm/leave text is always internally built (a
    # clock string), but the weather-statement and news candidates
    # carry real external text (an EC alert title, an RSS headline) —
    # unescaped, either could break the data-rotate-value attribute
    # outright (a literal " in the headline) or, rarer, inject markup
    # into the page. Escaped once and reused for both the attribute and
    # the visible span, matching how every other external-text render
    # site in this app already does it (e.g. weather_alerts_bar.
    # render_alert_bar's own html.escape calls).
    text = html.escape(candidate["text"])
    # data-rotate-value (not data-fade-value — a deliberately separate
    # attribute from the existing kiosk-jumbo-fade mechanism, so the
    # two scripts never both try to animate the same element) changes
    # whenever either the source or its text changes, so switching
    # sources and a same-source text update (a countdown's own first-
    # frame value ticking over between reruns) both trigger the swap
    # animation the same way.
    st.markdown(
        f"""<div class="headline-rotation {css_class}"
             data-rotate-value="{key}:{text}">
            <span class="live-countdown"{countdown_attrs}>{text}</span>
        </div>""",
        unsafe_allow_html=True,
    )
