"""Today Timeline: the whole day on one shared axis instead of the page
rotation — Weather/Commute/Calendar/Markets/Sports each laid out by real
start/end time, styled by real state (already happened / happening right
now / still ahead) rather than a guess.

Session request, after reviewing an approved concept mockup: "That looks
kind of incredible. Yeah. Build that." See config.py's own PAGES comment
for why this stays out of the passive rotation for now — reachable via
?page=timeline and the screen picker instead, same "new, getting lived
with" treatment as any other page pulled out of PAGES on purpose.

Every lane reuses real data already flowing into this app elsewhere —
commute_reminder.timeline_entries, calendar_client.todays_events,
weather_client.cached_hourly_forecast/cached_weather, market_yf_client.
todays_session_window/market_status/quote_for, sports_alerts.
timeline_entries — nothing here fetches anything on its own. Each lane is
wrapped in its own try/except (one source failing dims/omits that lane,
never blanks the page — same discipline _gather_signals-style functions
already use everywhere in this app)."""

import html
from datetime import datetime, timedelta

import streamlit as st

import calendar_client
import commute_reminder
import market_yf_client
import sports_alerts
import weather_client

# Fixed window, same as the approved mockup — a generous span covering
# any realistic day (an early shift, a late game) without needing to be
# sized per-day. Anything genuinely outside it clamps to the near edge
# (_pct) rather than being dropped off the board entirely.
_WINDOW_START_MIN = 5 * 60  # 5:00 AM
_WINDOW_END_MIN = 23 * 60 + 30  # 11:30 PM
_RULER_HOURS = [6, 8, 10, 12, 14, 16, 18, 20, 22]

_SUN_ICON = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="4.5" '
    'stroke="currentColor" stroke-width="2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1'
    'M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
)
_CAR_ICON = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M4 16l1.5-5.5A2 2 0 0 1 7.4 9h9.2'
    'a2 2 0 0 1 1.9 1.5L20 16" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>'
    '<rect x="3" y="16" width="18" height="4" rx="1.2" stroke="currentColor" stroke-width="2"/>'
    '<circle cx="7.5" cy="20" r="1.4" fill="currentColor"/><circle cx="16.5" cy="20" r="1.4" fill="currentColor"/></svg>'
)
_CAL_ICON = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><rect x="3" y="5" width="18" height="16" rx="2" '
    'stroke="currentColor" stroke-width="2"/><path d="M3 10h18M8 3v4M16 3v4" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round"/></svg>'
)
_CHART_ICON = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M4 18V10M10 18V5M16 18v-7M21 18V9" '
    'stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>'
)
_BALL_ICON = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" '
    'stroke="currentColor" stroke-width="2"/><path d="M6 6c2 2 3 4 3 6s-1 4-3 6M18 6c-2 2-3 4-3 6s1 4 3 6" '
    'stroke="currentColor" stroke-width="1.6"/></svg>'
)
_SUNRISE_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M2 18h20M6 18a6 6 0 0 1 12 0" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
_SUNSET_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M2 18h20M18 18a6 6 0 0 0-12 0" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'


def _minutes(dt: datetime) -> float:
    return dt.hour * 60 + dt.minute + dt.second / 60


def _pct(dt: datetime) -> float:
    """0-100 position on the shared axis, clamped to the window's own
    edges — the one piece of real position math every lane (and the
    ruler/gridlines/now-line) shares, so they can never quietly drift
    out of alignment the way the approved mockup's own gridlines
    briefly did (a real bug found and fixed before shipping — see that
    artifact's own history) by each computing their position against a
    different coordinate system."""
    span = _WINDOW_END_MIN - _WINDOW_START_MIN
    return max(0.0, min(100.0, (_minutes(dt) - _WINDOW_START_MIN) / span * 100))


def _compare_now(now: datetime, other: datetime) -> datetime:
    """`now` adjusted to compare safely against `other`, which may be
    naive or timezone-aware depending on its own source — calendar
    events can come back aware (calendar_client coerces a naive DTSTART
    to this app's own zone), while weather/commute/market/sports data
    elsewhere in this app is naive local throughout. Same "stamp `now`
    with the other value's own tzinfo rather than convert" approach
    pages_today.py's own _row_class already uses for the identical
    reason — these are never genuinely different timezones, just
    inconsistent tz-awareness across this app's various data sources."""
    return now.replace(tzinfo=other.tzinfo) if other.tzinfo else now


def _state_class(now: datetime, start: datetime, end: datetime) -> str:
    now_cmp = _compare_now(now, start)
    if end <= now_cmp:
        return "state-past"
    if start <= now_cmp < end:
        return "state-live"
    return "state-upcoming"


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%-I:%M %p")


