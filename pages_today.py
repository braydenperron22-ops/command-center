"""Today page: a personal day-to-day panel, starting with a to-do list
persisted to a shared JSON file rather than session state, so an edit
from your laptop shows up on the always-on kiosk — a separate browser
session entirely.

Room to grow into calendar/commute once those have real data sources
wired in — deliberately not stubbed out here with placeholder tiles
that don't do anything yet.
"""

import hashlib

import streamlit as st

import todo_store
from config import MAX_TODO_ITEMS


def render() -> None:
    st.markdown('<div class="page-title page-title-today">Today</div>', unsafe_allow_html=True)

    items = todo_store.load()

    with st.form("todo_add_form", clear_on_submit=True):
        new_text = st.text_input(
            "Add a to-do", key="todo_input", label_visibility="collapsed", placeholder="Add a to-do…"
        )
        submitted = st.form_submit_button("Add")
    if submitted and new_text.strip():
        items.append({"text": new_text.strip(), "done": False})
        todo_store.save(items)

    if not items:
        st.markdown(
            '<div class="tile"><div class="tile-prev">Nothing on your list — add something above.</div></div>',
            unsafe_allow_html=True,
        )
        return

    items = items[:MAX_TODO_ITEMS]
    changed = False
    for item in items:
        # Keyed by content hash, not list position — a position-based key
        # would let stale checkbox state from a since-removed item bleed
        # onto whatever item now occupies that slot after the list shifts
        # (e.g. right after "Clear completed").
        key = f"todo_{hashlib.sha1(item['text'].encode()).hexdigest()}"
        checked = st.checkbox(item["text"], value=item["done"], key=key)
        if checked != item["done"]:
            item["done"] = checked
            changed = True
    if changed:
        todo_store.save(items)

    if any(item["done"] for item in items):
        if st.button("Clear completed"):
            todo_store.save([item for item in items if not item["done"]])
            st.rerun()
