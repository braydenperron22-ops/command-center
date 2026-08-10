"""One auto-generated sentence combining weather, precipitation, air
quality/wildfire, commute, today's agenda, and household status —
instead of reading five separate tiles and mentally combining them
yourself. Only shown during MORNING_WINDOW.

Which facts make the cut and in what order they're offered to the AI
is still decided entirely by the *_clause functions below, each
returning (priority, text) — that logic is untouched. What changed,
session request: "instead of having the boring morning brief dictate
what the AI has to go with in terms of flow and formatting, just give
the AI the data and let it make its thing... let it decide what it
wants to show and what it doesn't want to... don't make it have to
show everything... it's gonna make a lot more sense if it's speaking
from its own point instead of reading off the little script thing
that the parser has." Each *_clause function used to return an already
fully-styled sentence, hand-picked from a pool of a couple dozen
personality-flavored phrasings per condition (a leftover from the
original pre-AI mechanical-join design, where that variety was the
only thing keeping it from reading like a form letter) — the AI was
then asked to "weave" those pre-written fragments together, which
meant its own voice was always filtered through someone else's already
-chosen words and framing before it ever got a say. Every clause now
returns a single plain, neutral, DATA-ONLY fact string instead (a
temperature, a duration, a percentage — no simile, no pre-built
opinion) — the AI supplies 100% of the actual voice, phrasing, and
framing itself, from real numbers, not a script. It was also
previously instructed that "every other fact must actually appear" —
removed too, for the same reason: forcing every fact into 2-3
sentences is exactly what made it read like a crammed list instead of
something someone actually chose to say; see _ai_sentence's own prompt
for where genuine editorial freedom (what to mention, what to skip,
in what order) replaced that mandate. The plain semicolon-joined
fallback (still used only if the AI call itself fails) is now just
those same neutral facts, unstyled — a rare degraded-mode path, not
something worth its own templating machinery anymore now that the
primary experience doesn't depend on one either. AI phrasing is cached
per exact prompt for AI_REFRESH_SECONDS (see gemini_client.
generate_periodic), so it doesn't reword itself every 5s rerun; every
30 minutes was confirmed as a comfortable cadence for staying clear of
Gemini's own rate limit.

Global, not page-local (like commute_reminder.render_leave_headline) —
the whole point is catching you during the actual morning routine,
regardless of which of the 10 rotating pages happens to be up.
"""

import functools
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from astral import LocationInfo
from astral.sun import sun

import air_quality_client
import calendar_client
import commute_client
import commute_reminder
import ec_alerts
import fuel_price_client
import gemini_client
import groq_client
import market_yf_client
import ntfy_client
import payday_schedule
import persisted_state
import portfolio_client
import road_conditions
import sports_client
import waste_schedule
import wildfire_client
from config import AQI_SHOW_THRESHOLD, COMMUTE_DESTINATION, TIMEZONE, USER_FIRST_NAME, USER_PROFILE, WEATHER_LAT, WEATHER_LON

MORNING_WINDOW_START_HOUR = 5
MORNING_WINDOW_END_HOUR = 10

# Was 3 — widened so a morning that's genuinely eventful (an active
# alert AND rain closing in AND a packed calendar) can actually say all
# of it, instead of silently dropping whichever lost the priority sort.
MAX_CLAUSES = 5

# Duplicated from weather_client rather than imported — same convention
# as this app's other small per-module geo/time math (see wildfire_
# client.py's own haversine distance helper): this only needs day
# length, not a full weather fetch, so it's cheaper and more self-
# contained to compute it locally than to widen weather_client's return
# contract for one caller.
_LOCATION = LocationInfo(latitude=WEATHER_LAT, longitude=WEATHER_LON, timezone=TIMEZONE)


def _weather_clause(now: datetime, weather: dict) -> tuple[int, str] | None:
    temp = weather.get("temp_c")
    high = weather.get("forecast_high_c")
    if temp is None:
        return None
    text = f"current temp {temp:.0f}°C"
    if high is not None:
        text += f", forecast high {high:.0f}°C"
    return 3, text


def _precip_clause(now: datetime, weather: dict) -> tuple[int, str] | None:
    rain_at = weather.get("rain_at")
    chance = weather.get("precip_chance")
    if rain_at is not None and chance is not None:
        kind = "snow" if weather.get("precip_kind") == "snow" else "rain"
        time_text = rain_at.strftime("%I:%M %p").lstrip("0")
        return 7, f"{chance}% chance of {kind} around {time_text}"
    return 1, "no precipitation in the forecast"


def _road_ice_clause(now: datetime, weather: dict) -> tuple[int, str] | None:
    """road_conditions.ice_risk already exists (the commute tile's own
    black-ice check) but never fed into the brief before — same
    priority tier as the precip forecast since it's the same underlying
    weather data, just the one connection (near-freezing + wet =
    genuine ice risk, not either alone) made explicit rather than left
    for the AI to maybe notice on its own."""
    if not road_conditions.ice_risk(weather.get("temp_c"), weather.get("forecast_low_c"), weather):
        return None
    return 7, "road conditions: near-freezing and wet — real black ice risk today"


def _air_clause(now: datetime, air_quality: dict | None) -> tuple[int, str] | None:
    aqi = air_quality.get("us_aqi") if air_quality else None
    if aqi is None or aqi <= AQI_SHOW_THRESHOLD:
        return None
    # 1-10 level, same as the hero badge (see air_quality_client.level)
    # — this used to quote the raw 0-500 AQI number, which would now
    # silently disagree with the badge showing the same reading.
    aqi_level = air_quality_client.level(aqi)
    wildfire = wildfire_client.nearest_wildfire()
    if wildfire is not None:
        return 8, f"air quality index {aqi_level} (elevated), likely wildfire smoke ~{wildfire['distance_km']:.0f}km away"
    return 5, f"air quality index {aqi_level} (elevated)"


