"""Minimal single-stroke SVG icons for weather conditions."""

_STROKE = 'fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"'

_ICONS = {
    "clear_day": f'<svg viewBox="0 0 24 24" {_STROKE}><circle cx="12" cy="12" r="4.2"/><path d="M12 2v2.4M12 19.6V22M4.2 4.2l1.7 1.7M18.1 18.1l1.7 1.7M2 12h2.4M19.6 12H22M4.2 19.8l1.7-1.7M18.1 5.9l1.7-1.7"/></svg>',
    "clear_night": f'<svg viewBox="0 0 24 24" {_STROKE}><path d="M20 14.5A8 8 0 1 1 9.5 4a6.4 6.4 0 0 0 10.5 10.5Z"/></svg>',
    "sunrise": f'<svg viewBox="0 0 24 24" {_STROKE}><circle cx="12" cy="14" r="4"/><path d="M12 6v2.4M5.5 10.5l1.5 1.5M18.5 10.5l-1.5 1.5M2 19h20M4 15.5h1M19 15.5h1"/></svg>',
    "sunset": f'<svg viewBox="0 0 24 24" {_STROKE}><circle cx="12" cy="12" r="4"/><path d="M12 4v2.4M5.5 8.5l1.5 1.5M18.5 8.5l-1.5 1.5M2 19h20M4 15.5h1M19 15.5h1"/></svg>',
    "cloudy": f'<svg viewBox="0 0 24 24" {_STROKE}><path d="M7 18.5a4.2 4.2 0 0 1-.7-8.34 5.5 5.5 0 0 1 10.6-1.9A4 4 0 0 1 17 18.5Z"/></svg>',
    "fog": f'<svg viewBox="0 0 24 24" {_STROKE}><path d="M6.5 10.5a4.2 4.2 0 0 1 8-1.7A4 4 0 0 1 16 16.5"/><path d="M4 16.5h16M4 20h16"/></svg>',
    "rain": f'<svg viewBox="0 0 24 24" {_STROKE}><path d="M7 14.5a4.2 4.2 0 0 1-.7-8.34 5.5 5.5 0 0 1 10.6-1.9A4 4 0 0 1 17 14.5Z"/><path d="M8 18v2M12 18v2M16 18v2"/></svg>',
    "snow": f'<svg viewBox="0 0 24 24" {_STROKE}><path d="M7 13.5a4.2 4.2 0 0 1-.7-8.34 5.5 5.5 0 0 1 10.6-1.9A4 4 0 0 1 17 13.5Z"/><path d="M8 18l.01.01M12 19l.01.01M16 18l.01.01"/></svg>',
    "storm": f'<svg viewBox="0 0 24 24" {_STROKE}><path d="M7 13.5a4.2 4.2 0 0 1-.7-8.34 5.5 5.5 0 0 1 10.6-1.9A4 4 0 0 1 17 13.5Z"/><path d="M13 15.5 10.5 19h3l-2 3.5"/></svg>',
}


def icon_for(category: str, phase: str) -> str:
    if category == "clear":
        if phase == "sunrise":
            return _ICONS["sunrise"]
        if phase == "sunset":
            return _ICONS["sunset"]
        return _ICONS["clear_day"] if phase == "day" else _ICONS["clear_night"]
    return _ICONS.get(category, _ICONS["cloudy"])
