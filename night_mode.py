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
color-temperature filter over the normal busy dashboard.

Session follow-up: "redesign the night page... make it even better."
User picked "Night Sky" from five real mockups (see the published
artifact from that session) — leans further into *night* rather than
just dimming the day down: a real, computed moon phase (not a generic
decoration — astral.moon.phase, the same library seasons_client.py/
scenery.py already depend on), a fixed starfield, a rare shooting star,
a soft horizon, and a real "sunrise in" countdown computed the same
way scenery.py's own sun-position math already is (locally, via
astral.sun — cheaper and more self-contained than a full weather
fetch, and correctly always means TOMORROW's sunrise, not today's
already-hours-past one, given this view only ever shows 9:30pm-4:30am)."""

import html
import math
import random
from datetime import datetime, timedelta

import streamlit as st
from astral import LocationInfo
from astral.moon import phase as moon_phase
from astral.sun import sun

from config import TIMEZONE, WEATHER_LAT, WEATHER_LON
from icons import label_for

# Same "duplicated rather than shared, this only needs real sun/moon
# math not a full weather fetch" reasoning scenery.py's own _LOCATION
# already documents.
_LOCATION = LocationInfo(latitude=WEATHER_LAT, longitude=WEATHER_LON, timezone=TIMEZONE)

# Each entry is (upper bound of k, name) where k = phase/28, checked in
# order — an 8-phase bucketing centered on the four "exact" moments
# (new=0, first quarter=0.25, full=0.5, last quarter=0.75), each
# spanning +/- 1/16 of the cycle, the same convention most real
# moon-phase calendars use.
_MOON_PHASE_NAMES = [
    (1 / 16, "New Moon"),
    (3 / 16, "Waxing Crescent"),
    (5 / 16, "First Quarter"),
    (7 / 16, "Waxing Gibbous"),
    (9 / 16, "Full Moon"),
    (11 / 16, "Waning Gibbous"),
    (13 / 16, "Last Quarter"),
    (15 / 16, "Waning Crescent"),
    (1.0, "New Moon"),
]


def _moon_visual(now: datetime) -> dict:
    """Real, computed lunar phase rendered as two same-size overlapping
    discs: a "shadow" disc slides across the lit disc, and how far it's
    slid (as a % of the disc's own diameter) is computed straight from
    the real phase, so the crescent/gibbous shape on screen is
    astronomically accurate, not decorative. Negative offset parks the
    shadow to the LEFT (waxing — the growing lit sliver is on the
    right, the conventional reading), positive parks it to the RIGHT
    (waning — lit sliver on the left); both converge smoothly through
    +/-100% at the true full-moon instant (k=0.5), where either side is
    equally "fully clear" — verified against real phase values live
    (e.g. today's actual 16.2/28 = waning gibbous, dark sliver
    correctly on the right) before shipping this."""
    raw = moon_phase(now.date())
    k = (raw % 28.0) / 28.0
    shadow_offset = -200.0 * k if k <= 0.5 else 200.0 * (1.0 - k)
    illumination = round((1 - math.cos(2 * math.pi * k)) / 2 * 100)
    name = next(label for cutoff, label in _MOON_PHASE_NAMES if k <= cutoff)
    return {"offset": shadow_offset, "illumination": illumination, "name": name}


def _next_sunrise(now: datetime) -> datetime | None:
    """The next real sunrise — today's if it hasn't happened yet
    (never true in practice during this view's own 9:30pm-4:30am
    window, but checked honestly rather than assumed), otherwise
    tomorrow's. Computed locally via astral.sun rather than reused from
    weather_client's own daily forecast, which only ever carries
    TODAY's sunrise — already many hours in the past by the time night
    mode is ever actually on screen (confirmed live: at 10:45pm,
    "today's" sunrise was that morning at 6:35am; the one worth showing
    is tomorrow's 6:36am). Returns None on any real failure — never
    worth losing the whole nightstand screen over a sun-position calc."""
    try:
        today = sun(_LOCATION.observer, date=now.date(), tzinfo=_LOCATION.timezone)
        today_sunrise = today["sunrise"].replace(tzinfo=None)
        if today_sunrise > now:
            return today_sunrise
        tomorrow = sun(_LOCATION.observer, date=now.date() + timedelta(days=1), tzinfo=_LOCATION.timezone)
        return tomorrow["sunrise"].replace(tzinfo=None)
    except Exception:
        return None


# Fixed, not re-rolled every rerun — a real sky, considered once, not a
# new random scatter every ~75s. Seed is arbitrary but permanent: this
# exact field is what "the night sky" looks like on this kiosk from now on.
_STAR_FIELD_SEED = 20260830
_STAR_COUNT = 46


def _star_field_html() -> str:
    rng = random.Random(_STAR_FIELD_SEED)
    stars = []
    for _ in range(_STAR_COUNT):
        top = rng.uniform(3, 56)
        left = rng.uniform(2, 98)
        size = rng.uniform(1.0, 2.6)
        opacity = rng.uniform(0.22, 0.82)
        stars.append(
            f'<div class="night-star" style="top:{top:.2f}%;left:{left:.2f}%;'
            f'width:{size:.2f}px;height:{size:.2f}px;opacity:{opacity:.2f};"></div>'
        )
    return "".join(stars)


# Long and rare on purpose — a beautiful, occasional surprise on a
# screen meant to sit quietly next to someone sleeping, not a repeating
# effect that draws the eye. 95s, prime relative to the app's own 75s
# outer autorefresh so it doesn't fall into visual lock-step with it.
_SHOOTING_STAR_CYCLE_SECONDS = 95

_HORIZON_PATH = "M0,40 L0,22 Q40,10 80,18 T160,14 Q200,8 240,16 T320,12 Q360,6 400,14 L400,40 Z"


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
        temp = round(weather["temp_c"])
        condition = html.escape(label_for(weather["weather_code"]))
        low = weather.get("forecast_low_c")
        low_html = f' <span class="night-lowsep">&middot;</span> Low {round(low)}&deg;' if low is not None else ""
        weather_html = f'<div class="night-weatherline"><span class="night-warm">{temp}&deg;</span> {condition}{low_html}</div>'

    sunrise_html = ""
    next_sunrise = _next_sunrise(now)
    if next_sunrise:
        remaining_seconds = max(0, int((next_sunrise - now).total_seconds()))
        hrs, rem = divmod(remaining_seconds, 3600)
        mins = rem // 60
        sunrise_text = f"Sunrise in {hrs}h {mins}m" if hrs > 0 else f"Sunrise in {mins}m"
        sunrise_html = f'<div class="night-sunline">{html.escape(sunrise_text)}</div>'

    moon = _moon_visual(now)

    # Same restart-safe trick as app.py's own rotation-timer-fill-a/-b
    # (theme.py) — Streamlit patches this element's style attribute on
    # the SAME persisted DOM node across reruns rather than replacing
    # it, and mutating animation-delay on an already-running animation
    # is a no-op per the CSS Animations spec, so a freshly-computed
    # delay alone would silently stop taking effect after the first
    # render. Alternating the class name every rerun forces a genuinely
    # new animation instance each time, which does respect the new
    # delay, while the star's own position stays visually continuous
    # from a viewer's perspective in between reruns.
    st.session_state["_night_sky_tick"] = st.session_state.get("_night_sky_tick", 0) + 1
    shoot_variant = "a" if st.session_state["_night_sky_tick"] % 2 == 0 else "b"
    shoot_elapsed = now.timestamp() % _SHOOTING_STAR_CYCLE_SECONDS
    # Confirmed live, two real bugs stacked here: (1) the kill-switch
    # exception rule (.night-shooting-star-a/-b in theme.py) sets
    # `animation` as a shorthand, which resets every sub-property it
    # doesn't mention — including delay — back to 0s, *with* the
    # rule's own !important (a shorthand's !important covers everything
    # it implicitly sets too), silently beating a plain inline delay.
    # (2) Putting `!important` directly in the inline style attribute
    # to fight back doesn't work either — confirmed live that
    # Streamlit's markdown rendering drops the ENTIRE style attribute
    # when its value contains `!important` (a plain, non-important
    # inline style on the exact same element, e.g. .night-mode-overlay
    # elsewhere in this file, survives fine; this one vanished whole).
    # Fix: pass the delay through a CSS custom property instead (not
    # part of the `animation` shorthand, so bug (1) can't touch it; not
    # `!important`, so bug (2) can't strip it) and let theme.py's own
    # separate, external `animation-delay: var(--night-shoot-delay)
    # !important;` longhand — declared purely in the stylesheet, never
    # inline — win the cascade instead.

    overlay_html = ""
    if dim > 0:
        overlay_alpha = dim * 0.82
        overlay_html = f'<div class="night-mode-overlay" style="background:rgba(0,0,0,{overlay_alpha:.3f});"></div>'

    st.markdown(
        f'<div class="night-mode night-mode-sky">'
        f'<div class="night-stars">{_star_field_html()}</div>'
        f'<div class="night-shooting-star night-shooting-star-{shoot_variant}" '
        f'style="--night-shoot-delay:-{shoot_elapsed:.2f}s;"></div>'
        f'<svg class="night-horizon" viewBox="0 0 400 40" preserveAspectRatio="none" aria-hidden="true">'
        f'<path d="{_HORIZON_PATH}" fill="#0A0705"></path>'
        f"</svg>"
        f'<div class="night-content">'
        f'<div class="night-moonwrap">'
        f'<div class="night-moon"><div class="night-moon-shadow" style="transform:translateX({moon["offset"]:.1f}%);"></div></div>'
        f'<div class="night-moonlabel">{html.escape(moon["name"])} &middot; {moon["illumination"]}% lit</div>'
        f"</div>"
        f'<div class="night-clockwrap">'
        f'<div class="night-clock">{time_str}<span class="night-ampm">{ampm}</span></div>'
        f'<div class="night-date">{date_str}</div>'
        f"</div>"
        f'<div class="night-bottomrow">'
        f"{weather_html}"
        f"{sunrise_html}"
        f"</div>"
        f"</div>"
        f"{overlay_html}"
        f"</div>",
        unsafe_allow_html=True,
    )
