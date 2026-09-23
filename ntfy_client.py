"""Push notifications via ntfy.sh — free, no signup, no API key. A
message is just an HTTP POST to a topic URL; the ntfy app on Brayden's
phone (subscribed to that same topic) gets it pushed instantly. Session
request: "how can we get push notifications from the dashboard for
free" — then, correcting an initial presence-gated design: "I wanted
to send me a push notification regardless if I'm home or not" — for
the leave-for-work toast milestones (commute_reminder.check) and
breaking news at the time (news.update_top_alert, since removed —
session request: "take the breaking news out of the notifications"),
unconditionally, not filtered by whether he's actually home. Grew from
those two into most of this app's genuinely severe/rare toast sources
— see each call site's own comment for why it earned a push.

The topic name IS the access control on ntfy's free public server —
anyone who knows it can subscribe to it (or post to it), so NTFY_TOPIC
must be a random, unguessable string, not a memorable name like
"brayden-alerts". Lives in secrets.toml like every other credential in
this app, never hardcoded here.
"""

import time

import requests
import streamlit as st

import persisted_state
from config import DASHBOARD_URL

NTFY_URL = "https://ntfy.sh"
REQUEST_TIMEOUT_SECONDS = 10

# Session request: "anything that I get a notification for on my phone
# I should get a notification for on the TV as well [while I'm on my
# Xbox, not looking at the kiosk] ... not like a breaking news
# headline because I get those for free anywhere else." Every real
# phone push already funnels through this one function -- queuing here
# means any future alert source reaches the TV automatically with zero
# extra wiring, and breaking news (removed from phone push entirely a
# while back, see this module's own docstring) is naturally excluded
# with no special-casing needed, exactly the same as it already is for
# the phone. Capped by both count and age so a kiosk-box outage
# doesn't dump a stale backlog onto the TV screen all at once once it's
# back — read/cleared by lg_tv_control.py on the kiosk box itself, over
# this same shared Upstash store (this Cloud app has no direct line to
# that separate process).
#
# Public (not underscore-prefixed) — session follow-up: "treated like
# the leave-in countdown... bedtime in two hours, bedtime in an hour,
# 30 minutes..." wanted a whole milestone ladder of TV-only toasts,
# with no real phone push at all for each one (the phone already gets
# its own single "Wind down" alert) — sleep_tracker.py calls this
# directly for that, same "promote to public once a second real caller
# exists" convention this app already follows elsewhere (e.g.
# pages_system_health.py's dashboard_stats/kiosk_stats/network_stats).
_TV_QUEUE_KEY = "tv_notification_queue"
_TV_QUEUE_CAP = 20
_TV_QUEUE_MAX_AGE_SECONDS = 10 * 60


def queue_for_tv(title: str, message: str) -> None:
    try:
        now = time.time()
        queue = persisted_state.load(_TV_QUEUE_KEY, [])
        queue = [n for n in queue if now - n.get("at", 0) <= _TV_QUEUE_MAX_AGE_SECONDS]
        queue.append({"title": title, "message": message, "at": now})
        del queue[:-_TV_QUEUE_CAP]
        persisted_state.save(_TV_QUEUE_KEY, queue)
    except Exception:
        pass


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
    queue_for_tv(title, message)
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
