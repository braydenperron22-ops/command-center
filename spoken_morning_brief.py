"""A morning brief meant to be SPOKEN aloud, not read on screen — session
request: motion-triggered via a living-room webcam, 5-10am, "when it
hears me wake up, it'll say, like, good morning, sir. I've reviewed
your commute... Highway 17 looks clear this morning. You have X amount
of obligations today... I want it to feel like a digital assistant that
is responsible for me."

Deliberately NOT the same text as the on-screen morning brief
(morning_briefing.py) despite drawing on the identical real facts (via
that module's own gather_facts) — that brief is explicitly, deliberately
written with "Jarvis energy from Iron Man" but the UNHINGED, sarcastic,
roast-him-directly, profanity-permitted version (see its own
_ai_headline_and_body docstring for that whole tuning history). What
was asked for here is closer to the ACTUAL Iron Man Jarvis: formal,
dutiful, "sir," genuinely reviewing things on the user's behalf. Reusing
the on-screen brief's own cached text would mean the first thing said
in the room some mornings is a sarcastic roast, which is not what was
asked for. Two real, separate personalities on purpose, not one reused
verbatim — same as this app already keeping the on-screen brief and
weather_alerts_bar's own spoken alerts in two different voices.

This module only ever produces TEXT — it has no idea how that text
gets spoken (Piper, sounddevice, whatever) and no idea what triggers
it (a webcam's motion detection, a cron job, anything else). That's
deliberate: the camera/motion-detection piece needs real hardware to
build and tune against (none exists yet as of this module's own
creation — see its own session history), so this half is built and
fully testable today, independent of that gap, the same "prove what
you can before the hardware arrives" approach this app's own voice/
package already took with --text-mode."""

from datetime import date, datetime, timedelta

import commute_reminder
import gemini_client
import morning_briefing
import persisted_state
from config import USER_FIRST_NAME

# "Camera turns on between 5am and 10am... turns off after the morning
# brief has run once." This module only exposes the time-window check
# and the once-per-day gate — whatever script actually drives the
# camera decides what "on"/"off" means for the hardware itself.
WINDOW_START_HOUR = 5
WINDOW_END_HOUR = 10

# Session follow-up, before a camera exists at all: "can you find a way
# to reliably detect that I'm awake? without needing a webcam?"
# commute_reminder.screen_wake_time() already answers almost exactly
# this question, for a different existing feature (it's what ends
# night mode and un-pauses the dashboard's own AI features each
# morning) — a real, calendar-grounded "when is the user expected to
# actually be up" time (leave-by minus a buffer, or sleep_tracker's own
# next-commitment estimate), not a guess invented for this feature.
# Reused here as the trigger moment for a SPOKEN brief specifically —
# session request: "make the threshold 30 mins so I'm for sure awake
# when it goes off." screen_wake_time is tuned for waking a SCREEN
# (silent, easy to ignore if early); an audio announcement playing to
# someone still actually asleep is a worse failure than firing a little
# late, so this adds real margin rather than reusing that raw value.
TRIGGER_BUFFER_MINUTES = 30

# Session report: "make it so the spoken brief is aware of time, if its
# stupidly early dont give me the entire shpeel just the necessary
# stuff." A shift that starts at 6am still means a real wake-and-speak
# moment around 5:1X am (screen_wake_time + TRIGGER_BUFFER_MINUTES,
# above) — the full multi-fact rundown is the wrong call at that hour
# even though every individual fact in it is still true. Below this
# hour, only genuinely necessary-to-get-out-the-door facts are eligible
# for the brief at all — an actual filter, not just "keep it short," so
# the AI can't decide a birthday or a market note is worth mentioning
# instead of being trusted to leave it out on its own.
EARLY_HOUR_CUTOFF = 6

