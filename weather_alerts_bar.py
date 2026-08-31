"""Renders the weather-statement banner: an active Environment Canada
alert takes priority — pulled from two genuinely separate EC products,
its general weather-warnings feed (ec_alerts) and its AQHI air quality
observations (ec_aqhi), confirmed live to not overlap at all — and our
own extreme-heat/extreme-cold fallback only ever shows when neither
has anything active for the region."""

import html
from datetime import datetime

import streamlit as st

import ec_alerts
import ec_aqhi
import ec_storm_timing
import groq_client
import kiosk_tts
import persisted_state
from config import EXTREME_COLD_THRESHOLD_C, EXTREME_HEAT_THRESHOLD_C

# Session request: "how can we make the severe weather alerts a little
# bit more menacing... they're just on and then talking" — tried a real
# siren clip in place of the shared gentle bell chime for genuinely
# severe hazards. Session follow-up: "scrap it and go back to the
# regular bell" — reverted; the full-screen red pulse overlay
# (app.py's kioskShowMenaceOverlay) stays for extreme/warning tiers,
# just the audio itself is back to the plain chime every other toast
# in this app already uses.

# Tornado/hurricane/tsunami are categorically more dangerous than any
# other hazard EC issues for this region — a Tornado Watch still
# deserves to look scarier than a routine Heat Warning, so hazard type
# has to weigh in alongside EC's warning/watch/statement tier wording,
# not just tier alone. Heat/cold/fog-family hazards are real but
# generally less sudden/life-threatening than storm/wind/flood/ice
# ones, so a Warning for one of these is visually subordinate to a
# storm-type Warning at the same tier (Tornado > Thunderstorm > Heat,
# as requested).
_EXTREME_HAZARD_TERMS = ("tornado", "hurricane", "tsunami")
_MODERATE_HAZARD_TERMS = ("heat", "cold", "frost", "fog", "rainfall", "snowfall", "air quality")

# Which hazard actually wins when several alerts are active at once —
# deliberately separate from _severity()'s tier-first coloring below.
# Tier (warning/watch/statement) reflects confidence/imminence, not
# danger, so a low-confidence Thunderstorm Watch still has to outrank a
# certain Heat Warning here: Tornado > Thunderstorm > Heat holds
# regardless of which one currently has the more definite tier wording.
_HAZARD_RANK = {
    "tornado": 100, "hurricane": 95, "tsunami": 95,
    "thunderstorm": 80, "tropical storm": 75, "flood": 70,
    "blizzard": 65, "winter storm": 65, "ice storm": 63, "freezing rain": 60,
    "wind": 55, "rainfall": 50, "snowfall": 45,
    # Ranked above heat/cold, not with fog/frost: by the time
    # ec_aqhi.aqhi_alert() ever produces a title at all, it's already
    # filtered to High Risk or worse (see ec_aqhi._HIGH_RISK_AQHI) —
    # a genuinely serious condition, not the routine end of the
    # "air quality" bucket the old rank of 15 (tied with fog) assumed.
    "air quality": 35,
    "heat": 30, "cold": 30, "frost": 20, "fog": 15,
}
_DEFAULT_HAZARD_RANK = 40  # an unrecognized hazard — assume moderate rather than trivial or extreme
_TIER_TIEBREAK = {"warning": 2, "watch": 1, "statement": 0}


def _is_severe_hazard(title: str) -> bool:
    """True for a genuine storm-type hazard (thunderstorm/tornado/
    hurricane/tropical storm/tsunami) — the exact same criterion
    already established for storm-proximity escalation (ec_storm_
    timing.STORM_HAZARD_TERMS, used for the Govee lights/countdown
    headline) — reused here rather than a second, possibly-drifting
    definition of "severe."

    Session report: "will the AI voice read every single EC alert?
    even if its a heat or squall warning?" followed by "yes, fix that"
    — app.py's kioskPlayWeatherAlert used to hardcode kioskAlertVolume
    (true) for every weather voice alert regardless of actual hazard,
    so a routine Heat Warning at 2am got the same never-fully-silent
    volume floor as a real tornado. This flag, threaded through get_
    new_alerts/get_storm_proximity_alerts -> render_alert_bar's own
    data-severe attribute, lets app.py pass the real per-alert value
    instead."""
    return any(term in title.lower() for term in ec_storm_timing.STORM_HAZARD_TERMS)


def _tier(title: str) -> str:
    t = title.lower()
    if "warning" in t:
        return "warning"
    if "watch" in t:
        return "watch"
    return "statement"


def _type_label(title: str) -> str:
    """The real EC bulletin type — Warning/Watch/Advisory/Statement —
    for saying the actual type out loud. Deliberately NOT just
    _tier(title).capitalize(): _tier only distinguishes 3 buckets
    (warning/watch/"everything else") because that's all its own
    caller, severity coloring, needs — it folds a real Advisory into
    the same "statement" bucket as an actual Special Weather Statement.
    That's the right call for a color tier, but wrong for saying the
    real type out loud — confirmed live against the actual active
    alert while building this ("YELLOW ADVISORY - FOG..."), which
    _tier alone would report as "statement," not the real word EC
    itself used. Falls back to "Statement" (EC's own generic bulletin
    name, "Special Weather Statement") only when none of the other
    three real type words appear at all."""
    t = title.lower()
    if "warning" in t:
        return "Warning"
    if "watch" in t:
        return "Watch"
    if "advisory" in t:
        return "Advisory"
    return "Statement"


def _hazard_rank(title: str) -> int:
    t = title.lower()
    matches = [rank for hazard, rank in _HAZARD_RANK.items() if hazard in t]
    return max(matches) if matches else _DEFAULT_HAZARD_RANK


def _selection_score(alert: dict) -> tuple[int, int]:
    """Which single alert wins when several are active — hazard type
    first (Tornado > Thunderstorm > Heat, full stop, regardless of
    tier), EC's warning/watch/statement wording only as a tiebreak
    between two alerts for the *same* hazard (a Thunderstorm Warning
    still outranks a Thunderstorm Watch)."""
    title = alert["title"]
    return (_hazard_rank(title), _TIER_TIEBREAK[_tier(title)])