def _hour_label(hour: int) -> str:
    period = "a" if hour < 12 else "p"
    h12 = hour % 12 or 12
    return f"{h12}{period}"


def _empty_lane(text: str) -> str:
    return f'<span class="lane-empty">{html.escape(text)}</span>'


def _safe_lane(fn, now: datetime) -> str:
    try:
        return fn(now)
    except Exception:
        return _empty_lane("Unavailable right now")


def _weather_lane_html(now: datetime) -> str:
    hourly = weather_client.cached_hourly_forecast() or []
    weather = weather_client.cached_weather() or {}
    parts = []
    if hourly:
        # Real, documented gap, stated honestly rather than faked:
        # hourly_forecast() is filtered to current-hour-onward only
        # (see that function's own docstring) — no historical-
        # intraday-actuals source exists anywhere in this app, so the
        # curve only draws from now onward; the portion of the lane
        # before "now" stays empty rather than inventing a shape for
        # hours already passed.
        temps = [h["temp_c"] for h in hourly]
        lo, hi = min(temps), max(temps)
        temp_span = max(hi - lo, 0.5)

        def y_for(t: float) -> float:
            return 46 - (t - lo) / temp_span * 34

        points = [(_pct(h["at"]), y_for(h["temp_c"])) for h in hourly]
        line = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        fill_path = (
            f"M{points[0][0]:.2f},58 L" + " L".join(f"{x:.2f},{y:.2f}" for x, y in points)
            + f" L{points[-1][0]:.2f},58 Z"
        )
        parts.append(
            '<svg class="weather-svg" viewBox="0 0 100 58" preserveAspectRatio="none">'
            '<defs><linearGradient id="timeline-temp-fill" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0%" stop-color="var(--tl-sun)" stop-opacity="0.35"/>'
            '<stop offset="100%" stop-color="var(--tl-sun)" stop-opacity="0"/></linearGradient></defs>'
            f'<path d="{fill_path}" fill="url(#timeline-temp-fill)"/>'
            f'<polyline points="{line}" fill="none" stroke="var(--tl-sun)" stroke-width="1.4" vector-effect="non-scaling-stroke"/>'
            "</svg>"
        )
        parts.append(f'<div class="weather-now-temp mono" style="left:{_pct(now):.2f}%">{hourly[0]["temp_c"]:.0f}°</div>')
    else:
        parts.append(_empty_lane("Forecast unavailable"))
    sunrise, sunset = weather.get("sunrise"), weather.get("sunset")
    if sunrise is not None:
        parts.append(f'<div class="sun-icon-inline" style="left:{_pct(sunrise):.2f}%">{_SUNRISE_ICON}<span class="mono">{_fmt_time(sunrise)}</span></div>')
    if sunset is not None:
        parts.append(f'<div class="sun-icon-inline" style="left:{_pct(sunset):.2f}%">{_SUNSET_ICON}<span class="mono">{_fmt_time(sunset)}</span></div>')
    return "".join(parts)


def _commute_lane_html(now: datetime) -> str:
    entries = commute_reminder.timeline_entries(now)
    if not entries:
        return _empty_lane("Nothing scheduled")
    parts = []
    for entry in entries:
        leave_by = entry["leave_by"]
        is_past = leave_by <= _compare_now(now, leave_by)
        if entry["is_home"]:
            verb = "Started" if is_past else "Starts"
        else:
            verb = "Left" if is_past else "Leave"
        detail = f"{verb} {_fmt_time(leave_by)}"
        if entry["road"]:
            detail += f' · via {entry["road"]}'
        cls = "state-past" if is_past else "state-upcoming"
        parts.append(
            f'<div class="marker {cls}" style="left:{_pct(leave_by):.2f}%">'
            f'<span class="pin-label mono">{html.escape(entry["label"])} — {html.escape(detail)}</span>'
            '<span class="pin"></span></div>'
        )
    return "".join(parts)


def _calendar_lane_html(now: datetime) -> str:
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return _empty_lane("No calendar connected")
    events = [e for e in calendar_client.todays_events(calendars, now.date()) if not e["all_day"]]
    if not events:
        return _empty_lane("Nothing scheduled")
    parts = []
    for event in events:
        start = event["start"]
        # Known, documented gotcha — never surface event["end"] as real
        # for one of these: a shift-calendar import's own end time is a
        # placeholder, not real data. SHIFT_ASSUMED_LENGTH_HOURS (the
        # same constant commute_reminder's own postgame-notice logic
        # already trusts for this exact situation) stands in instead,
        # rendered visually distinct (dashed, "block-approx") from a
        # real, trustworthy end time.
        if event["show_end_time"]:
            end = event["end"]
            block_cls = "block-solid"
        else:
            end = start + timedelta(hours=commute_reminder.SHIFT_ASSUMED_LENGTH_HOURS)
            block_cls = "block-approx"
        state = _state_class(now, start, end)
        left = _pct(start)
        width = max(_pct(end) - left, 1.4)
        parts.append(
            f'<div class="block {block_cls} {state} mono" style="left:{left:.2f}%;width:{width:.2f}%">'
            f'{html.escape(event["summary"])}</div>'
        )
    return "".join(parts)


