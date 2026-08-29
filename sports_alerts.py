"""Real-time scoring-play toast + Govee-flash alerts for the Jays/Habs
live games — session request: "every time there's an update in a game
have a blue headline come through with a blue govee flash [...] the
headline should have the score with both team logos and the play that
scored [...] same with the habs but make it red." Reuses the exact
toast-queue/Govee-flash mechanism news.py's own breaking-news alerts
already use (see app.py's news_queue and govee_lighting.sync_lights's
score_flash param) — this is just a genuinely new source feeding that
same pipeline: each league's own live play-by-play feed, not RSS
headlines.

Flash color was briefly dynamic per play instead of fixed per league —
session request: "team that we're playing against updates that
dynamically change based on what team we're playing with their team
colors on the govy lights," later scrapped: "scrap what I said... about
having two different toast alerts for both teams... any score update,
just make it a Blue Jays update" — a live opponent-scored play went out
with no toast at all, and rather than chase that down, every play (ours
or theirs) now flashes this league's own fixed FLASH_BLUE/FLASH_RED
below, same as every other alert type here always has.

MLB's own live game feed already writes a real English sentence per
scoring play ("Cedric Mullins homers (12) on a fly ball to center
field.") — used verbatim rather than re-synthesized, both simpler and
more trustworthy than a paraphrase. NHL's own feed has no equivalent
ready-made sentence, so one is built here from the scorer/assists/
strength fields it does carry.

A general team-news headline feed (Google News RSS per team) lived
here briefly and was removed at the user's own request — "they're not
bringing any value... more annoying than anything with the constant
flashing. Just keep it at game updates and when the game ends."
Replaced with what the same feedback asked for instead: in-game streak
alerts (a Jays pitcher striking out 3+ straight batters, back-to-back
homers — see _mlb_streak_events) and a page-independent "First pitch
in Xm" countdown headline for the final hour before a game
(render_game_countdown, mirroring commute_reminder's leave headline).

Later expanded (session request: "expand the blue jays / habs toast
alerts... pre game stuff like time till first pitch, warmups underway,
first pitch next and more as well as more in game alerts") with four
more toast types, all through the same get_new_alerts()/
render_alert_bar() pipeline above: pregame countdown milestones
(PREGAME_MILESTONES_MINUTES), an MLB-only "warmups underway" toast
(sports_client's own detail_state field is what makes this
distinguishable from any other still-upcoming game), a "first pitch!"/
"puck drop!" toast the moment a game goes live, and in-game lead-change
toasts alongside the existing scoring-play ones.
"""

import html
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st

import fetch_throttle
import kiosk_tts
import persisted_state
import scores_client
import sports_client
from config import TIMEZONE

MLB_LIVE_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_id}/feed/live"
NHL_LANDING_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/landing"
# A scoring play should show up close to when it actually happened, not
# lag behind the live game itself — tighter than sports_client's own
# 30s LIVE_DETAIL_CACHE_TTL_SECONDS (count/outs churn every pitch
# regardless; a scoring play is the one thing here worth polling for
# specifically).
LIVE_FEED_CACHE_TTL_SECONDS = 15
# Comfortably more than one game could ever produce (MLB rarely scores
# more than ~15-20 times in a game) — same "ordered dict as a bounded
# set" pattern as news.py's own MAX_SEEN_HEADLINES, just sized for a
# much smaller universe of events per session.
MAX_SEEN_PLAYS = 200

# get_new_alerts()'s own dedup/baseline trackers — module-level, not
# st.session_state. Session report: "opposing team toast still not
# firing on score updates," while a live-simulated run of
# get_new_alerts() against the exact same real game correctly produced
# the alert — same root cause just found and fixed in
# govee_lighting.py: this kiosk isn't the only session ever connected
# (a phone checking the score), and every one of these trackers lived
# in st.session_state, so each connected session kept its own
# independent "have I already alerted on this play" state and its own
# independent per-game baseline_done flag. A session that reconnects or
# opens mid-game re-quiets its own view of the whole backlog on its
# first tick (the same harmless bootstrap news.py's own baseline uses),
# but with session-scoped state that first-tick reset can happen at any
# point in the game, on any connected session, independent of whether
# the kiosk's own long-running session already has a perfectly good
# baseline — and since toast_queue (already module-level, see its own
# docstring) is the one shared destination every session pushes into,
# it's whichever session runs next that determines whether a given real
# play ever reaches it. One shared copy here means every session agrees
# on what's already been alerted.
_seen_scoring_plays: dict[str, bool] = {}
_pregame_milestones_shown: dict[int, set] = {}
_warmup_alerted: dict[int, bool] = {}
_last_leader: dict[int, str] = {}
_start_alerted: dict[int, bool] = {}
_final_alerted: dict[int, bool] = {}
_baseline_done: dict[str, bool] = {}
# game_id -> True while a goal-to-go alert has already fired for the
# CURRENT drive's approach to the end zone — see _nfl_goal_to_go_alert's
# own docstring for why this resets (rather than staying True for the
# rest of the game) the moment the situation stops being goal-to-go.
_nfl_goal_to_go_active: dict[int, bool] = {}
# Same "fires once per stretch, resets when it clears" shape as
# _nfl_goal_to_go_active, for the MLB threatening-situation toast below.
_mlb_threat_active: dict[int, bool] = {}

FLASH_BLUE = (0, 70, 255)  # Blue Jays' own game — a clean, unmistakable blue on a light bulb
FLASH_RED = (255, 0, 0)  # Canadiens' own game — same red govee_lighting's breaking-news flash already uses
FLASH_GOLD = (255, 176, 0)  # Saints' own game — real team gold (ESPN's own color is a duller #d3bc8d), hand-brightened for a bulb same reasoning as scores_client._boost_for_bulb applies to a dim-but-real ESPN color

# How close to first pitch/puck drop the countdown headline starts
# showing — session request: "First Pitch In, and then we start
# counting down from like an hour, similar to the get ready to go
# timers" (commute_reminder's HEADLINE_WINDOW_MINUTES — same idea, not
# kept in sync; that one was later bumped to 120 on its own).
COUNTDOWN_WINDOW_MINUTES = 60
# A game's state stays "upcoming" briefly past its scheduled start
# (delays, ceremonies, the feed just lagging) — keep the headline up as
# "any minute now" for this long past the scheduled time rather than
# having it vanish right at the most anticipatory moment. Also governs
# how long takeover_state() below holds the jumbotron open across that
# same gap — was 15, bumped after a real live case (Jays/Mariners,
# 2026-08-29): first pitch was scheduled 3:07pm, but the game was
# genuinely still ESPN's own real "Warmup" detail_state at 3:28pm — 21
# minutes past scheduled start, already outside the old 15-minute
# grace window — so takeover_state() returned None and the kiosk
# dropped out of jumbotron mode mid-warmup, back to normal rotation,
# for a game that was very much still about to start (confirmed via
# direct fetch_jays() check: state="upcoming", detail_state="Warmup").
# User initially suspected an active severe thunderstorm warning was
# responsible — checked directly, it wasn't (no code path connects EC
# alert severity to takeover/page state at all; weather alerts only
# ever add a toast during a takeover, see weather_alerts_bar.py's own
# module docstring) — this ordinary delayed-first-pitch case was the
# real, unrelated cause. 45 gives real headroom for a genuine delay
# without holding a takeover open indefinitely if a game is actually
# postponed for the day.
COUNTDOWN_GRACE_MINUTES = 45

