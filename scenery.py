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
    # A real wildfire-smoke sky, not a weather condition — muted,
    # hazy brown-amber rather than any clean blue or orange, on purpose:
    # actual smoke-choked skies look dirty, not vivid, which is exactly
    # what distinguishes this from a warm sunset at a glance. Only
    # engaged when air_quality_client's reading is genuinely extreme
    # (see app.py), not for routine haze.
    ("smoke", "day"): ("#3a2a1f", "#5c4029", "#a3652f", "#d99248"),
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


def condition_light_color(category: str) -> tuple[int, int, int]:
    """RGB for the bedroom Govee light's environment-mirroring base state
    (see govee_lighting.py) — the same horizon-glow stop (the brightest,
    most saturated of each condition's 4-stop gradient) already used for
    the on-screen sky itself, so the room's ambient color is always
    drawn from the identical source of truth as whatever's actually
    rendered, not a second, separately maintained approximation that
    could quietly drift out of sync with it. Falls back to "cloudy" for
    an unrecognized category rather than raising, since a light with a
    reasonable neutral color beats a crashed rerun."""
    stops = _SKY_STOPS.get((category, "day"), _SKY_STOPS[("cloudy", "day")])
    return _hex_to_rgb(stops[3])


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


# Session request: "add a lot more conditions... a little bit more
# realistic... proper animations for rain or excessive heat or
# whatever." Deliberately does NOT touch condition_category()'s own 6
# buckets — that taxonomy also drives govee_lighting.condition_light_
# color (the bedroom light's color), the daily/hourly forecast
# "category" field (weather_client.py), and ec_forecast's own
# independent text-based classifier, none of which asked for finer
# granularity. Intensity instead comes from the raw WMO weather_code
# ALREADY available to every caller — a real, continuous signal within
# the existing "rain"/"snow" buckets (light drizzle vs. a downpour)
# rather than a new category string that would have to ripple through
# every one of those other consumers too.
def _rain_intensity(code: int) -> float:
    if code in (51, 56, 80):
        return 0.25  # light drizzle
    if code in (53, 57, 61):
        return 0.5  # moderate
    if code in (55, 63, 81):
        return 0.75  # rain
    return 1.0  # 65/66/67/82 — heavy rain, freezing rain, violent showers


def _snow_intensity(code: int) -> float:
    if code in (71, 77):
        return 0.4  # light / snow grains
    if code in (73, 85):
        return 0.65  # moderate / slight showers
    return 1.0  # 75/86 — heavy snow


def _particles(category: str, code: int) -> str:
    if category in ("rain", "storm"):
        # A storm's own rain is always the heaviest tier regardless of
        # its own weather_code (95-99 don't encode rain intensity the
        # way 51-82 do) — matches how storms actually look, not a
        # lighter drizzle under thunder.
        intensity = 1.0 if category == "storm" else _rain_intensity(code)
        count = round(16 + 20 * intensity)
        return "".join(
            f'<div class="cc-drop" style="left:{(i * 13) % 100}%;'
            f'animation-duration:{(1.0 - 0.5 * intensity) + (i % 5) * 0.12:.2f}s;'
            f'animation-delay:-{(i % 10) * 0.1}s;"></div>'
            for i in range(count)
        )
    if category == "snow":
        intensity = _snow_intensity(code)
        count = round(14 + 18 * intensity)
        return "".join(
            f'<div class="cc-flake" style="left:{(i * 17) % 100}%;'
            f'animation-duration:{(10 - 5 * intensity) + (i % 6) * 0.5:.2f}s;'
            f'animation-delay:-{(i % 10) * 0.6}s;"></div>'
            for i in range(count)
        )
    return ""


