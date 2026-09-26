"""Shopping list — session request, after ruling out a bunch of
heavier options (a Todoist integration, sharing this app's own Upstash
credentials with a separate Claude project, a voice-assistant tool):
"I just want to find the simplest way to do this. And I don't want to
sign up for a million different things... sometimes I'm on the go...
it'd be nice to be able to do it through my phone." This page IS that —
a plain text box on this same dashboard, reachable from a phone browser
at ?page=shopping, writing straight into this app's own already-
existing Upstash-backed persisted_state. No new account, no new API
token, nothing else to sign up for or hand credentials to.

Not part of the normal PAGES rotation (see config.py) — reached only
via a direct link, same "hidden unless asked for" treatment as the
maintenance page. Unlike the passive, hands-off TV kiosk display (see
the project's own "never pitch interactive controls on the kiosk"
precedent), this page is explicitly for personal phone use — typing
while out — so plain interactive Streamlit widgets are the right tool
here, not a read-only kiosk tile.

No pricing/running-total here yet — that was still an open, harder
question (no free official per-item price API exists) when this page
was built. This is deliberately just the list, so the actually-easy
"can I add to it from my phone" problem shipped without waiting on the
harder one.
"""

import time

import streamlit as st

import persisted_state

_ITEMS_KEY = "shopping_list_items"


def _load_items() -> list[dict]:
    return persisted_state.load(_ITEMS_KEY, [])


def _save_items(items: list[dict]) -> None:
    persisted_state.save(_ITEMS_KEY, items)


def render() -> None:
    st.markdown("## Shopping List")

    items = _load_items()

    with st.form("shopping_add_form", clear_on_submit=True):
        new_item = st.text_input("Add an item", label_visibility="collapsed", placeholder="Add an item…")
        submitted = st.form_submit_button("Add", use_container_width=True)
    if submitted and new_item.strip():
        items.append({"label": new_item.strip(), "added_at": time.time()})
        _save_items(items)
        st.rerun()

    if not items:
        st.caption("Nothing on the list yet.")
        return

    for i, item in enumerate(items):
        col1, col2 = st.columns([5, 1])
        col1.write(item["label"])
        if col2.button("✕", key=f"shopping_remove_{i}", help="Remove"):
            items.pop(i)
            _save_items(items)
            st.rerun()

    st.divider()
    if st.button("Clear list"):
        _save_items([])
        st.rerun()