# The minimum consecutive-strikeout run worth interrupting the screen
# for — 2 in a row is routine, 3 is a pitcher genuinely dealing.
K_STREAK_MIN = 3

# Pregame toast milestones — session request: "expand the blue jays /
# habs toast alerts... pre game stuff like time till first pitch,
# warmups underway, first pitch next." Same due-milestone pattern as
# commute_reminder.MILESTONES_MINUTES/_due_milestone: widest first,
# each fires at most once per game, and opening the dashboard partway
# through the window skips (without replaying) any bigger ones already
# blown past. Narrower than commute's own list — this is a toast blip
# alongside the persistent countdown headline (render_game_countdown),
# not the only clock in town, so it doesn't need every 5-minute rung.
PREGAME_MILESTONES_MINUTES = [60, 30, 15, 5]

# Jumbotron takeover (see takeover_state / pages_jumbotron.py) — session
# request: "one hour before any game habs or jays and during the game I
# want it to go to that exactly so the game can be enjoyed with this
# system, before reverting back to the other system." The takeover
# window opens this far ahead of first pitch/puck drop...
TAKEOVER_LEAD_MINUTES = 60
# ...and holds this long after a game goes final, so the result, final
# linescore and scoring summary are actually readable before the kiosk
# releases back to its normal rotation.
TAKEOVER_POSTGAME_MINUTES = 15

# Session report: "the post game recap ended almost immediately...
# hardwire that it must stay for 15 mins postgame so no refresh can
# take it out." Root cause: jumbotron_seen_games/jumbotron_final_at used
# to live in st.session_state, which is scoped per browser connection —
# any reconnect (a kiosk auto-reload, a Streamlit websocket hiccup) wiped
# both dicts, so the very next rerun found this final game missing from
# "seen" and dropped the postgame takeover immediately, no matter how
# recently it had actually gone final. Same fix news.py's own
# _decided/_seen_headlines already use: a module-level global, loaded
# from persisted_state ONCE at import time (not on every 5s rerun — see
# persisted_state.py's own module docstring on Upstash's command cap),
# so these survive any browser reconnect within this running process,
# and a real process restart besides. Written back to persisted_state
# only on an actual change (a game newly seen/newly final), not every
# read, keeping write volume the same as the old occasional session-
# state mutation would have been.
_jumbotron_seen_games: dict = dict(persisted_state.load("jumbotron_seen_games", {}))
_jumbotron_final_at: dict = dict(persisted_state.load("jumbotron_final_at", {}))

# Session request: when several alerts/headlines are active at once,
# the order is "leave in at the top, then Habs, then Jays" — this is
# the Habs-then-Jays half, shared by render_game_countdown's stacking
# order and app.py's toast-queue priority sort (commute itself is
# ranked there, since commute alerts aren't this module's to order).
# Session request adding the Saints: "Saints should have the lowest
# gameday priority... habs -> jays -> saints" — appended last, since
# _takeover_priority ranks by position in this list (lower index wins).
# Only a TIEBREAKER now (see LEVEL_PRIORITY/_takeover_priority below) —
# session request: "even though the habs are technically higher in
# priority ranking because it's a preseason game, the jays would take
# authority" if the Jays are in a regular-season game at the same
# time. Team identity alone no longer decides it; game level does
# first, this only breaks a tie within the same level.
COUNTDOWN_PRIORITY = ["nhl", "mlb", "nfl"]
# Session request: "regardless of level, playoff games trump all" (and
# a regular-season game outranks a preseason one even from a normally
# higher-priority team). Lower rank wins, same convention as
# COUNTDOWN_PRIORITY. A game with no recognized "level" (shouldn't
# happen — every sports_client normalize function sets one — but
# treated as "regular" rather than crashing) sits in the middle.
LEVEL_PRIORITY = {"playoff": 0, "regular": 1, "preseason": 2}

_LEAGUES = [
    {
        "sport": "mlb", "label": "BLUE JAYS", "fetch_status": sports_client.fetch_jays,
        "flash_color": FLASH_BLUE, "kickoff_label": "First pitch",
    },
    {
        "sport": "nhl", "label": "CANADIENS", "fetch_status": sports_client.fetch_habs,
        "flash_color": FLASH_RED, "kickoff_label": "Puck drop",
    },
    {
        "sport": "nfl", "label": "SAINTS", "fetch_status": sports_client.fetch_saints,
        "flash_color": FLASH_GOLD, "kickoff_label": "Kickoff",
    },
]

# Session request: "during the semis and the finals... regardless of
# if my team is out or not, I wanna watch every game of those series...
# as the featured game." Below the tracked Jays/Habs/Saints games
# above, this is a SECOND, independent source of takeover_state()
# candidates: any live/upcoming/recently-final game leaguewide (not
# just our own team's) that's genuinely in the semis or later. Never
# fires for a game our own tracked team is actually playing in — that
# one already comes through the candidates above, with the real "our
# team" framing pages_jumbotron.py's board is built around (see
# pages_jumbotron._board_html's own "neutral" branch for what's
# different when THIS is the source instead).
_NEUTRAL_TEAM_ABBR = {"mlb": sports_client.MLB_TEAM_ABBR, "nhl": sports_client.NHL_TEAM_ABBR, "nfl": sports_client.NFL_TEAM_ABBR}
# scores_client._normalize_game's state strings ("pre"/"in"/"post") vs.
# the "upcoming"/"live"/"final" vocabulary every fetch_jays/fetch_habs/
# fetch_saints dict (and everything below in this module) already uses.
_ESPN_STATE_TO_TAKEOVER = {"pre": "upcoming", "in": "live", "post": "final"}


def _is_playoff_semis_or_final(sport: str, round_text: str | None) -> bool:
    """True for a real conference-final-or-later round — confirmed live
    (see scores_client.fetch_playoff_round_games's own docstring) that
    each league's ESPN round headline cleanly identifies this: NHL's
    "East Final"/"West Final"/"Stanley Cup Final" all contain "Final"
    while "1st Round"/"2nd Round" never do; NFL's "AFC Championship"/
    "NFC Championship"/"Super Bowl LIX" vs. "Wild Card Playoffs"/
    "Divisional Playoffs"; MLB's "ALCS"/"NLCS"/"World Series" vs.
    "ALWC"/"NLWC"/"ALDS"/"NLDS" (only the championship-series codes
    contain "LCS" — the wild card and division series codes don't).
    False for an earlier round or a non-playoff game (round_text is
    None for both)."""
    if not round_text:
        return False
    text = round_text.lower()
    if sport == "nhl":
        return "final" in text
    if sport == "nfl":
        return "championship" in text or "super bowl" in text
    if sport == "mlb":
        return "lcs" in text or "world series" in text
    return False