def _markets_lane_html(now: datetime) -> str:
    window = market_yf_client.todays_session_window(now)
    if window is None:
        return _empty_lane("Closed today")
    open_dt, close_dt = window
    label = "NYSE"
    try:
        status = market_yf_client.market_status(now)
        quote = market_yf_client.quote_for(market_yf_client.primary_symbol(status))
        if quote and quote.get("intraday") is not None:
            pct = quote["intraday"]
            sign = "+" if pct >= 0 else ""
            label += f" · S&amp;P {sign}{pct:.2f}%"
    except Exception:
        pass
    state = _state_class(now, open_dt, close_dt)
    left = _pct(open_dt)
    width = max(_pct(close_dt) - left, 1.4)
    return f'<div class="block block-solid {state} mono" style="left:{left:.2f}%;width:{width:.2f}%">{label}</div>'


def _sports_lane_html(now: datetime) -> str:
    entries = sports_alerts.timeline_entries(now)
    if not entries:
        return _empty_lane("No game today")
    state_map = {"upcoming": "state-upcoming", "live": "state-live", "final": "state-past"}
    parts = []
    for entry in entries:
        left = _pct(entry["start"])
        width = max(_pct(entry["end"]) - left, 1.4)
        state = state_map.get(entry["state"], "state-upcoming")
        r, g, b = entry["accent"]
        if entry["score"] is not None:
            team_score, opp_score = entry["score"]
            label = f'{entry["abbr"]} {team_score}-{opp_score} {entry["opp_abbr"]}'
        else:
            label = f'{entry["kickoff_label"]} {_fmt_time(entry["start"])}'
        parts.append(
            f'<div class="block block-solid {state} mono" style="left:{left:.2f}%;width:{width:.2f}%;--sport-accent:{r},{g},{b}">'
            f'{html.escape(label)}</div>'
        )
    return "".join(parts)


_LANES = [
    ("weather", "Weather", _SUN_ICON, _weather_lane_html),
    ("commute", "Commute", _CAR_ICON, _commute_lane_html),
    ("calendar", "Calendar", _CAL_ICON, _calendar_lane_html),
    ("markets", "Markets", _CHART_ICON, _markets_lane_html),
    ("sports", "Sports", _BALL_ICON, _sports_lane_html),
]


_LANE_LABEL_WIDTH_PX = 132


def _axis_left(pct: float) -> str:
    """CSS `left` value for anything positioned against the FULL lanes
    box (.timeline-gridlines, .now-line) rather than inside one lane's
    own .lane-track (which already starts 132px in via flex layout, so
    a plain `left:{pct}%` there already lines up for free). Real bug
    caught and fixed in the approved mockup before this was ever
    written as real code: gridlines using a plain left:{pct}% against
    the full-width container landed ~132px further left than the same
    percentage measured inside a lane-track — this calc() keeps every
    element on one shared coordinate system regardless of which
    container it's actually nested in."""
    return f"calc({_LANE_LABEL_WIDTH_PX}px + (100% - {_LANE_LABEL_WIDTH_PX}px) * {pct / 100:.4f})"


def render(now: datetime) -> None:
    hour_marks = [now.replace(hour=h, minute=0, second=0, microsecond=0) for h in _RULER_HOURS]
    ruler = "".join(f'<span class="tick" style="left:{_pct(dt):.2f}%">{_hour_label(h)}</span>' for h, dt in zip(_RULER_HOURS, hour_marks))
    gridlines = "".join(f'<div class="gridline" style="left:{_axis_left(_pct(dt))}"></div>' for dt in hour_marks)
    now_line = f'<div class="now-line" style="left:{_axis_left(_pct(now))}"><span class="now-chip mono">{_fmt_time(now)}</span></div>'
    lane_html = "".join(
        f'<div class="lane" data-lane="{key}"><div class="lane-label">{icon}{label}</div>'
        f'<div class="lane-track">{_safe_lane(fn, now)}</div></div>'
        for key, label, icon, fn in _LANES
    )
    st.markdown(
        f'<div class="timeline-board">'
        f'<div class="timeline-ruler">{ruler}</div>'
        f'<div class="timeline-lanes">'
        f'<div class="timeline-gridlines">{gridlines}</div>'
        f"{now_line}"
        f"{lane_html}"
        "</div></div>",
        unsafe_allow_html=True,
    )
