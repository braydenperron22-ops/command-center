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
    nothing tomorrow" filler no one asked for).

    Filtered to calendar_client.SELF_OWNER — same "this fact is read in
    first person, so it's only ever Brayden's own calendar" fix as
    morning_briefing._agenda_clause (see calendar_client.SELF_OWNER's
    own comment for the full story)."""
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return None
    tomorrow = (now + timedelta(days=1)).date()
    events = [
        e for e in calendar_client.todays_events(calendars, tomorrow)
        if not e["all_day"] and e.get("owner", calendar_client.SELF_OWNER) == calendar_client.SELF_OWNER
    ]
    if not events:
        return None
    events.sort(key=lambda e: e["start"])
    return morning_briefing.format_agenda_list(events, now)


def _ai_evening_sentence(now: datetime, agenda_block: str) -> tuple[str, str] | None:
    """(headline, body) for tomorrow's preview, or None on any AI
    failure/overnight pause — render() falls back to a plain sentence
    built straight from agenda_block in that case, same "never lose the
    real content just because the phrasing failed" rule
    morning_briefing.render already follows for its own AI step.

    Session report: "that's not AI generated... it doesn't have the
    same charm that the [morning] brief does." It WAS already AI-
    generated — the real bug was a thin prompt, not a silent fallback:
    no personality guidance and no "find a real connection" instruction
    meant the model's safest output was just restating the calendar
    facts in barely different words ("Unpaid Vacation kicks things off
    at 9:00 AM, followed by Saturday Night Hockey at 7:30 PM" — nearly
    identical to the raw agenda_block it was handed). Now reuses
    morning_briefing's own personality-mode rotation (same `now.date()`
    seed as that morning's own brief, so the whole day reads as one
    consistent voice) and an explicit instruction to find a real
    narrative thread between tomorrow's events instead of reciting them
    in order."""
    if groq_client.ai_pulls_paused():
        return None
    mode = morning_briefing.personality_mode(now)
    mode_instruction = morning_briefing._PERSONALITY_MODES[mode]
    prompt = (
        f"You write a short, casual heads-up for tomorrow, shown as a small text block on "
        f"{USER_FIRST_NAME}'s home dashboard tonight — a quick preview of what's coming, not a "
        f"full daily brief.\n\n"
        f"Today's tone, already decided for you rather than your own call (it rotates day to day "
        f"on its own fixed schedule, the same one driving tomorrow morning's own brief, so the "
        f"voice stays consistent across the whole day): {mode_instruction}\n\n"
        f"Two parts: a short headline (a few words) and one or two sentences naming what's "
        f"actually on tomorrow's calendar below. Find a real, specific connection or thread "
        f"between tomorrow's events if one genuinely exists (a slow morning before a late night "
        f"out, a day off bookended by something else) rather than just restating each one "
        f"plainly in order — a flat restatement of the calendar isn't what's wanted here, this "
        f"should read like a real, charming thought, not a list. Still never invent anything "
        f"beyond what's given below. Real digits, not spelled-out numbers.\n\n"
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

    result = _ai_evening_sentence(now, agenda_block)
    if result is None:
        headline, body = "Tomorrow", agenda_block[0].upper() + agenda_block[1:] + "."
    else:
        headline, body = result

    st.markdown(
        f'<div class="morning-briefing"><div class="morning-headline">{html.escape(headline)}</div>'
        f'<div class="morning-body">{html.escape(body)}</div></div>',
        unsafe_allow_html=True,
    )