def _severity(title: str) -> str:
    """One of "extreme" (tornado/hurricane/tsunami, any tier) >
    "warning" > "warning-moderate" (a Warning-tier heat/cold/fog-family
    hazard) > "watch" > "statement". EC's own title text always
    contains a tier word (e.g. "YELLOW WARNING - HEAT...", "Severe
    Thunderstorm Warning", "Special Weather Statement") and the hazard
    name itself, so this needs no separate fields from the feed. Drives
    how hard the bar visually pulls attention for whichever alert
    _selection_score picked — tier still decides the color/intensity
    honestly (a Watch shouldn't look as certain as a Warning) even
    though it's hazard type that decided which alert got shown."""
    t = title.lower()
    if any(term in t for term in _EXTREME_HAZARD_TERMS):
        return "extreme"
    tier = _tier(title)
    if tier == "warning":
        return "warning-moderate" if any(term in t for term in _MODERATE_HAZARD_TERMS) else "warning"
    return tier


def _fallback_text(weather: dict | None) -> str | None:
    if not weather:
        return None
    high = weather.get("forecast_high_c")
    low = weather.get("forecast_low_c")
    if high is not None and high >= EXTREME_HEAT_THRESHOLD_C:
        return f"Extreme Heat Advisory — today's high near {high:.0f}°C"
    if low is not None and low <= EXTREME_COLD_THRESHOLD_C:
        return f"Extreme Cold Advisory — today's low near {low:.0f}°C"
    return None


def _combined_alerts() -> list[dict]:
    """EC's general weather-warnings feed plus, separately, a
    synthesized alert for a genuinely elevated AQHI reading (see
    ec_aqhi.aqhi_alert) — confirmed live these are two real,
    independent EC products with no overlap (the weather feed does not
    carry air quality at all), so both need fetching and both need to
    participate in the same selection/severity logic below. Each
    guarded separately so a failure fetching one doesn't also hide the
    other."""
    try:
        alerts = list(ec_alerts.fetch_alerts())
    except Exception:
        alerts = []
    try:
        aqhi = ec_aqhi.aqhi_alert()
    except Exception:
        aqhi = None
    if aqhi is not None:
        alerts.append(aqhi)
    return alerts


def current_severity() -> str | None:
    """The same alert render() below would show, resolved to just its
    severity tier — for callers elsewhere in the app (the Govee light)
    that need to react to real EC alerts without duplicating the
    fetch/selection logic. None if nothing's active, or if the only
    thing showing is our own manual heat/cold fallback (that's a
    self-generated heuristic, not a genuine EC alert, and shouldn't
    trigger a real-alert response anywhere)."""
    alerts = _combined_alerts()
    if not alerts:
        return None
    alert = max(alerts, key=_selection_score)
    return _severity(alert["title"])


# Session request: "a recent special weather statement just came in but
# it didnt show as a toast alert, make sure they show up." weather_
# statement_candidate (headline_rotation.py's own unified rotation)
# already surfaces whatever's currently active in the persistent
# banner, but that banner is suppressed during a jumbotron takeover
# (app.py) — with nothing else picking up the slack, a new alert issued
# while a game's on screen went completely unseen, which is exactly what
# happened here. get_new_alerts below mirrors news.get_new_alerts's own
# shape so app.py's existing toast queue (which DOES still run during a
# takeover) can carry this too, resolving from the exact same
# _combined_alerts/_selection_score logic weather_statement_candidate
# uses so the toast and the banner always agree on which alert currently
# wins.
#
# Persisted (not a plain module-level set) so a redeploy/restart can't
# re-toast an alert this process already showed — same reasoning as
# news.py's own news_seen_headlines. Deliberately has NO "first call
# just establishes a baseline, don't alert yet" step the way news.
# get_new_alerts has: that exists there to avoid flooding dozens of
# already-old headlines on a fresh restart, but the failure mode here
# is the opposite and far worse — silently suppressing the one toast
# that matters most (a warning already active the moment a redeploy
# happens to land) is not an acceptable trade for a life-safety feed
# that's supposed to "work consistently."
MAX_SEEN_ALERTS = 200
# Per-instance (session request: "every single toast we get... every
# terminal gets its own alert") — same reasoning as news.py/
# commute_reminder.py/prediction_markets_client.py's own toast dedup.
_seen_alert_keys: dict = dict(persisted_state.load_per_instance("weather_seen_alerts", {}))

# Session request: "when a special weather statement is issued... it
# should always say this is a warning/watch/whatever... and every time
# it is updated, you should say this warning has been updated... this
# is how it should always always always start." Deliberately a SEPARATE
# store from _seen_alert_keys above, keyed by TITLE not id: EC issues a
# new id every time it re-issues/extends an already-active alert (see
# get_new_alerts's own docstring on why that's what makes a "continued"
# reissue toast at all), so "have I seen THIS EXACT id before" can never
# answer "is this genuinely the first time, or a reissue of something
# already active" — only the title stays stable across a reissue.
_ANNOUNCED_TITLES_KEY = "weather_announced_titles"
_announced_titles: dict = dict(persisted_state.load_per_instance(_ANNOUNCED_TITLES_KEY, {}))


def _is_update(title: str) -> bool:
    return title in _announced_titles


def _mark_title_announced(title: str) -> None:
    _announced_titles[title] = True
    if len(_announced_titles) > MAX_SEEN_ALERTS:
        _announced_titles.pop(next(iter(_announced_titles)))
    persisted_state.save_per_instance(_ANNOUNCED_TITLES_KEY, _announced_titles)

