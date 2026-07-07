"""Renders a scene reflecting current weather + time of day: a realistic
4-stop gradient sky (deep at the zenith, glowing hazier right at the
horizon), a faint fixed grain texture, rain/snow particles, a sky-tinted
vignette for depth, and — at night — pure flat black with stars scattered
across it, no gradient.

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


# Four stops each (zenith -> upper -> lower -> horizon glow) for a
# realistic sky — real skies get lighter/hazier toward the horizon (a thin
# brighter atmospheric band right at the edge) and deeper toward the
# zenith, so a 3-stop gradient without that final glow read a bit flat.
# Night is the one exception: pure flat black (all four stops identical).
_SKY_STOPS = {
    ("clear", "day"): ("#16304f", "#1c3a5e", "#5b9bc9", "#bcd9e8"),
    ("cloudy", "day"): ("#242e3a", "#2c3a4a", "#6c8298", "#8fa0ae"),
    ("fog", "day"): ("#3c444d", "#454e58", "#879098", "#a8b0b8"),
    ("rain", "day"): ("#1c2734", "#24313e", "#5a7182", "#71889a"),
    ("snow", "day"): ("#2a3c4d", "#33465a", "#82a3b8", "#aecbdb"),
    ("storm", "day"): ("#1f222e", "#262a38", "#565f74", "#6b7690"),
    # Sunrise: cooler, crisper morning light — dusty pink/lavender rather
    # than sunset's deeper, richer orange/red dusk tones.
    "sunrise": ("#221f3c", "#2a2648", "#f4b876", "#fdd9a0"),
    "sunset": ("#151a2e", "#1b2038", "#ec9f5c", "#f8c27a"),
    "night": ("#000000", "#000000", "#000000", "#000000"),
}


def _stops_for(category: str, phase: str) -> tuple[str, str, str, str]:
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


def _blended_stops(category: str, from_phase: str, to_phase: str, t: float) -> list[str]:
    """t=0 is fully from_phase, t=1 is fully to_phase — the blended
    4-color stop list. Night's stops are all black, so it degrades to a
    flat color naturally without any special-casing here. Used by
    sky_style for both the gradient itself and the vignette tint, so
    there's one source of truth for "what color is the sky right now."
    """
    t = max(0.0, min(1.0, t))
    from_stops = _stops_for(category, from_phase)
    to_stops = _stops_for(category, to_phase)
    return [_lerp_hex(f, s, t) for f, s in zip(from_stops, to_stops)]


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
    with little stars, as requested, not gated on "clear" conditions.
    Static (no twinkle animation): a subtle per-star opacity variation
    instead gives natural-looking variety without anything pulsing —
    every other looping animation in the top-of-screen region has been
    removed for the same reason (reads as busy/cheap, not premium)."""
    if phase != "night":
        return ""
    return "".join(
        f'<div class="cc-star" style="left:{(i * 37) % 100}%;top:{(i * 53) % 65}%;'
        f'opacity:{0.35 + (i % 5) * 0.13:.2f};"></div>'
        for i in range(40)
    )


def sky_style(weather_code: int, phase: str, from_phase: str, blend: float) -> str:
    """The sky background — a plain color gradient plus a vignette, both
    as layers on the same persistent background property. No sun/cloud
    shapes: those were tried as separate DOM elements (flashed on every
    rerun) and then as extra background-image layers baked into this same
    property (still visibly popped) — removed entirely rather than kept
    chasing the rendering glitch, since this app's forced full-page rerun
    every second makes any element or layer riding on the
    constantly-recomputed background fundamentally fragile.

    The vignette used to be its own DOM div (in `scene_html`) and had the
    exact same problem — it got fully re-inserted every second right
    alongside the sun/clouds, visibly flashing at the screen edges even
    though it never changes. Moved here as a second background-image
    layer for the same reason the sky gradient itself has always been
    stable: updating a background *property* on an element that already
    exists is just a style change, not a mount/unmount.
    """
    category = condition_category(weather_code)
    stops = _blended_stops(category, from_phase, phase, blend)
    sky = (
        f"linear-gradient(160deg, {stops[0]} 0%, {stops[1]} 45%, "
        f"{stops[2]} 88%, {stops[3]} 100%)"
    )
    # Tinted with the sky's own zenith tone (darkened) rather than flat
    # black — a vignette that's just a shade of the same sky it's edging
    # reads as depth; pure black against a warm sunset sky looked muddy.
    zr, zg, zb = _hex_to_rgb(stops[0])
    vignette_tint = f"rgba({zr // 3}, {zg // 3}, {zb // 3}, 0.5)"
    vignette = f"radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, {vignette_tint} 100%)"
    return f"""<style>
    [data-testid="stAppViewContainer"] {{
        background-image: {vignette}, {sky};
        background-attachment: fixed;
    }}
    [data-testid="stHeader"] {{ background: transparent; }}
    </style>"""


def scene_html(weather_code: int, phase: str) -> str:
    """Static CSS rules + decorative scene HTML: stars and rain/snow
    particles (sun/cloud shapes and the vignette live in `sky_style`
    instead). Depends only on weather category and phase, not elapsed
    time, so it stays byte-identical between reruns except when
    phase/condition changes.
    """
    category = condition_category(weather_code)
    particles = _particles(category)
    stars = _stars(phase)

    return f"""
    <style>
    .cc-scene {{ position: fixed; inset: 0; z-index: -1; overflow: hidden; pointer-events: none; }}

    /* A faint fixed grain over the whole sky — real skies (and good
       wallpaper) aren't perfectly smooth gradients, they have a little
       texture. Purely static (same on every render, no variables), so
       it's exactly as safe as the stars/particles above. */
    .cc-grain {{
        position: absolute; inset: 0;
        background-image: radial-gradient(rgba(255,255,255,0.05) 1px, transparent 1px);
        background-size: 3px 3px;
        opacity: 0.5;
    }}

    .cc-star {{
        position: absolute; width: 2px; height: 2px; border-radius: 50%;
        background: white;
    }}
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
    </style>
    <div class="cc-scene">{stars}{particles}<div class="cc-grain"></div></div>
    """