# The categories that matter for getting out the door safely and on
# time: an active alert, real driving conditions, the commute itself,
# and the day's actual schedule. Deliberately excludes routine context
# (general weather chat, air quality, markets, birthdays, tonight's
# game, etc.) that's true every single morning regardless of the hour
# and isn't worth a stupidly-early brief's limited attention. Names
# match morning_briefing.gather_facts' own clause-name column exactly.
_ESSENTIAL_FACT_NAMES = {"alert", "precip", "nowcast", "road_ice", "commute", "agenda"}


def is_stupidly_early(now: datetime) -> bool:
    return now.hour < EARLY_HOUR_CUTOFF


def trigger_time(now: datetime) -> datetime | None:
    """The real moment to fire the spoken brief today — screen_wake_time
    plus TRIGGER_BUFFER_MINUTES — or None on a day with no real
    commitment to wake up for at all (screen_wake_time's own contract,
    inherited from sleep_tracker.wake_time_for: "a genuine day off
    doesn't get a synthetic bedtime"). Naive, matching every other
    `now` this app passes around outside sleep_tracker/commute_reminder's
    own internal aware-datetime math."""
    wake = commute_reminder.screen_wake_time(now)
    if wake is None:
        return None
    return wake.replace(tzinfo=None) + timedelta(minutes=TRIGGER_BUFFER_MINUTES)

# Real Gemini call, but no reason to ever generate this twice for the
# same calendar day — once delivered, the facts it was built from are
# already "this morning," not something that meaningfully changes
# again before the window closes. Persisted (not a plain module
# global) so a restart of whatever script calls this doesn't
# re-deliver the same morning's brief a second time.
_LAST_DELIVERED_KEY = "spoken_morning_brief_last_delivered_date"


def in_window(now: datetime) -> bool:
    return WINDOW_START_HOUR <= now.hour < WINDOW_END_HOUR


def already_delivered_today(today: date) -> bool:
    last = persisted_state.load(_LAST_DELIVERED_KEY, None)
    return last == today.isoformat()


def mark_delivered(today: date) -> None:
    persisted_state.save(_LAST_DELIVERED_KEY, today.isoformat())


def _prompt(facts: list[str], terse: bool = False) -> str:
    facts_block = "\n".join(f"- {f}" for f in facts)
    length_instruction = (
        # terse=True: facts is already pre-filtered to just the
        # essential categories (see _ESSENTIAL_FACT_NAMES) — this only
        # needs to ask for BREVITY, not also re-ask it to skip
        # anything, since the non-essential facts were never given to
        # it to skip in the first place.
        "It's stupidly early right now — he needs to get out the door, not sit through a "
        "rundown. One or two short sentences, the bare essentials only: an active alert if "
        "there is one, then the commute and/or his schedule, whichever actually matters. No "
        "pleasantries beyond the greeting itself, no editorializing, nothing beyond what's "
        "strictly useful to know before he leaves."
        if terse else
        "Write it as 3 to 5 short, complete sentences — real full stops for natural spoken "
        "pauses between thoughts, not one long comma-spliced run-on stapled together. This is "
        "the first thing he hears walking into the room — keep it brief enough to actually "
        "listen to, not a recitation of every fact below.\n\n"
        "Pick whichever 3 or 4 facts genuinely matter most for his day. Something genuinely "
        "urgent — an active weather/road alert, a real commute delay — earns the opening line. "
        "On an ordinary day, though, don't default to opening on the commute and closing on "
        "the schedule (or vice versa): those are two facts among several, not bookends with "
        "everything else sandwiched in between. Once you've covered whatever work-related "
        "facts genuinely matter, move on and let something else — weather, a birthday, "
        "tonight's game, whatever's actually there — round the brief out; don't circle back "
        "to another commute/schedule mention as the closing line just because the day happens "
        "to involve work. It's fine, and better, to leave less important facts out entirely "
        "rather than mention everything."
    )
    return (
        f"You are {USER_FIRST_NAME}'s personal assistant, greeting him out loud the moment he "
        f"walks into the room this morning. Address him as \"sir.\" Speak in the first person, "
        f"as someone who has personally already reviewed everything below on his behalf — "
        f"\"I've reviewed your commute,\" \"I can confirm,\" \"you have,\" never a flat, "
        f"impersonal list. Calm, formal, genuinely dutiful — think a butler or an executive "
        f"assistant who takes real pride in being thorough, not a hype man and not sarcastic. "
        f"This will be spoken aloud by a text-to-speech voice, not displayed as text: real "
        f"digits not spelled-out numbers, no headers, no bullet points, no markdown.\n\n"
        f"{length_instruction}\n\n"
        f"Open with a greeting (\"Good morning, sir.\") and never invent anything beyond what's "
        f"given.\n\n"
        f"What you've reviewed this morning:\n{facts_block}\n\n"
        f"Respond with only the spoken paragraph itself, nothing else."
    )