# Rises rather than falls (opposite of rain/snow) — small warm blurred
# dots drifting up and fading, the same "small, subtle, tileable"
# particle shape already proven stable across reruns (see this module's
# own top docstring), not a literal pixel-distorting heat-haze shader,
# which would be far more expensive for genuinely no more legibility.
def _heat_shimmer() -> str:
    return "".join(
        f'<div class="cc-heat" style="left:{(i * 19) % 100}%;'
        f'animation-duration:{5 + (i % 4)}s;animation-delay:-{(i % 8) * 0.7:.1f}s;"></div>'
        for i in range(16)
    )


# Static-position, opacity-only twinkle (same "no pulsing element reads
# as premium" reasoning the stars above already settled on) rather than
# a moving particle — frost doesn't drift, it just catches the light.
def _cold_sparkle() -> str:
    return "".join(
        f'<div class="cc-frost" style="left:{(i * 23) % 100}%;top:{(i * 31) % 90}%;'
        f'animation-duration:{3 + (i % 4)}s;animation-delay:-{(i % 8) * 0.5:.1f}s;"></div>'
        for i in range(14)
    )


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


def sky_style(category: str, phase: str, from_phase: str, blend: float, temp_extreme: str | None = None) -> str:
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

    Takes an already-resolved category rather than a raw weather code —
    the caller may override it (e.g. app.py forcing "smoke" during a
    genuinely extreme AQI reading), and recomputing from weather_code
    here would silently discard that.

    temp_extreme ("heat"/"cold"/None, from app.py's own real temp_c/
    feels_like_c against config.EXTREME_HEAT_THRESHOLD_C/EXTREME_COLD_
    THRESHOLD_C — the same numbers weather_alerts_bar's own fallback
    banner already uses) adds one more static gradient layer, same safe
    pattern as the vignette above — a subtle warm/cool wash low in the
    frame, not a color swap of the sky itself, which stays entirely
    condition/phase-driven as it always has.
    """
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
    layers = [vignette, sky]
    if temp_extreme == "heat":
        layers.insert(1, "radial-gradient(ellipse 90% 45% at 50% 100%, rgba(255,140,60,0.12), transparent 65%)")
    elif temp_extreme == "cold":
        layers.insert(1, "radial-gradient(ellipse 90% 45% at 50% 100%, rgba(140,200,255,0.12), transparent 65%)")
    return f"""<style>
    [data-testid="stAppViewContainer"] {{
        background-image: {", ".join(layers)};
        background-attachment: fixed;
    }}
    [data-testid="stHeader"] {{ background: transparent; }}
    </style>"""


# How long the storm-flash cycle repeats, in seconds — the ONE new
# effect here that's abrupt/attention-grabbing rather than continuous,
# so a rerun landing mid-flash is the one case actually worth guarding
# against directly (a restarting drift or falling animation just looks
# continuous either way, same as the existing rain/snow already prove).
# Rather than a fixed per-element animation-delay (fine for many small
# staggered particles, useless for one single full-screen flash), the
# delay is computed fresh from real elapsed time-of-day every render —
# so regardless of exactly when a rerun happens to land, the flash's
# rendered phase is always the mathematically correct one for the
# actual current second, and a "restart" is indistinguishable from the
# animation having simply been running the whole time.
_STORM_FLASH_CYCLE_SECONDS = 11


def _storm_flash(now) -> str:
    seconds_of_day = now.hour * 3600 + now.minute * 60 + now.second
    delay = -(seconds_of_day % _STORM_FLASH_CYCLE_SECONDS)
    return f'<div class="cc-lightning" style="animation-delay:{delay}s;"></div>'


# Large, softly blurred, slow side-to-side drift — the "misty" read fog
# actually needs, and it's a `transform` animation on one big element
# rather than the multi-layer background-image sky_style otherwise uses
# for anything static: animating just ONE layer's position within a
# shared, comma-separated background-image property (vignette + sky +
# fog all at once) has no clean way to target a single layer's motion,
# where a dedicated child of the already-proven-safe .cc-scene container
# does. 70s period is slow enough that even a full rerun-triggered
# restart lands within a couple of visual degrees of where it should be.
def _fog_haze() -> str:
    return '<div class="cc-fog"></div>'


def scene_html(category: str, phase: str, code: int, now, temp_extreme: str | None = None) -> str:
    """Static CSS rules + decorative scene HTML: stars, rain/snow/fog/
    heat/cold/lightning (sun/cloud shapes and the vignette live in
    `sky_style` instead). Everything here depends only on category/
    phase/code/temp_extreme, not on anything that changes between
    reruns except the storm flash's own time-synced delay (see
    _storm_flash) — so it stays byte-identical rerun to rerun otherwise,
    same "safe to remount" property the original rain/snow/stars always
    had. Takes an already-resolved category, same reasoning as
    sky_style — a caller's override (e.g. "smoke") has to actually
    reach the render, not get silently recomputed away.
    """
    particles = _particles(category, code)
    stars = _stars(phase)
    fog = _fog_haze() if category == "fog" else ""
    lightning = _storm_flash(now) if category == "storm" else ""
    heat = _heat_shimmer() if temp_extreme == "heat" else ""
    frost = _cold_sparkle() if temp_extreme == "cold" else ""

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

    /* Fog: one large blurred haze layer, slowly swaying — see _fog_haze's
       own comment on why this lives here instead of in sky_style's
       shared background-image property. */
    .cc-fog {{
        position: absolute; inset: -20% -20%;
        background:
            radial-gradient(ellipse 60% 50% at 30% 40%, rgba(255,255,255,0.14), transparent 65%),
            radial-gradient(ellipse 50% 40% at 75% 60%, rgba(255,255,255,0.10), transparent 60%);
        filter: blur(2px);
        animation: cc-drift 70s ease-in-out infinite;
    }}
    @keyframes cc-drift {{
        0%, 100% {{ transform: translateX(-3%); }}
        50% {{ transform: translateX(3%); }}
    }}

    /* Storm: a rare, brief double-flash — see _storm_flash's own
       comment on the time-synced delay that keeps a rerun from ever
       causing a visible restart glitch here specifically. */
    .cc-lightning {{
        position: absolute; inset: 0; background: white;
        animation: cc-flash {_STORM_FLASH_CYCLE_SECONDS}s ease-in-out infinite;
    }}
    @keyframes cc-flash {{
        0%, 91%, 100% {{ opacity: 0; }}
        92% {{ opacity: 0.45; }}
        93% {{ opacity: 0.05; }}
        94% {{ opacity: 0.3; }}
        95% {{ opacity: 0; }}
    }}

    /* Heat: small warm dots rising and fading — opposite direction of
       rain/snow on purpose, same small/subtle/tileable shape already
       proven stable across reruns. */
    .cc-heat {{
        position: absolute; bottom: -5%; width: 10px; height: 10px; border-radius: 50%;
        background: radial-gradient(circle, rgba(255,176,84,0.4), transparent 70%);
        animation: cc-rise linear infinite;
    }}
    @keyframes cc-rise {{
        0% {{ transform: translateY(0); opacity: 0; }}
        15% {{ opacity: 0.55; }}
        85% {{ opacity: 0.55; }}
        100% {{ transform: translateY(-105vh); opacity: 0; }}
    }}

    /* Cold: static-position twinkle, not a moving particle — frost
       doesn't drift, it catches the light. Same "no pulsing element
       reads as premium" reasoning the stars above already settled on,
       deliberately broken here (frost genuinely does catch/lose the
       light) rather than copied blindly. */
    .cc-frost {{
        position: absolute; width: 3px; height: 3px; border-radius: 50%;
        background: rgba(224,242,255,0.85);
        animation: cc-twinkle ease-in-out infinite;
    }}
    @keyframes cc-twinkle {{
        0%, 100% {{ opacity: 0.15; }}
        50% {{ opacity: 0.65; }}
    }}
    </style>
    <div class="cc-scene">{stars}{particles}{fog}{lightning}{heat}{frost}<div class="cc-grain"></div></div>
    """
