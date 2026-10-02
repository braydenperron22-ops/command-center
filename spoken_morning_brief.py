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

from datetime import datetime, timedelta

import commute_reminder
import gemini_client
import holidays_client
import morning_briefing
import persisted_state
import seasons_client
import sleep_tracker
from config import USER_FIRST_NAME

# "Camera turns on between 5am and 10am... turns off after the morning
# brief has run once." This module only exposes the time-window check
# and the once-per-day gate — whatever script actually drives the
# camera decides what "on"/"off" means for the hardware itself.
#
# Live bug, confirmed with real numbers: a noon shift (leave_by
# 11:24am) computes trigger_time at 10:27am — past the old 10am close,
# so run_spoken_morning_brief.py's own in_window check (the cheap gate
# checked BEFORE trigger_time is ever computed, see its own Upstash-
# cost-audit comment for why) would exit before the real trigger moment
# ever arrived, and the brief would silently never fire that day.
# Extended to noon — same boundary sleep_tracker.WAKE_RELEVANT_CUTOFF_
# HOUR already uses elsewhere in this app for "still a real morning
# commitment worth waking up for," not a new, unrelated number —
# comfortably covers trigger_time for any shift up to right around
# noon (TRIGGER_LEAD_MINUTES=57 ahead of leave_by, which itself trails
# the shift start), consistent with the rest of the app already
# treating a shift starting well past noon as not morning-relevant.
WINDOW_START_HOUR = 5
WINDOW_END_HOUR = 12

# Session correction: "change it that the morning brief only plays...
# on the one hour mark of my first obligation of the day." Was
# screen_wake_time + TRIGGER_BUFFER_MINUTES (leave-by minus 90, plus a
# 30-minute safety margin, tuned for "make sure I'm for sure awake when
# it goes off") — replaced entirely with sleep_tracker.wake_time_for's
# own plain "commitment start minus one hour" moment, no added margin,
# exactly what was asked for. The old margin's reasoning (a screen
# lighting up early is easy to ignore, but a voice announcement playing
# to someone still asleep is a worse failure) no longer applies now
# that the trigger moment is explicitly defined by the user, not
# derived from a screen-wake heuristic.

# Session report: "make it so the spoken brief is aware of time, if its
# stupidly early dont give me the entire shpeel just the necessary
# stuff," later refined: "if it's a really early obligation, give me a
# shorter version... anything after seven a.m. can get the full brief."
# Below this hour, only genuinely necessary-to-get-out-the-door facts
# are eligible for the brief at all — an actual filter, not just "keep
# it short," so the AI can't decide a birthday or a market note is
# worth mentioning instead of being trusted to leave it out on its own.
# Checked against trigger_time's own hour (the real first-obligation-
# minus-an-hour moment), not whatever the wall clock happens to read
# when this actually runs — those are normally the same minute, but a
# polling loop landing a little late right at the boundary shouldn't
# flip which version gets generated.
EARLY_HOUR_CUTOFF = 7

# The categories that matter for getting out the door safely and on
# time: an active alert, real driving conditions, the commute itself,
# and the day's actual schedule. Deliberately excludes routine context
# (general weather chat, air quality, markets, birthdays, tonight's
# game, etc.) that's true every single morning regardless of the hour
# and isn't worth a stupidly-early brief's limited attention. Names
# match morning_briefing.gather_facts' own clause-name column exactly.
_ESSENTIAL_FACT_NAMES = {"alert", "precip", "nowcast", "road_ice", "commute", "agenda"}


# Session correction, right after the above shipped: "spoken brief
# should be when the leave-in timer for my first obligation hits an
# hour, not one hour before my first [obligation]." leave_by_time
# already accounts for the real commute, so "leave-in timer hits 60"
# is leave_by minus this, not the raw commitment start minus this —
# same relationship get_up_time (commute_reminder.py) already has to
# the countdown the user actually watches, just a 60-minute lead
# instead of 90.
#
# Bug report, right after THAT shipped: "if it fires at the one hour
# mark... it usually gets cut off by the leave in an hour spoken
# thing." commute_reminder's own leave-timer has its own real spoken
# alert at the exact 60-minute milestone (MILESTONES_MINUTES) — firing
# the brief at that identical instant meant the two spoken alerts
# collided and one cut the other off. 57, not 60, gives the leave-timer
# alert a real 3-minute head start to finish before the brief starts.
TRIGGER_LEAD_MINUTES = 57