# Session report: "it's still going twice... for the severe thunderstorm
# warning alert thing." get_new_alerts (below, the one-shot "just
# arrived" toast) and get_storm_proximity_alerts (further down, the
# repeating countdown) are deliberately separate systems, each
# individually correct on its own terms — but nothing stopped both from
# firing for the SAME real alert close together in real time. Confirmed
# live: a real alert already had 5 proximity milestones recorded while
# its own one-shot toast still hadn't fired, meaning that one-shot
# toast was queued to land right on top of whatever milestone had just
# played, sounding exactly like an echo even though neither system was
# individually malfunctioning. Shared per-alert cooldown so a toast
# from EITHER system DEFERS (not permanently skips — nothing here marks
# _seen_alert_keys/_storm_milestones_shown while on cooldown, so each
# side just tries again on a later rerun) if the OTHER system already
# toasted for the same alert recently. 5 minutes is comfortably above
# the tightest real gap between two consecutive proximity milestones
# (2 minutes, the 5-to-3 step) so this practically only ever suppresses
# a genuine same-moment collision with the one-shot toast, not the
# proximity countdown's own normal cadence against itself.
WEATHER_TOAST_COOLDOWN_SECONDS = 5 * 60
_last_weather_toast_at: dict[str, float] = dict(persisted_state.load_per_instance("weather_last_toast_at", {}))


def _weather_toast_on_cooldown(key: str, now_ts: float) -> bool:
    last = _last_weather_toast_at.get(key)
    return last is not None and now_ts - last < WEATHER_TOAST_COOLDOWN_SECONDS


def _mark_weather_toast_fired(key: str, now_ts: float) -> None:
    _last_weather_toast_at[key] = now_ts
    if len(_last_weather_toast_at) > MAX_SEEN_ALERTS:
        _last_weather_toast_at.pop(next(iter(_last_weather_toast_at)))
    persisted_state.save_per_instance("weather_last_toast_at", _last_weather_toast_at)


def _friendly_headline(title: str, type_label: str | None = None, is_update: bool = False) -> str:
    """A short, natural-sounding rewrite of EC's own raw alert title —
    session request: "rephrase a special weather alert... it's just
    this yellow advisory fog North bay, powassan, mattawa, which isn't
    fun," then, on a first pass that read too much like the spoken
    summary below: "I don't want you to write a paragraph. I want a
    simpler, more conversational alert." One short sentence, not a
    rewrite of the full bulletin — distinct from _spoken_summary's own
    groq_client.generate call just above, which deliberately DOES
    produce a flowing paragraph, but only for Piper to read aloud, never
    for the screen.

    Only the DISPLAYED words change — every caller keeps computing
    severity/tier/storm-phase/hazard-rank off the real, unrewritten
    `alert["title"]` (see this module's own _severity/_tier/_is_severe_
    hazard/_selection_score), never off this function's return value,
    so a rewrite that happens to drop or reword "warning"/"watch" can
    never silently change how urgent this looks or behaves.

    Cached by groq_client.generate's own exact-prompt-text caching
    (see its own docstring) — the raw title stays identical across
    every ~5s rerun for as long as the same alert stays active, so this
    only ever pays for a real call once per genuinely new alert
    issuance, not every rerun. Falls back to the raw title unchanged on
    any AI outage/rate limit, same as every other AI-optional path in
    this app — a real hazard worded plainly beats no banner at all.

    `type_label`/`is_update`, when given, prepend a deterministic
    "Advisory:"/"Advisory updated:" prefix — session request: "it
    should always say this is a warning/watch/whatever... this is how
    it should always always always start." Built in code, not left to
    the AI rewrite prompt above, on purpose: an AI instruction to
    "always open with the type" is a should, not a guarantee (this
    exact class of reliability gap already burned the morning brief's
    profanity prompt once — see that memory), and "always always
    always" is exactly the bar a prompt alone can't promise. Optional
    and defaulted off because this function has a second caller,
    weather_statement_candidate's own PERSISTENT banner — that one
    keeps its current unprefixed behavior; the "issued"/"updated"
    framing is specific to get_new_alerts's one-shot toast moment, not
    a standing status display."""
    rewritten = groq_client.generate(
        "Rewrite this Environment Canada weather alert title as one short, casual sentence a person would "
        "actually say out loud to a friend — not a formal bulletin, not a paragraph. Keep the real hazard "
        "and location. Under 12 words. Reply with only the sentence, nothing else.\n\n" + title,
        temperature=0.6,
        max_output_tokens=80,
        account="primary",
        reasoning_effort="low",
    )
    body = rewritten or title
    if type_label is None:
        return body
    prefix = f"{type_label} updated" if is_update else type_label
    return f"{prefix}: {body}"


