"""Renders a scene reflecting current weather + time of day: a realistic
gradient sky (lighter near the horizon, deeper at the zenith), rain/snow
particles, a light vignette for depth, and — at night — pure flat black
with stars scattered across it, no gradient.

No sun or cloud shapes: they were tried both as DOM elements and as
background-image layers baked into the sky gradient, and both still
visibly flashed/popped every second (this app reruns its whole script
every second for the clock tick, which makes anything riding on the
constantly-recomputed background fragile). Dropped entirely in favor of
just the gradient, which has been stable throughout. Rain/snow/star
twinkle remain as actual elements with animation, since those read fine
even when restarted each second (small, subtle, tileable).

The sky color is computed as a server-side interpolation between the
previous phase's colors and the current one, blended by elapsed real
time — NOT a CSS `transition`. A CSS transition can't survive this app's
1-second autorefresh: the whole `<style>` block gets re-emitted fresh on
every rerun, and testing confirmed it causes an instant snap the moment
the phase flips rather than an animated fade (the same class of bug fixed
earlier for the country-rotation crossfade and the breaking-news bar).
"""

from datetime import timedelta

FADE_SECONDS = 90  # quick, not an abrupt cut, but no lingering brightness


def condition_category(code: int) -> str:
    if code == 0:
        return "clear"
    if code in (1, 2, 3):
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if code in range(51, 68) or code in (80, 81, 82):
        return "rain"
    if code in range(71, 78) or code in (85, 86):
        return "snow"
    if code in range(95, 100):
        return "storm"
    return "cloudy"


def phase_for(now, sunrise, sunset, transition_minutes: int = 40, earliest_sunrise_hour: int = 7) -> str:
    """Classify the moment as day / night / sunrise / sunset from real solar times.

    The warm transition only leads UP TO sunset/sunrise — once the actual
    moment passes, it's immediately night/day. No lingering bright "sunset"
    window afterward (a pitch-black room shouldn't still be lit up warm
    40 minutes after the sun's actually down).

    This runs 24/7 in a bedroom, so the sunrise brightening is also clamped
    to never start before `earliest_sunrise_hour` regardless of the real
    astronomical sunrise (which can be well before 6am in summer) — actual
    sunrise still applies as-is if it's naturally later than that floor
    (e.g. winter mornings).
    """
    earliest_sunrise = now.replace(hour=earliest_sunrise_hour, minute=0, second=0, microsecond=0)
    earliest_sunrise += timedelta(minutes=transition_minutes)
    effective_sunrise = max(sunrise, earliest_sunrise)

    minutes_to_sunrise = (effective_sunrise - now).total_seconds() / 60
    minutes_to_sunset = (sunset - now).total_seconds() / 60
    if 0 <= minutes_to_sunset <= transition_minutes:
        return "sunset"
    if 0 <= minutes_to_sunrise <= transition_minutes:
        return "sunrise"
    if effective_sunrise <= now < sunset:
        return "day"
    return "night"


# Three stops each (zenith -> mid -> horizon) for a realistic sky, since
# real skies actually do get lighter/hazier toward the horizon and deeper
# toward the zenith — a single flat color reads as fake. Night is the one
# exception: pure flat black (all three stops identical), per request.
_SKY_STOPS = {
    ("clear", "day"): ("#1c3a5e", "#2f6294", "#5b9bc9"),
    ("cloudy", "day"): ("#2c3a4a", "#46596d", "#6c8298"),
    ("fog", "day"): ("#454e58", "#626d78", "#879098"),
    ("rain", "day"): ("#24313e", "#3c4f60", "#5a7182"),
    ("snow", "day"): ("#33465a", "#526e86", "#82a3b8"),
    ("storm", "day"): ("#262a38", "#3d4456", "#565f74"),
    # Sunrise: cooler, crisper morning light — dusty pink/lavender rather
    # than sunset's deeper, richer orange/red dusk tones.
    "sunrise": ("#2a2648", "#8a6a92", "#f4b876"),
    "sunset": ("#1b2038", "#c1604f", "#ec9f5c"),
    "night": ("#000000", "#000000", "#000000"),
}


def _stops_for(category: str, phase: str) -> tuple[str, str, str]:
    if phase == "night":
        return _SKY_STOPS["night"]
    if phase in ("sunrise", "sunset"):
        return _SKY_STOPS[phase]
    return _SKY_STOPS[(category, "day")]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lerp_hex(a: str, b: str, t: float) -> str:
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