def trigger_time(now: datetime) -> datetime | None:
    """The real moment to fire the spoken brief today — TRIGGER_LEAD_
    MINUTES before today's real leave-by time (when the leave-in
    countdown itself would read "1:00:00"), or sleep_tracker.
    wake_time_for as the fallback whenever there's no leave-by
    available (no shift today, or the commute estimate isn't up —
    degrading to the commitment's own start time minus the same lead,
    never nothing). None on a day with no real commitment to wake up
    for at all. Naive, matching every other `now` this app passes
    around outside sleep_tracker/commute_reminder's own internal
    aware-datetime math."""
    leave_by = commute_reminder.leave_by_time(now)
    if leave_by is not None:
        wake = leave_by - timedelta(minutes=TRIGGER_LEAD_MINUTES)
    else:
        wake = sleep_tracker.wake_time_for(now)
    if wake is None:
        return None
    return wake.replace(tzinfo=None) if wake.tzinfo else wake


def is_stupidly_early(now: datetime) -> bool:
    trigger = trigger_time(now)
    if trigger is None:
        return False
    return trigger.hour < EARLY_HOUR_CUTOFF

# Real Gemini call, but no reason to ever generate this twice for the
# same SHIFT — once delivered, the facts it was built from are already
# "this morning," not something that meaningfully changes again before
# that shift's own window closes. Persisted (not a plain module
# global) so a restart of whatever script calls this doesn't
# re-deliver the same shift's brief a second time.
#
# Session request: "make it so that the shorter brief happens before
# the gym, and then the bigger brief happens before work." Was keyed
# by plain calendar date alone — a day with two real obligations (gym,
# then work) only ever got ONE delivery, whichever fired first, since
# the whole day shared one flag. commute_reminder.leave_by_time (and
# therefore trigger_time below) already naturally advances from gym's
# leave_by to work's once gym's own window closes (see
# commute_reminder._current_shift) — the missing piece was purely this
# dedup gate treating the whole day as one slot instead of one slot
# PER shift. Now keyed by commute_reminder.current_shift_identity
# (that shift's own start time, stable across a live commute estimate
# refining by a minute or two — see that function's own docstring for
# why leave_by itself isn't safe to key off directly), so gym and work
# each get their own independent delivery, and is_stupidly_early's
# existing EARLY_HOUR_CUTOFF check naturally gives gym (early) the
# terse version and work (later) the full one, no separate "which
# obligation is this" logic needed.
_LAST_DELIVERED_KEY = "spoken_morning_brief_last_delivered_shift"


def in_window(now: datetime) -> bool:
    return WINDOW_START_HOUR <= now.hour < WINDOW_END_HOUR


def _delivery_identity(now: datetime) -> str | None:
    identity = commute_reminder.current_shift_identity(now)
    if identity is not None:
        return f"{now.date().isoformat()}:{identity}"
    # No real shift today (a day off, or the commute estimate simply
    # isn't available) — falls back to sleep_tracker.wake_time_for,
    # same as trigger_time's own fallback just below. One slot for the
    # whole day in that case, same as before this change: there's only
    # ever one real wake moment to key off.
    wake = sleep_tracker.wake_time_for(now)
    return f"{now.date().isoformat()}:wake" if wake is not None else None


def already_delivered_today(now: datetime) -> bool:
    """Name kept for continuity with the existing caller (run_spoken_
    morning_brief.py) — despite the name, this is keyed per shift now,
    not per calendar day; see _LAST_DELIVERED_KEY's own comment."""
    identity = _delivery_identity(now)
    if identity is None:
        return False
    last = persisted_state.load(_LAST_DELIVERED_KEY, None)
    return last == identity


def mark_delivered(now: datetime) -> None:
    identity = _delivery_identity(now)
    if identity is not None:
        persisted_state.save(_LAST_DELIVERED_KEY, identity)


