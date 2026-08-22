"""UFC event + fight-card data for the jumbotron's UFC coverage —
session request: "add UFC to the jumbotron." Genuinely different shape
from the MLB/NHL/NFL modules this app already has (see sports_client.py):
those track one team's single game with an evolving numeric score; a
UFC event is a date with a multi-bout fight card, each bout a discrete
win/loss/method result, no live score to poll for. Kept as its own
module rather than squeezed into sports_client.py's existing per-team
shape, since almost nothing about "team_id, opponent, score" transfers.

Pulls from ESPN's own MMA scoreboard endpoint (site.api.espn.com, same
general API family sports_client.py already uses for the Saints) —
confirmed live: passing a specific `dates=YYYYMMDD` returns whatever
UFC event (if any) is scheduled that calendar day, with every bout on
the card in `competitions`, ordered earliest-prelim first, main event
last (confirmed live: the last competition's fighters always match the
event's own title, e.g. "UFC Fight Night: Medić vs. Rodriguez" -> the
last bout is Rodriguez vs. Medić).

Deliberately does NOT try to report a bout's finishing method (KO/
submission/decision) — ESPN's scoreboard response carries a raw play-
by-play event log (Round Start, Takedown, Submission Attempt...) but
no clean method field, and guessing a method from that log risks
reporting something false (an early, failed submission attempt looks
identical in the log to whatever actually finished the fight). Winner,
round, and time are all confirmed reliable fields; method isn't, so
it's left out rather than risk inventing it.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st

import data_health
import fetch_throttle
import sports_client
from config import TIMEZONE

UFC_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
# Matches sports_client.py's own GAME_CACHE_TTL_SECONDS — frequent
# enough to catch a live bout ending and the next one starting.
CACHE_TTL_SECONDS = 5 * 60

_last_good_event: dict | None = None
_last_good_event_date: str | None = None  # which calendar date _last_good_event actually answers for

_STATE_MAP = {"pre": "upcoming", "in": "live", "post": "final"}


def _to_local(iso_utc: str) -> datetime:
    return datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(ZoneInfo(TIMEZONE)).replace(tzinfo=None)


def _normalize_bout(comp: dict, order: int, is_main_event: bool) -> dict:
    competitors = comp["competitors"]
    a, b = competitors[0], competitors[1]

    def fighter(c: dict) -> dict:
        athlete = c["athlete"]
        record = next((r["summary"] for r in c.get("records", []) if r.get("name") == "overall"), None)
        return {
            # This id is what the core-API live-stats path below AND
            # fetch_fighter_profile's own athlete lookup both key on —
            # confirmed live against a real card that ESPN's MMA
            # scoreboard uses the same id for "this competitor slot" and
            # "this athlete" (no separate nested athlete.id field exists
            # at all in the real payload, unlike some other ESPN sports).
            "id": c["id"],
            "name": athlete["displayName"],
            "short_name": athlete.get("shortName") or athlete["displayName"],
            "record": record,
            "winner": bool(c.get("winner")),
            # Free from this same scoreboard payload — no extra fetch
            # needed (session request: "make it feel more professional"
            # — real broadcasts always show fighter nationality).
            "flag": ((athlete.get("flag") or {}).get("href")),
        }

    status = comp["status"]
    return {
        "bout_id": comp["id"],
        "order": order,
        "is_main_event": is_main_event,
        "weight_class": (comp.get("type") or {}).get("abbreviation") or "",
        "fighter_a": fighter(a),
        "fighter_b": fighter(b),
        "state": _STATE_MAP.get(status["type"]["state"], "upcoming"),
        "round": int(status.get("period") or 0),
        "clock": status.get("displayClock") or "",
    }


def _normalize_event(e: dict) -> dict:
    bouts_raw = e.get("competitions") or []
    last_idx = len(bouts_raw) - 1
    bouts = [_normalize_bout(c, i, i == last_idx) for i, c in enumerate(bouts_raw)]
    return {
        "event_id": e["id"],
        "name": e["name"],
        "start_time": _to_local(e["date"]),
        "state": _STATE_MAP.get(((e.get("status") or {}).get("type") or {}).get("state"), "upcoming"),
        "bouts": bouts,
    }


# Session request: "I want the live fight to take up like the whole
# screen... you have both fighters and live fight stats." ESPN's plain
# scoreboard payload above (competitors[].statistics) is confirmed live
# to always come back an empty list for MMA — the real per-fighter
# numbers live on ESPN's separate "core" API instead (a different host
# entirely, not used anywhere else in this app yet). Also confirmed
# live: pickcenterAvailable is false on every single bout of a real
# card — ESPN simply doesn't run a moneyline/odds product for MMA the
# way it does for the team sports, so there's no real "implied win
# odds" number to show here at all; inventing one would break this
# app's own "never show a stat that isn't real" rule. These live
# strike/takedown/control-time numbers are the honest substitute — for
# a fight, real-time volume and control genuinely are what a viewer (or
# a judge) reads the fight by, unlike a score-derived model.
UFC_CORE_API_BASE = "https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc"
# Matches sports_client.py's own LIVE_DETAIL_CACHE_TTL_SECONDS — the
# same 5s cadence as the app's own rerun timer, since these numbers
# genuinely change mid-round, unlike the scoreboard fetch above.
LIVE_STATS_CACHE_TTL_SECONDS = 5

# The handful of splits a real broadcast's own "tale of the tape"
# leans on — ESPN's core API actually returns 35+ granular categories
# per fighter (strike location/target breakdowns, advances, reversals,
# slam rate...), most of it too in-the-weeds to read from across a
# room. displayValue is already a clean pre-formatted string (same
# preference for ESPN's own formatting scores_client.team_record/
# game_leader already have), used verbatim rather than re-deriving it
# from the raw numeric value.
_STAT_FIELDS = {
    "sig_strikes_landed": "SSL",
    "sig_strikes_attempted": "SSA",
    "takedowns_landed": "TDL",
    "takedowns_attempted": "TDA",
    "knockdowns": "KD",
    "control_time": "TIC",
}


@st.cache_data(ttl=LIVE_STATS_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_fighter_stats_raw(event_id: str, bout_id: str, fighter_id: str) -> dict:
    fetch_throttle.wait_turn()
    url = f"{UFC_CORE_API_BASE}/events/{event_id}/competitions/{bout_id}/competitors/{fighter_id}/statistics"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _fighter_stat_line(event_id: str, bout_id: str, fighter_id: str) -> dict | None:
    try:
        raw = _fetch_fighter_stats_raw(event_id, bout_id, fighter_id)
    except Exception:
        return None
    # .strip(): a few of ESPN's own abbreviations carry a stray trailing
    # tab character in the raw payload (confirmed live, e.g. "SCBL\t") —
    # harmless for the fields actually used here, but cheap enough to
    # guard against regardless of which fields get pulled in later.
    values = {
        s["abbreviation"].strip(): s.get("displayValue")
        for cat in (raw.get("splits") or {}).get("categories", [])
        for s in cat.get("stats", [])
    }
    return {key: values.get(abbrev) for key, abbrev in _STAT_FIELDS.items()}


# Session request: "add player photos... make it feel more
# professional... right now it just has the name." ESPN's site-API
# athlete endpoint (a different one from UFC_CORE_API_BASE above, which
# only carries live per-bout stats) has everything a real "tale of the
# tape" broadcast graphic needs in one call: headshot, nickname,
# height/reach/age, stance, and a career win-method breakdown — checked
# live, all present for a real fighter (Anthony Hernandez, 2026-08-22
# card). Bio data, not live stats — a fighter's height/reach/nickname/
# career record never change mid-card, so this gets its own much
# longer cache than LIVE_STATS_CACHE_TTL_SECONDS above.
UFC_ATHLETE_PROFILE_URL = "https://site.api.espn.com/apis/common/v3/sports/mma/ufc/athletes/{athlete_id}"
PROFILE_CACHE_TTL_SECONDS = 6 * 60 * 60


@st.cache_data(ttl=PROFILE_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_fighter_profile_raw(athlete_id: str) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(UFC_ATHLETE_PROFILE_URL.format(athlete_id=athlete_id), timeout=10)
    resp.raise_for_status()
    return resp.json().get("athlete") or {}


def fetch_fighter_profile(athlete_id: str) -> dict | None:
    """{"headshot", "nickname", "height", "reach", "age", "stance",
    "wins_ko", "wins_sub", "wins_dec"} for this fighter, or None on any
    fetch failure. The win-method breakdown is derived from ESPN's own
    statsSummary (a real (T)KO-(T)KOL and SUB-SUBL split, e.g. "3-2"/
    "9-1" — checked live) rather than guessed: wins_dec is whatever's
    left of the fighter's own total win count after subtracting the two
    real categories, since ESPN doesn't publish a separate decision-wins
    stat directly but ITS OWN win total (from the same summary) makes
    the remainder an honest, derived-not-invented number rather than a
    guess."""
    try:
        raw = _fetch_fighter_profile_raw(athlete_id)
    except Exception:
        return None
    if not raw:
        return None

    stats = {s.get("abbreviation"): s for s in (raw.get("statsSummary") or {}).get("statistics", [])}

    def wins_from(stat: dict | None) -> int:
        if not stat or not stat.get("displayValue"):
            return 0
        try:
            return int(stat["displayValue"].split("-")[0])
        except (ValueError, IndexError):
            return 0

    total_wins = wins_from(stats.get("W-L-D"))
    wins_ko = wins_from(stats.get("(T)KO"))
    wins_sub = wins_from(stats.get("SUB"))
    wins_dec = max(0, total_wins - wins_ko - wins_sub)

    headshot = (raw.get("headshot") or {}).get("href")
    return {
        "headshot": headshot,
        "nickname": raw.get("nickname"),
        "height": raw.get("displayHeight"),
        "reach": raw.get("displayReach"),
        "age": raw.get("age"),
        "stance": (raw.get("stance") or {}).get("text"),
        "wins_ko": wins_ko,
        "wins_sub": wins_sub,
        "wins_dec": wins_dec,
    }


def fetch_bout_stats(event_id: str, bout_id: str, fighter_a_id: str, fighter_b_id: str) -> dict | None:
    """{"fighter_a": {...}, "fighter_b": {...}}, each a dict of
    _STAT_FIELDS' keys -> ESPN's own pre-formatted display string (e.g.
    control_time is already "1:24", not raw seconds). None only if
    either fetch genuinely failed — a bout that hasn't started yet still
    returns a real dict of zeros (an honest "nothing's happened," not
    missing data), so this isn't gated on bout state; callers decide
    whether zeros are worth showing (see pages_jumbotron._ufc_board_html
    — pregame countdown skips this entirely, nothing to show yet).

    Session report: "can we incorporate the same delay mode as we have
    with the ESPN API... it's low key spoiling some of the data before
    I even know what's going on." Wrapped through sports_client.
    delayed() — the same broadcast-delay buffer sports_alerts.py's own
    MLB/NHL/NFL scoring-play toasts already use, for the same reason
    theirs do (session precedent: "just got an alert way before the
    actual play happened"). Applied once, here at the shared source,
    rather than at each caller separately: the jumbotron's own stat
    bars, the recent-action ticker (recent_event, below — its delta
    comparison naturally stays correct either way, since both sides of
    the comparison are equally delayed), and the knockdown toast
    (get_new_alerts, below) all read through this one function, so
    delaying it here means all three move in lockstep at the same
    trailing pace instead of the numbers updating live while only the
    ticker/toast explaining them lagged behind."""
    a = _fighter_stat_line(event_id, bout_id, fighter_a_id)
    b = _fighter_stat_line(event_id, bout_id, fighter_b_id)
    result = {"fighter_a": a, "fighter_b": b} if a is not None and b is not None else None
    return sports_client.delayed(f"ufc_stats_{bout_id}", result)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_raw(date_str: str) -> dict | None:
    fetch_throttle.wait_turn()
    resp = requests.get(UFC_SCOREBOARD_URL, params={"dates": date_str}, timeout=10)
    resp.raise_for_status()
    events = resp.json().get("events") or []
    return events[0] if events else None


def fetch_event_for_date(day: date) -> dict | None:
    """The UFC event scheduled on `day` (local calendar date), normalized
    — {"event_id", "name", "start_time", "state": "upcoming"|"live"|
    "final", "bouts": [...]}, or None if nothing's scheduled that day.
    `bouts` is ordered earliest-prelim first, main event last (see this
    module's own docstring on why that ordering is trustworthy).

    Last-good fallback keyed to the SAME requested date, unlike sports_
    client.py's own per-team fallbacks — a transient fetch failure
    returns the last real answer only if it was actually for this same
    date; a stale answer for a different day would be actively wrong
    here (unlike a team's single ongoing game, where "yesterday's last
    known state" is still a reasonable stand-in)."""
    global _last_good_event, _last_good_event_date
    date_str = day.strftime("%Y%m%d")
    try:
        raw = _fetch_raw(date_str)
    except Exception:
        return _last_good_event if _last_good_event_date == date_str else None
    data_health.record_success("sports_schedule")
    if raw is None:
        _last_good_event, _last_good_event_date = None, date_str
        return None
    event = _normalize_event(raw)
    _last_good_event, _last_good_event_date = event, date_str
    return event


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_calendar_raw() -> list[dict]:
    """Every UFC event ESPN currently has scheduled this season (~40+
    entries confirmed live), name + date only — no bout-level detail,
    just enough for "what's the next one." The plain scoreboard
    endpoint (no `dates` param) returns this full-season list under
    leagues[0].calendar alongside its own single nearest-event answer;
    reusing that same call here instead of a separate endpoint."""
    fetch_throttle.wait_turn()
    resp = requests.get(UFC_SCOREBOARD_URL, params={"f": "json"}, timeout=10)
    resp.raise_for_status()
    leagues = resp.json().get("leagues") or []
    return leagues[0].get("calendar", []) if leagues else []


_last_good_calendar: list[dict] | None = None


def fetch_next_event(now: datetime) -> dict | None:
    """{"name", "start_time"} for the next UFC event scheduled on or
    after `now` (any day — this is for the "My Teams" rail card's own
    off-day fallback, see pages_jumbotron._ufc_rail_hero_html, not the
    Saturday-5pm takeover window, which is deliberately narrower), or
    None if ESPN doesn't have anything scheduled that far out yet.
    Deliberately no bout-level detail here — the calendar entries don't
    carry it, and this is only ever used for a compact "next event in
    N days" line, not a full card."""
    global _last_good_calendar
    try:
        calendar = _fetch_calendar_raw()
    except Exception:
        calendar = _last_good_calendar
    else:
        _last_good_calendar = calendar
        data_health.record_success("sports_schedule")
    if not calendar:
        return None
    # Naive-local, matching this app's own `now` convention (see
    # takeover_state's own comment) — _to_local already produces a
    # naive-local value for each entry's startDate, so normalizing
    # `now` the same way (not the other way around) keeps both sides
    # directly comparable with no extra tzinfo round-trip.
    if now.tzinfo is not None:
        now = now.astimezone(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
    upcoming = sorted(
        (entry for entry in calendar if _to_local(entry["startDate"]) >= now),
        key=lambda entry: entry["startDate"],
    )
    if not upcoming:
        return None
    return {"name": upcoming[0]["label"], "start_time": _to_local(upcoming[0]["startDate"])}


def current_bout(event: dict) -> dict | None:
    """Which bout to actually show right now — session request: "auto
    rotation between fights," i.e. the displayed bout should track the
    event's own progress automatically rather than sit fixed on one.
    The bout currently "live" if there is one; otherwise the most
    recently completed one (so a just-finished result stays up until
    the next bout's own data shows it's live); otherwise the very
    first bout on the card (nothing's happened yet). None only if the
    card is genuinely empty."""
    bouts = event.get("bouts") or []
    if not bouts:
        return None
    live = next((b for b in bouts if b["state"] == "live"), None)
    if live:
        return live
    completed = [b for b in bouts if b["state"] == "final"]
    if completed:
        return completed[-1]
    return bouts[0]


# Coverage window — session request: "auto rotation between fights
# coverage starts at 5pm every saturday, only will not be shown on
# main if habs are playing. otherwise let it run." A fixed clock-time
# rule, not sports_alerts.py's own TAKEOVER_LEAD_MINUTES-before-first-
# bout window: a UFC card doesn't have one clean "start_time" the way
# a single game does (it spans hours, early prelims through main
# event), and 5pm is well before even the earliest prelims typically
# start — real advance notice the same way the other sports' pregame
# window gives. Deliberately does NOT hold a postgame recap the way
# sports_alerts.takeover_state does (TAKEOVER_POSTGAME_MINUTES) — the
# session request only asked for "upcoming event countdown" and "live
# fight card, bout-by-bout," not a recap, so coverage simply ends once
# the card's own state reaches "final".
COVERAGE_START_HOUR = 17  # 5pm


def takeover_state(now: datetime) -> dict | None:
    """{"phase": "countdown"|"live", "event": ...} while UFC coverage
    should own the jumbotron, else None. Callers (app.py) are
    responsible for the one exception the same session request named —
    "will not be shown on main if habs are playing" — this function
    only knows about UFC's own schedule, not the Habs'."""
    if now.weekday() != 5 or now.hour < COVERAGE_START_HOUR:
        return None
    event = fetch_event_for_date(now.date())
    if event is None or event["state"] == "final":
        return None
    phase = "live" if event["state"] == "live" else "countdown"
    return {"phase": phase, "event": event}


# --- Toast alerts + recent-action ticker (stat-delta based) -------------
# Session follow-up: "how else can we improve the viewing experience...
# I genuinely want to enjoy watching this... but I don't know how."
# Two asks: a toast for big moments, and a compact "recent action" line.
# Both come from fetch_bout_stats' own per-fighter numbers, not ESPN's
# raw play-by-play log (comp["details"]/the core-API "plays" endpoint) —
# checked live against a full finished bout: every single entry there
# (Takedown, Takedown Attempt, Round Start/End, Walkout...) carries only
# a bare type/period/clock, genuinely no fighter attribution anywhere,
# for the entire fight. Reporting "TAKEDOWN" with no name would be
# honest but nearly useless; the per-fighter stats this module already
# polls for the stat bars ARE attributed, so both features are built by
# comparing this poll's numbers against the last poll's, per fighter,
# instead — real, attributed data, not a compromise version of the
# ticker idea.
_last_seen_stats: dict[str, dict] = {}
_last_seen_kd: dict[str, dict] = {}
# A real, sustained control sequence, not just the clock ticking one
# second — see recent_event's own docstring.
CONTROL_TIME_DELTA_SECONDS = 8


def parse_control_time_seconds(text: str | None) -> int:
    """"1:24" -> 84 — used both to size pages_jumbotron.py's own stat
    comparison bar and (below) to detect a real control-time delta, so
    it lives here rather than duplicated in both modules. 0 for None/
    empty/anything unparseable, same as a bout that hasn't had any
    control time yet."""
    if not text:
        return 0
    try:
        minutes, seconds = text.split(":")
        return int(minutes) * 60 + int(seconds)
    except (ValueError, AttributeError):
        return 0


# Ranked most-notable first — a poll can see several deltas land at
# once (a burst of strikes plus a takedown between two 5s polls isn't
# rare), and only the single most notable one is worth a ticker line;
# showing all of them at once would read as noise, not a broadcast cue.
_EVENT_PRIORITY = ["knockdowns", "takedowns_landed", "sig_strikes_landed", "control_time"]
_EVENT_LABEL = {
    "knockdowns": "KNOCKDOWN",
    "takedowns_landed": "TAKEDOWN",
    "sig_strikes_landed": "SIG. STRIKE",
    "control_time": "TAKES CONTROL",
}


def recent_event(bout_id: str, fighter_a: dict, fighter_b: dict, stats: dict | None) -> dict | None:
    """{"text", "accent"} for the single most notable stat change since
    the last time this was called for this bout, or None if nothing
    changed (the common case — most 5s polls see no real delta) or
    `stats` itself is None. Compares real per-fighter numbers to the
    last-seen snapshot rather than reading anything off ESPN's own
    unattributed play-by-play log — see this section's own top comment
    for why. control_time is compared in whole seconds (its own
    "1:24"-style display string isn't directly comparable) via
    parse_control_time_seconds, and only flagged once it grows by a
    real amount (CONTROL_TIME_DELTA_SECONDS) rather than every single
    second it ticks up, which would otherwise dominate every poll
    during any real grappling exchange."""
    if not stats:
        return None
    prev = _last_seen_stats.get(bout_id)
    _last_seen_stats[bout_id] = stats
    if prev is None:
        return None

    def val(fighter_stats: dict, key: str) -> float:
        raw = fighter_stats.get(key)
        if key == "control_time":
            return parse_control_time_seconds(raw)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0

    for key in _EVENT_PRIORITY:
        for side, fighter, tone in (("fighter_a", fighter_a, "a"), ("fighter_b", fighter_b, "b")):
            delta = val(stats[side], key) - val(prev[side], key)
            if key == "control_time" and delta < CONTROL_TIME_DELTA_SECONDS:
                continue
            if key != "control_time" and delta < 1:
                continue
            return {"text": f"{fighter['short_name']} {_EVENT_LABEL[key]}", "accent": tone}
    return None


def get_new_alerts(now: datetime) -> list[dict]:
    """A toast for a genuine knockdown — {"kind": "sports", "sport":
    "ufc", ...}, the exact shape sports_alerts.render_alert_bar already
    renders (reused directly rather than building a parallel toast
    path — see theme.py's own .sports-alert-bar-ufc for the one new
    thing that shape needed). [] outside the Saturday-5pm+ coverage
    window (same gate takeover_state uses) or when nothing's changed.
    Knockdowns specifically, not every stat delta recent_event also
    tracks — a knockdown is the one moment genuinely worth a toast on
    its own; the rest is what the jumbotron's own ticker line is for."""
    if now.weekday() != 5 or now.hour < COVERAGE_START_HOUR:
        return []
    event = fetch_event_for_date(now.date())
    if event is None or event["state"] != "live":
        return []
    bout = current_bout(event)
    if not bout or bout["state"] != "live":
        return []
    try:
        stats = fetch_bout_stats(event["event_id"], bout["bout_id"], bout["fighter_a"]["id"], bout["fighter_b"]["id"])
    except Exception:
        return []
    if not stats:
        return []

    prev_kd = _last_seen_kd.get(bout["bout_id"])
    current_kd = {
        "fighter_a": int(float(stats["fighter_a"].get("knockdowns") or 0)),
        "fighter_b": int(float(stats["fighter_b"].get("knockdowns") or 0)),
    }
    _last_seen_kd[bout["bout_id"]] = current_kd
    if prev_kd is None:
        return []

    alerts = []
    for side, fighter, opponent in (
        ("fighter_a", bout["fighter_a"], bout["fighter_b"]),
        ("fighter_b", bout["fighter_b"], bout["fighter_a"]),
    ):
        if current_kd[side] > prev_kd.get(side, 0):
            try:
                profile = fetch_fighter_profile(fighter["id"])
            except Exception:
                profile = None
            try:
                opp_profile = fetch_fighter_profile(opponent["id"])
            except Exception:
                opp_profile = None
            alerts.append(
                {
                    "kind": "sports",
                    "type": "score",
                    "sport": "ufc",
                    "team_label": "UFC",
                    "team_logo": (profile or {}).get("headshot") or "",
                    "opponent_logo": (opp_profile or {}).get("headshot") or "",
                    "team_score": None,
                    "opp_score": None,
                    "description": f"KNOCKDOWN! {fighter['name']} rocks {opponent['name']}",
                    "flash_color": (255, 59, 48),
                    "spoken": f"Knockdown! {fighter['name']} rocks {opponent['name']}",
                }
            )
    return alerts
