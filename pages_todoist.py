"""Todoist page — session request: "I found a second use for Todoist...
a wireless way for me to make a to-do list and it gets shipped to the
dashboard... can we make it so the dashboard can actually read that
stuff." Read-only, passive kiosk-tile style (not pages_shopping.py's
own interactive phone-entry widgets) — tasks get added from the
Todoist app itself, on any device, and just show up here. See
todoist_client.py's own docstring for the real API details and why
Groceries/To-Do are two separate Todoist projects, not one list.

Not part of the normal PAGES rotation yet — same "new, not yet lived
with" treatment pages_net_worth.py started with. Reachable via
?page=todoist and the screen picker.
"""

import html

import streamlit as st

import todoist_client

# Todoist's own priority scale: 4 = highest (shown as "Priority 1" in
# their own UI, confusingly inverted from the raw API value) down to
# 1 = none. Red for the real "p1" urgency, fading down from there —
# same gradient-by-severity convention every weather/AQI badge already
# uses, not a new color language for this page.
_PRIORITY_COLOR = {4: "#FF3B30", 3: "#FF9F0A", 2: "#64D2FF"}


def _task_row(task: dict) -> str:
    content = html.escape(task["content"])
    color = _PRIORITY_COLOR.get(task["priority"])
    dot = f'<span style="color:{color}; margin-right:0.5rem;">●</span>' if color else ""
    due_html = ""
    due = task.get("due")
    if due and due.get("string"):
        due_html = f'<span class="tile-prev" style="margin-left:0.6rem;">{html.escape(due["string"])}</span>'
    return (
        f'<div class="market-metric" style="padding:0.5rem 0;">'
        f'<span class="market-metric-label" style="font-size:1rem;">{dot}{content}{due_html}</span>'
        f'</div>'
    )


def _list_tile(title: str, tasks: list[dict]) -> None:
    if not tasks:
        body = '<div class="tile-prev">Nothing on this list right now.</div>'
    else:
        body = "".join(_task_row(t) for t in tasks)
    st.markdown(
        f'<div class="tile"><div class="tile-label">{title.upper()}</div>{body}</div>',
        unsafe_allow_html=True,
    )


def render() -> None:
    st.markdown('<div class="page-title">To-Do</div>', unsafe_allow_html=True)

    if not st.secrets.get("TODOIST_API_TOKEN"):
        st.markdown(
            '<div class="tile"><div class="tile-prev">Todoist not configured yet.</div></div>',
            unsafe_allow_html=True,
        )
        return

    col1, col2 = st.columns(2)
    with col1:
        _list_tile("Groceries", todoist_client.groceries())
    with col2:
        _list_tile("To-Do", todoist_client.todo())