def _prompt(
    facts: list[str],
    terse: bool = False,
    holidays_block: str = "",
    seasons_block: str = "",
    environment_block: str = "",
    learned_notes_block: str = "",
) -> str:
    facts_block = "\n".join(f"- {f}" for f in facts)
    # Session request: "add other facts to it, so it has a bigger pool
    # to pick from, so the brief is higher quality." Reuses the exact
    # same 3 real, already-computed background sources morning_
    # briefing._ai_headline_and_body already gives the on-screen brief
    # (same wording, too — already proven there) — this brief never
    # received them before, drawing only on gather_facts' own clause
    # list. None of the three fire unconditionally (unlike moon phase,
    # which is why this needed its own fix): a holiday only matters
    # near one, a season change only around an equinox/solstice, an
    # environment trend only when the real numbers show a genuine
    # multi-day direction — real, naturally-varying texture, not daily
    # filler. Skipped entirely in terse mode, same as this brief's
    # whole background-context philosophy there.
    background_sections = (
        ""
        if terse
        else (
            (
                f"Upcoming Canadian statutory holidays, for context — worth naming whenever it's "
                f"genuinely relevant to something below, not only the obvious long-weekend case: "
                f"{holidays_block}\n\n"
                if holidays_block
                else ""
            )
            + (
                f"Upcoming season change, for context — worth naming whenever it actually connects "
                f"to something below, not only on the change day itself: {seasons_block}\n\n"
                if seasons_block
                else ""
            )
            + (
                f"Recent environmental trend data, for context — actively worth naming whenever "
                f"there's a real multi-day direction in it, not only when it's dramatic: "
                f"{environment_block}\n\n"
                if environment_block
                else ""
            )
            # Session request: "does the spoken brief have access to
            # the long form learned notes from my actual morning brief?
            # Because that's valuable data to have." Same real note
            # morning_briefing._ai_headline_and_body already reads for
            # the on-screen brief, same "actively check for a genuine
            # connection, never force one" instruction — just voiced in
            # THIS brief's own dutiful register rather than that one's
            # sarcastic one. The raw note itself still isn't read back
            # verbatim; only a specific connection drawn from it is.
            + (
                f"Long-term patterns you've picked up about him across many past mornings, for "
                f"context — actively check this for a real, specific connection to today's facts "
                f"(a routine it confirms or breaks, a person or interest that comes up again, a "
                f"schedule pattern that lines up with today) and work it in naturally when there's "
                f"a genuine one. Never read this note out loud or summarize it as its own topic — "
                f"only ever surface it as a connection to something actually happening today, and "
                f"never force one that isn't really there: {learned_notes_block}\n\n"
                if learned_notes_block
                else ""
            )
        )
    )
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
        # Session report, comprehensive rewrite, after the podcast-length
        # version had already landed: "narrate my day, don't read my
        # data back to me." Full 12-point spec — the core shift is away
        # from a fact-count/word-count target entirely and toward a
        # real narrative arc with actionable things weighted over
        # ambient ones, historical context used without naming itself,
        # a dry observational voice, and an ending that closes the day
        # out instead of a fixed sign-off. Superseded the previous
        # "300 words is a FLOOR" instruction outright — that pushed
        # genuinely good results (249 words, real added detail) but the
        # user's own next request here ("don't force information into
        # the brief just because it exists... a shorter, more natural
        # briefing is better than padding") is a direct, explicit
        # reversal of "never undershoot a floor." Length now follows
        # the day's real content, not a target.
        "This is a narrated orientation to the day, not a bulletin and not a transcript of the "
        "data below. Follow a loose arc: what kind of morning this is, what actually has to "
        "happen (work, gym, commute, appointments, anything that shapes how he needs to move "
        "through the day), anything genuinely unusual worth flagging, then the environment around "
        "it (weather, daylight, the market, gas prices) as supporting color near the end, not its "
        "own headline item — and the evening or tomorrow only if there's a real reason to mention "
        "it. Actionable things earn more weight and more words than passively-interesting ones: a "
        "real commute delay matters more than the moon phase, every time. Something genuinely "
        "urgent (an active alert, a real delay) can open ahead of the usual arc if it's truly the "
        "most important thing to know right now.\n\n"
        "Move between these the way one thought leads into the next — gym into the morning "
        "routine into the commute into the workday into the weather into the evening — not as "
        "separate sections stapled together. If historical context genuinely helps explain today "
        "(his usual commute time, a recurring gym/work rhythm, a real multi-day weather or price "
        "move), work it in naturally, but never call something an \"established pattern\" or "
        "\"established trend\" outright — that phrase reads as a system citing its own data, not "
        "a person who just knows this about him. Say it the way a person actually would instead: "
        "\"same as usual,\" \"like most Wednesdays,\" \"same as it's been all week,\" or just state "
        "the fact plainly with no label on it at all.\n\n"
        "A short, dry observation is welcome when the day actually earns one — something like "
        "\"this is a pretty straightforward Wednesday,\" \"nothing dramatic on the commute this "
        "morning, just a couple extra minutes,\" \"the weather's officially decided summer is "
        "over,\" or \"nothing particularly unusual on the schedule today, which is probably a "
        "good thing.\" Understated, not a joke dressed up as a bit — and only when it's genuinely "
        "warranted by what's actually true today, never forced in as a tic. Most mornings don't "
        "need one; some do.\n\n"
        "When something calls for a recommendation, fold the reasoning in rather than just "
        "stating the conclusion — \"it's eleven degrees this morning and only getting to fifteen, "
        "so this is definitely a jacket day\" instead of \"you'll want a jacket.\" Let sentences "
        "actually vary in length and shape, some short, some longer, rather than every line "
        "following the identical subject-verb-fact structure — this gets listened to, not read, "
        "so it needs real rhythm.\n\n"
        "Don't force in a category that has nothing real to say today — a shorter, more natural "
        "briefing beats padding one out to hit a length. Something technically true every single "
        "day (today's moon phase, say) doesn't need a mention just because it's available; include "
        "it only when it's genuinely interesting or connects to something else. And don't cram "
        "several numbers into one breathless sentence — if something matters, give it its own "
        "moment to actually register instead of stacking it next to three other facts. Let this "
        "run as long as the day's real content genuinely supports: a loaded morning can take a "
        "couple of minutes, a quiet one might only need thirty seconds, and that's correct, not a "
        "shortfall.\n\n"
        # Session report, from the podcast-length version: "fun fact
        # about the moon, fun fact about the world, fun facts about
        # whatever... anything that can bring value." Real moon-phase
        # data is one of the given facts below (astral.moon, a real
        # computed value, not trivia); this paragraph covers the OPEN-
        # ENDED "whatever" part, which has no real data source behind
        # it. This app has been burned by exactly this failure mode
        # before (a past morning brief confidently stated a specific
        # wrong date pulled from the model's own training data instead
        # of anything actually given) — so this stays deliberately
        # narrow: one real, safe, well-established tidbit at most,
        # explicitly optional, with silence as the correct default.
        "You may add ONE extra general-knowledge or seasonal tidbit beyond the facts below, but "
        "only if you are completely certain it's accurate and genuinely well-established — never "
        "a specific, obscure, or hard-to-verify number, date, or statistic. If you're not fully "
        "confident something is true, leave it out entirely; no trivia at all beats a wrong one.\n\n"
        # Session report: "don't always finish with a generic 'have a
        # good one, sir'... the ending should connect to the day, such
        # as acknowledging the workday, gym, evening plans, or
        # tomorrow's first obligation." Replaces the fixed sign-off
        # examples entirely — a real, content-aware close instead of a
        # stock phrase repeated every morning regardless of what the
        # day actually holds.
        "End on whatever actually closes today out, not a generic sign-off repeated every "
        "morning — a plain nod to the workday ahead, the gym session, tonight's plans, or "
        "tomorrow's first commitment if that's genuinely the more natural close. It should still "
        "feel like a real ending, not just stopping; it just has to be grounded in today's actual "
        "content rather than a stock phrase."
    )
    return (
        # Session report, comprehensive rewrite: "narrate my day, don't
        # read my data back to me... make it sound like an intelligent
        # person who knows my routines is briefing me, not an AI reading
        # a dashboard." The old persona line explicitly MODELED the
        # exact meta-language now being asked to remove ("I've reviewed
        # your commute," "I can confirm") — this isn't a tweak, it's a
        # direct reversal of that instruction.
        f"You are narrating {USER_FIRST_NAME}'s morning to him, out loud, the moment he walks "
        f"into the room — think a sharp, dry-witted, genuinely observant person who already "
        f"knows his routines, not a system announcing that it has processed data. Address him as "
        f"\"sir\" where it fits naturally, but never frame the briefing around your own process — "
        f"avoid phrases like \"I have already reviewed,\" \"I can confirm,\" \"I can take you "
        f"through,\" \"I have also noted,\" \"you will also notice\": these announce what the "
        f"system is doing instead of just telling him what's actually happening. Just narrate the "
        f"day directly, the way someone who already knows this about him would walk him through "
        f"it. Genuinely dutiful and thorough, not a hype man and not sarcastic — see the "
        f"observational-commentary guidance below for the one kind of personality that IS wanted. "
        # Session report, live: "all of the numbers in the brief, can
        # you have them written out as text? And instead of like C, can
        # you use Celsius? Because it is confused. It's very confused."
        # Reversed from the original "real digits not spelled-out
        # numbers" instruction — that rule was written for a kiosk
        # reading itself on-screen (a different, text-only feature),
        # never re-examined once this became something a real TTS voice
        # has to actually pronounce. Piper's phonemizer is live-
        # confirmed to stumble on bare digits/symbols; spelling
        # everything out in full words sidesteps that instead of
        # relying on Piper's own number-to-speech handling to get it
        # right.
        f"This will be spoken aloud by a text-to-speech voice that sometimes stumbles over "
        f"numerals and abbreviated units, not displayed as text: spell every number out in words "
        f"(\"fifteen\" not \"15,\" \"seven oh seven\" not \"7:07\"), and spell out every unit in "
        f"full (\"degrees Celsius\" not \"°C\" or \"C,\" \"percent\" not \"%,\" \"cents\" not "
        f"\"¢,\" \"dollars\" not \"$\") — no digits, no symbols, no abbreviations anywhere in "
        f"the response. No headers, no bullet points, no markdown. Refer to the S&P 500 (or its "
        f"futures) as just \"the market\" and ONLY \"the market\" — never spell out the full index "
        f"name (\"the standard and poor's five hundred index\") anywhere, including elsewhere in "
        f"the same sentence; that reads as absurd, not thorough.\n\n"
        f"{length_instruction}\n\n"
        f"Open with a greeting (\"Good morning, sir.\") and never invent anything beyond what's "
        f"given.\n\n"
        f"{background_sections}"
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
    if terse:
        prompt = _prompt(facts, terse=True)
    else:
        # Best-effort — a failed holiday/season/environment fetch costs
        # only this one optional background section, never the brief
        # itself (same "degrade, don't block" shape as every other
        # try/except in this app's own background-context plumbing).
        try:
            holidays_block = holidays_client.upcoming_holidays_block(now)
        except Exception:
            holidays_block = ""
        try:
            seasons_block = seasons_client.upcoming_seasons_block(now)
        except Exception:
            seasons_block = ""
        try:
            environment_block = morning_briefing.environment_trends_block()
        except Exception:
            environment_block = ""
        try:
            learned_notes_block = morning_briefing.learned_notes()
        except Exception:
            learned_notes_block = ""
        prompt = _prompt(
            facts, terse=False,
            holidays_block=holidays_block, seasons_block=seasons_block, environment_block=environment_block,
            learned_notes_block=learned_notes_block,
        )
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
    # 700, not 500: the full brief now targets 300-450 words (~400-600
    # tokens at English's usual ~1.33 tokens/word) — raised again along
    # with the length target itself so the new "use essentially
    # everything" instruction doesn't get hard-clipped mid-sentence.
    # terse's 90 is untouched, that mode's own target didn't change.
    text = gemini_client.generate_periodic(
        feature_key, refresh_seconds=4 * 3600, prompt=prompt, temperature=0.6, max_output_tokens=90 if terse else 700
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