def get_new_alerts(now: datetime) -> list[dict]:
    """New weather alerts since the last check — {"kind": "weather",
    "severity", "label", "headline"}, the toast queue's own generic
    shape (see news.get_new_alerts/sports_alerts.get_new_alerts).
    Keyed by the winning alert's own stable id (ec_alerts.fetch_alerts's
    "id" field for a real EC alert — genuinely unique per issuance,
    embeds the issue timestamp — or its title for the AQHI-synthesized
    alert, which has no id of its own) so a genuinely new issuance
    always toasts even if an alert with the same hazard/title was seen
    before, while an alert that's merely still active from a prior
    rerun never re-toasts — confirmed live this is exactly why a
    "continued" re-issuance (EC extending an already-active warning's
    own expected clear time) toasts again: same title, new id. The
    manual heat/cold fallback (render()'s own else branch) is
    deliberately NOT included — it's a slow-moving daily forecast
    threshold, not a discrete "just came in" moment, and
    current_severity() already treats it as not a real alert for the
    same reason.

    Session follow-up, on exactly that "continued" reissue toast: "can
    you add the clearing time to the toast." Storm-grade alerts (see
    ec_storm_timing.storm_phase/STORM_HAZARD_TERMS) get a real EC-
    sourced clock time appended — "arriving around" for "approaching",
    "clearing by" for "here"/"leaving" (target already means whichever
    of those is next, see storm_phase's own docstring) — straight off
    the same "target" the countdown headline uses, so the toast and the
    on-screen timer always agree. Non-storm-grade alerts (a Heat
    Warning, say) get no time appended — there's no meaningful EC
    "clear" instant to show for those in the first place."""
    alerts = _combined_alerts()
    if not alerts:
        return []
    alert = max(alerts, key=_selection_score)
    key = alert.get("id") or alert["title"]
    if key in _seen_alert_keys:
        return []
    now_ts = now.timestamp()
    if _weather_toast_on_cooldown(key, now_ts):
        # A proximity-milestone toast for this exact alert already
        # fired within WEATHER_TOAST_COOLDOWN_SECONDS — defer, don't
        # mark seen, so this genuinely fires (not gets lost) on a later
        # rerun once the cooldown clears (see this module's own
        # _weather_toast_on_cooldown docstring for the full story).
        return []
    _seen_alert_keys[key] = True
    if len(_seen_alert_keys) > MAX_SEEN_ALERTS:
        _seen_alert_keys.pop(next(iter(_seen_alert_keys)))
    persisted_state.save_per_instance("weather_seen_alerts", _seen_alert_keys)
    _mark_weather_toast_fired(key, now_ts)
    # is_update checked BEFORE marking this title announced below — the
    # first time a title is ever seen, _is_update must read False.
    type_label = _type_label(alert["title"])
    is_update = _is_update(alert["title"])
    _mark_title_announced(alert["title"])
    severity = _severity(alert["title"])
    headline = _friendly_headline(alert["title"], type_label, is_update)
    phase_info = ec_storm_timing.storm_phase(now, alert["title"], severity)
    # Session follow-up: "make it so that the clearing [time] number
    # sits where the leave in section is in the jumbotron" — this used
    # to just get appended as plain trailing text onto `headline`
    # ("...Mattawa — clearing by 4:09 PM"), easy to miss buried at the
    # end of a long sentence. Now a separate countdown_target_ms/
    # countdown_verb pair instead, so render_alert_bar can render it as
    # its own live-ticking element (same .live-countdown/data-target-ms
    # mechanism commute_reminder.render_ticker_leave_bar's "Leave in"
    # already uses) positioned distinctly rather than lost in the
    # sentence — a real countdown ("Clearing in 38:12"), not a static
    # clock-face time, for the same reason "Leave in" counts down
    # instead of showing a fixed departure time.
    countdown_target_ms = None
    countdown_verb = None
    if phase_info is not None:
        countdown_target_ms = int(phase_info["target"].timestamp() * 1000)
        countdown_verb = "Arriving" if phase_info["phase"] == "approaching" else "Clearing"
    return [
        {
            "kind": "weather",
            "severity": severity,
            "label": "Environment Canada",
            "headline": headline,
            "countdown_target_ms": countdown_target_ms,
            "countdown_verb": countdown_verb,
            # Session request: "can you make it read the entire alert from
            # EC when its first issued" — see _spoken_summary's own
            # docstring for where this text actually comes from and why.
            # Only meaningful for this one-shot "just came in" toast —
            # get_storm_proximity_alerts's own repeating milestone toasts
            # below intentionally don't carry this (nothing new to read
            # out again every few minutes), so their dicts have no
            # "summary" key at all and render_alert_bar's own
            # .get("summary", "") default covers it.
            "summary": _spoken_summary(alert, type_label, is_update),
            # See _is_severe_hazard's own docstring — a heat/squall/
            # statement-tier alert gets the normal quiet-at-night volume
            # curve, not the never-fully-silent one real storms get.
            "severe": _is_severe_hazard(alert["title"]),
        }
    ]


_SPOKEN_LABELS = ("What:", "When:", "Where:", "Who:", "Why:", "Additional information:")


def _strip_spoken_labels(text: str) -> str:
    """Drops EC's own plain-text section labels (meant for a reader's
    eye, not a listener's ear) from bulletin text before it's spoken —
    moved here from app.py's kioskCleanSpokenSummary now that Piper
    renders audio server-side: everything about what gets spoken has to
    be decided before synthesis, not touched up client-side afterward."""
    for label in _SPOKEN_LABELS:
        text = text.replace(label, "")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


# Session report, live during a real severe thunderstorm alert (which
# happened to land at the same time as a real Blue Jays scoring toast):
# "I'm sorry, I can't read this without the updated weather data" got
# spoken aloud verbatim. groq_client.generate returned a genuine LLM
# refusal/confusion response rather than raising — it got a real
# response back, just not a usable rewrite — so _spoken_summary's own
# `rewritten or raw` treated it as a successful result and read it
# straight to Piper. groq_client.generate's own caching only ever skips
# a genuine FAILURE (an exception, a rate limit, None) — a "successful"
# call that happens to return refusal text like this still gets
# cached, so a bad response can keep recurring across calls until the
# underlying raw bulletin text itself changes. Guarded here (not in
# groq_client.py) — this is a content-quality check specific to what a
# rewrite is supposed to look like, not a general failure mode the
# shared client should try to detect on every caller's behalf.
_REFUSAL_PREFIXES = ("i'm sorry", "i am sorry", "sorry,", "i can't", "i cannot", "as an ai", "i don't have", "i do not have")


def _looks_like_refusal(text: str) -> bool:
    # Real bug, caught live testing this same fix: the model's actual
    # refusal opened with a curly apostrophe ("I’m sorry..."), which
    # a plain "i'm sorry" (straight apostrophe) prefix check silently
    # missed entirely — normalized here rather than trying to enumerate
    # every unicode apostrophe variant a model might reach for.
    stripped = text.strip().lower().replace("’", "'").replace("‘", "'")
    return any(stripped.startswith(p) for p in _REFUSAL_PREFIXES)


def _milestone_spoken_text(title: str, approaching: bool, milestone: int) -> str:
    """Spoken sentence for a storm-proximity milestone toast (get_storm_
    proximity_alerts) — wording matches, verbatim, what app.py's
    kioskPlayWeatherAlert used to build client-side by parsing the
    headline's own " — expected to arrive/clear in about N min" suffix,
    per the session's own "broadcast anchor" phrasing choice. Moved
    server-side for the same reason as _strip_spoken_labels: Piper needs
    the final text before it can render any audio at all."""
    lower = title.lower()
    if milestone == 0:
        return f"The {lower} is arriving now." if approaching else f"The {lower} is now clearing."
    if approaching:
        return f"A {lower} is expected to arrive in {milestone} minutes."
    return f"The {lower} is expected to clear in {milestone} minutes."