def _neutral_playoff_candidates() -> list[tuple[dict, None, dict]]:
    """Extra (league, status, game) candidates — same shape the loop in
    takeover_state() below already builds from _LEAGUES — for every
    live/upcoming/recently-final semis-or-later game across all three
    leagues that ISN'T one of our own tracked teams' games. `status` is
    always None here (nothing downstream needs a fetch_jays()-shaped
    dict for a neutral game — see pages_jumbotron._board_html's own
    "neutral" branch, which reads everything it needs straight off
    `game` instead)."""
    out: list[tuple[dict, None, dict]] = []
    for sport in ("mlb", "nhl", "nfl"):
        our_abbr = _NEUTRAL_TEAM_ABBR[sport]
        try:
            games = scores_client.fetch_playoff_round_games(sport)
        except Exception:
            continue
        for game in games:
            if our_abbr in (game["home"]["abbr"], game["away"]["abbr"]):
                continue
            if not _is_playoff_semis_or_final(sport, game.get("round_text")):
                continue
            state = _ESPN_STATE_TO_TAKEOVER.get(game["state"])
            if state is None:
                continue
            neutral_game = dict(game, game_id=game["event_id"], state=state, level="playoff")
            round_label = (game.get("round_text") or "PLAYOFFS").split(" - Game")[0].strip().upper()
            league = {"sport": sport, "label": round_label, "neutral": True}
            out.append((league, None, neutral_game))
    return out


