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


_SKY_GRADIENTS = {
    ("clear", True): "linear-gradient(160deg, #0e1c33 0%, #1c3a5e 45%, #3f6d95 100%)",
    ("clear", False): "linear-gradient(160deg, #05060d 0%, #0a0f1e 55%, #131a2e 100%)",
    ("cloudy", True): "linear-gradient(160deg, #1a2230 0%, #2c3a4a 50%, #4a5a68 100%)",
    ("cloudy", False): "linear-gradient(160deg, #0a0c12 0%, #171b24 55%, #262c37 100%)",
    ("fog", True): "linear-gradient(160deg, #2b3038 0%, #454b52 55%, #656b71 100%)",
    ("fog", False): "linear-gradient(160deg, #101216 0%, #1e2126 55%, #2e3238 100%)",
    ("rain", True): "linear-gradient(160deg, #131b26 0%, #24313e 50%, #3c4a58 100%)",
    ("rain", False): "linear-gradient(160deg, #04060a 0%, #0c1017 55%, #161d26 100%)",
    ("snow", True): "linear-gradient(160deg, #1c2733 0%, #33465a 50%, #5b7488 100%)",
    ("snow", False): "linear-gradient(160deg, #0a0d14 0%, #171e28 55%, #252f3c 100%)",
    ("storm", True): "linear-gradient(160deg, #14161f 0%, #262a38 50%, #3a3f4e 100%)",
    ("storm", False): "linear-gradient(160deg, #030308 0%, #090a12 55%, #12141f 100%)",
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


def _stars(is_day: bool, category: str) -> str:
    if is_day or category != "clear":
        return ""
    return "".join(
        f'<div class="cc-star" style="left:{(i * 37) % 100}%;top:{(i * 53) % 65}%;'
        f'animation-delay:{(i % 5) * 0.9}s;"></div>'
        for i in range(30)
    )


def background_css_and_html(weather_code: int, is_day: bool) -> str:
    """Full <style> + particle layer HTML for a soft, abstract ambient scene."""
    category = condition_category(weather_code)
    sky = _SKY_GRADIENTS[(category, is_day)]
    accent = _ACCENT[category]
    particles = _particles(category)
    stars = _stars(is_day, category)

    return f"""
    <style>
    [data-testid="stAppViewContainer"] {{
        background: {sky};
        background-attachment: fixed;
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
    <div class="cc-scene"><div class="cc-glow a"></div><div class="cc-glow b"></div>{stars}{particles}</div>
    """
