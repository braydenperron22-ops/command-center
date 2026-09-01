"""Overnight nightstand display — session request: "because this is on
a regular display now and not a monitor... get rid of the smart plug...
replace [it] by a designated night mode where the display goes dark,
and it's used as like a nightstand display... clock, weather...
minimalist... make the colors friendly on the eyes... as little blue
light as possible."

Replaces govee_lighting.sync_plug (which used to cut power to the
monitor overnight on a fixed 9:30pm-4:30am schedule, with the same
live-game/leave-timer/storm overrides this module's own trigger reuses
— see app.py's own night-mode gating for exactly how). The physical
Govee LIGHT automation is untouched — this is a screen-content change
only ("the lights can stay").

Deliberately warm and dim rather than reusing this app's normal dark
theme as-is: the normal palette leans on blue-white text/accents
(#F5F5F7, #0A84FF) for daytime legibility, exactly the wavelengths
that suppress melatonin and make a 3am glance at the screen actually
wake you up. Every color here is a warm amber/ember tone instead, nothing
above a dim brightness, similar in spirit to a red-light flashlight or
f.lux's own night shift, but applied to fixed content rather than a
color-temperature filter over the normal busy dashboard."""

import html
from datetime import datetime

import streamlit as st

import road_conditions_511
import weather_alerts_bar
from icons import icon_for, label_for


def _overnight_attention_items(now: datetime) -> list[str]:
    """What's still real and worth a glance the moment you wake up —
    session request: "if there's an ongoing special weather statement
    or road closure... something worth my attention overnight, just a
    little tab that shows it's still active." Two real, already-live
    sources, checked fresh on every render (this view reruns like any
    other page): weather_alerts_bar's own current active-alert type,
    and road_conditions_511's own real, route-matched active issues.

    Session follow-up: "make [it] bigger and write it out fully... it's
    not very visible" — this used to be a deliberately generic "Weather
    statement active"/"Road closure active" existence check, on the
    reasoning that the real detail was one page-flip away on Weather/
    Household. Now says the real thing (the actual EC alert type, the
    actual roadway) instead of a placeholder category — still no AI
    rewrite and no new network calls (weather_alerts_bar.current_type_
    label/road_conditions_511.readable_roadway are both cheap, reused
    off data these sources already fetch), so this stays as safe to
    call on every ordinary rerun as the plain existence check was.

    Reaching this function at all already means nothing storm-grade is
    active — a genuine thunderstorm/tornado/hurricane bypasses night
    mode entirely before render() is ever called (see app.py's own
    _night_mode_storm_active gate) — so whatever shows up here is a
    lesser tier (fog, frost, heat, an advisory) that's still real and
    still worth knowing, just not urgent enough to already have kicked
    you off this screen."""
    items = []
    try:
        type_label = weather_alerts_bar.current_type_label()
        if type_label is not None:
            items.append(f"{type_label} active")
    except Exception:
        pass
    try:
        issues = road_conditions_511.road_issues_near_commute(now)
        if issues:
            issue = issues[0]
            roadway = road_conditions_511.readable_roadway(issue["roadway"]) or "Road"
            detail = "closed" if issue["type"] == "road closure" else issue["type"]
            items.append(f"{roadway} {detail}")
    except Exception:
        pass
    return items


def render(now: datetime, weather: dict | None, category: str, phase: str, dim: float = 0.0) -> None:
    """`dim` is app.py's own `night_dim` (0.0-1.0) — the exact same
    value the regular dashboard's own sleep overlay uses. Session
    report: "dim the display to the same extent that it's dimmed
    overnight normally." That regular overlay is a separate, unrelated
    fixed div at z-index:20 — this view's own z-index:10000 (deliberately
    the highest in the app, see its own CSS comment) sits ON TOP of it,
    so the existing overlay was rendering underneath night mode the
    whole time, doing nothing visible. Reapplied here, inside this
    view's own stacking context, with the identical *0.82 multiplier
    so the two are genuinely the same darkness, not just similarly
    dark by coincidence."""
    time_str = now.strftime("%-I:%M").lstrip("0") or "12:00"
    ampm = now.strftime("%p")
    date_str = now.strftime("%A, %B %-d")

    weather_html = ""
    if weather and weather.get("temp_c") is not None:
        icon_svg = icon_for(category, phase)
        temp = round(weather["temp_c"])
        condition = html.escape(label_for(weather["weather_code"]))
        # Tonight's/today's real forecast low, already fetched alongside
        # the current reading (weather_client.fetch_weather) — a
        # genuinely useful nightstand detail ("how cold is it getting")
        # rather than a second network call for something new.
        low = weather.get("forecast_low_c")
        low_html = f'<span class="night-weather-low">Low {round(low)}°</span>' if low is not None else ""
        weather_html = (
            f'<div class="night-weather">'
            f'<span class="night-weather-icon">{icon_svg}</span>'
            f'<span class="night-weather-temp">{temp}°</span>'
            f'<span class="night-weather-cond">{condition}</span>'
            f"{low_html}"
            f"</div>"
        )

    overlay_html = ""
    if dim > 0:
        overlay_alpha = dim * 0.82
        overlay_html = f'<div class="night-mode-overlay" style="background:rgba(0,0,0,{overlay_alpha:.3f});"></div>'

    # Session history on this element: "subtle urgency... a little tab
    # that shows it's still active" (small static corner pill) -> "make
    # it bigger and write it out fully... not very visible in the
    # corner" (bigger pill, real content) -> "like a modified headline
    # bar... dash across the top... without the red or the colors"
    # (tried as a horizontally-scrolling ticker, same mechanism as
    # ticker.py's own bottom market ticker) -> this pass, correcting
    # that last guess: "centered in the middle, please, just like on
    # the main display." The main display's own static, centered,
    # full-width top bar is .headline-rotation, not the scrolling
    # ticker — see .night-ticker's own CSS comment in theme.py for the
    # full history and why only its SHAPE got borrowed, not its
    # severity-tiered coloring ("without the red or the colors" still
    # holds). Static now, so no ticker-scroll animation and no entry in
    # theme.py's global kill-switch exception list either — both
    # removed along with the scrolling version.
    #
    # Multiple simultaneous items (weather + a road closure both
    # active) join on one centered line with a dot separator, rather
    # than each getting their own line or rotating like .headline-
    # rotation's own multi-source rotation does — night mode
    # realistically never has more than two active at once, so one
    # joined line covers it without needing that rotation machinery.
    ticker_html = ""
    attention_items = _overnight_attention_items(now)
    if attention_items:
        separator = '<span class="night-ticker-dot"></span>'
        ticker_html = f'<div class="night-ticker">{separator.join(html.escape(item) for item in attention_items)}</div>'

    st.markdown(
        f'<div class="night-mode">'
        f'<div class="night-clock">{time_str}<span class="night-ampm">{ampm}</span></div>'
        f'<div class="night-date">{date_str}</div>'
        f"{weather_html}"
        f"{ticker_html}"
        f"{overlay_html}"
        f"</div>",
        unsafe_allow_html=True,
    )