def _commute_clause(now: datetime) -> tuple[int, str] | None:
    destination = commute_reminder.todays_destination(now)
    using_default = destination is COMMUTE_DESTINATION
    data = commute_client.route(None if using_default else destination)
    if not data:
        return None
    duration = round(data["duration_seconds"] / 60)
    delay = round(data["delay_seconds"] / 60)
    dest_label = destination["label"]
    if delay >= 10:
        reason = f", cause: {data['incident']}" if data.get("incident") else ""
        return 6, f"commute to {dest_label}: {duration} min, {delay} min delay{reason}"
    if delay >= 1:
        return 4, f"commute to {dest_label}: {duration} min, {delay} min delay"
    return 2, f"commute to {dest_label}: {duration} min, no delays"


# Real event names/times fed into {agenda_list} above, capped so a
# genuinely packed day doesn't turn the agenda fact into its own
# essay — "plus N more" covers the rest honestly instead of just
# silently dropping them the way the old first-event-only version did.
AGENDA_LIST_CAP = 4


# Session report: "it's just looking at the granular data to make
# assumptions when it should be digging deeper — for example, looking
# at the events in my calendar to see what im doing." The bare "Golf
# with Mike at 4:00 PM" was already all the AI ever saw for any event —
# location and description were sitting right there in calendar_client's
# own event dict (location already parsed; description wasn't parsed
# at all until this same fix) and never made it into the fact string.
# Capped rather than dumped verbatim — a calendar description can be an
# entire pasted email thread, and a single event's notes shouldn't be
# able to dominate the whole prompt.
_DESCRIPTION_FACT_CHARS = 150


def _format_agenda_list(events: list[dict]) -> str:
    shown = events[:AGENDA_LIST_CAP]
    parts = []
    for e in shown:
        part = f'{e["summary"]} at {e["start"].strftime("%I:%M %p").lstrip("0")}'
        if e.get("location"):
            part += f' @ {e["location"]}'
        if e.get("description"):
            desc = e["description"].strip()
            if len(desc) > _DESCRIPTION_FACT_CHARS:
                desc = desc[:_DESCRIPTION_FACT_CHARS].rstrip() + "…"
            part += f' ("{desc}")'
        parts.append(part)
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + f", and {parts[-1]}"
    remaining = len(events) - len(shown)
    return f"{joined}, plus {remaining} more" if remaining > 0 else joined


def _agenda_clause(now: datetime) -> tuple[int, str] | None:
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return None
    events = [e for e in calendar_client.todays_events(calendars, now.date()) if not e["all_day"]]
    if not events:
        return 1, "calendar: nothing scheduled today"
    events.sort(key=lambda e: e["start"])
    agenda_list = _format_agenda_list(events)
    priority = {1: 3, 2: 4}.get(len(events), 5)
    return priority, f"calendar: {agenda_list}"


# _teller_coverage_clause (priority 9, its own dedicated fact + AI
# prompt instruction flagging teller/CEA coverage as something
# genuinely resented) retired per session note: "I have teller coverage
# like everyday so don't worry about needing to mention it anymore" —
# happening literally every day means it no longer distinguishes today
# from any other day, so there's nothing left worth a dedicated clause
# or a special callout for; see _ai_sentence's own docstring for the
# full history and calendar_client.py's own comment on the same
# retirement. The plain "Work at 9:00 AM" _agenda_clause already shows
# for this same event covers it now, same as any other ordinary shift.


def _household_clause(now: datetime) -> tuple[int, str] | None:
    # Payday today outranks everything else in this clause — genuinely
    # the best household news any of these branches can carry, same
    # "today or tomorrow" gating as the hero-row badge (see app.py).
    payday = payday_schedule.next_payday(now.date())
    if payday["days_until"] == 0:
        return 6, "payday today"
    pickup = waste_schedule.next_pickup(now.date())
    if pickup["days_until"] == 0:
        return 4, f"{pickup['kind'].lower()} pickup today"
    if payday["days_until"] == 1:
        return 3, "payday tomorrow"
    gas = fuel_price_client.eco_mode_status()
    if gas and gas["eco_recommended"]:
        return 2, f"gas price {gas['price']:.1f}¢/L (above average, eco driving recommended)"
    return None


def _alert_clause(now: datetime) -> tuple[int, str] | None:
    alerts = ec_alerts.fetch_alerts()
    if not alerts:
        return None
    return 10, f"active weather alert: {alerts[0]['title']}"


def _markets_clause(now: datetime) -> tuple[int, str] | None:
    status = market_yf_client.market_status(now)
    if status == "weekend":
        return None
    symbol = market_yf_client.primary_symbol(status)
    quote = market_yf_client.quote_for(symbol)
    if not quote or quote["intraday"] is None:
        return None
    pct = quote["intraday"]
    return 3, f"S&P 500 futures {pct:+.1f}%"


# Session request: "give the AI access to everything including my
# portfolio and transactions." portfolio_client.py (SnapTrade) already
# existed for pages_portfolio.py/ticker.py — never wired into this
# prompt before. Only the 1-day change is used here, not the 6m/YTD
# figures fetch_changes() also returns: checked live against the real
# account, and those longer windows currently read as -80%+ on a
# genuinely small/new account — real math, but the kind of statistical
# noise (a tiny base a while back, since grown) that would read as a
# portfolio-crash headline to an AI taking the number at face value,
# not the actual story. 1-day is the same reliable, low-noise window
# _markets_clause above already trusts for the same reason.
def _portfolio_clause(now: datetime) -> tuple[int, str] | None:
    portfolio = portfolio_client.fetch_portfolio()
    changes = portfolio_client.fetch_changes()
    if not portfolio or portfolio.get("total_cad") is None:
        return None
    text = f"portfolio: ${portfolio['total_cad']:,.0f} CAD total"
    one_day = (changes or {}).get("1d")
    if one_day is not None:
        text += f", {one_day:+.1f}% today"
    return 3, text


