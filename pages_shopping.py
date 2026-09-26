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
from datetime import datetime

import streamlit as st

import persisted_state

_ITEMS_KEY = "shopping_list_items"


def _load_items() -> list[dict]:
    return persisted_state.load(_ITEMS_KEY, [])


def _save_items(items: list[dict]) -> None:
    persisted_state.save(_ITEMS_KEY, items)


# Session request: "make it so that the list automatically clears. On
# Monday night." Fires once, the first rerun at/after CLEAR_HOUR on a
# Monday — keyed by that Monday's own date (not just "did it run
# today") so it can't fire twice for the same week even across the many
# reruns still left in that Monday night. Same load-once-at-import,
# save-only-on-the-real-event shape sleep_tracker's own _pushed_dates
# uses — never call persisted_state.load() on every rerun, only at
# import time and right after an actual write.
MONDAY = 0
CLEAR_HOUR = 21  # 9pm — "Monday night"
_CLEARED_WEEK_KEY = "shopping_list_last_cleared_monday"
_last_cleared_monday: str | None = persisted_state.load(_CLEARED_WEEK_KEY, None)


def maybe_clear_weekly(now: datetime) -> None:
    """Call once per rerun (app.py, unconditional — same shape as
    sleep_tracker.maybe_push_wind_down) regardless of whether the
    shopping page itself is currently open, so the reset actually
    happens even if nobody looks at the list that night."""
    global _last_cleared_monday
    if now.weekday() != MONDAY or now.hour < CLEAR_HOUR:
        return
    today_key = now.date().isoformat()
    if _last_cleared_monday == today_key:
        return
    _save_items([])
    _last_cleared_monday = today_key
    persisted_state.save(_CLEARED_WEEK_KEY, today_key)


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