def blended_sky(category: str, from_phase: str, to_phase: str, t: float) -> str:
    """t=0 is fully from_phase, t=1 is fully to_phase. Returns a CSS
    gradient string (night's stops are all black, so it degrades to a
    flat color naturally without any special-casing here)."""
    t = max(0.0, min(1.0, t))
    from_stops = _stops_for(category, from_phase)
    to_stops = _stops_for(category, to_phase)
    stops = [_lerp_hex(f, s, t) for f, s in zip(from_stops, to_stops)]
    return f"linear-gradient(160deg, {stops[0]} 0%, {stops[1]} 50%, {stops[2]} 100%)"


def _particles(category: str) -> str:
    if category == "rain" or category == "storm":
        return "".join(
            f'<div class="cc-drop" style="left:{(i * 13) % 100}%;'
            f'animation-duration:{0.6 + (i % 5) * 0.15}s;animation-delay:-{(i % 10) * 0.1}s;"></div>'
            for i in range(28)
        )
    if category == "snow":
        return "".join(
            f'<div class="cc-flake" style="left:{(i * 17) % 100}%;'
            f'animation-duration:{7 + (i % 6)}s;animation-delay:-{(i % 10) * 0.6}s;"></div>'
            for i in range(24)
        )
    return ""


def _stars(phase: str) -> str:
    """Stars at night regardless of weather category — a fully black sky
    with little stars, as requested, not gated on "clear" conditions."""
    if phase != "night":
        return ""
    return "".join(
        f'<div class="cc-star" style="left:{(i * 37) % 100}%;top:{(i * 53) % 65}%;'
        f'animation-delay:{(i % 5) * 0.9}s;"></div>'
        for i in range(40)
    )


def sky_style(weather_code: int, phase: str, from_phase: str, blend: float) -> str:
    """The sky background — a plain color gradient, no sun/cloud shapes.
    Those were tried as separate DOM elements (flashed on every rerun)
    and then as extra background-image layers baked into this same
    property (still visibly popped) — removed entirely rather than kept
    chasing the rendering glitch, since this app's forced full-page
    rerun every second makes any element or layer riding on the
    constantly-recomputed background fundamentally fragile. The gradient
    itself has been stable throughout, so it's what's left.
    """
    category = condition_category(weather_code)
    sky = blended_sky(category, from_phase, phase, blend)
    return f"""<style>
    [data-testid="stAppViewContainer"] {{
        background: {sky};
        background-attachment: fixed;
    }}
    [data-testid="stHeader"] {{ background: transparent; }}
    </style>"""


def scene_html(weather_code: int, phase: str) -> str:
    """Static CSS rules + decorative scene HTML: stars and rain/snow
    particles (sun/cloud shapes were removed — see `sky_style`). Depends
    only on weather category and phase, not elapsed time, so it stays
    byte-identical between reruns except when phase/condition changes.
    """
    category = condition_category(weather_code)
    particles = _particles(category)
    stars = _stars(phase)

    return f"""
    <style>
    .cc-scene {{ position: fixed; inset: 0; z-index: -1; overflow: hidden; pointer-events: none; }}

    .cc-star {{
        position: absolute; width: 2px; height: 2px; border-radius: 50%;
        background: white; animation: cc-twinkle 4s ease-in-out infinite;
    }}
    @keyframes cc-twinkle {{ 0%, 100% {{ opacity: 0.2; }} 50% {{ opacity: 1; }} }}
    .cc-drop {{
        position: absolute; top: -5%; width: 1.5px; height: 16px;
        background: rgba(180, 205, 230, 0.45);
        animation: cc-fall linear infinite;
    }}
    @keyframes cc-fall {{ from {{ transform: translateY(0); }} to {{ transform: translateY(110vh); }} }}
    .cc-flake {{
        position: absolute; top: -5%; width: 4px; height: 4px; border-radius: 50%;
        background: rgba(255,255,255,0.75);
        animation: cc-snowfall linear infinite;
    }}
    @keyframes cc-snowfall {{
        from {{ transform: translate(0, 0); }}
        to {{ transform: translate(24px, 110vh); }}
    }}

    .cc-vignette {{
        position: absolute; inset: 0;
        background: radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(0,0,0,0.28) 100%);
    }}
    </style>
    <div class="cc-scene">{stars}{particles}<div class="cc-vignette"></div></div>
    """