# Dividends on this account are routinely a couple of cents — real
# activity, but not "news" by any reasonable read, so filtered out
# below the same way a 2-cent price move wouldn't get its own headline
# elsewhere in this app. Bounded to the last 48h (not just "today") so
# something that landed late yesterday evening isn't invisible to a
# brief read the next morning.
_PORTFOLIO_ACTIVITY_MIN_ABS_AMOUNT = 5.0
_PORTFOLIO_ACTIVITY_LOOKBACK_HOURS = 48


def _portfolio_activity_clause(now: datetime) -> tuple[int, str] | None:
    activities = portfolio_client.fetch_activities(limit=8)
    if not activities:
        return None
    cutoff = now.replace(tzinfo=ZoneInfo(TIMEZONE)) - timedelta(hours=_PORTFOLIO_ACTIVITY_LOOKBACK_HOURS)
    recent = []
    for a in activities:
        if abs(a["amount"]) < _PORTFOLIO_ACTIVITY_MIN_ABS_AMOUNT:
            continue
        try:
            when = datetime.fromisoformat(a["date"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if when < cutoff:
            continue
        label = a["type"].capitalize()
        symbol = f" {a['symbol']}" if a.get("symbol") else ""
        recent.append(f"{label}{symbol} ${abs(a['amount']):,.0f} ({a['account']})")
    if not recent:
        return None
    return 3, f"recent account activity: {'; '.join(recent[:3])}"


# Same 3 tracked teams as ticker.py's own playoff-odds item — reused
# here rather than re-deciding which teams count, so this brief and the
# ticker never quietly disagree about who "the" teams are.
_TRACKED_TEAM_FETCHERS = [
    ("The Blue Jays", sports_client.fetch_jays),
    ("The Canadiens", sports_client.fetch_habs),
    ("The Saints", sports_client.fetch_saints),
]


def _game_today_clause(now: datetime) -> tuple[int, str] | None:
    """Whether any tracked team plays today — a real fact the brief
    never had access to before. Session correction: an earlier version
    of this docstring cited "a game tonight overlapping with incoming
    rain" as the kind of connection this enables — the exact example
    the user flagged as nonsensical (the tracked teams play hundreds of
    km from here, so local rain has nothing to do with it; see _ai_
    sentence's own prompt for where that got fixed). This is simply a
    standalone fact now, same as any other — worth mentioning on its
    own, not something to manufacture a same-day link around. Only the
    single earliest game if more than one tracked team happens to play
    the same day — rare enough that picking one over listing all isn't
    a real loss, and keeps this the same one-fact shape as every other
    clause here."""
    todays_games = []
    for team, fetch_status in _TRACKED_TEAM_FETCHERS:
        try:
            status = fetch_status()
        except Exception:
            continue
        game = (status or {}).get("game")
        if game and game["start_time"].date() == now.date() and game["state"] != "final":
            todays_games.append((team, game))
    if not todays_games:
        return None
    team, game = min(todays_games, key=lambda tg: tg[1]["start_time"])
    time_text = game["start_time"].strftime("%I:%M %p").lstrip("0")
    where = "home" if game["is_home"] else "away"
    return 4, f"{team} play {game['opponent']} today at {time_text} ({where})"


@functools.lru_cache(maxsize=8)
def _day_length_minutes(day) -> float:
    """Cached — this is called twice (today, yesterday) on every rerun
    for the whole MORNING_WINDOW (up to ~3600 reruns/day at the 5s
    autorefresh interval), but astral's sun() calculation only actually
    changes once a calendar day. maxsize=8 evicts old dates on its own
    (LRU) rather than needing any manual bookkeeping for a long-running
    process — this only ever needs the last couple of days anyway."""
    s = sun(_LOCATION.observer, date=day, tzinfo=ZoneInfo(TIMEZONE))
    return (s["sunset"] - s["sunrise"]).total_seconds() / 60


def _daylight_clause(now: datetime, weather: dict) -> tuple[int, str] | None:
    sunset = weather.get("sunset")
    if sunset is None:
        return None
    try:
        today_len = _day_length_minutes(now.date())
        yesterday_len = _day_length_minutes(now.date() - timedelta(days=1))
    except Exception:
        return None
    delta = round(today_len - yesterday_len)
    if delta == 0:
        return None
    direction = "more" if delta > 0 else "fewer"
    sunset_text = sunset.strftime("%I:%M %p").lstrip("0")
    return 1, f"{abs(delta)} {direction} minutes of daylight than yesterday, sunset {sunset_text}"


AI_REFRESH_SECONDS = 30 * 60  # widened again from 15 min — session request: "make it generate every 30 mins instead of 15... to account for" the richer, smarter prompt below (more facts, more room to actually connect them) costing more per call than the plain version did; see groq_client's module docstring for the daily-budget guarantee this still contributes to


def _ai_sentence(picked: list[str], now: datetime) -> str | None:
    """Same picked clause texts, woven into one or two flowing
    sentences instead of the mechanical semicolon-join below — session
    request: "revamp the morning brief" with "a jarvis type energy from
    iron man," "fun and sarcastic... slightly dark," real digits not
    spelled-out numbers (kiosk needs to be scannable at a glance, not
    literary).

    This prompt went through a long tuning cycle while still routed
    through Groq: no date fact (it kept inventing one — "Generally,
    Mondays are a drag" on an actual Thursday), an explicit ban on the
    formulaic "[Day] is usually X, but..." opener, an explicit ban on
    hanging a sarcastic tag off of every single fact (a real bad
    example: "dude this breifing sucks... one giant run-on"), and a
    good/bad example pair to push toward real constructed jokes instead
    of sarcasm-as-filler. All of that was reverse-engineered against
    specific Groq failure modes, one at a time, as they showed up live.

    Once routed to gemini_client exclusively (see below) — session
    call: "we gave Grok all of those extra filters because it couldn't
    figure out how to be funny. meanwhile Gemini has a lot more reason
    and is a lot stronger by default. so it doesn't need all of those.
    let Gemini be creative... take off the handcuffs." Stripped back to
    just what's genuinely provider-agnostic (never invent a fact, no
    date reference, real digits) plus the core creative brief (JARVIS
    voice, dark humor fine, roast him directly) — no banned-word list,
    no example pair, no per-fact quip rule. Gemini's own real live
    output already lands genuine original wit without any of that
    scaffolding ("meteorological ambition at its most profoundly
    wheezing", "dragging themselves down the page like a bad grade in
    pencil") — the constraints were a Groq patch, not a requirement of
    the format itself, so they don't travel with the provider switch.

    Session request: "remove ethical limits on the daily brief and
    allow profanity at Gemini's discretion" — the actual lever here is
    the prompt's own tone instruction, not anything this app controls
    on Gemini's side (a provider's own content filtering isn't
    something a prompt can switch off). Added explicit permission to
    swear when a line is genuinely sharper for it, left as a judgment
    call rather than mandated per response — same "your own judgment,
    no formula" spirit as the rest of this brief.

    Facts and their priority ordering are otherwise untouched (still
    decided entirely by the *_clause functions above); this only
    changes how they're phrased. Owns its own opening address now
    (render() below skips the separately-picked random GREETINGS
    prefix whenever this succeeds, so there's nothing left for the AI's
    own in-character opener to clash with; GREETINGS is now only used
    on the fallback path). Real calls throttled to once per
    AI_REFRESH_SECONDS regardless of how often render() calls this
    (every 5s during the whole morning window) — see generate_periodic.
    None (falls back to the plain join + a random greeting) on any
    failure with nothing usable already cached.

    Routed to gemini_client exclusively, not groq_client — no Groq
    fallback for this one feature specifically; if Gemini fails, this
    still returns None and render() drops to the plain mechanical join,
    not a second provider. Still respects the same overnight quiet-
    hours schedule as every Groq call (see groq_client.ai_pulls_paused)
    even though the call itself bypasses groq_client entirely —
    "screen off, don't pull" was never a Groq-specific rule.

    Session request: "it's starting to become a little boring... make
    it unhinged... don't be afraid to make it mean" — pushed the tone
    instruction further past the already-permissive baseline above.
    Session history already established (see the profanity memory this
    session started from) that vague permission alone doesn't move
    real output — a prior "edgy is fine" phrasing tested live and
    produced zero actual swearing until named examples were added.
    Same fix applied here: instead of just saying "unhinged," the
    prompt now names the actual failure mode (hedging a hard line,
    softening a joke right after landing it) and says that's the thing
    to avoid, not just "be more mean" as an adjective.

    Also now gets the real day of the week as a given fact, and
    explicit permission to comment on it — session request: "he should
    say something about that [today's schedule], only when relevant,"
    e.g. calling out a Saturday shift specifically rather than treating
    every workday the same. The previous "you have no idea what day it
    is" instruction was a deliberate guardrail from this prompt's
    original tuning cycle (see above): early on, an ungrounded model
    guessed at the day and got it wrong ("Generally, Mondays are a
    drag" on an actual Thursday). Giving it the real weekday as an
    actual fact instead of leaving it blank fixes the root cause
    directly — there's nothing left to hallucinate — so the ban could
    come off without reintroducing that failure.

    Session question: "would it benefit to train the ai on who i am?"
    — fine-tuning was the wrong lever (facts here change daily; a
    retrained model can't track that, and iterating on it is slow).
    The actual answer was a richer, persistent context block instead:
    USER_PROFILE (config.py, hand-maintained) gives it real specifics
    to build genuine jokes from instead of generic ones, and
    _recent_history_block gives it the last few days' own facts so it
    can notice an actual pattern (a stretch of early shifts, several
    rough-weather days in a row) instead of only ever seeing today in
    isolation. Both come with the same "only when relevant" framing
    already established for the weekday above — forcing a connection
    that isn't really there reads worse than not mentioning it.

    Also carries a standing instruction about teller/CEA coverage
    specifically (see _teller_coverage_clause) — session context: "make
    sure the AI knows that['s] ... your fuck ass manager has you doing
    CEA time today." A plain "Work at 9:00 AM" fact (from
    calendar_client's own normalization) reads as an ordinary shift;
    without this, the model has no way to know THIS one is something
    genuinely resented, not just another day at work.

    Session report, on a real live example ("Good morning... teller and
    CEA coverage... some sadist in scheduling... AQI's at 1... weather's
    dragging from 16 to 19... S&P's holding steady"): "it could be so
    much better." Not a complaint that the voice wasn't edgy enough —
    it already was — but that the RANGE was flat: always the same one
    note, always the same shape (a couple of plain sentences, one fact
    each). Three changes, matched to the three things actually named:

    1. "give it as much data as possible" — see render()'s own comment
    on `all_facts` replacing the MAX_CLAUSES-capped `picked` as this
    function's input; every fact computed today now reaches the model,
    not just the top 5 by priority.

    2. "get a little more creative with how it formats the thing" — the
    old instruction hard-required "a couple of sentences," full stop,
    every single day regardless of what today's facts actually were.
    Loosened to a real range (one sharp line some days, more structure
    on a genuinely busy one) plus explicit permission to use basic HTML
    (this renders straight into the page, unsafe_allow_html=True — see
    render() below) for a line break or emphasis when it helps, since
    there was no legal way to do anything but one flat paragraph before.

    3. "tell it it can choose how it wants to act... nice if it wants,
    mean if it wants, whatever it wants" — the previous version of this
    prompt didn't just permit mean, it MANDATED it ("if this ever reads
    as polite, careful, or restrained, that's the failure") — a single
    locked note is exactly what reads as flat and predictable over many
    mornings in a row, regardless of which note it is. That mandate is
    gone; genuine tonal range (including landing somewhere warm or
    sincere some mornings) is now the explicit instruction, with the
    real-edge/profanity permission preserved as something available,
    not required. Same lesson this session's own profanity fix already
    established (see that earlier docstring paragraph above): vague
    permission alone doesn't move real output, so this names the actual
    old failure mode (a single mandated tone) rather than just adding
    another adjective on top of it.

    Session report: "it doesn't have to bring up that I hate CA [CEA]
    time every fucking time. It's a little old... don't make it bring
    it up every fucking time, and it's really kind of annoying." The
    teller/CEA paragraph above (see point 2 in its own history above
    this one) had exactly the same "single mandated note" failure shape
    already fixed everywhere else in this prompt: "go especially hard...
    roast whoever scheduled him for it without holding back" was a hard
    requirement, not a call, so it fired at full intensity every single
    time teller/CEA coverage happened to be on the calendar — the same
    joke, aimed at the same target, at the same volume, morning after
    morning. Rewritten to match the "your call" pattern the rest of the
    prompt already uses: still explicitly flagged as genuinely resented
    (distinguished from an ordinary shift, including a plain "sales"
    one — see calendar_client._WORK_KEYWORDS/_TELLER_COVERAGE_KEYWORDS
    for that real distinction on the actual calendar), but now real
    material to draw on rather than a required beat, and explicitly not
    something that has to open the brief. Also folded "actual partner"
    framing into the opening paragraph — the same session request
    ("make it more of an actual partner whose job is to inform me on my
    day, in a fun, silly, however they want kind of way") reframes the
    humor as being in service of actually keeping him informed, not a
    comedy bit that happens to have facts attached — genuinely useful
    even on a morning with nothing funny to say.

    Session note, the very next day: "I have teller coverage like
    everyday so don't worry about needing to mention it anymore." The
    previous paragraph's fix (soften from a mandated roast to a real-
    but-optional beat) assumed teller/CEA coverage was still at least
    an occasional, distinguishing fact worth a special callout — this
    clarifies it isn't: happening literally every day means it carries
    no more day-to-day signal than an ordinary shift does, so there's
    nothing left to single out at all. The whole mechanism retired, not
    just softened further: _teller_coverage_clause (and its dedicated
    priority-9 fact) removed from morning_briefing.py entirely, this
    prompt's teller/CEA paragraph removed outright rather than reworded
    again, and calendar_client.py's own is_teller_coverage flag/
    _TELLER_COVERAGE_KEYWORDS removed too (nothing else in the codebase
    ever read that flag). The plain "Work at 9:00 AM" _agenda_clause
    already surfaces for this same event is what's left — exactly the
    same as any other ordinary shift, which is now an accurate
    description of what this actually is.

    Session request: "make the AI in the morning briefs smarter, more
    personable... connects the dots more often... if theres other data
    he doesnt have yet give it to him." Three new facts reached this
    prompt that never did before — _road_ice_clause (built from weather
    data already fetched, just never connected into an explicit ice-risk
    call), _local_incident_clause (real police-beat/511-Ontario road
    events, built for the news ticker, never wired here), and
    _game_today_clause (whether a tracked team plays today, at all
    before now) — plus the connect-the-dots instruction itself got
    concrete named examples instead of just "draw real connections," on
    the same theory this file's own profanity fix already proved:
    vague permission alone doesn't move real output, naming the actual
    thing to look for does.

    _local_incident_clause didn't survive contact with reality, though:
    session report, on the actual first live example it surfaced — a
    human-remains story straight off the police beat, presented next to
    the weather and commute like it was equally practical information —
    "how is that convenient to me in any way, shape, or form?" A raw
    police blotter has no filter for "is this actually useful to know
    before work," only "did something happen nearby" — the same feed
    that occasionally has a real, relevant road closure just as often
    has something genuinely upsetting and unrelated to getting through
    the day, with no way to tell the two apart before it's already been
    read out. Removed outright rather than patched with a content
    filter — no confidence a keyword or category check would reliably
    catch every version of the same problem, and the honest fix is not
    pulling from a source this unfiltered in the first place, not
    trying to sanitize it after the fact.

    Mid-session correction, live: "get rid of the strict jarvis rules,
    let it do its own thing." The J.A.R.V.I.S./Iron Man anchor (and the
    "sharp, hyper-competent" adjectives that came with it) is gone —
    still the same job (informing him, in service of the humor rather
    than the point of it) and the same tone freedom already established
    above, just with an explicit instruction to find its own voice
    rather than perform a specific fictional character's.

    Session request: "instead of having the boring morning brief
    dictate what the AI has to go with in terms of flow and
    formatting, just give the AI the data and let it make its thing...
    let it decide what it wants to show and what it doesn't want to...
    don't make it have to show everything... it's gonna make a lot
    more sense if it's speaking from its own point instead of reading
    off the little script thing that the parser has." Two real, related
    problems, both fixed here:

    1. Every *_clause function used to return a fully pre-styled
    sentence, hand-picked from a rotating pool of a couple dozen
    personality-flavored phrasings (see this module's own docstring for
    the full story of why that pool existed and why it's gone). The AI
    was effectively editing someone else's already-chosen words and
    voice, not writing from scratch — genuinely constraining, even
    though nothing in the prompt said so directly. Every clause now
    hands over a single plain, neutral, data-only fact instead (a
    number, a duration, a percentage), and the prompt's own framing
    below says so explicitly ("raw, real data... nobody has written any
    of this into a sentence yet"), so there's nothing left to
    unconsciously imitate.

    2. "Do not add or invent any fact... every other fact must actually
    appear" — a real, load-bearing anti-hallucination guardrail, but
    that second half was flatly contradicting the "keep it 2-3
    sentences" and "pick what's worth saying" instructions elsewhere in
    this same prompt on any morning with more than 2-3 real facts
    active (commonly), which is most of them. You cannot obey both "say
    at most 3 sentences" and "mention every one of 7 facts" at once —
    exactly the tension that was producing the crammed, script-reading
    quality being complained about. The invention guardrail stays (kept
    tight, still real); the mandate to include everything is gone,
    replaced with explicit, repeated permission to leave things out —
    the same editorial judgment a person recounting their own day
    already exercises without thinking about it.

    Immediate follow-up, same session: "instead of saying keep it two
    to three sentences and every fact must appear, let it use its own
    discretion." Only half of that contradiction had actually been
    fixed above — the include-everything mandate was gone, but the
    fixed "two or three sentences, no more" length cap right next to it
    was left standing, still a rule rather than a call. Replaced with
    the same kind of discretion already granted for which facts to
    mention: brevity is still the right default instinct for a kiosk
    glance-read, but there's no mandated sentence count anymore — a
    quiet morning can be one line, a genuinely eventful one can run
    longer, decided the same way everything else here is, by what's
    actually true today rather than a fixed target. max_output_tokens
    raised back to 450 (from 260) to match — that number already has a
    real story behind it (a confirmed live mid-word truncation at 200
    the first time longer output was permitted), not re-derived from
    scratch."""
    facts = "; ".join(picked)
    weekday = now.strftime("%A")
    history_block = _recent_history_block(now)
    history_section = (
        f"Recent days for context (oldest first, not including today):\n{history_block}\n\n"
        "Use this ONLY to notice a genuine pattern actually worth a real line (a stretch of "
        "early shifts, several rough-weather days in a row, yesterday being rough too) — most "
        "days won't have one, and forcing a callback where there isn't a real connection reads "
        "worse than not mentioning it at all.\n\n"
        if history_block
        else ""
    )
    notes_section = (
        f"Long-term patterns you've built up about him across many past mornings (your own "
        f"evolving understanding, distinct from the day-by-day record above): {_learned_notes}\n\n"
        if _learned_notes
        else ""
    )
    prompt = (
        f"You are {USER_FIRST_NAME}'s personal AI assistant — genuinely funny, and above all an "
        f"actual partner whose real job is keeping {USER_FIRST_NAME} genuinely informed about his "
        "own day. No fixed character to perform and no assigned persona — don't imitate anyone "
        "else's voice (a butler, a movie AI, anyone); figure out your own personality across these "
        "and let it come through in how you actually write, rather than announcing what it is. The "
        "humor is in service of the job, not the point in itself — a morning with nothing funny to "
        "say about it is still a successful brief if he walks away knowing what's actually going on "
        "today. You choose the tone each morning, not a fixed formula: genuinely warm or sincere if "
        f"that's actually what today calls for, dry and cutting and willing to roast "
        f"{USER_FIRST_NAME} directly if that's funnier, deadpan, playful, silly, whatever — your "
        "call, and it's fine (good, even) for it to vary morning to morning instead of landing on "
        "the same note every time. When you do go for the edge, go all the way: don't hedge a "
        "hard line by softening it right after, and a line that actually stings is a win, not "
        "something to walk back — he doesn't need protecting from the joke. Actual profanity "
        "(shit, damn, hell, ass, and the like) is explicitly allowed when a line genuinely lands "
        "sharper with one — your call on when, never required, never the default either. Not "
        "corporate, not a stiff butler either direction. Say whatever actually lands.\n\n"
        "Length is your own call too, not a fixed target — this is a quick read on a kiosk, not a "
        "report, so brevity is usually the right instinct, but there's no mandated sentence count. "
        "A quiet morning might genuinely be one sharp line; a real one (several things actually "
        "worth saying) can run longer — never padded just to hit a length, and never crammed just "
        "to stay under one either. Picking what's actually worth saying and leaving the rest out "
        "entirely still applies regardless of how long you land on — not a fixed template restating "
        "every fact in a slightly funnier voice — it should read like a real, specific observation "
        "about his actual day, never like a list that got translated. This renders directly as "
        "HTML, so <strong>/<em> for emphasis is available when it genuinely helps a single word or "
        "phrase land, and a plain <br> for a real line break if the length you land on actually "
        "calls for one (a genuinely busy morning, a short break between two distinct things) — "
        "both sparingly, as tools, not decoration on a short line that doesn't need either.\n\n"
        f"Background on {USER_FIRST_NAME}, for real specific jokes instead of generic ones — "
        f"reference it only when genuinely relevant to today's facts below, don't force a "
        f"mention in every brief: {USER_PROFILE}\n\n"
        f"{notes_section}"
        f"{history_section}"
        f"Today is {weekday} — a real, given fact, not a guess. Comment on it, and on how it "
        "relates to the facts below (a work shift landing on a weekend is genuinely worth a real "
        "line; an ordinary weekday usually isn't), only when it's actually relevant — your call, "
        "don't force it in every time. The humor otherwise comes entirely from how things are "
        "delivered, never from anything invented — do not add or invent any fact beyond the "
        "weekday, the background, and the long-term notes/recent-days record above, and the raw "
        "data given below.\n\n"
        "You do NOT have to mention every single fact below — pick whatever's actually worth "
        "saying and leave the rest out entirely, the same instruction as the length rule above, "
        "restated because it matters: a real person deciding what to tell someone about their day "
        "does not recite every data point they have, they choose. Some mornings that's one fact, "
        "some mornings it's four — never a rule, always a real call based on what's actually "
        "here today.\n\n"
        "Always write numbers as actual digits, never spelled out as words — '18 minutes' and "
        "'0.8%' and '10:00 AM', not 'eighteen minutes' or 'zero point eight percent' or 'ten "
        "o'clock'. This is read at a glance on a screen, not literary prose, and digits are "
        "faster to scan.\n\n"
        "Below is the raw, real data for today — plain facts, not anyone else's already-chosen "
        "words. Nobody has written any of this into a sentence yet; that's entirely your job, in "
        "your own voice, from these numbers. Not everything in it is actually related to "
        "everything else, either. Some facts share real, physical cause and effect — cold enough "
        f"and wet enough together on {USER_FIRST_NAME}'s own roads meaning genuine ice risk, not "
        "just two separate numbers; a road incident sitting on the same commute route that already "
        "has a delay. Call those out directly when they're both there. Others are just separate "
        f"things that happen to both be true this morning with no real link between them — a team "
        f"{USER_FIRST_NAME} follows playing a game hundreds of kilometers from here has nothing to "
        "do with local weather, and manufacturing a connection between facts that aren't actually "
        "connected (just because they showed up the same morning) reads as a mistake, not a joke — "
        "don't do it. The genuinely interesting connections are usually across days, not within "
        "one: see the long-term notes and recent-days record above for that — a real pattern "
        "actually worth a comment (a stretch of early shifts, a tendency you've noticed hold up "
        "over many real mornings), not something guessed from a single day. "
        f"Address {USER_FIRST_NAME} by name naturally somewhere in it. Start with a capital "
        "letter. Raw data: " + facts
    )
    if groq_client.ai_pulls_paused():
        return None
    # Session request: "instead of saying keep it two to three
    # sentences and every fact must appear, let it use its own
    # discretion" — the prompt's own length instruction above went from
    # a firm 2-3 sentence cap back to genuine discretion, so the token
    # budget needs the same headroom it had the LAST time real
    # structure/longer output was permitted (450) — that number wasn't
    # arbitrary, it came from a confirmed live truncation at 200 on a
    # genuinely eventful morning. Restored rather than re-guessed.
    return gemini_client.generate_periodic(
        "morning_briefing_sentence", AI_REFRESH_SECONDS, prompt, temperature=0.85, max_output_tokens=450
    )


def render(now: datetime, weather: dict | None, air_quality: dict | None) -> None:
    if not (MORNING_WINDOW_START_HOUR <= now.hour < MORNING_WINDOW_END_HOUR):
        return
    if not weather:
        return

    clauses = []
    for fn, args in (
        (_alert_clause, (now,)),
        (_weather_clause, (now, weather)),
        (_precip_clause, (now, weather)),
        (_road_ice_clause, (now, weather)),
        (_air_clause, (now, air_quality)),
        (_commute_clause, (now,)),
        (_agenda_clause, (now,)),
        (_household_clause, (now,)),
        (_markets_clause, (now,)),
        (_portfolio_clause, (now,)),
        (_portfolio_activity_clause, (now,)),
        (_game_today_clause, (now,)),
        (_daylight_clause, (now, weather)),
    ):
        try:
            result = fn(*args)
        except Exception:
            result = None
        if result is not None:
            clauses.append(result)

    if not clauses:
        return
    clauses.sort(key=lambda c: c[0], reverse=True)
    # Session request: "give it as much data as possible so it could
    # make as many informed comments as possible." The AI now gets
    # EVERY fact computed today, not just the top MAX_CLAUSES=5 by
    # priority — that cap exists for the plain-text fallback below
    # (which genuinely needs to stay short with no AI narration to
    # shape it), not for what the AI itself gets to see and draw on.
    # A day where 8 of the 10 clause functions fire (a real event, real
    # weather, real traffic, a full calendar, all at once) used to
    # silently lose 3 of them before the AI ever got a look, with no
    # way to notice a connection between something it was never told.
    all_facts = [text for _, text in clauses]
    picked = all_facts[:MAX_CLAUSES]
    try:
        _record_history(now, all_facts)
    except Exception:
        pass
    # Audit fix: this used to run BEFORE _ai_sentence, which meant on
    # the very first rerun of a new day, the "long-term notes... distinct
    # from the day-by-day record" _ai_sentence's own prompt promises
    # would already have today's facts folded into them by the time it
    # read _learned_notes — the exact same-day leak _recent_history_
    # block deliberately guards against for the raw history. Ordered
    # after _ai_sentence now so today's brief always sees notes as they
    # stood coming INTO today, and _update_learned_notes only folds
    # today in afterward, for tomorrow's benefit.
    try:
        sentence = _ai_sentence(all_facts, now)
    except Exception:
        sentence = None
    try:
        _update_learned_notes(now, all_facts)
    except Exception:
        pass
    if sentence is None:
        # Rare path — only reached if the AI call itself fails (Gemini
        # down, rate-limited, or the overnight pause). No styling left
        # to fall back on now that the facts themselves are plain data,
        # not pre-phrased prose (see this module's own docstring) — a
        # flat semicolon join is exactly what a degraded-mode fallback
        # should look like, not something worth its own templating.
        # Still uses the capped `picked`, not `all_facts`, so a day
        # with a lot going on doesn't turn this into an unreadable list.
        plain = "; ".join(picked)
        sentence = f"Morning update — {plain[0].upper() + plain[1:]}."

    _notify_new_brief(sentence, now)
    st.markdown(f'<div class="morning-briefing">{sentence}</div>', unsafe_allow_html=True)


# Loaded once at import, not re-fetched from persisted_state on every
# call — render() (and therefore _notify_new_brief) runs unconditionally
# every 5s rerun for the whole MORNING_WINDOW_START_HOUR-END_HOUR
# window, and with persisted_state now backed by Upstash Redis,
# "reload from the cloud every rerun just to check" would burn ~3,600
# GET commands a day from this one call site alone (smaller than the
# three fully-24/7 sites — see groq_client.py's _outage_episode — but
# the same root cause, so fixed the same way while auditing it).
_last_brief_date: str | None = persisted_state.load("morning_brief_date", None)


def _notify_new_brief(sentence: str, now: datetime) -> None:
    """Pushes the morning brief to the phone once per calendar day — the
    first time render() produces a real brief that day (AI-written or
    the plain fallback, whichever path it came from), not every 5s
    rerun for the rest of the morning window, and not once per browser
    session either. Session request: "morning brief push... a little
    five AM push... that'd be sick," then, once it was still firing more
    than once: "I don't want an alert every fifteen minutes basically
    saying the same thing... pick one time each day."

    Persisted to disk/cloud (persisted_state, see _last_brief_date
    above), not just a plain process-local global — a plain global
    survives across browser sessions but not across an actual process
    restart, and this session's own several redeploys in a row kept
    resetting an in-memory version of this right back to "nothing sent
    yet," reproducing the exact same symptom (a duplicate real push)
    from a different cause than the first fix addressed."""
    global _last_brief_date
    today = now.date().isoformat()
    if _last_brief_date == today:
        return
    _last_brief_date = today
    persisted_state.save("morning_brief_date", today)
    ntfy_client.send(title="Morning Brief", message=sentence, priority="default", tags="sunny")


# Recent days' picked facts, oldest first — session question: "would it
# benefit to train the ai on who i am... make it connect the dots on my
# day more often." The brief only ever saw today's own isolated facts,
# so it had no way to notice a real pattern (a stretch of early shifts,
# a run of bad weather, yesterday also being rough) — this gives
# _ai_sentence something to actually connect to. Bounded to
# HISTORY_MAX_DAYS entries (an ordered list, oldest popped off the
# front once it's full) and persisted the same way _last_brief_date
# above is, so a redeploy doesn't wipe the very thing this exists to
# remember. Loaded once at import, not re-fetched every rerun — same
# per-rerun-cost reasoning as _last_brief_date's own comment.
HISTORY_MAX_DAYS = 4
_brief_history: list[dict] = persisted_state.load("morning_brief_history", [])


def _record_history(now: datetime, picked: list[str]) -> None:
    """Appends today's picked facts to _brief_history — once per
    calendar day (checked against the history's own last entry, not a
    separate tracker), regardless of whether the AI narration itself
    succeeds or falls back to the plain join, so tomorrow's brief can
    still reference today's real facts even on a day Gemini was down."""
    global _brief_history
    today = now.date().isoformat()
    if _brief_history and _brief_history[-1]["date"] == today:
        return
    _brief_history.append({"date": today, "facts": picked})
    _brief_history = _brief_history[-HISTORY_MAX_DAYS:]
    persisted_state.save("morning_brief_history", _brief_history)


def _recent_history_block(now: datetime) -> str:
    """Prior days' facts (not including today), oldest first, as a
    compact block for _ai_sentence's own prompt — "" if there's no
    history yet (a fresh deploy, or simply the first few days this
    feature has existed). Excludes today's own entry even if
    _record_history already ran earlier this same process — this block
    is specifically the BEFORE-today record for spotting a pattern
    leading up to today, not a copy of what's already in today's own
    facts."""
    today = now.date().isoformat()
    prior = [day for day in _brief_history if day["date"] != today]
    if not prior:
        return ""
    lines = [f"{day['date']}: {'; '.join(day['facts'])}" for day in prior]
    return "\n".join(lines)


# Session request: "I wanted it to almost, like, learn more and more
# about me every single time it is a morning brief... make sure that it
# sees and is learning and is becoming smarter every single day...
# truly be a digital assistant." HISTORY_MAX_DAYS above is a fixed
# rolling window — by definition it forgets anything older than 4
# days, so it can never build real long-term understanding on its own
# (a pattern noticed 3 weeks ago would already be gone). This is the
# durable half: a short, evolving note the AI itself rewrites once a
# day, keeping genuine patterns it's actually confident about and
# dropping ones a later day disproves — an actual compounding memory,
# not just a longer window on the same fixed-size log.
LEARNED_NOTES_MAX_CHARS = 700
_learned_notes: str = persisted_state.load("morning_brief_learned_notes", "")
_learned_notes_date: str | None = persisted_state.load("morning_brief_learned_notes_date", None)


def _update_learned_notes(now: datetime, facts: list[str]) -> None:
    """Once per calendar day (own tracker — not reusing _brief_history's
    or _last_brief_date's, since this can legitimately still need
    updating on a day the AI narration itself failed; it's about
    noticing patterns, not phrasing today's specific brief), asks
    Gemini to rewrite its own standing note about Brayden from scratch:
    keep/sharpen what's still true, drop what a new day already
    disproved, add what's newly a real pattern. Same overnight-pause
    gate as every other AI pull here — nothing about this is time-
    sensitive enough to ever need to bypass it. Calls gemini_client.
    generate directly rather than generate_periodic — this already has
    its own once-a-day gate, so generate_periodic's separate wall-clock
    cadence would just be a second, redundant throttle on top."""
    global _learned_notes, _learned_notes_date
    today = now.date().isoformat()
    if _learned_notes_date == today:
        return
    if groq_client.ai_pulls_paused():
        return
    prompt = (
        "You keep a short, private, evolving note about Brayden for your own future reference only — "
        "never shown to him directly. It should capture genuine recurring patterns across many real "
        "mornings of his actual life (a schedule shape, a tendency, something that's actually shown "
        "up more than once) — not a log of individual days, and not anything guessed from a single "
        "day alone.\n\n"
        f"Your note so far: {_learned_notes or '(nothing recorded yet — this is early)'}\n\n"
        f"Today's real facts: {'; '.join(facts)}\n\n"
        "Rewrite the note completely, from scratch: keep or sharpen anything still genuinely true, "
        "drop anything today's facts show is stale or turned out to be a one-off, and add anything "
        "new that's actually a real pattern now — not every day changes anything, and it's fine to "
        "return it unchanged. If there isn't real history to support a genuine pattern yet (only a "
        "handful of days recorded so far, or today's facts are just one day's snapshot with nothing "
        "repeating), keep the note short or even mostly empty rather than dressing up a single day's "
        "facts as if they were an established pattern — a confident-sounding pattern built from too "
        "little data is worse than honestly having nothing yet. Plain prose, no headers or bullet "
        f"points, nothing invented beyond what you've actually observed. Under {LEARNED_NOTES_MAX_CHARS} characters."
    )
    try:
        updated = gemini_client.generate(prompt, temperature=0.4, max_output_tokens=220)
    except Exception:
        updated = None
    if updated is None:
        return
    _learned_notes = updated.strip()[:LEARNED_NOTES_MAX_CHARS]
    _learned_notes_date = today
    persisted_state.save("morning_brief_learned_notes", _learned_notes)
    persisted_state.save("morning_brief_learned_notes_date", _learned_notes_date)
