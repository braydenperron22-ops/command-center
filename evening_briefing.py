"""Tomorrow-preview evening brief — session request: "Do you think we
should have a tomorrow brief that starts at, like, seven or eight PM?
... make sure that the AI is only, like, actually called if we're not
in jumbotron mode... have the AI called to do an evening brief and
kinda let me know what is on the calendar for tomorrow." Session
follow-up on placement: "Same way that the morning brief shows up is
how I wanted to show up. I'm, you know, a little text bar on the main
page. It's nothing crazy."

Same page-independent placement as morning_briefing.render (app.py
calls this right alongside it, gated on the same `not _jumbotron_active`
check) and the exact same small headline+body treatment (reuses
morning_briefing's own .morning-briefing/.morning-headline/.morning-body
CSS directly, not a lookalike copy) — just its own once-a-day evening
window, and a much narrower job: tomorrow's calendar only, not the
whole day's worth of facts morning_briefing.py gathers.

Routed to gemini_client directly, same as morning_briefing's own
_ai_headline_and_body — this is the same kind of short narrated text,
so it gets the same provider choice, not the rest of the app's
Groq-primary default."""

import html
from datetime import datetime, timedelta

import streamlit as st

import calendar_client
import gemini_client
import groq_client
import morning_briefing
from config import USER_FIRST_NAME

# "starts at, like, seven or eight PM" — window, not a single instant,
# same shape as morning_briefing.MORNING_WINDOW_START_HOUR/END_HOUR:
# render() gets called every ~5s rerun regardless of page, and needs
# some real span to actually catch a moment inside it. Ends before a
# realistic bedtime — this is a heads-up for tomorrow, not something
# that should still be trying to appear at midnight.
EVENING_WINDOW_START_HOUR = 19
EVENING_WINDOW_END_HOUR = 23

# Same cadence as morning_briefing.AI_REFRESH_SECONDS — this is a much
# simpler prompt (one calendar fact block, not ten clause sources), but
# there's no reason for it to re-narrate on a tighter schedule than the
# brief it's modeled after when tomorrow's calendar itself is not
# something that changes minute to minute.
AI_REFRESH_SECONDS = 30 * 60


def _tomorrow_agenda_block(now: datetime) -> str | None:
    """morning_briefing.format_agenda_list's own output, for tomorrow's
    date instead of today's — None if calendars aren't configured or
    tomorrow's calendar is genuinely empty (nothing to preview, so
    render() shows nothing at all rather than an empty "you have
    nothing tomorrow" filler no one asked for)."""
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return None
    tomorrow = (now + timedelta(days=1)).date()
    events = [e for e in calendar_client.todays_events(calendars, tomorrow) if not e["all_day"]]
    if not events:
        return None
    events.sort(key=lambda e: e["start"])
    return morning_briefing.format_agenda_list(events)


def _ai_evening_sentence(agenda_block: str) -> tuple[str, str] | None:
    """(headline, body) for tomorrow's preview, or None on any AI
    failure/overnight pause — render() falls back to a plain sentence
    built straight from agenda_block in that case, same "never lose the
    real content just because the phrasing failed" rule
    morning_briefing.render already follows for its own AI step."""
    if groq_client.ai_pulls_paused():
        return None
    prompt = (
        f"You write a short, casual heads-up for tomorrow, shown as a small text block on "
        f"{USER_FIRST_NAME}'s home dashboard tonight — a quick preview of what's coming, not a "
        f"full daily brief. Two parts: a short headline (a few words) and one or two sentences "
        f"naming what's actually on tomorrow's calendar below. Real digits, not spelled-out "
        f"numbers. Never invent anything beyond what's given below. A little personality is fine, "
        f"but keep it brief — this gets glanced at, not read closely.\n\n"
        f"Tomorrow's calendar: {agenda_block}\n\n"
        f'Respond in exactly this shape, nothing else: a headline, then a blank line, then the body.'
    )
    raw = gemini_client.generate_periodic("evening_briefing_sentence", AI_REFRESH_SECONDS, prompt, temperature=0.8, max_output_tokens=200)
    return morning_briefing.parse_headline_body(raw) if raw else None


def render(now: datetime) -> None:
    if not (EVENING_WINDOW_START_HOUR <= now.hour < EVENING_WINDOW_END_HOUR):
        return
    agenda_block = _tomorrow_agenda_block(now)
    if agenda_block is None:
        return

    result = _ai_evening_sentence(agenda_block)
    if result is None:
        headline, body = "Tomorrow", agenda_block[0].upper() + agenda_block[1:] + "."
    else:
        headline, body = result

    st.markdown(
        f'<div class="morning-briefing"><div class="morning-headline">{html.escape(headline)}</div>'
        f'<div class="morning-body">{html.escape(body)}</div></div>',
        unsafe_allow_html=True,
    )
