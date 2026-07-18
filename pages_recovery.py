"""Temporary page: wisdom teeth recovery timer. Self-contained HTML/CSS/JS
(see recovery_timer.html) rendered via components.html rather than
st.markdown — it runs its own setInterval clock tick every second, which
needs a real isolated document rather than sharing the dashboard's DOM
(this app's own 5s autorefresh would otherwise tear it down and reset
the interval constantly).

Added at the user's request while actually recovering — stays in the
rotation (see PAGES/PAGE_DURATION_OVERRIDES in config.py) until they ask
for it to come back out, at which point delete this file, recovery_timer.html,
and the "recovery" entries in config.py/app.py.
"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_HTML_PATH = Path(__file__).with_name("recovery_timer.html")


def render() -> None:
    st.markdown('<div class="page-title page-title-recovery">Recovery</div>', unsafe_allow_html=True)
    components.html(_HTML_PATH.read_text(), height=980, scrolling=False)