def _spoken_summary(alert: dict, type_label: str, is_update: bool) -> str:
    """The text kioskPlayWeatherAlert (app.py) speaks in full for a
    genuine new alert. Session discovery, live-testing against a real
    active alert: EC's own ATOM <summary> is NOT the real bulletin for a
    genuine alert — just an "Issued: {time}" stub — so this reaches for
    ec_alerts.fetch_full_description() instead, which pulls the real
    hazard/timing/impacts/safety text off EC's own human-readable report
    page. Falls back to the ATOM summary (or AQHI's own synthesized one)
    if that comes back empty — a real EC/AQHI hiccup, not the normal
    path, same fallback shape every other client in this app already
    uses for a fetch that can genuinely fail.

    Session follow-up: "can we feed weather alerts to chatgpt and tell
    it to turn it into a flowy paragraph that our TTS can read" — the
    raw bulletin is EC's own plain-text advisory format (section labels,
    bulleted-feeling line breaks), fine on a screen but choppy read
    aloud verbatim even after app.py's own kioskCleanSpokenSummary strips
    the labels themselves. Rewritten through groq_client.generate (low
    temperature — faithfulness matters far more than creative variety
    here) into one flowing, natural-sounding paragraph, explicitly

    Session follow-up: "shorten up the storm [briefing]... it repeats
    itself every time there's an update, which is fine... but I would
    like it to explain the conditions and what's going on and what to
    watch for... get rid of the parts where it's like blah blah blah to
    report this... for more information go here... get rid of the
    links and the written parts." Confirmed live against a real
    bulletin (a genuine severe thunderstorm warning): every EC bulletin
    ends with the same shape — generic, not-this-event boilerplate
    ("Severe thunderstorm warnings are issued when...", "...can produce
    tornadoes") followed by a "monitor alerts / report severe weather /
    for more information" footer carrying an email, a hashtag, and a
    URL, none of which mean anything spoken aloud. The prompt below now
    explicitly excludes both — a semantic instruction, not a fixed
    paragraph-count or regex cut, since EC's own bulletin length/
    structure varies by hazard type; this is intentionally judgment-
    based the same way the rest of this prompt already is.
    instructed not to add or invent anything beyond what EC actually
    wrote. groq_client.generate already returns None (never raises)
    during its own overnight pause, a tracked game window, or a genuine
    rate limit — this falls back to the raw (unrewritten but still
    complete and accurate) text in that case rather than losing the
    alert's content entirely; only a Groq/Gemini outage AND an empty
    fetch at the same time ever loses real content, not either alone.

    Only reached for a genuine EC alert (has its own "id" —
    ec_aqhi.aqhi_alert's own synthesized alert has none): that one's
    "summary" is already a short, plain one-liner with nothing
    structural to smooth over, so it's returned as-is.

    Session follow-up: moving the kiosk's voice from the browser's own
    speechSynthesis to server-rendered Piper audio (see kiosk_tts.py —
    "voices on Dell suck... it sounds different on my dell streamlit
    kiosk than on my macbook") meant this could no longer ever return ""
    the way it briefly could on a genuine EC/AQHI fetch failure: the
    audio has to be rendered from SOME text. A plain generic line
    covers that one rare case now, instead of leaving app.py's own JS
    to invent a fallback wrapper — everything about what gets spoken is
    decided here, once, server-side.

    `type_label`/`is_update` (required — this function has exactly one
    caller, get_new_alerts's own one-shot toast) build a deterministic
    lead-in sentence — session request: "it should always say this is
    a warning/watch/whatever... every time it's updated, say this
    warning has been updated... this is how it should always always
    always start." Computed once, up front, and prepended to every
    return path below (including both fallback branches) rather than
    duplicated per-branch, so "always always always" can't quietly stop
    being true from a future edit to just one of them. Built in code,
    not folded into either AI prompt below — see _friendly_headline's
    own comment on why an instruction isn't the same guarantee as code."""
    # a/an agreement — caught live: "This is a advisory" (the only one
    # of _type_label's four possible words that starts with a vowel
    # sound). A plain first-letter check is safe here specifically
    # because the input is always one of exactly those four known
    # words, not general English text.
    article = "an" if type_label[0].lower() in "aeiou" else "a"
    lead_in = f"This {type_label.lower()} has been updated." if is_update else f"This is {article} {type_label.lower()}."
    if "id" not in alert:
        body = alert.get("summary", "") or f"A new {alert['title'].lower()} is now active in your area."
        return f"{lead_in} {body}"
    # Real bug, caught live (a "SEVERE THUNDERSTORM ENDED" alert whose
    # report page had already gone empty): this used to fall back to
    # alert["summary"] here, but for a real EC alert (the "id" branch
    # above already ruled out AQHI) that's just the ATOM feed's own
    # "Issued: {time}" stub — not real content, just enough of a
    # non-empty string to defeat the `if not raw` guard right below and
    # get sent to the AI rewrite anyway, which then had nothing
    # substantive to work with and produced a refusal instead of a
    # rewrite (see _looks_like_refusal below for that same live
    # incident's other half). No fallback here now — an empty full
    # description IS the "nothing more specific available" case this
    # guard exists for.
    raw = ec_alerts.fetch_full_description()
    if not raw:
        return f"{lead_in} No further details are available yet."
    # account="primary"/reasoning_effort="low": see groq_client.
    # GROQ_MODEL's own comment on the real Aug 2026 llama-3.3-70b-
    # versatile decommission — this account now runs gpt-oss-120b too
    # (same model as pages_conflicts.py's "chatgpt" account), so it
    # needs its own explicit account. Real cost checked live against
    # this exact prompt: only 7 reasoning tokens, comfortably inside
    # the existing 400-token budget below — a plain rewrite task like
    # this one needs far less reasoning than a judgment call.
    # Session request: "make sure a toast actually fires if the AIs are
    # asleep... make sure it wakes them up." The toast and its Piper
    # voice were already unaffected by the pause (this module never
    # touches groq_client's own gated path except right here) — this
    # was the one real gap: a genuine severe-weather bulletin arriving
    # during the overnight pause or a live tracked game used to
    # silently skip this smoothing step and fall back to the plainer
    # raw EC text. allow_during_pause=True treats this call the same
    # way weather_alerts_bar's own storm-phase Govee lights already
    # treat the night gate — a real, narrowly-scoped safety exception,
    # not a blanket removal of the pause for anything else.
    rewritten = groq_client.generate(
        "Rewrite this Environment Canada weather alert bulletin as a single smooth, natural-sounding "
        "paragraph meant to be read aloud by a text-to-speech voice. Keep every real fact SPECIFIC TO "
        "THIS EVENT — current location, movement, timing, impacts, and any safety guidance for this "
        "event. Remove section labels like 'What:'/'When:'/'Additional information:'. Also drop "
        "anything that isn't specific to this event: generic definitions of what this warning type "
        "means in general (e.g. 'severe thunderstorm warnings are issued when...', 'severe "
        "thunderstorms can produce tornadoes'), and any closing instructions to keep monitoring "
        "alerts, report severe weather, or visit a website — including emails, phone numbers, "
        "hashtags, and URLs, none of which mean anything spoken aloud. Turn what's left into flowing "
        "spoken sentences. Don't add anything that isn't in the original text, and don't editorialize."
        "\n\n" + raw,
        temperature=0.3,
        max_output_tokens=400,
        account="primary",
        reasoning_effort="low",
        allow_during_pause=True,
    )
    if rewritten and _looks_like_refusal(rewritten):
        rewritten = None
    return f"{lead_in} {_strip_spoken_labels(rewritten or raw)}"


