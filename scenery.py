"""Generates a CSS background scene reflecting current weather + time of day."""

# WMO weather_code buckets -> a scene category
def _condition_category(code: int) -> str:
    if code == 0:
        return "clear"
    if code in (1, 2, 3):
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if code in range(51, 68):
        return "rain"
    if code in range(71, 78):
        return "snow"
    if code in (80, 81, 82):
        return "rain"
    if code in (85, 86):
        return "snow"
    if code in range(95, 100):
        return "storm"
    return "cloudy"


_SKY_GRADIENTS = {
    ("clear", True): "linear-gradient(180deg, #4a90d9 0%, #87ceeb 55%, #d4ecf7 100%)",
    ("clear", False): "linear-gradient(180deg, #01020a 0%, #0b1030 55%, #1b2452 100%)",
    ("cloudy", True): "linear-gradient(180deg, #7d8ea0 0%, #a9b7c2 55%, #cfd8dd 100%)",
    ("cloudy", False): "linear-gradient(180deg, #14161f 0%, #262b38 55%, #3a4150 100%)",
    ("fog", True): "linear-gradient(180deg, #b9bdc2 0%, #d3d6d8 60%, #e7e9ea 100%)",
    ("fog", False): "linear-gradient(180deg, #1b1d21 0%, #2c2e33 60%, #40434a 100%)",
    ("rain", True): "linear-gradient(180deg, #4a5866 0%, #6b7d8c 55%, #8a9aa6 100%)",
    ("rain", False): "linear-gradient(180deg, #05070c 0%, #10151f 55%, #1c2430 100%)",
    ("snow", True): "linear-gradient(180deg, #9fb3c8 0%, #cfe0ec 55%, #f2f7fb 100%)",
    ("snow", False): "linear-gradient(180deg, #0c1018 0%, #1c2431 55%, #2f3a4a 100%)",
    ("storm", True): "linear-gradient(180deg, #33394a 0%, #4d5468 55%, #6b7180 100%)",
    ("storm", False): "linear-gradient(180deg, #04040a 0%, #0c0e1a 55%, #171a2b 100%)",
}


def _overlay_layer(category: str, is_day: bool) -> str:
    """Returns the extra animated HTML layer (clouds, rain, snow, stars) for the scene."""
    if category == "clear" and not is_day:
        stars = "".join(
            f'<div class="cc-star" style="left:{(i * 37) % 100}%;top:{(i * 53) % 70}%;'
            f'animation-delay:{(i % 5) * 0.7}s;"></div>'
            for i in range(40)
        )
        return f'<div class="cc-moon"></div>{stars}'
    if category == "clear" and is_day:
        return '<div class="cc-sun"></div>'
    if category in ("cloudy", "fog", "storm"):
        return "".join(
            f'<div class="cc-cloud" style="top:{8 + (i * 11) % 40}%;'
            f'animation-duration:{40 + (i * 7) % 30}s;animation-delay:-{(i * 5) % 20}s;'
            f'transform:scale({0.7 + (i % 4) * 0.2});opacity:{0.5 + (i % 3) * 0.15};"></div>'
            for i in range(6)
        )
    if category == "rain":
        drops = "".join(
            f'<div class="cc-drop" style="left:{(i * 13) % 100}%;'
            f'animation-duration:{0.5 + (i % 5) * 0.15}s;animation-delay:-{(i % 10) * 0.1}s;"></div>'
            for i in range(40)
        )
        return drops
    if category == "snow":
        flakes = "".join(
            f'<div class="cc-flake" style="left:{(i * 17) % 100}%;'
            f'animation-duration:{6 + (i % 6)}s;animation-delay:-{(i % 10) * 0.6}s;"></div>'
            for i in range(35)
        )
        return flakes
    return ""


def background_css_and_html(weather_code: int, is_day: bool) -> str:
    """Full <style> + layer HTML for an animated full-page weather scene."""
    category = _condition_category(weather_code)
    sky = _SKY_GRADIENTS[(category, is_day)]
    overlay = _overlay_layer(category, is_day)

    return f"""
    <style>
    [data-testid="stAppViewContainer"] {{
        background: {sky};
        background-attachment: fixed;
    }}
    [data-testid="stHeader"] {{
        background: transparent;
    }}
    .cc-scene {{
        position: fixed;
        inset: 0;
        z-index: 0;
        overflow: hidden;
        pointer-events: none;
    }}
    .cc-sun {{
        position: absolute; top: 8%; right: 12%;
        width: 90px; height: 90px; border-radius: 50%;
        background: radial-gradient(circle, #fff6d0 0%, #ffe066 60%, rgba(255,224,102,0) 100%);
        box-shadow: 0 0 60px 20px rgba(255, 230, 130, 0.5);
    }}
    .cc-moon {{
        position: absolute; top: 8%; right: 14%;
        width: 60px; height: 60px; border-radius: 50%;
        background: #f2f2e6;
        box-shadow: inset -12px -4px 0 0 #cfcfbf, 0 0 30px 8px rgba(240,240,220,0.3);
    }}
    .cc-star {{
        position: absolute; width: 3px; height: 3px; border-radius: 50%;
        background: white; animation: cc-twinkle 3s ease-in-out infinite;
    }}
    @keyframes cc-twinkle {{ 0%, 100% {{ opacity: 0.2; }} 50% {{ opacity: 1; }} }}
    .cc-cloud {{
        position: absolute; left: -20%; width: 220px; height: 70px;
        background: rgba(255,255,255,0.75); border-radius: 50px;
        animation: cc-drift linear infinite;
    }}
    .cc-cloud::before, .cc-cloud::after {{
        content: ""; position: absolute; background: inherit; border-radius: 50%;
    }}
    .cc-cloud::before {{ width: 110px; height: 110px; top: -50px; left: 25px; }}
    .cc-cloud::after {{ width: 90px; height: 90px; top: -35px; right: 25px; }}
    @keyframes cc-drift {{ from {{ left: -25%; }} to {{ left: 120%; }} }}
    .cc-drop {{
        position: absolute; top: -5%; width: 2px; height: 18px;
        background: rgba(190, 215, 235, 0.7);
        animation: cc-fall linear infinite;
    }}
    @keyframes cc-fall {{ from {{ transform: translateY(0); }} to {{ transform: translateY(110vh); }} }}
    .cc-flake {{
        position: absolute; top: -5%; width: 6px; height: 6px; border-radius: 50%;
        background: rgba(255,255,255,0.9);
        animation: cc-snowfall linear infinite;
    }}
    @keyframes cc-snowfall {{
        from {{ transform: translate(0, 0); }}
        to {{ transform: translate(30px, 110vh); }}
    }}
    .st-key-weather_card, .st-key-agenda_card, .st-key-email_card, .st-key-tasks_card {{
        background: rgba(20, 24, 33, 0.55) !important;
        backdrop-filter: blur(10px);
        border-radius: 14px !important;
        border: 1px solid rgba(255,255,255,0.12) !important;
    }}
    </style>
    <div class="cc-scene">{overlay}</div>
    """