def generate(now: datetime, weather: dict | None, air_quality: dict | None) -> str | None:
    """The full spoken paragraph for this morning, or None if there are
    no real facts to report yet (weather/commute/calendar all still
    unavailable — same "nothing to say yet" case morning_briefing's own
    render() treats as "show nothing") or the AI call itself fails.
    Cached for the whole morning via gemini_client.generate_periodic —
    a caller can call this every few seconds with no real cost; only
    the first call each refresh window is a real request.

    Below EARLY_HOUR_CUTOFF, `facts` is pre-filtered to just
    _ESSENTIAL_FACT_NAMES and the prompt switches to its terse mode
    (see _prompt's own comment) — a stupidly-early morning gets the
    short, necessary-only version, not the full rundown."""
    terse = is_stupidly_early(now)
    facts = morning_briefing.gather_facts(now, weather, air_quality, only=_ESSENTIAL_FACT_NAMES if terse else None)
    if not facts:
        return None
    prompt = _prompt(facts, terse=terse)
    # The real "only once per morning" gate is already_delivered_today/
    # mark_delivered above, which whatever drives the camera is expected
    # to check before calling this at all and record right after
    # successfully speaking the result. This refresh window is just a
    # courtesy safety net against an accidental double-call in quick
    # succession (a retry, a bounce on the motion trigger) reusing the
    # same text instead of spending a second real Gemini call on facts
    # that haven't changed in the last few minutes.
    #
    # Separate cache keys for terse vs. full: generate() can genuinely
    # be called more than once in one morning (a bad tick that returns
    # None doesn't mark delivered, so the next minute's tick tries
    # again) — if that retry happens to straddle EARLY_HOUR_CUTOFF, a
    # shared key would risk handing back a stale terse answer once it's
    # no longer stupidly early, or vice versa.
    feature_key = "spoken_morning_brief_terse" if terse else "spoken_morning_brief"
    text = gemini_client.generate_periodic(
        feature_key, refresh_seconds=4 * 3600, prompt=prompt, temperature=0.6, max_output_tokens=90 if terse else 250
    )
    if text is None:
        return None
    # Session report, live: got yesterday's brief spoken back at him.
    # generate_periodic's own fallback-to-last-good-value on a failed
    # real call (see its own docstring) is the right default for a
    # silent dashboard tile, but this is SPOKEN with "Good morning,
    # sir, I've reviewed your commute" framing -- reading out a stale
    # cross-day fallback as if it were freshly reviewed this morning is
    # actively misleading, not just a little behind. Most likely cause
    # that morning: the kiosk box's own real WiFi instability (already
    # documented elsewhere this session) took out the real Gemini call
    # during the trigger window, same as any other network-dependent
    # feature that morning. Checked here, not inside generate_periodic
    # itself, so every other periodic feature keeps its normal silent-
    # staleness tolerance -- run_spoken_morning_brief._tick already
    # retries next minute on a None, so this just makes it keep
    # retrying instead of speaking something wrong.
    generated_at = gemini_client.periodic_cache_status().get(feature_key)
    if generated_at is None or datetime.fromtimestamp(generated_at).date() != now.date():
        return None
    return text