def render_alert_bar(alert: dict) -> None:
    """Bottom-strip toast for a brand-new weather alert — same plain,
    immediately-visible bar as news.render_alert_bar (see its own
    docstring for why the old stretch-then-slide intro was dropped
    entirely), colored by severity via .weather-alert-bar-* (theme.py),
    the same palette render()'s own .weather-statement-* modifiers use
    so the toast and the persistent banner never disagree about how
    urgent this looks."""
    bar_class = f"weather-alert-bar weather-alert-bar-{alert.get('severity', 'statement')}"
    label = html.escape(alert.get("label", "Weather Alert"))
    headline = html.escape(alert.get("headline", ""))
    # "summary" is now always the exact final sentence to speak — EC's
    # full (Groq-smoothed) bulletin for a brand-new alert, or the
    # milestone phrasing from _milestone_spoken_text — never raw/partial
    # text needing further client-side parsing (see both functions' own
    # docstrings). data-summary keeps it around as the speechSynthesis
    # fallback text; data-audio-b64 is the real Piper-rendered voice
    # (kiosk_tts.py), only absent if synthesis itself failed.
    spoken_text = alert.get("summary", "")
    summary = html.escape(spoken_text)
    audio_b64 = kiosk_tts.synthesize_base64(spoken_text) if spoken_text else None
    audio_attr = f' data-audio-b64="{audio_b64}"' if audio_b64 else ""
    # See _is_severe_hazard's own docstring — app.py's kioskPlayWeather
    # Alert reads this instead of hardcoding the never-fully-silent
    # volume curve for every weather alert regardless of actual hazard.
    # Defaults False (the quieter, normal curve) for any caller that
    # somehow predates this key — safer to under-escalate an unknown
    # case than blast at night by default.
    severe_attr = "true" if alert.get("severe", False) else "false"
    # Session request (lightning_client's own toast): "make it so it
    # doesn't speak... not audible." Every weather-kind toast up to now
    # has always made SOME sound (app.py's kioskCheckToastChime always
    # calls kioskPlayWeatherAlert for one matching this bar's own CSS
    # class, which plays a chime bell regardless of whether there's a
    # spoken summary at all) — there was no existing "silent toast"
    # path to reuse. Opt-in and defaults False so every real EC alert
    # keeps its exact existing chime+voice behavior; only a caller that
    # explicitly asks for quiet (lightning, at least for now) skips it,
    # while still getting the same visible slide-in toast.
    silent_attr = ' data-silent="true"' if alert.get("silent", False) else ""
    # Session follow-up: "make it so that the clearing [time] number
    # sits where the leave in section is in the jumbotron" — a real
    # live-ticking countdown (same .live-countdown/data-target-ms
    # mechanism as commute_reminder.render_ticker_leave_bar's own
    # "Leave in"), pushed to the right of this bar via
    # .weather-alert-countdown (theme.py) rather than buried as plain
    # trailing text at the end of `headline`. Only present when
    # get_new_alerts actually resolved a storm phase/target — the
    # get_storm_proximity_alerts milestone toasts below don't carry
    # these keys at all, same "absent, not empty" convention as
    # "summary" above.
    #
    # Session report: "it's still going twice... there's also a div
    # error on it" — a literal, visible "</div>" text fragment showing
    # up on screen. This span used to be conditionally OMITTED entirely
    # (an empty string) when there's no countdown, meaning this bar's
    # own real child-element COUNT varied — 3 children for a get_new_
    # alerts toast (with the badge), only 2 for a get_storm_proximity_
    # alerts milestone toast (without it) — while both toast KINDS
    # render through this exact same call, landing at the exact same
    # script position/DOM slot across reruns (toast_queue.py's own
    # dispatch, app.py). Streamlit's own patching for a repeated
    # st.markdown(unsafe_allow_html=True) at one script position isn't
    # a plain full-string replace — confirmed live, going from a
    # countdown-bearing render to a non-countdown one left a stray
    # trailing "</div>" as real, visible text. Always rendering the
    # span now (empty content, hidden via CSS when there's nothing to
    # show) keeps the real structure — 3 children, always — identical
    # across every render regardless of countdown presence, which is
    # the actual fix: nothing here EVER changes shape between renders
    # anymore for Streamlit's own diffing to trip over.
    countdown_target_ms = alert.get("countdown_target_ms")
    countdown_verb = alert.get("countdown_verb")
    if countdown_target_ms and countdown_verb:
        countdown_html = (
            f'<span class="weather-alert-countdown live-countdown" data-target-ms="{countdown_target_ms}" '
            f'data-format="clock" data-template="{countdown_verb} in {{}}">{countdown_verb} soon</span>'
        )
    else:
        countdown_html = '<span class="weather-alert-countdown weather-alert-countdown-empty"></span>'
    st.markdown(
        f"""<div class="{bar_class}" data-summary="{summary}"{audio_attr} data-severe="{severe_attr}"{silent_attr}>
            <span class="news-breaking-label">{label}</span>
            <span class="news-alert-headline">{headline}</span>
            {countdown_html}
        </div>""",
        unsafe_allow_html=True,
    )


