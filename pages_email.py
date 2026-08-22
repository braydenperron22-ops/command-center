"""Email page: important inbox email seen in the last WINDOW_SECONDS,
flagged for read/unread.

Session request: "Can you make a similar system to the news, but have
every toast alert that comes through for emails go into, like, a little
list there? similar to how the news pages make a separate page with all,
like, the emails. Can you flag if I haven't read it... flag if it's not
read... If the AI deems it important." Mirrors pages_news.py's own
list-page pattern (persisted "first seen" dict, 24h window, newest
first, capped list) rather than reusing get_new_alerts's own toast-only
dedup state, which is per-instance and never replayable on a second
kiosk.

Session follow-up: "make it so that the emails that shows up on the
email page need to be approved by the AI as important which it already
does for the morning brief" — reverses the original "show everything,
like News does" design in favor of matching morning_brief_summary's
and get_new_alerts's own filter exactly: only email_client.is_important
verdicts of True ever make it into _seen_at at all, not just a visual
badge on an otherwise-unfiltered list.

Unread status is the one field here that's genuinely live, not a
"decide once, trust forever" verdict like a headline's category — the
user can read an email on their phone any time, so it's re-read from
email_client's own fetch on every render rather than frozen at first
sight the way the importance verdict deliberately is."""

import html
import time

import streamlit as st

import email_client
import persisted_state

WINDOW_SECONDS = 24 * 60 * 60
MAX_SHOWN = 10

# Same load-once-at-import, persisted_state-backed pattern as
# pages_news.py's own _seen_at — see that file's comment for why
# session-scoped state isn't good enough here either.
_seen_at: dict = persisted_state.load("email_feed_seen_at", {})


def _relative_time(seconds_ago: float) -> str:
    minutes = int(seconds_ago / 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    return f"{hours}h ago"


def render():
    global _seen_at
    st.markdown('<div class="page-title page-title-email">Important Email — Last 24 Hours</div>', unsafe_allow_html=True)

    if not email_client.configured():
        st.markdown(
            '<div class="tile"><div class="tile-prev">Email isn\'t set up yet — GMAIL_ADDRESS/GMAIL_APP_PASSWORD aren\'t in secrets.</div></div>',
            unsafe_allow_html=True,
        )
        return

    now_ts = time.time()
    changed = False

    # cached_recent_important(), not fetch_recent(...) + classify(...)
    # directly — this page render must never be the thing that triggers
    # a real (IMAP connect+fetch, plus a possible Groq classification
    # call) fetch; see email_client's own module comment for the live
    # bug this caused. Already fully classified by warm_daily_feed.
    raw = email_client.cached_recent_important()
    if not raw:
        st.markdown(
            '<div class="tile"><div class="tile-prev">No emails in the last 24 hours.</div></div>',
            unsafe_allow_html=True,
        )
        return

    raw_by_id = {e["message_id"]: e for e in raw}

    for e in raw:
        mid = e["message_id"]
        if mid in _seen_at:
            continue
        # Session request: "the emails that shows up... need to be
        # approved by the AI as important." Not-yet-classified reads as
        # False (email_client.is_important's own docstring), so a
        # genuinely important email that hasn't been judged yet simply
        # isn't added this render — it's still sitting in `raw` on the
        # next one, so it gets picked up the moment classification
        # actually resolves, not lost.
        if not email_client.is_important(mid):
            continue
        _seen_at[mid] = {"from": e["from"], "subject": e["subject"], "first_seen": now_ts}
        changed = True

    for mid in [mid for mid, entry in _seen_at.items() if now_ts - entry["first_seen"] > WINDOW_SECONDS]:
        del _seen_at[mid]
        changed = True

    if changed:
        persisted_state.save("email_feed_seen_at", _seen_at)

    entries = sorted(
        ((mid, entry) for mid, entry in _seen_at.items()),
        key=lambda pair: pair[1]["first_seen"],
        reverse=True,
    )[:MAX_SHOWN]

    if not entries:
        st.markdown(
            '<div class="tile"><div class="tile-prev">No important emails in the last 24 hours.</div></div>',
            unsafe_allow_html=True,
        )
        return

    rows = []
    for mid, entry in entries:
        # Falls back to "read" (there isn't a last-known state to fall
        # back to, so this only matters right at the fetch-window
        # boundary — see fetch_recent's shared 24h lookback above, same
        # window as WINDOW_SECONDS, so this is rare) rather than a
        # missing raw_by_id entry silently reading as unread.
        unread = raw_by_id[mid]["unread"] if mid in raw_by_id else False
        unread_dot = '<span class="email-unread-dot"></span>' if unread else ""
        subject_class = "email-subject-unread" if unread else ""
        # No separate "Important" badge here anymore — every row on this
        # page already is one, so the tag would just repeat itself on
        # every line instead of distinguishing anything. The red
        # left-border row class stays, same visual language as a
        # breaking-news row, since that's still an honest signal here.
        rows.append(
            f'<div class="news-feed-row news-feed-row-breaking">'
            f'<div class="news-feed-headline">{unread_dot}'
            f'<span class="{subject_class}">{html.escape(entry["subject"])}</span></div>'
            f'<div class="news-feed-meta">{html.escape(entry["from"])} · {_relative_time(now_ts - entry["first_seen"])}</div>'
            f"</div>"
        )
    st.markdown(f'<div class="news-feed-list">{"".join(rows)}</div>', unsafe_allow_html=True)
