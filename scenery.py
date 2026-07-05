"""Generates a soft, abstract CSS background reflecting current weather + time of day."""


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


def phase_for(now, sunrise, sunset, transition_minutes: int = 40) -> str:
    """Classify the moment as day / night / sunrise / sunset from real solar times."""
    to_sunrise = abs((now - sunrise).total_seconds()) / 60
    to_sunset = abs((now - sunset).total_seconds()) / 60
    if to_sunrise <= transition_minutes:
        return "sunrise"
    if to_sunset <= transition_minutes:
        return "sunset"
    if sunrise < now < sunset:
        return "day"
    return "night"


_SKY_GRADIENTS = {
    ("clear", "day"): "linear-gradient(160deg, #1c3a5e 0%, #2f6294 45%, #5b9bc9 100%)",
    ("clear", "night"): "linear-gradient(160deg, #131b30 0%, #1e2c4a 55%, #2c3f61 100%)",
    ("cloudy", "day"): "linear-gradient(160deg, #2c3a4a 0%, #46596d 50%, #6c8298 100%)",
    ("cloudy", "night"): "linear-gradient(160deg, #1a2130 0%, #2a3646 55%, #3d4d5f 100%)",
    ("fog", "day"): "linear-gradient(160deg, #454e58 0%, #626d78 55%, #879098 100%)",
    ("fog", "night"): "linear-gradient(160deg, #232830 0%, #343c46 55%, #48515c 100%)",
    ("rain", "day"): "linear-gradient(160deg, #24313e 0%, #3c4f60 50%, #5a7182 100%)",
    ("rain", "night"): "linear-gradient(160deg, #16202c 0%, #253340 55%, #354553 100%)",
    ("snow", "day"): "linear-gradient(160deg, #33465a 0%, #526e86 50%, #82a3b8 100%)",
    ("snow", "night"): "linear-gradient(160deg, #1c2733 0%, #2f4154 55%, #445a6e 100%)",
    ("storm", "day"): "linear-gradient(160deg, #262a38 0%, #3d4456 50%, #565f74 100%)",
    ("storm", "night"): "linear-gradient(160deg, #17191f 0%, #262a38 55%, #363c4c 100%)",
    # Sunrise/sunset use the same warm sky for every weather category — the
    # horizon glow does the work of distinguishing the moment, clouds/rain/
    # snow still tint the accent below.
    "sunrise": "linear-gradient(160deg, #1c2740 0%, #5a4a6d 38%, #c87862 72%, #f0b972 100%)",
    "sunset": "linear-gradient(160deg, #1b2038 0%, #5d4364 35%, #c1604f 70%, #ec9f5c 100%)",
}

_ACCENT = {
    "clear": "rgba(255, 214, 130, 0.16)",
    "cloudy": "rgba(180, 195, 210, 0.10)",
    "fog": "rgba(200, 205, 210, 0.08)",
    "rain": "rgba(120, 160, 200, 0.14)",
    "snow": "rgba(210, 225, 240, 0.14)",
    "storm": "rgba(160, 140, 210, 0.14)",
}


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


def _stars(phase: str, category: str) -> str:
    if phase != "night" or category != "clear":
        return ""
    return "".join(
        f'<div class="cc-star" style="left:{(i * 37) % 100}%;top:{(i * 53) % 65}%;'
        f'animation-delay:{(i % 5) * 0.9}s;"></div>'
        for i in range(30)
    )


def _horizon_glow(phase: str) -> str:
    """A warm sun disc glowing near the horizon during sunrise/sunset."""
    if phase not in ("sunrise", "sunset"):
        return ""
    side = "left: 20%;" if phase == "sunrise" else "right: 20%;"
    return f'<div class="cc-sun" style="{side}"></div>'


def background_css_and_html(weather_code: int, phase: str) -> str:
    """Full <style> + particle layer HTML for a soft, abstract ambient scene."""
    category = condition_category(weather_code)
    sky_key = phase if phase in ("sunrise", "sunset") else (category, phase)
    sky = _SKY_GRADIENTS[sky_key]
    accent = _ACCENT[category]
    particles = _particles(category)
    stars = _stars(phase, category)
    sun = _horizon_glow(phase)

    return f"""
    <style>
    [data-testid="stAppViewContainer"] {{
        background: {sky};
        background-attachment: fixed;
        transition: background 3s ease;
    }}
    [data-testid="stHeader"] {{ background: transparent; }}
    .cc-scene {{ position: fixed; inset: 0; z-index: 0; overflow: hidden; pointer-events: none; }}
    .cc-glow {{
        position: absolute; width: 60vw; height: 60vw; border-radius: 50%;
        background: radial-gradient(circle, {accent} 0%, rgba(0,0,0,0) 70%);
        filter: blur(10px);
        animation: cc-drift-slow 50s ease-in-out infinite;
    }}
    .cc-glow.a {{ top: -20%; right: -10%; }}
    .cc-glow.b {{ bottom: -25%; left: -15%; animation-duration: 65s; animation-direction: reverse; }}
    @keyframes cc-drift-slow {{
        0%, 100% {{ transform: translate(0, 0) scale(1); }}
        50% {{ transform: translate(-4%, 3%) scale(1.06); }}
    }}
    .cc-sun {{
        position: absolute; bottom: -8vw; width: 26vw; height: 26vw; border-radius: 50%;
        background: radial-gradient(circle, rgba(255, 200, 130, 0.55) 0%, rgba(255, 150, 90, 0.22) 45%, rgba(0,0,0,0) 75%);
        filter: blur(2px);
        animation: cc-sun-pulse 6s ease-in-out infinite;
    }}
    @keyframes cc-sun-pulse {{
        0%, 100% {{ opacity: 0.75; transform: scale(1); }}
        50% {{ opacity: 1; transform: scale(1.08); }}
    }}
    .cc-star {{
        position: absolute; width: 2px; height: 2px; border-radius: 50%;
        background: white; animation: cc-twinkle 4s ease-in-out infinite;
    }}
    @keyframes cc-twinkle {{ 0%, 100% {{ opacity: 0.15; }} 50% {{ opacity: 0.9; }} }}
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
    <div class="cc-scene"><div class="cc-glow a"></div><div class="cc-glow b"></div>{sun}{stars}{particles}</div>
    """
