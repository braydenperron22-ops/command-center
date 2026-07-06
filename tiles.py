"""Rendering for a single indicator tile."""

import streamlit as st

from config import SIGNIFICANT_Z

# A z-score of this magnitude or beyond fills the severity bar all the way to the edge.
SEVERITY_CAP = 3.0

SPARKLINE_COLOR = {"good": "#32D74B", "bad": "#FF6961", "neutral": "#5AC8FA", "inline": "#9BA0AC"}


def _tone(classification: str, good_direction: str | None) -> tuple[str, str]:
    """Map a direction-neutral (above/below/in-line) classification to a
    display label + tone, using this indicator's good_direction so the
    color actually means something (e.g. above-trend GDP is "improving"
    and green, above-trend unemployment is "worsening" and red — the same
    "above" reading means opposite things depending on the indicator).
    """
    if classification == "in-line":
        return "in-line", "inline"
    if good_direction is None:
        label = "above trend" if classification == "above" else "below trend"
        return label, "neutral"
    favorable = (classification == "above" and good_direction == "up") or (
        classification == "below" and good_direction == "down"
    )
    return ("improving", "good") if favorable else ("worsening", "bad")


def _sparkline_svg(history: list[float], tone: str, width: int = 72, height: int = 28) -> str:
    """A quiet, minimal trend line — no axes/ticks/labels, just the shape."""
    if not history or len(history) < 2:
        return ""
    lo, hi = min(history), max(history)
    span = (hi - lo) or 1.0
    step = width / (len(history) - 1)
    points = " ".join(
        f"{i * step:.1f},{height - ((v - lo) / span) * height:.1f}" for i, v in enumerate(history)
    )
    color = SPARKLINE_COLOR.get(tone, "#9BA0AC")
    return (
        f'<svg class="sparkline" viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
        f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.75" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def render_tile(
    label: str,
    unit: str,
    reading: dict | None,
    good_direction: str | None = None,
    is_new: bool = False,
    extra_line: str | None = None,
):
    with st.container():
        if reading is None:
            st.markdown(
                f"""<div class="tile">
                    <div class="tile-label">{label}</div>
                    <div class="tile-value">—</div>
                    <div class="tile-prev">data unavailable</div>
                </div>""",
                unsafe_allow_html=True,
            )
            return

        display_label, tone = _tone(reading["classification"], good_direction)

        z = reading.get("z_score", 0.0)
        magnitude_pct = min(abs(z) / SEVERITY_CAP, 1.0) * 50
        if z >= 0:
            fill_style = f"left: 50%; width: {magnitude_pct:.1f}%;"
        else:
            fill_style = f"left: {50 - magnitude_pct:.1f}%; width: {magnitude_pct:.1f}%;"

        significant = abs(z) >= SIGNIFICANT_Z
        accent_class = "" if tone == "inline" else f"tile-accent-{tone}"
        significant_class = "tile-significant" if significant and tone != "inline" else ""
        new_badge = '<div class="new-badge">NEW DATA</div>' if is_new else ""
        badge_class = "badge-inline" if tone == "inline" else f"badge-{tone}"
        fill_class = "severity-fill-inline" if tone == "inline" else f"severity-fill-{tone}"
        sparkline = _sparkline_svg(reading.get("history", []), tone)
        # Always reserve this slot's height, populated or not — relying on
        # cross-tile flex stretch to equalize a genuinely-taller tile against
        # its siblings proved unreliable through Streamlit's internal DOM.
        extra_line_html = f'<div class="tile-extra">{extra_line or ""}</div>'

        st.markdown(
            f"""<div class="tile {accent_class} {significant_class}">{new_badge}
                <div class="tile-label">{label}</div>
                <div class="tile-value-row">
                    <div class="tile-value">{reading['current']:.1f}{unit}</div>{sparkline}
                </div>
                <div class="tile-prev">previous {reading['previous']:.1f}{unit} · as of {reading['as_of']}</div>
                <div class="badge {badge_class}">{display_label}</div>
                <div class="severity-track">
                    <div class="severity-fill {fill_class}" style="{fill_style}"></div>
                </div>
                <div class="severity-caption">{z:+.1f}σ vs trailing trend{' · significant move' if significant else ''}</div>{extra_line_html}
            </div>""",
            unsafe_allow_html=True,
        )
