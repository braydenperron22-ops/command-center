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
"""

import html
from datetime import datetime

import requests
import streamlit as st

import fetch_throttle
import sports_client

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

FLASH_BLUE = (0, 70, 255)  # Blue Jays' own game — a clean, unmistakable blue on a light bulb
FLASH_RED = (255, 0, 0)  # Canadiens' own game — same red govee_lighting's breaking-news flash already uses

# How close to first pitch/puck drop the countdown headline starts
# showing — session request: "First Pitch In, and then we start
# counting down from like an hour, similar to the get ready to go
# timers" (commute_reminder's HEADLINE_WINDOW_MINUTES, same value).
COUNTDOWN_WINDOW_MINUTES = 60
# A game's state stays "upcoming" briefly past its scheduled start
# (delays, ceremonies, the feed just lagging) — keep the headline up as
# "any minute now" for this long past the scheduled time rather than
# having it vanish right at the most anticipatory moment.
COUNTDOWN_GRACE_MINUTES = 15

# The minimum consecutive-strikeout run worth interrupting the screen
# for — 2 in a row is routine, 3 is a pitcher genuinely dealing.
K_STREAK_MIN = 3

# Session request: when several alerts/headlines are active at once,
# the order is "leave in at the top, then Habs, then Jays" — this is
# the Habs-then-Jays half, shared by render_game_countdown's stacking
# order and app.py's toast-queue priority sort (commute itself is
# ranked there, since commute alerts aren't this module's to order).
COUNTDOWN_PRIORITY = ["nhl", "mlb"]

_LEAGUES = [
    {
        "sport": "mlb", "label": "BLUE JAYS", "fetch_status": sports_client.fetch_jays,
        "flash_color": FLASH_BLUE, "kickoff_label": "First pitch",
    },
    {
        "sport": "nhl", "label": "CANADIENS", "fetch_status": sports_client.fetch_habs,
        "flash_color": FLASH_RED, "kickoff_label": "Puck drop",
    },
]


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
    next poll a few seconds later, not lost)."""
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
    return out


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
    one at the end of allPlays isn't a result yet."""
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

    return events


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
    unlike MLB there's no ready-made sentence to reuse verbatim here."""
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
    return out


_SCORING_PLAY_FETCHERS = {"mlb": _mlb_scoring_plays, "nhl": _nhl_scoring_plays}


def get_new_alerts() -> list[dict]:
    """New scoring plays (and Jays streak moments — see
    _mlb_streak_events) since the last check, across whichever of the
    Jays/Habs games is actually live right now — {"kind": "sports",
    "sport", "team_label", "team_logo", "opponent_logo", "team_score",
    "opp_score", "description", "flash_color"}. Baseline established
    per game_id on its first sighting (same reasoning as news.
    get_new_alerts): a game only just going live, or the dashboard
    opening mid-game, shouldn't replay every scoring play that already
    happened as if it just did. Call at most once per rerun — like
    news.get_new_alerts, marking a play "seen" is a side effect."""
    seen = st.session_state.setdefault("seen_scoring_plays", {})
    # game_id -> True once the end-of-game alert has fired for it, so a
    # game sitting as _pick_current_game's own "today's game" pick for
    # the rest of the day (see sports_client._pick_current_game) doesn't
    # re-alert on every later rerun.
    final_alerted = st.session_state.setdefault("sports_alert_final_alerted", {})
    alerts = []

    for league in _LEAGUES:
        status = league["fetch_status"]()
        game = status["game"] if status else None
        if not game:
            continue

        game_id = game["game_id"]
        # Doubles as "was this game ever actually observed live this
        # session" — the end-of-game alert below only fires for a game
        # that reached this True at some point, so a game that was
        # already final by the time the kiosk started watching (or
        # before a fresh deploy) doesn't get a stale "it just ended"
        # alert for something that happened before this session existed.
        baseline_key = f"sports_alert_baseline_{league['sport']}_{game_id}"

        if game["state"] == "live":
            baseline_done = st.session_state.get(baseline_key, False)
            plays = [(p, "score") for p in _SCORING_PLAY_FETCHERS[league["sport"]](game_id)]
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
                    }
                )
            st.session_state[baseline_key] = True

        elif (
            game["state"] == "final"
            and st.session_state.get(baseline_key)
            and not final_alerted.get(game_id)
            and game["team_score"] is not None
            and game["opp_score"] is not None
        ):
            final_alerted[game_id] = True
            team_score, opp_score = game["team_score"], game["opp_score"]
            result = "W" if team_score > opp_score else "L" if team_score < opp_score else "T"
            opponent_word = "vs" if game["is_home"] else "@"
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
                }
            )

    return alerts


def any_game_live() -> bool:
    """True if either the Jays' or Habs' own tracked game is live right
    now — session request: the screen shouldn't dim/sleep for the night
    while a game is still going, only once it's actually over (see
    app.py's night_dim override)."""
    for league in _LEAGUES:
        status = league["fetch_status"]()
        game = status["game"] if status else None
        if game and game["state"] == "live":
            return True
    return False


def render_alert_bar(alert: dict, elapsed: float, variant: str = "a") -> None:
    """Same stretch/slide toast intro as news.render_alert_bar (see its
    own comment + theme.py's toast-*-intro keyframes) — a per-team
    color bar (Jays blue / Habs red) carrying both team logos and the
    score, plus the play/streak that just happened or the final result
    (session request: "make an end of game alert"), instead of a plain
    text headline."""
    bar_class = "sports-alert-bar-mlb" if alert["sport"] == "mlb" else "sports-alert-bar-nhl"
    delay = f"animation-delay: -{elapsed:.2f}s;"
    description = html.escape(alert["description"])
    suffix = {"final": "FINAL", "streak": "STREAK"}.get(alert.get("type"), "UPDATE")
    label_text = f"{alert['team_label']} {suffix}"
    st.markdown(
        f'<div class="{bar_class}">'
        f'<span class="news-breaking-label toast-label-anim-{variant}" style="{delay}">{label_text}</span>'
        f'<span class="sports-alert-score toast-headline-anim-{variant}" style="{delay}">'
        f'<img src="{alert["team_logo"]}" />{alert["team_score"]}–{alert["opp_score"]}'
        f'<img src="{alert["opponent_logo"]}" /></span>'
        f'<span class="news-alert-headline toast-headline-anim-{variant}" style="{delay}">{description}</span>'
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
    before this); Habs-before-Jays is COUNTDOWN_PRIORITY here."""
    active = []
    for league in _LEAGUES:
        status = league["fetch_status"]()
        game = status["game"] if status else None
        if not game or game["state"] != "upcoming" or game.get("start_time") is None:
            continue
        minutes_until = (game["start_time"] - now).total_seconds() / 60
        if not (-COUNTDOWN_GRACE_MINUTES <= minutes_until <= COUNTDOWN_WINDOW_MINUTES):
            continue
        active.append({"league": league, "minutes_until": minutes_until})

    active.sort(key=lambda entry: COUNTDOWN_PRIORITY.index(entry["league"]["sport"]))
    for entry in active:
        kickoff = entry["league"]["kickoff_label"]
        minutes = int(entry["minutes_until"])
        text = f"{kickoff} any minute now" if minutes <= 0 else f"{kickoff} in {minutes} min"
        st.markdown(
            f'<div class="game-countdown-headline game-countdown-{entry["league"]["sport"]}">{text}</div>',
            unsafe_allow_html=True,
        )
