"""Push notifications via ntfy.sh — free, no signup, no API key. A
message is just an HTTP POST to a topic URL; the ntfy app on Brayden's
phone (subscribed to that same topic) gets it pushed instantly. Session
request: "how can we get push notifications from the dashboard for
free" — then, correcting an initial presence-gated design: "I wanted
to send me a push notification regardless if I'm home or not" — for
breaking news (news.update_top_alert) and the leave-for-work toast
milestones (commute_reminder.check), unconditionally, not filtered by
whether he's actually home.

The topic name IS the access control on ntfy's free public server —
anyone who knows it can subscribe to it (or post to it), so NTFY_TOPIC
must be a random, unguessable string, not a memorable name like
"brayden-alerts". Lives in secrets.toml like every other credential in
this app, never hardcoded here.
"""

import requests
import streamlit as st

from config import DASHBOARD_URL

NTFY_URL = "https://ntfy.sh"
REQUEST_TIMEOUT_SECONDS = 10


def send(title: str, message: str, priority: str = "default", tags: str | None = None, click: str | bool = True) -> bool:
    """Best-effort push — True on success, False on any failure
    (missing topic, network blip, ntfy itself down). Never raises, same
    "a third-party call must never take a page down" rule every other
    client in this app already follows (see groq_client.generate's own
    docstring). `priority`: ntfy's own scale, "min"/"low"/"default"/
    "high"/"urgent" — urgent also bypasses the phone's silent/DND mode.
    `tags`: ntfy's emoji-shortcode feature (e.g. "rotating_light" for a
    🚨), purely cosmetic, optional.

    `click` — session request: "I should be able to see what my
    dashboard is doing from my phone... like a byproduct of my
    dashboard," not a dead-end text. Sets ntfy's own Click action, so
    tapping the notification opens the URL directly instead of just the
    ntfy app. True (the default) uses DASHBOARD_URL — every caller gets
    a live tap-through for free without needing its own URL. A caller
    can pass a more specific in-app URL instead (a real page/query-
    param deep link, once one exists) or False to omit the header
    entirely for a push that genuinely has nothing worth opening."""
    topic = st.secrets.get("NTFY_TOPIC")
    if not topic:
        return False
    headers = {"Title": title, "Priority": priority}
    if tags:
        headers["Tags"] = tags
    if click:
        headers["Click"] = DASHBOARD_URL if click is True else click
    try:
        resp = requests.post(
            f"{NTFY_URL}/{topic}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return True
    except Exception:
        return False