@st.cache_data(ttl=LIVE_FEED_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_mlb_live_feed_raw(game_id: int) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(MLB_LIVE_FEED_URL.format(game_id=game_id), timeout=15)
    resp.raise_for_status()
    return resp.json()


def _mlb_scoring_plays(game_id: int) -> list[dict]:
    """Every scoring play so far in this game — {"play_id",
    "description", "away_score", "home_score"}. [] on any fetch
    failure (no last-good fallback needed: the caller's own "seen"
    tracking means a transient miss here is just caught on the very
    next poll a few seconds later, not lost). Session report: "just got
    an alert way before the actual play happened" — this used to read
    the live feed straight through, ignoring the jumbotron's own
    broadcast-delay setting every other live value already respects
    (sports_client.get_live_delay_seconds). Wrapped the OUTPUT list (not
    the raw feed) through sports_client.delayed() instead of the raw
    payload — cheaper to buffer (a handful of small play dicts, not the
    whole growing play-by-play) for the exact same delayed result."""
    try:
        data = _fetch_mlb_live_feed_raw(game_id)
    except Exception:
        return []
    plays = data.get("liveData", {}).get("plays", {})
    all_plays = plays.get("allPlays", [])
    out = []
    for idx in plays.get("scoringPlays", []):
        if idx >= len(all_plays):
            continue
        p = all_plays[idx]
        result = p.get("result", {})
        description = result.get("description")
        if not description:
            continue
        out.append(
            {
                "play_id": f"mlb-{game_id}-{p.get('about', {}).get('atBatIndex')}",
                "description": description,
                "away_score": result.get("awayScore"),
                "home_score": result.get("homeScore"),
            }
        )
    return sports_client.delayed(f"mlb_alert_scoring_{game_id}", out)


def _mlb_streak_events(game_id: int, is_home: bool) -> list[dict]:
    """Jays hot-streak moments worth their own alert (session request:
    "a Jays pitcher has struck out three batters in a row... if back to
    back homers are hit, things like that") — same {"play_id",
    "description", "away_score", "home_score"} shape as
    _mlb_scoring_plays so both run through get_new_alerts' one
    seen/baseline flow. Two kinds, both Jays-only (the whole point is
    OUR team heating up, not the opponent's):

    - A Jays pitcher's consecutive-strikeout run reaching K_STREAK_MIN,
      plus every K extending it past that — each later K is its own
      at-bat minutes after the last, and a 4th/5th straight K is rarer
      and more exciting than the 3rd, not spam.
    - Back-to-back (or longer) Jays homers: every homer that directly
      follows another one in the same half-inning.

    Built from the same cached live feed the scoring plays use — no
    extra network cost. Only completed at-bats count; the in-progress
    one at the end of allPlays isn't a result yet. Delayed the same way
    as _mlb_scoring_plays (see its own comment) and for the same
    reason — a streak alert is still a toast off the live feed."""
    try:
        data = _fetch_mlb_live_feed_raw(game_id)
    except Exception:
        return []
    all_plays = data.get("liveData", {}).get("plays", {}).get("allPlays", [])
    jays_batting_half = "bottom" if is_home else "top"

    events = []
    k_streak: list[dict] = []
    hr_streak: list[dict] = []
    hr_streak_key = None  # (inning, halfInning) — a homer run can't span innings

    for p in all_plays:
        about = p.get("about", {})
        if not about.get("isComplete"):
            continue
        result = p.get("result", {})
        event_type = result.get("eventType") or ""
        at_bat_index = about.get("atBatIndex")
        half = about.get("halfInning")
        scores = {"away_score": result.get("awayScore"), "home_score": result.get("homeScore")}

        if half == jays_batting_half:
            # Jays at the plate: track consecutive homers.
            batter = (p.get("matchup", {}).get("batter") or {}).get("fullName")
            key = (about.get("inning"), half)
            if event_type == "home_run" and batter:
                if key != hr_streak_key:
                    hr_streak, hr_streak_key = [], key
                hr_streak.append({"batter": batter, "at_bat_index": at_bat_index, **scores})
                if len(hr_streak) == 2:
                    description = f"Back-to-back homers — {hr_streak[0]['batter']} and {batter}!"
                elif len(hr_streak) > 2:
                    description = f"{batter} makes it {len(hr_streak)} straight homers!"
                else:
                    description = None
                if description:
                    events.append({"play_id": f"mlb-{game_id}-hrstreak-{at_bat_index}", "description": description, **scores})
            else:
                hr_streak, hr_streak_key = [], None
        else:
            # Jays in the field: track the pitching staff's consecutive
            # strikeouts. "strikeout_double_play" etc. still start with
            # "strikeout" and are still a K. The run deliberately
            # survives an inning break — "three batters in a row" is
            # about consecutive batters faced, wherever they fall.
            pitcher = (p.get("matchup", {}).get("pitcher") or {}).get("fullName")
            if event_type.startswith("strikeout"):
                k_streak.append({"pitcher": pitcher, "at_bat_index": at_bat_index, **scores})
                n = len(k_streak)
                if n >= K_STREAK_MIN:
                    pitchers = {k["pitcher"] for k in k_streak if k["pitcher"]}
                    who = pitchers.pop() if len(pitchers) == 1 else "Blue Jays pitching"
                    events.append(
                        {
                            "play_id": f"mlb-{game_id}-kstreak-{at_bat_index}",
                            "description": f"{who} has struck out {n} straight batters!",
                            **scores,
                        }
                    )
            else:
                k_streak = []

    return sports_client.delayed(f"mlb_alert_streak_{game_id}", events)


def _mlb_threat_label(detail: dict) -> str | None:
    """"Bases loaded"/"Runners on the corners"/None for the current
    inning state (sports_client.fetch_mlb_live_detail's own "bases"/
    "outs" fields) — session request: "bases loaded alerts... runners
    on the corners with no outs... situations where they look
    threatening to score." Two named situations, not a general run-
    expectancy model — matches exactly what was asked for rather than
    inventing extra thresholds. "Corners" is the real baseball term for
    first + third specifically (the two "corner" bases, as opposed to
    second) — gated to 0 outs, same boundary named in the request; real
    run-expectancy tables back that boundary too (corners drops from
    ~1.8 expected runs at 0 outs to ~1.0 at 1 out, a genuine cliff, not
    an arbitrary cutoff). Bases loaded has no out-count qualifier in
    the request and stays meaningfully above average run expectancy
    even at 2 outs, so it's flagged regardless of outs."""
    bases = detail.get("bases") or {}
    if bases.get("first") and bases.get("second") and bases.get("third"):
        return "Bases loaded"
    if bases.get("first") and bases.get("third") and not bases.get("second") and detail.get("outs") == 0:
        return "Runners on the corners"
    return None


@st.cache_data(ttl=LIVE_FEED_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_nhl_landing_raw(game_id: int) -> dict:
    fetch_throttle.wait_turn()
    resp = requests.get(NHL_LANDING_URL.format(game_id=game_id), timeout=15)
    resp.raise_for_status()
    return resp.json()


def _nhl_goal_description(goal: dict) -> str:
    scorer = (goal.get("name") or {}).get("default")
    if not scorer:
        return ""
    strength_phrase = {"pp": " on the power play", "sh": " shorthanded"}.get(goal.get("strength"), "")
    assists = [(a.get("name") or {}).get("default") for a in goal.get("assists") or []]
    assists = [a for a in assists if a]
    assist_phrase = f", assisted by {', '.join(assists)}" if assists else ", unassisted"
    return f"{scorer} scores{strength_phrase}{assist_phrase}."


def _nhl_scoring_plays(game_id: int) -> list[dict]:
    """Same shape as _mlb_scoring_plays — built from the landing
    endpoint's own per-period goal list (see sports_client's earlier
    use of this same endpoint for period-by-period line score), since
    unlike MLB there's no ready-made sentence to reuse verbatim here.
    Delayed the same way and for the same reason as _mlb_scoring_plays
    — see its own comment."""
    try:
        data = _fetch_nhl_landing_raw(game_id)
    except Exception:
        return []
    out = []
    for period in data.get("summary", {}).get("scoring", []):
        for goal in period.get("goals", []):
            description = _nhl_goal_description(goal)
            event_id = goal.get("eventId")
            if not description or event_id is None:
                continue
            out.append(
                {
                    "play_id": f"nhl-{game_id}-{event_id}",
                    "description": description,
                    "away_score": goal.get("awayScore"),
                    "home_score": goal.get("homeScore"),
                }
            )
    return sports_client.delayed(f"nhl_alert_scoring_{game_id}", out)


def _nfl_scoring_plays(game_id: int) -> list[dict]:
    """Every scoring play so far in this game — {"play_id",
    "description", "away_score", "home_score"}, same shape/purpose as
    _mlb_scoring_plays/_nhl_scoring_plays above. Used to be a
    deliberate, permanent no-op — flagged at the time as "no equally
    rich free NFL play-by-play source the way MLB Stats API's live feed
    and the NHL API's landing endpoint are." That turned out to be
    wrong: ESPN's own summary endpoint (scores_client.fetch_summary,
    already used elsewhere in this app for win probability/leaders/
    game_blurb) carries a real top-level "scoringPlays" array in
    exactly this shape — confirmed live (Rams @ Saints, 2026-08-22).
    Session report that caught the gap: "they just scored another
    touchdown, and I didn't get a single alert." Same broadcast-delay
    wrapping (sports_client.delayed) the MLB/NHL versions use, for the
    same reason theirs do — see that function's own docstring."""
    match = {"sport": "football", "league": "nfl", "event_id": game_id}
    summary = scores_client.fetch_summary(match)
    out = []
    for p in summary.get("scoringPlays") or []:
        description = p.get("text")
        play_id = p.get("id")
        if not description or play_id is None:
            continue
        out.append(
            {
                "play_id": f"nfl-{game_id}-{play_id}",
                "description": description,
                "away_score": p.get("awayScore"),
                "home_score": p.get("homeScore"),
            }
        )
    return sports_client.delayed(f"nfl_alert_scoring_{game_id}", out)


_SCORING_PLAY_FETCHERS = {"mlb": _mlb_scoring_plays, "nhl": _nhl_scoring_plays, "nfl": _nfl_scoring_plays}


def _due_pregame_milestone(minutes_until: float, shown: set) -> int | None:
    """The largest not-yet-shown pregame milestone reached — same
    skip-and-mark-passed-ones-shown logic as commute_reminder.
    _due_milestone, so opening the dashboard partway through the
    window fires the nearest real milestone rather than replaying every
    bigger one already blown past."""
    candidates = [m for m in PREGAME_MILESTONES_MINUTES if minutes_until <= m]
    if not candidates:
        return None
    due = min(candidates)
    if due in shown:
        return None
    for m in PREGAME_MILESTONES_MINUTES:
        if m > due:
            shown.add(m)
    return due


def get_new_alerts(now: datetime) -> list[dict]:
    """New pregame milestones, scoring plays (and Jays streak moments —
    see _mlb_streak_events), lead changes, and start/final moments
    since the last check, across whichever of the Jays/Habs games is
    relevant right now — {"kind": "sports", "sport", "team_label",
    "team_logo", "opponent_logo", "team_score", "opp_score",
    "description", "flash_color"} (team_score/opp_score are None for a
    pregame alert — see render_alert_bar's own handling of that).
    Baseline established per game_id on its first live sighting (same
    reasoning as news.get_new_alerts): a game only just going live, or
    the dashboard opening mid-game, shouldn't replay every scoring play
    that already happened as if it just did. Call at most once per
    rerun — like news.get_new_alerts, marking something "seen" is a
    side effect.

    Session request: "expand the blue jays / habs toast alerts...
    pre game stuff like time till first pitch, warmups underway, first
    pitch next and more as well as more in game alerts." Pregame
    milestones/warmup and the live-start toast are separate, smaller
    blips alongside render_game_countdown's own persistent headline —
    that headline is the one clock in the corner of the screen; these
    are the "ding, heads up" moments."""
    seen = _seen_scoring_plays
    # game_id -> set of pregame milestone minutes already fired.
    pregame_shown = _pregame_milestones_shown
    # game_id -> True once the "warmups underway" toast has fired (MLB only).
    warmup_alerted = _warmup_alerted
    # game_id -> the last-known score leader ("us"/"opp"/"tied"), for
    # detecting a genuine lead change rather than just any score move.
    last_leader = _last_leader
    # game_id -> True once the "first pitch!"/"puck drop!" toast fired.
    start_alerted = _start_alerted
    # game_id -> True once the end-of-game alert has fired for it, so a
    # game sitting as _pick_current_game's own "today's game" pick for
    # the rest of the day (see sports_client._pick_current_game) doesn't
    # re-alert on every later rerun.
    final_alerted = _final_alerted
    alerts = []

    for league in _LEAGUES:
        status = league["fetch_status"]()
        game = status["game"] if status else None
        if not game:
            continue

        game_id = game["game_id"]
        # Doubles as "was this game ever actually observed live" — the
        # end-of-game alert below only fires for a game that reached
        # this True at some point, so a game that was already final by
        # the time this process started watching (or before a fresh
        # deploy) doesn't get a stale "it just ended" alert for
        # something that happened before this process existed.
        baseline_key = f"{league['sport']}_{game_id}"

        if game["state"] == "upcoming":
            minutes_until = (game["start_time"] - now).total_seconds() / 60
            if minutes_until >= 0:
                shown = pregame_shown.setdefault(game_id, set())
                milestone = _due_pregame_milestone(minutes_until, shown)
                if milestone is not None:
                    shown.add(milestone)
                    alerts.append(
                        {
                            "kind": "sports",
                            "type": "pregame",
                            "sport": league["sport"],
                            "team_label": league["label"],
                            "team_logo": status["team_logo"],
                            "opponent_logo": game["opponent_logo"],
                            "team_score": None,
                            "opp_score": None,
                            "description": f"{league['kickoff_label']} in {milestone} min",
                            "flash_color": league["flash_color"],
                        }
                    )
            # MLB-only — see sports_client._normalize_mlb_game's own
            # docstring on "detail_state" for why NHL has no equivalent.
            if (
                league["sport"] == "mlb"
                and game.get("detail_state") == "Warmup"
                and not warmup_alerted.get(game_id)
            ):
                warmup_alerted[game_id] = True
                opponent_word = "vs" if game["is_home"] else "@"
                alerts.append(
                    {
                        "kind": "sports",
                        "type": "pregame",
                        "sport": league["sport"],
                        "team_label": league["label"],
                        "team_logo": status["team_logo"],
                        "opponent_logo": game["opponent_logo"],
                        "team_score": None,
                        "opp_score": None,
                        "description": f"Warmups underway {opponent_word} {game['opponent']}",
                        "flash_color": league["flash_color"],
                    }
                )

        elif game["state"] == "live":
            baseline_done = _baseline_done.get(baseline_key, False)
            # First live sighting: the "first pitch!"/"puck drop!" toast
            # — only within COUNTDOWN_GRACE_MINUTES of the scheduled
            # start, same staleness guard render_game_countdown uses, so
            # a mid-game app restart doesn't fire this hours late.
            if (
                not baseline_done
                and not start_alerted.get(game_id)
                and (now - game["start_time"]).total_seconds() <= COUNTDOWN_GRACE_MINUTES * 60
            ):
                start_alerted[game_id] = True
                opponent_word = "vs" if game["is_home"] else "@"
                alerts.append(
                    {
                        "kind": "sports",
                        "type": "start",
                        "sport": league["sport"],
                        "team_label": league["label"],
                        "team_logo": status["team_logo"],
                        "opponent_logo": game["opponent_logo"],
                        "team_score": None,
                        "opp_score": None,
                        "description": f"{league['kickoff_label']}! {league['label'].title()} {opponent_word} {game['opponent']} is underway",
                        "flash_color": league["flash_color"],
                    }
                )
            elif not baseline_done:
                start_alerted[game_id] = True

            scoring_plays = _SCORING_PLAY_FETCHERS[league["sport"]](game_id)
            plays = [(p, "score") for p in scoring_plays]
            if league["sport"] == "mlb":
                plays += [(p, "streak") for p in _mlb_streak_events(game_id, game["is_home"])]
            for play, play_type in plays:
                if play["play_id"] in seen:
                    continue
                seen[play["play_id"]] = True
                if len(seen) > MAX_SEEN_PLAYS:
                    seen.pop(next(iter(seen)))
                if not baseline_done:
                    continue
                team_score = play["home_score"] if game["is_home"] else play["away_score"]
                opp_score = play["away_score"] if game["is_home"] else play["home_score"]
                if team_score is None or opp_score is None:
                    continue
                alerts.append(
                    {
                        "kind": "sports",
                        "type": play_type,
                        "sport": league["sport"],
                        "team_label": league["label"],
                        "team_logo": status["team_logo"],
                        "opponent_logo": game["opponent_logo"],
                        "team_score": team_score,
                        "opp_score": opp_score,
                        "description": play["description"],
                        "flash_color": league["flash_color"],
                        # Session request: "add the scoring play for the
                        # Habs, Jays and Saints [voice]." Now real for all
                        # three leagues (see _nfl_scoring_plays's own
                        # docstring for when NFL's own gap closed) —
                        # spoken only for a real scoring play specifically,
                        # not the streak entries (a K-streak reads oddly
                        # read aloud as a "scoring play"), team-labeled
                        # since MLB's own live-feed sentence and NHL's
                        # built one don't always name the team plainly on
                        # their own.
                        "spoken": f"{league['label'].title()}: {play['description']}" if play_type == "score" else None,
                    }
                )
                # More in-game alerts (session request): a genuine lead
                # change is its own moment worth calling out, distinct
                # from "here's the play that just happened" above — only
                # judged off real scoring plays, not the streak entries
                # (same play, a second synthetic alert for the same
                # score with nothing new to compare).
                if play_type == "score" and baseline_done:
                    leader = "us" if team_score > opp_score else "opp" if opp_score > team_score else "tied"
                    previous = last_leader.get(game_id)
                    last_leader[game_id] = leader
                    if previous is not None and leader != previous and leader != "tied":
                        who = league["label"].title() if leader == "us" else game["opponent"]
                        # Plural agreement — every tracked/opponent team
                        # name here is plural ("Blue Jays", "Rays",
                        # "Canadiens", ...), so "take"/"regain", not
                        # "takes"/"regains".
                        verb = "take" if previous == "tied" else "retake" if leader == "us" else "regain"
                        alerts.append(
                            {
                                "kind": "sports",
                                "type": "lead_change",
                                "sport": league["sport"],
                                "team_label": league["label"],
                                "team_logo": status["team_logo"],
                                "opponent_logo": game["opponent_logo"],
                                "team_score": team_score,
                                "opp_score": opp_score,
                                "description": f"{who} {verb} the lead, {team_score}–{opp_score}",
                                "flash_color": league["flash_color"],
                            }
                        )
                    elif previous is not None and leader == "tied" and previous != "tied":
                        alerts.append(
                            {
                                "kind": "sports",
                                "type": "lead_change",
                                "sport": league["sport"],
                                "team_label": league["label"],
                                "team_logo": status["team_logo"],
                                "opponent_logo": game["opponent_logo"],
                                "team_score": team_score,
                                "opp_score": opp_score,
                                "description": f"Tied up, {team_score}–{opp_score}",
                                "flash_color": league["flash_color"],
                            }
                        )
                elif play_type == "score":
                    leader = "us" if team_score > opp_score else "opp" if opp_score > team_score else "tied"
                    last_leader[game_id] = leader

            # Goal-to-go toast — session request, live during the
            # Saints' own first game watched on the kiosk: "when
            # they're within, like, first and goal, second and goal...
            # fire off a toast and make it red. That'd be so fucking
            # sick." NFL only — the other two leagues have no equivalent
            # "about to score" situational state to watch for. Fires
            # once per drive's approach (goes True the first live
            # sighting of "& Goal" in the down/distance text, and stays
            # True — no repeat toast every 5s rerun while the same
            # goal-to-go stretch continues), then resets the moment the
            # situation stops being goal-to-go (a score, a turnover, or
            # the ball moving back out of goal-to-go range), so the
            # NEXT drive that reaches the goal line fires its own fresh
            # toast rather than staying silently "already alerted"
            # forever after the first one.
            if league["sport"] == "nfl" and baseline_done:
                situation = sports_client.fetch_nfl_situation(game_id) or {}
                down_text = situation.get("shortDownDistanceText") or situation.get("downDistanceText") or ""
                is_goal_to_go = "goal" in down_text.lower()
                was_active = _nfl_goal_to_go_active.get(game_id, False)
                _nfl_goal_to_go_active[game_id] = is_goal_to_go
                if is_goal_to_go and not was_active:
                    # Direct team-id compare (situation.possession is a
                    # raw ESPN team id) rather than resolving home/away
                    # first — simpler than threading the competitors
                    # list all the way through just to answer "is this
                    # us" when sports_client.NFL_TEAM_ID already answers
                    # it directly, same shortcut _normalize_nfl_game's
                    # own is_home check already takes.
                    possessor_is_us = situation.get("possession") == str(sports_client.NFL_TEAM_ID)
                    # Real broadcast excitement is watching OUR team
                    # threaten to score, not the opponent's — session
                    # framing was entirely from that angle ("that'd be
                    # so fucking sick"), so this only fires for our own
                    # offense reaching the goal line, not the opponent's.
                    if possessor_is_us:
                        alerts.append(
                            {
                                "kind": "sports",
                                "type": "goal_line",
                                "sport": league["sport"],
                                "team_label": league["label"],
                                "team_logo": status["team_logo"],
                                "opponent_logo": game["opponent_logo"],
                                "team_score": game["team_score"],
                                "opp_score": game["opp_score"],
                                "description": f"{down_text} — {league['label'].title()} are threatening to score!",
                                "flash_color": FLASH_RED,
                                "spoken": f"{league['label'].title()}: {down_text}",
                            }
                        )

            # MLB "threatening to score" toast — session request: "add,
            # like, bases loaded alerts or... the Jays are looking
            # threatening or... the Yankees are looking threatening
            # when they have... bases loaded with no outs or... runners
            # on the corners with no outs." Same repeat-guard shape as
            # the NFL goal-to-go block above (fires once per threatening
            # stretch, resets the moment it clears — _mlb_threat_active),
            # but unlike that one, fires for BOTH sides: the request
            # explicitly named both "we're threatening" and "they're
            # threatening" as wanted, not just our own offense — a
            # bases-loaded jam is exactly as tense to watch when the
            # OPPONENT'S at the plate.
            if league["sport"] == "mlb" and baseline_done:
                detail = sports_client.fetch_mlb_live_detail(game_id) or {}
                inning_state = detail.get("inning_state")
                # Only a real half-inning at bat has a meaningful bases/
                # outs state worth alerting on — "Middle"/"End" are the
                # between-innings transition states.
                threat_label = _mlb_threat_label(detail) if inning_state in ("Top", "Bottom") else None
                was_threat = _mlb_threat_active.get(game_id, False)
                _mlb_threat_active[game_id] = threat_label is not None
                if threat_label and not was_threat:
                    # Home team bats in the bottom half — combined with
                    # is_home, the same shortcut _mlb_streak_events'
                    # own jays_batting_half already uses.
                    jays_batting = (inning_state == "Bottom") == game["is_home"]
                    batting_team = league["label"].title() if jays_batting else game["opponent"]
                    outs = detail.get("outs") or 0
                    outs_text = "no outs" if outs == 0 else f"{outs} out" if outs == 1 else f"{outs} outs"
                    # Fresher than game["team_score"]/opp_score (that
                    # pair is only as fresh as the 5-minute schedule-
                    # level cache, same staleness sports_client.
                    # fetch_nfl_situation's own fix addressed for NFL
                    # earlier this session) — detail's own away_score/
                    # home_score come from this same live-linescore
                    # fetch, already paid for above.
                    team_score = detail.get("home_score") if game["is_home"] else detail.get("away_score")
                    opp_score = detail.get("away_score") if game["is_home"] else detail.get("home_score")
                    alerts.append(
                        {
                            "kind": "sports",
                            "type": "mlb_threat",
                            "sport": league["sport"],
                            "team_label": league["label"],
                            "team_logo": status["team_logo"],
                            "opponent_logo": game["opponent_logo"],
                            "team_score": team_score,
                            "opp_score": opp_score,
                            "description": f"{threat_label}, {outs_text} — {batting_team} threatening to score!",
                            "flash_color": FLASH_RED,
                            "spoken": f"{batting_team}: {threat_label}, {outs_text}",
                        }
                    )

            _baseline_done[baseline_key] = True

        elif (
            game["state"] == "final"
            and _baseline_done.get(baseline_key)
            and not final_alerted.get(game_id)
            and game["team_score"] is not None
            and game["opp_score"] is not None
        ):
            final_alerted[game_id] = True
            team_score, opp_score = game["team_score"], game["opp_score"]
            result = "W" if team_score > opp_score else "L" if team_score < opp_score else "T"
            opponent_word = "vs" if game["is_home"] else "@"
            # Session request: "add the scoring play for the Habs, Jays
            # and Saints [voice]" — final fires for all three sports
            # (unlike live scoring plays, which only MLB/NHL have real
            # data for), so this is the one moment Saints games actually
            # get a spoken callout too. The on-screen description ("Final
            # — W vs Tigers") reads fine at a glance but badly out loud
            # ("Final, W, vs, Tigers") — a real sentence built separately
            # here instead of just handing the same string to Piper.
            result_word = {"W": "beat", "L": "lost to", "T": "tied"}[result]
            alerts.append(
                {
                    "kind": "sports",
                    "type": "final",
                    "sport": league["sport"],
                    "team_label": league["label"],
                    "team_logo": status["team_logo"],
                    "opponent_logo": game["opponent_logo"],
                    "team_score": team_score,
                    "opp_score": opp_score,
                    "description": f"Final — {result} {opponent_word} {game['opponent']}",
                    "flash_color": league["flash_color"],
                    "spoken": f"Final: the {league['label'].title()} {result_word} the {game['opponent']}, {team_score} to {opp_score}.",
                }
            )

    return alerts


def _takeover_priority(league: dict, game: dict) -> tuple[int, int]:
    """(level_rank, team_rank) — level always wins first (session
    request: "regardless of level, playoff games trump all," and a
    regular-season game outranks a preseason one even from a normally
    higher-priority team — "even though the habs are technically
    higher in priority ranking because it's a preseason game, the jays
    would take authority"); team identity (COUNTDOWN_PRIORITY) only
    breaks a tie within the same level."""
    sport = league["sport"]
    team_rank = COUNTDOWN_PRIORITY.index(sport) if sport in COUNTDOWN_PRIORITY else len(COUNTDOWN_PRIORITY)
    return (LEVEL_PRIORITY.get(game.get("level"), 1), team_rank)


def game_time_active(now: datetime | None = None) -> bool:
    """True for the same pregame-lead-through-postgame-hold window
    takeover_state's own phase breakdown covers — session request,
    after hitting the Groq/Gemini free-tier rate limit: "make all the
    ai's go into a forced rest during game time... finding a pause is
    the next best move." groq_client/gemini_client call this to skip
    every AI generate() during that whole window (not just while a game
    is actually live) since the point is saving budget for whenever the
    user's actually looking at the dashboard again, not a claim that
    pregame/postgame AI calls are individually harmful. game_blurb's own
    postgame recap is the one deliberate exception (passes
    allow_during_game=True), since that's the one AI call this pause
    exists around, not despite."""
    # Naive, matching app.py's own `now` — sports_client's game
    # start_time is naive too (see that module's own convention), and
    # takeover_state's minutes_until subtraction raises TypeError on a
    # naive/aware mix (confirmed live: this crashed the maintenance
    # page's ai_status_by_model() call the first time this ran).
    now = now or datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
    return takeover_state(now) is not None


def takeover_state(now: datetime) -> dict | None:
    """Which game, if any, should take the entire screen over right now
    — {"phase": "pregame"|"live"|"postgame", "league", "status", "game",
    "minutes_until"} — or None to let the kiosk rotate normally.

    Session request: the kiosk runs as usual, then hands the whole
    screen to the jumbotron (pages_jumbotron.py) from
    TAKEOVER_LEAD_MINUTES before first pitch/puck drop through the end
    of the game, reverting on its own once TAKEOVER_POSTGAME_MINUTES
    have passed since it went final.

    Live beats pregame beats postgame, and within a phase Habs beat
    Jays — the same priority order everything else in this module uses
    (see COUNTDOWN_PRIORITY).

    The postgame hold only applies to a game this app actually watched
    (tracked in the persisted `_jumbotron_seen_games`, see its own
    module-level comment) — sports_client's own _pick_current_game keeps
    returning today's game for the rest of the day once it's final, so
    without that gate a kiosk started in the evening would take the
    screen over for a game that finished hours earlier. Because both
    that flag and the actual final-time stamp now survive a browser
    reconnect or process restart (rather than resetting with
    st.session_state), a restart mid-postgame resumes the real 15-minute
    countdown exactly where it left off instead of dropping the takeover
    early — session report: "the post game recap ended almost
    immediately... hardwire that it must stay for 15 mins postgame so no
    refresh can take it out." A restart hours after a game's real end
    still correctly stays out of postgame: the stamp reflects when the
    game actually went final, not when this process happened to notice,
    so the elapsed-time check below is just as true across a restart as
    within one continuous run.
    """
    candidates = []
    for league in _LEAGUES:
        status = league["fetch_status"]()
        game = status["game"] if status else None
        if game:
            candidates.append((league, status, game))
    candidates.extend(_neutral_playoff_candidates())
    if not candidates:
        return None

    _prune_jumbotron_postgame_state()

    live = sorted(
        (c for c in candidates if c[2]["state"] == "live"),
        key=lambda c: _takeover_priority(c[0], c[2]),
    )
    if live:
        league, status, game = live[0]
        _mark_jumbotron_seen(game["game_id"])
        return {"phase": "live", "league": league, "status": status, "game": game, "minutes_until": None}

    pregame = []
    for league, status, game in candidates:
        if game["state"] != "upcoming" or game.get("start_time") is None:
            continue
        minutes_until = (game["start_time"] - now).total_seconds() / 60
        # The same grace period render_game_countdown uses: a game whose
        # scheduled start has passed but that hasn't flipped to "live"
        # yet (delays, ceremonies, a lagging feed) is the LAST moment to
        # drop the takeover.
        if -COUNTDOWN_GRACE_MINUTES <= minutes_until <= TAKEOVER_LEAD_MINUTES:
            pregame.append((league, status, game, minutes_until))
    if pregame:
        pregame.sort(key=lambda c: _takeover_priority(c[0], c[2]))
        league, status, game, minutes_until = pregame[0]
        _mark_jumbotron_seen(game["game_id"])
        return {"phase": "pregame", "league": league, "status": status, "game": game, "minutes_until": minutes_until}

    postgame = []
    for league, status, game in candidates:
        if game["state"] != "final" or str(game["game_id"]) not in _jumbotron_seen_games:
            continue
        # Stamped on first sighting rather than read from the feed —
        # neither league's compact game dict carries an "ended at", and
        # what this actually needs to measure is "how long has this been
        # on screen since it ended," which is a wall-clock question.
        stamped = _mark_jumbotron_final(game["game_id"])
        if time.time() - stamped <= TAKEOVER_POSTGAME_MINUTES * 60:
            postgame.append((league, status, game))
    if postgame:
        postgame.sort(key=lambda c: _takeover_priority(c[0], c[2]))
        league, status, game = postgame[0]
        return {"phase": "postgame", "league": league, "status": status, "game": game, "minutes_until": None}

    return None


def _mark_jumbotron_seen(game_id) -> None:
    """Records that this game was actually watched live/pregame this
    process — a no-op past the first call for a given game_id, so this
    doesn't write to persisted_state on every 5s rerun, only the one
    rerun that actually changes anything. Keyed by str(game_id): JSON
    (both the local file and Upstash) only has string keys, so an int
    game_id round-trips back from persisted_state.load() as a string —
    confirmed live this silently broke the lookup after a simulated
    restart before switching every key here to str() consistently."""
    key = str(game_id)
    if key not in _jumbotron_seen_games:
        _jumbotron_seen_games[key] = True
        persisted_state.save("jumbotron_seen_games", _jumbotron_seen_games)


def _mark_jumbotron_final(game_id) -> float:
    """The real wall-clock moment this game was first observed as final
    — stamped once and persisted immediately, same "only write on an
    actual change" reasoning as _mark_jumbotron_seen above (including
    the str(game_id) keying — see its own comment)."""
    key = str(game_id)
    if key not in _jumbotron_final_at:
        _jumbotron_final_at[key] = time.time()
        persisted_state.save("jumbotron_final_at", _jumbotron_final_at)
    return _jumbotron_final_at[key]


# How long a decided game_id sticks around in persisted state after its
# postgame window closes — comfortably longer than TAKEOVER_POSTGAME_
# MINUTES so nothing currently relevant is ever at risk, just cleaning
# up entries with no further reason to exist so this doesn't grow
# unbounded across a whole season.
_JUMBOTRON_STATE_PRUNE_SECONDS = 4 * 60 * 60


def _prune_jumbotron_postgame_state() -> None:
    cutoff = time.time() - _JUMBOTRON_STATE_PRUNE_SECONDS
    stale = [gid for gid, stamped in _jumbotron_final_at.items() if stamped <= cutoff]
    if not stale:
        return
    for gid in stale:
        del _jumbotron_final_at[gid]
        _jumbotron_seen_games.pop(gid, None)
    persisted_state.save("jumbotron_final_at", _jumbotron_final_at)
    persisted_state.save("jumbotron_seen_games", _jumbotron_seen_games)


def takeover_preview_state() -> dict | None:
    """The same shape takeover_state returns, for whichever game is
    nearest, ignoring the timing windows entirely — used only by the
    manual `?page=jumbotron` override so the board can be looked at on
    a day with no game currently in its window. None if neither team
    has a game at all (both leagues in the offseason)."""
    for league in _LEAGUES:
        status = league["fetch_status"]()
        game = status["game"] if status else None
        if not game:
            continue
        phase = {"live": "live", "final": "postgame"}.get(game["state"], "pregame")
        return {"phase": phase, "league": league, "status": status, "game": game, "minutes_until": None}
    return None


def game_holds_screen_awake(takeover: dict | None) -> bool:
    """True while a live/recent game should keep the screen in its
    normal, fully-active state regardless of the overnight schedule —
    originally the trigger for the monitor's own smart plug ("the smart
    plug can't turn off if there's a live game... after the game is
    over the setup can sleep"), now repurposed for the same reasoning
    behind night_mode.py's own trigger once the plug itself was removed
    (a display that's physically always on doesn't need a plug held
    open, but still shouldn't drop into the dim nightstand view mid-
    game). Originally just "game state == live", which cut the plug (now:
    entered night mode) the instant a game went final — session
    correction: "the second the end of game recap happened the smart
    plug turned off... shouldn't have happened for at least 5 mins."
    Now rides the exact same postgame hold the jumbotron's own recap
    uses (phase "postgame", TAKEOVER_POSTGAME_MINUTES — comfortably
    more than 5), rather than reverting the instant state flips to
    "final".

    Takes the same takeover_state() dict app.py already computes each
    rerun, rather than re-deriving live status itself — that dict is
    nulled by the manual "End Session" dismiss check before this ever
    sees it, which is exactly the one exception asked for: "the only
    time it shouldn't [stay on] is when i close out mid game.\""""
    return takeover is not None and takeover["phase"] in ("live", "postgame")


def render_alert_bar(alert: dict) -> None:
    """Same plain, immediately-visible bar as news.render_alert_bar (see
    its own docstring for why the old stretch/slide intro was dropped
    entirely) — a per-team color bar (Jays blue / Habs red / Saints
    gold) carrying both team logos and the score, plus the play/streak/
    lead-change that just happened, the final result (session request:
    "make an end of game alert"), or a pregame moment (session request:
    "expand the blue jays / habs toast alerts... pre game stuff")
    instead of a plain text headline. A pregame or game-start alert has
    no real score yet (team_score/opp_score are None) — shown as just
    the two logos, no score chip, rather than a misleading "0–0".

    `bar_class` built from `alert["sport"]` directly (not a hardcoded
    mlb/nhl binary, which is what this was before the Saints) — needs
    a matching `.sports-alert-bar-{sport}` rule in theme.py for every
    sport in _LEAGUES, same convention `.jumbo-hero-{sport}`/
    `.game-countdown-{sport}` already use elsewhere. A "goal_line" or
    "mlb_threat" alert (see the goal-to-go and threatening-situation
    checks above) overrides this per-sport color with a fixed red
    instead — session request: "fire off a toast and make it red...
    that'd be so fucking sick" — real urgency should read as red
    regardless of Saints gold being the sport's own normal color, the
    same way this app already reserves red for a
    genuinely urgent moment elsewhere (storm-phase lighting).

    Session report: "the bottom bar goes away... the red headliner...
    should be there, but it's not." Every field below is now `.get()`
    with a plain fallback rather than bracket access — a single
    missing key here used to be able to crash the whole render (caught
    upstream in app.py, but leaving the bottom bar blank for that
    rerun instead of at least showing this alert's other fields)."""
    # "sports-alert-bar-goalline" — the fixed urgent-red styling
    # session request "make it red... that'd be so fucking sick"
    # originally built for the NFL goal-to-go toast — reused as-is for
    # the MLB threatening-to-score toast below rather than a new CSS
    # class: same "about to score" excitement, same real urgency,
    # nothing sport-specific about the actual styling despite the name.
    is_scoring_threat = alert.get("type") in ("goal_line", "mlb_threat")
    bar_class = "sports-alert-bar-goalline" if is_scoring_threat else f"sports-alert-bar-{alert.get('sport', 'mlb')}"
    description = html.escape(alert.get("description", ""))
    suffix = {
        "final": "FINAL",
        "streak": "STREAK",
        "pregame": "PREGAME",
        "start": "LIVE",
        "lead_change": "LEAD CHANGE",
        "goal_line": "GOAL LINE",
        "mlb_threat": "THREAT",
    }.get(alert.get("type"), "UPDATE")
    label_text = f"{alert.get('team_label', '')} {suffix}"
    has_score = alert.get("team_score") is not None and alert.get("opp_score") is not None
    score_text = f"{alert.get('team_score')}–{alert.get('opp_score')}" if has_score else ""
    team_logo = alert.get("team_logo", "")
    opponent_logo = alert.get("opponent_logo", "")
    # Session request: "add the scoring play for the Habs, Jays and
    # Saints [voice]" — only "score" and "final" alerts carry a real
    # "spoken" sentence (see get_new_alerts's own comments on both);
    # every other type (pregame, warmup, start, streak, lead_change)
    # leaves it unset, same "no summary, no audio, chime only" shape
    # weather_alerts_bar/commute_reminder already use for their own
    # optional voice lines.
    spoken_text = alert.get("spoken") or ""
    summary_attr = html.escape(spoken_text)
    audio_b64 = kiosk_tts.synthesize_base64(spoken_text) if spoken_text else None
    audio_attr = f' data-audio-b64="{audio_b64}"' if audio_b64 else ""
    st.markdown(
        f'<div class="{bar_class}" data-summary="{summary_attr}"{audio_attr}>'
        f'<span class="news-breaking-label">{label_text}</span>'
        f'<span class="sports-alert-score">'
        f'<img src="{team_logo}" />{score_text}'
        f'<img src="{opponent_logo}" /></span>'
        f'<span class="news-alert-headline">{description}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_game_countdown(now: datetime) -> None:
    """A standalone countdown headline above the hero clock row for the
    final hour before a Jays/Habs game — "First pitch in 43 min" —
    page-independent, exactly like commute_reminder.
    render_leave_headline (session request: "similar to the get ready
    to go timers"). Silent outside the COUNTDOWN_WINDOW_MINUTES window;
    holds as "any minute now" for COUNTDOWN_GRACE_MINUTES past the
    scheduled start if the game hasn't actually gone live yet.

    If both teams play within the same hour (a fall evening with a Jays
    playoff game and a Habs game genuinely can), both render — session
    request: the priority order when several things are going on at
    once is "leave in at the top, then Habs, then Jays." The leave
    headline's spot at the very top is app.py's call order (it renders
    before this); Habs-before-Jays (COUNTDOWN_PRIORITY) only breaks a
    tie now — level (LEVEL_PRIORITY) decides first, same reasoning and
    same _takeover_priority helper as takeover_state's own priority
    sort (session request: "regardless of level, playoff games trump
    all" — this docstring's own Jays-playoff-vs-Habs example is exactly
    that case).

    Ticks for real once a second via app.py's global live-countdown
    ticker (session request, same as commute_reminder's leave headline:
    "make that logic work for all the timer elements") — the text
    below is only the first frame's value."""
    active = []
    for league in _LEAGUES:
        status = league["fetch_status"]()
        game = status["game"] if status else None
        if not game or game["state"] != "upcoming" or game.get("start_time") is None:
            continue
        minutes_until = (game["start_time"] - now).total_seconds() / 60
        if not (-COUNTDOWN_GRACE_MINUTES <= minutes_until <= COUNTDOWN_WINDOW_MINUTES):
            continue
        active.append({"league": league, "game": game, "minutes_until": minutes_until, "start_time": game["start_time"]})

    active.sort(key=lambda entry: _takeover_priority(entry["league"], entry["game"]))
    for entry in active:
        kickoff = entry["league"]["kickoff_label"]
        minutes = int(entry["minutes_until"])
        text = f"{kickoff} any minute now" if minutes <= 0 else f"{kickoff} in {minutes} min"
        target_ms = int(entry["start_time"].replace(tzinfo=ZoneInfo(TIMEZONE)).timestamp() * 1000)
        st.markdown(
            f'<div class="game-countdown-headline game-countdown-{entry["league"]["sport"]}">'
            f'<span class="live-countdown" data-target-ms="{target_ms}" data-format="words" '
            f'data-template="{html.escape(kickoff)} in {{}}" data-zero-text="{html.escape(kickoff)} any minute now">'
            f"{text}</span></div>",
            unsafe_allow_html=True,
        )
