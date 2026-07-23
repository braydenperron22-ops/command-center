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

NTFY_URL = "https://ntfy.sh"
REQUEST_TIMEOUT_SECONDS = 10


def send(title: str, message: str, priority: str = "default", tags: str | None = None) -> bool:
    """Best-effort push — True on success, False on any failure
    (missing topic, network blip, ntfy itself down). Never raises, same
    "a third-party call must never take a page down" rule every other
    client in this app already follows (see groq_client.generate's own
    docstring). `priority`: ntfy's own scale, "min"/"low"/"default"/
    "high"/"urgent" — urgent also bypasses the phone's silent/DND mode.
    `tags`: ntfy's emoji-shortcode feature (e.g. "rotating_light" for a
    🚨), purely cosmetic, optional."""
    topic = st.secrets.get("NTFY_TOPIC")
    if not topic:
        return False
    headers = {"Title": title, "Priority": priority}
    if tags:
        headers["Tags"] = tags
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