def _current_alert_and_severity() -> tuple[dict, str] | None:
    alerts = _combined_alerts()
    if not alerts:
        return None
    alert = max(alerts, key=_selection_score)
    return alert, _severity(alert["title"])


def current_storm_phase(now: datetime) -> dict | None:
    """{"phase": "approaching"|"here"|"leaving", "minutes": float,
    "target": datetime} for whichever alert is currently "the" one (see
    _current_alert_and_severity), or None — for govee_lighting.
    sync_lights (session request: "red govee flashes for when the storm
    is approaching... solid red at like 30% for when its here... same
    thing for when the storm is leaving") and storm_headline_candidate
    below. Thin wrapper around ec_storm_timing.storm_phase using the
    exact same alert selection get_new_alerts/weather_statement_
    candidate already use, so the light, the toast, the banner, and the
    headline never disagree about which alert is "the" current one."""
    resolved = _current_alert_and_severity()
    if resolved is None:
        return None
    alert, severity = resolved
    return ec_storm_timing.storm_phase(now, alert["title"], severity)


# Milestone-based, not a flat interval — session request: "make sure
# theres toast alerts from up to 2 hours and counting down for when a
# storm is approaching and when it is leaving." Mirrors commute_
# reminder.MILESTONES_MINUTES exactly (same widest-to-narrowest shape,
# same "up to 2 hours" outer bound), reusing the model the user's own
# storm-headline requests have already been referencing throughout this
# feature. One shared list for both phases, not two: "leaving" never
# has more than LEAVING_TAIL_MINUTES (30) left by construction, so the
# 120/90/60/45 milestones simply never fire for it — nothing extra to
# special-case.
#
# Session report: "the toast alerts for the storm are being double
# pushed... back to back... echo effect." This used to be plain
# in-memory state, deliberately not persisted, on the assumption a
# restart resetting a repeating reminder's progress was rare and
# low-stakes ("acceptable... resets a repeating reminder's progress
# once"). That assumption didn't hold up: this app now gets restarted
# routinely (dev iterations, and watchdog_kiosk.sh can restart it
# automatically too — see project_kiosk_watchdog), and a real storm's
# own "leaving" phase can span many hours of reissues — any restart
# during that window forgot every milestone already shown, so the very
# next server rerun could re-fire whatever milestone was already due,
# sounding exactly like an echo (same headline, same voice line, played
# again). Persisted the same way get_new_alerts's own _seen_alert_keys
# already is — per-instance (a second kiosk/dev box sharing this same
# Upstash store should track its OWN progress, not silently inherit
# another instance's), with the same MAX_SEEN_ALERTS-style pruning so
# this doesn't grow unbounded across many storms over time.
MAX_SEEN_STORM_ALERTS = 50
STORM_MILESTONES_MINUTES = [120, 90, 60, 45, 30, 20, 15, 10, 5, 3, 0]
_storm_milestones_shown: dict[str, set[int]] = {
    k: set(v) for k, v in persisted_state.load_per_instance("weather_storm_milestones_shown", {}).items()
}


def _save_storm_milestones_shown() -> None:
    persisted_state.save_per_instance(
        "weather_storm_milestones_shown", {k: sorted(v) for k, v in _storm_milestones_shown.items()}
    )


def _due_storm_milestone(minutes_remaining: float, shown: set[int]) -> int | None:
    """The largest not-yet-shown milestone reached — same skip-ahead
    logic as commute_reminder._due_milestone: waking up from a gap
    (e.g. the dashboard was on a different rotation page's data fetch
    for a few minutes) fires only the milestone actually due now, and
    marks any larger ones already blown past as shown too, rather than
    bursting out every milestone missed in between."""
    candidates = [m for m in STORM_MILESTONES_MINUTES if minutes_remaining <= m]
    if not candidates:
        return None
    due = min(candidates)
    if due in shown:
        return None
    for m in STORM_MILESTONES_MINUTES:
        if m > due:
            shown.add(m)
    return due


def _format_clock(remaining_seconds: float) -> str:
    """H:MM:SS (or MM:SS under an hour) — first-frame value only; the
    element's own data-target-ms/data-format drive the real per-second
    tick from there via app.py's global live-countdown ticker. Same
    shape as commute_reminder._format_clock, duplicated rather than
    imported — this app's own established convention for a small,
    module-specific first-frame formatter (see also pages_jumbotron.
    _fmt_countdown's own copy)."""
    total = max(0, int(remaining_seconds))
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


# Session request: "make it so all the red headlines within the last 2
# hours cycle at the top of the screen with a cool animation when it
# swaps" — normalizes this same storm-phase info (and, separately, the
# persistent weather-statement banner's own text/severity below) into
# headline_rotation.py's shared 4-tier scale (see theme.py's own
# .headline-rotation rules), rather than leaking storm/weather-
# statement-specific class names into a component meant to look
# consistent regardless of which source is currently showing.
_SEVERITY_TO_ROTATION_CLASS = {
    "extreme": "rotation-critical",
    "warning": "rotation-warning",
    "warning-moderate": "rotation-warning",
    "watch": "rotation-notice",
    "statement": "rotation-notice",
}


