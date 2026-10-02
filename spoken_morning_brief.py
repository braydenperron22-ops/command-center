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
        # Session report: "my spoken brief was short as fuck... I want
        # it to be like a podcast of my day... I want to be able to
        # listen to it. I want it to be at least a minute or two long
        # so I can listen to it while I'm making breakfast." The old
        # "3 to 5 short sentences... 15-30 seconds" target was a tight
        # bulletin by design — directly the opposite of what's wanted
        # now that there's real time to fill (breakfast), not a reason
        # to rush. Stupidly-early mode (terse=True, above) is
        # unchanged on purpose — still short for an actually rushed
        # morning; this length change is the normal-morning case only.
        # Follow-up, once the 1-2 minute version landed: "can we add
        # more facts though? It should feel like a big brief... loop in
        # more facts, anything that can bring value." Pushed further to
        # 2-3 minutes with an explicit "use essentially everything,
        # don't hold back" instruction below, rather than just raising
        # the word count and hoping it fills the space on its own.
        # Verified live: a bare "roughly 300-450 words" range was
        # consistently undershot (161-208 words across several real
        # Gemini calls, same facts, regardless of temperature) — a
        # stated range alone doesn't reliably produce compliance, same
        # lesson this app's other prompts have already learned. Framing
        # 300 as a floor plus naming the actual MECHANISM for getting
        # there (expand on facts with real detail, don't just state and
        # move on) measurably worked better live: 249 words, genuinely
        # richer ("stepping outside will require a light jacket," "a
        # nice way to unwind") rather than just more facts crammed in.
        "Write this as a genuine 2 to 3 minutes of natural spoken audio. Treat 300 words as a "
        "FLOOR, not a target to land near — if what you've drafted comes in under that, you're "
        "leaving real detail on the table: go back and add a genuine sentence of real context or "
        "color to several of the facts below (what the temperature actually means for what to "
        "wear outside, why a commute time is or isn't notable, how the evening's plans shape the "
        "rest of the day) rather than stating each one plainly and moving to the next. Still "
        "short, complete sentences throughout — real full stops for natural spoken pauses between "
        "thoughts, never one long comma-spliced run-on — just many more of them than a tight "
        "summary would use.\n\n"
        # Session report: "it kind of reads like a shopping list right
        # now... I want it to connect the dots legitimately... doesn't "
        # read off as a checklist." The old instructions below ("pick 3
        # or 4 facts... move on... round it out") describe a sequence
        # of facts taken one at a time, which is exactly what produces
        # that checklist feel even with full sentences and real connecting
        # words — the fix is telling it to actually relate facts to each
        # other, not just to pick good ones and recite them in order.
        "This has to sound like a person actually talking, not a checklist read out loud one "
        "item at a time. Weave facts together wherever a real connection exists between them — "
        "the weather affecting how the commute or the day will feel, a packed schedule meaning "
        "less time tonight, anything that genuinely relates — instead of stating them side by "
        "side with nothing tying them together. One flowing thought beats a list of unconnected "
        "facts. Still never invent a connection that isn't actually there — a real one beats a "
        "forced one, same rule as everywhere else.\n\n"
        # Session follow-up, right after "use essentially everything"
        # shipped: "it doesn't have to mention the moon phase every
        # time... I want you to add other facts to it, so it has a
        # bigger pool to pick from, so the brief is higher quality."
        # "Use essentially everything" was the wrong instruction for a
        # fact that's technically available every single day (the moon
        # phase, always computable) — it forced a daily mention whether
        # or not it actually added anything that morning. Replaced with
        # real editorial judgment over a bigger pool instead: the extra
        # background sections below (holidays/season/environment
        # trends) exist specifically to make that pool bigger and more
        # VARIED day to day, not to all be stapled in every time either.
        "You have a rich pool of real facts and background below — use genuine editorial "
        "judgment on which ones are actually worth including today, not an obligation to mention "
        "every single one every single morning. Something that's technically true every day "
        "(today's moon phase, say) doesn't need a line just because it's available — include it "
        "when it's genuinely interesting or connects to something else, skip it on a day it "
        "doesn't add anything. Walk through the day the way someone would actually fill you in "
        "on it, covering the commute, the schedule, the weather, and whatever else below is "
        "actually worth knowing. Something genuinely urgent — an active weather/road alert, a "
        "real commute delay — earns the opening line. On an ordinary day, though, don't default "
        "to opening on the commute and closing on the schedule (or vice versa): those are two "
        "facts among several, not bookends with everything else sandwiched in between.\n\n"
        # Session report, same follow-up: "fun fact about the moon, fun
        # fact about the world, fun facts about whatever... anything
        # that can bring value." Real moon-phase data is now one of the
        # given facts below (astral.moon, a real computed value, not
        # trivia) — this paragraph covers the OPEN-ENDED "whatever"
        # part, which has no real data source behind it. This app has
        # been burned by exactly this failure mode before (a past
        # morning brief confidently stated a specific wrong date pulled
        # from the model's own training data instead of anything
        # actually given) — so this is deliberately narrow: one real,
        # safe, well-established tidbit at most, explicitly optional,
        # with silence as the correct default over a guess.
        "You may add ONE extra general-knowledge or seasonal tidbit beyond the facts below, but "
        "only if you are completely certain it's accurate and genuinely well-established — never "
        "a specific, obscure, or hard-to-verify number, date, or statistic. If you're not fully "
        "confident something is true, leave it out entirely; no trivia at all beats a wrong one.\n\n"
        # Session report: "I want it to have a clean send-off. Whenever
        # it's done now, it just stops talking... end the conversation
        # off in a way that feels natural but not overly supportive or
        # corny." A real gap, not a style note — the prompt never asked
        # for a close at all, so it had nothing to end on but whichever
        # fact happened to be picked last.
        "Close with one short, natural sign-off — something like \"Have a good one\" or \"Enjoy "
        "your day\" — the kind of thing someone says on their way out the door. Not warm or "
        "supportive (no \"you've got this,\" no \"I believe in you,\" nothing corny) — just a "
        "plain, brief close, not a pep talk."
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
        prompt = _prompt(
            facts, terse=False,
            holidays_block=holidays_block, seasons_block=seasons_block, environment_block=environment_block,
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
