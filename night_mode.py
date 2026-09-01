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

    # Session request: "subtle urgency... a little tab that shows it's
    # still active when I wake up" — see _overnight_attention_items's
    # own docstring for what qualifies and why. A plain static tag per
    # item, no animation (this app's own global kill-switch would drop
    # one anyway) and no color escalation beyond the rest of the
    # screen's own warm palette — "subtle" is the whole point, not a
    # second alarm layered onto a screen that's supposed to stay calm.
    attention_html = ""
    attention_items = _overnight_attention_items(now)
    if attention_items:
        tags = "".join(f'<span class="night-attention-item"><span class="night-attention-dot"></span>{html.escape(item)}</span>' for item in attention_items)
        attention_html = f'<div class="night-attention">{tags}</div>'

    st.markdown(
        f'<div class="night-mode">'
        f'<div class="night-clock">{time_str}<span class="night-ampm">{ampm}</span></div>'
        f'<div class="night-date">{date_str}</div>'
        f"{weather_html}"
        f"{attention_html}"
        f"{overlay_html}"
        f"</div>",
        unsafe_allow_html=True,
    )
