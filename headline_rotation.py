"""Unified top-of-screen rotation for every "red headline" — the
leave-in countdown, the storm-proximity countdown, the persistent
weather-statement banner, and breaking news — replacing the old fixed
vertical stack (four separate pinned slots, most empty most of the
time, stacked at fixed offsets whenever more than one happened to be
active) with one shared slot that cycles through whichever are
currently active, with a real swap animation instead of everything
just sitting there permanently reserved.

Session request: "make it so all the red headlines within the last 2
hours cycle at the top of the screen with a cool animation when it
swaps, make it hard cached in upstash so refreshes dont reset it." "2
hours" isn't a new number invented for this — it's the exact same
TOP_ALERT_HOLD_SECONDS breaking news has always used (news.py's own
render_top_alert_bar/config.py), now applied uniformly to all four
sources instead of just the one. The Upstash half is real too: news.
py's own top_alert lived in st.session_state until this same session
fixed it (see that module's own comment) — the rotation's own position/
timing state gets the identical treatment here, for the identical
reason: a page reload must never reset which headline is showing or
restart its swap timer.
"""

import html
import time
from datetime import datetime

import streamlit as st

import commute_reminder
import news
import persisted_state
import weather_alerts_bar
from config import TOP_ALERT_HOLD_SECONDS

# How long each headline holds the shared slot before swapping to the
# next one, when more than one is eligible at once. Long enough to
# actually read a full sentence, short enough that a stack of several
# active headlines all get seen within a reasonable time.
SWAP_INTERVAL_SECONDS = 8

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
    top = news.top_alert_candidate()
    if top is not None:
        out["news"] = top
    return out


def _update_first_seen(now_epoch: float, active_keys: set[str]) -> dict[str, float]:
    """Tracks, per source key, the epoch timestamp it MOST RECENTLY
    started being active — dropped the instant it stops being active,
    so if it comes back later it's treated as newly-seen again, not as
    a continuation of whatever streak it had before. This is what gives
    "within the last 2 hours" real, literal meaning for every source
    uniformly, including the two (weather-statement, breaking news)
    that have no inherent 2-hour bound of their own the way the leave/
    storm countdowns already do."""
    global _first_seen
    changed = False
    for key in list(_first_seen):
        if key not in active_keys:
            del _first_seen[key]
            changed = True
    for key in active_keys:
        if key not in _first_seen:
            _first_seen[key] = now_epoch
            changed = True
    if changed:
        persisted_state.save("headline_rotation_first_seen", _first_seen)
    return _first_seen


def _advance_rotation(now_epoch: float, eligible_keys: list[str]) -> str:
    """Which key currently holds the shared slot — persisted so a page
    reload picks up exactly where the rotation left off instead of
    restarting at the first item with a fresh swap timer. Restarts
    fresh (index 0, a new full SWAP_INTERVAL_SECONDS) whenever the
    eligible SET itself changes shape (something new became eligible,
    or something aged out) — safer than trying to preserve an index
    that might no longer even be in range, and simple: the set changing
    is itself already a real, noticeable moment worth resetting the
    clock on."""
    global _rotation_state
    if _rotation_state.get("order") != eligible_keys:
        _rotation_state = {"order": eligible_keys, "index": 0, "swap_at": now_epoch + SWAP_INTERVAL_SECONDS}
        persisted_state.save("headline_rotation_state", _rotation_state)
    elif len(eligible_keys) > 1 and now_epoch >= _rotation_state["swap_at"]:
        new_index = (_rotation_state["index"] + 1) % len(eligible_keys)
        _rotation_state = {"order": eligible_keys, "index": new_index, "swap_at": now_epoch + SWAP_INTERVAL_SECONDS}
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
    # Oldest-first — a headline that's been waiting longest gets first
    # turn in a newly-formed rotation, rather than an arbitrary order.
    eligible_keys = sorted(
        (key for key in candidates if now_epoch - first_seen[key] <= TOP_ALERT_HOLD_SECONDS),
        key=lambda k: first_seen[k],
    )
    if not eligible_keys:
        return False
    current_key = _advance_rotation(now_epoch, eligible_keys)
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