def storm_headline_candidate(now: datetime) -> dict | None:
    """A bright countdown to whatever ec_storm_timing.storm_phase's own
    "target" currently is — session request: "can we make an
    APPROACHING: and CLEARING: timer using these values pulled from the
    EC alert for ultimate transparency." "CLEARING IN" is the user's own
    phrase, used for both "here" and "leaving" — session correction:
    "it should say clearing in and then a timer to [event_end_datetime]
    since thats when the message actually clears," not only once that
    instant has already passed. "APPROACHING" only ever shows for
    "approaching". Either way the target is always something real and
    current, never stale or made up — "here"'s own target IS event_end_
    datetime itself, not a value re-derived from "minutes" (which would
    drift out of sync with it)."""
    resolved = _current_alert_and_severity()
    if resolved is None:
        return None
    alert, severity = resolved
    info = ec_storm_timing.storm_phase(now, alert["title"], severity)
    if info is None:
        return None
    target_ms = int(info["target"].timestamp() * 1000)
    label = "APPROACHING" if info["phase"] == "approaching" else "CLEARING IN"
    tier = "extreme" if severity == "extreme" else "warning"
    remaining = max(0.0, info["minutes"] * 60)
    return {
        "text": f"{label}: {_format_clock(remaining)}",
        "css_class": _SEVERITY_TO_ROTATION_CLASS[tier],
        "target_ms": target_ms,
        "template": label + ": {}",
        "zero_text": None,
    }


def weather_statement_candidate(weather: dict | None) -> dict | None:
    """Whatever the persistent weather-statement banner would show — a
    real EC alert (any severity, most-severe-first via _selection_score
    when several are active) or, if none, our own manual heat/cold
    fallback (_fallback_text) — normalized for headline_rotation.py's
    unified rotation. None when there's genuinely nothing to show. Not
    a countdown (no natural "clears at" instant for a plain statement/
    fallback the way storm proximity has), so target_ms is always
    None."""
    alerts = _combined_alerts()
    if alerts:
        alert = max(alerts, key=_selection_score)
        text = _friendly_headline(alert["title"])
        if len(alerts) > 1:
            text += f" (+{len(alerts) - 1} more alert{'s' if len(alerts) > 2 else ''})"
        rotation_class = _SEVERITY_TO_ROTATION_CLASS[_severity(alert["title"])]
    else:
        text = _fallback_text(weather)
        if not text:
            return None
        rotation_class = "rotation-notice"
    return {"text": text, "css_class": rotation_class, "target_ms": None, "template": "{}", "zero_text": None}


def get_storm_proximity_alerts(now: datetime) -> list[dict]:
    """Milestone toasts while a storm-grade alert is approaching or
    leaving — session request, in two parts: first "toast alerts for
    when the storm gets closer every like 5-10 mins... same thing for
    when the storm is leaving," then refined to "make sure theres toast
    alerts from up to 2 hours and counting down for when a storm is
    approaching and when it is leaving." Fires at STORM_MILESTONES_
    MINUTES checkpoints as the remaining time counts down, not a flat
    interval — see _due_storm_milestone. Distinct from get_new_alerts's
    own one-shot "a new alert just came in" toast: this repeats across
    the whole approaching/leaving window, giving a running sense of how
    close it is. Nothing fires during "here" — the steady red light
    (govee_lighting.sync_lights) is the ambient signal for that; a
    milestone toast for something already overhead would just be
    noise, not news (the CLEARING IN countdown headline already covers
    "here" on its own, passively, without an interruption)."""
    resolved = _current_alert_and_severity()
    if resolved is None:
        return []
    alert, severity = resolved
    phase_info = ec_storm_timing.storm_phase(now, alert["title"], severity)
    if phase_info is None or phase_info["phase"] not in ("approaching", "leaving"):
        return []
    key = alert.get("id") or alert["title"]
    shown = _storm_milestones_shown.setdefault(key, set())
    milestone = _due_storm_milestone(phase_info["minutes"], shown)
    if milestone is None:
        return []
    now_ts = now.timestamp()
    if _weather_toast_on_cooldown(key, now_ts):
        # The one-shot "new alert" toast for this exact alert already
        # fired within WEATHER_TOAST_COOLDOWN_SECONDS — defer, don't
        # mark this milestone shown, so it's genuinely re-evaluated (not
        # lost) on a later rerun once the cooldown clears — either this
        # same milestone fires then, or a smaller one does if enough
        # real time has passed by then, same skip-ahead logic
        # _due_storm_milestone already uses elsewhere.
        return []
    shown.add(milestone)
    if len(_storm_milestones_shown) > MAX_SEEN_STORM_ALERTS:
        _storm_milestones_shown.pop(next(iter(_storm_milestones_shown)))
    _save_storm_milestones_shown()
    _mark_weather_toast_fired(key, now_ts)
    approaching = phase_info["phase"] == "approaching"
    if milestone == 0:
        headline = f"{alert['title']} — {'arriving' if approaching else 'clearing'} now"
    else:
        verb = "expected to arrive in about" if approaching else "expected to clear in about"
        headline = f"{alert['title']} — {verb} {milestone} min"
    return [
        {
            "kind": "weather",
            "severity": severity,
            "label": "Environment Canada",
            "headline": headline,
            "summary": _milestone_spoken_text(alert["title"], approaching, milestone),
            # Always True here — storm_phase (above) only ever returns
            # non-None for a hazard already in STORM_HAZARD_TERMS, the
            # same set _is_severe_hazard checks, so a milestone toast is
            # never anything BUT a genuine severe hazard. Set explicitly
            # rather than relying on render_alert_bar's own default, so
            # this doesn't silently start reading False if that default
            # ever changes.
            "severe": True,
        }
    ]
