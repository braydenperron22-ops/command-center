"""Rendering for a single indicator tile."""

import streamlit as st

from config import SIGNIFICANT_Z

BADGE_CLASS = {"hot": "badge-hot", "cool": "badge-cool", "in-line": "badge-inline"}
SEVERITY_FILL_CLASS = {"hot": "severity-fill-hot", "cool": "severity-fill-cool", "in-line": "severity-fill-inline"}
FLASH_CLASS = {"hot": "tile-flash-hot", "cool": "tile-flash-cool"}

# A z-score of this magnitude or beyond fills the severity bar all the way to the edge.
SEVERITY_CAP = 3.0


def render_tile(label: str, unit: str, reading: dict | None, is_new: bool = False):
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

        classification = reading["classification"]
        badge_class = BADGE_CLASS.get(classification, "badge-inline")
        fill_class = SEVERITY_FILL_CLASS.get(classification, "severity-fill-inline")

        z = reading.get("z_score", 0.0)
        magnitude_pct = min(abs(z) / SEVERITY_CAP, 1.0) * 50
        if z >= 0:
            fill_style = f"left: 50%; width: {magnitude_pct:.1f}%;"
        else:
            fill_style = f"left: {50 - magnitude_pct:.1f}%; width: {magnitude_pct:.1f}%;"

        significant = abs(z) >= SIGNIFICANT_Z
        flash_class = FLASH_CLASS.get(classification, "") if significant else ""
        new_badge = '<div class="new-badge">NEW DATA</div>' if is_new else ""

        st.markdown(
            f"""<div class="tile {flash_class}">{new_badge}
                <div class="tile-label">{label}</div>
                <div class="tile-value">{reading['current']:.1f}{unit}</div>
                <div class="tile-prev">previous {reading['previous']:.1f}{unit} · as of {reading['as_of']}</div>
                <div class="badge {badge_class}">{classification}</div>
                <div class="severity-track">
                    <div class="severity-fill {fill_class}" style="{fill_style}"></div>
                </div>
                <div class="severity-caption">{z:+.1f}σ vs trailing trend{' · significant move' if significant else ''}</div>
            </div>""",
            unsafe_allow_html=True,
        )
