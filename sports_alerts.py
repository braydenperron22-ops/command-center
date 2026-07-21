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
"""

import html

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

_LEAGUES = [
    {"sport": "mlb", "label": "BLUE JAYS", "fetch_status": sports_client.fetch_jays, "flash_color": FLASH_BLUE},
    {"sport": "nhl", "label": "CANADIENS", "fetch_status": sports_client.fetch_habs, "flash_color": FLASH_RED},
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
    """New scoring plays since the last check, across whichever of the
    Jays/Habs games is actually live right now — {"kind": "sports",
    "sport", "team_label", "team_logo", "opponent_logo", "team_score",
    "opp_score", "description", "flash_color"}. Baseline established
    per game_id on its first sighting (same reasoning as news.
    get_new_alerts): a game only just going live, or the dashboard
    opening mid-game, shouldn't replay every scoring play that already
    happened as if it just did. Call at most once per rerun — like
    news.get_new_alerts, marking a play "seen" is a side effect."""
    seen = st.session_state.setdefault("seen_scoring_plays", {})
    alerts = []

    for league in _LEAGUES:
        status = league["fetch_status"]()
        game = status["game"] if status else None
        if not game or game["state"] != "live":
            continue

        game_id = game["game_id"]
        baseline_key = f"sports_alert_baseline_{league['sport']}_{game_id}"
        baseline_done = st.session_state.get(baseline_key, False)

        for play in _SCORING_PLAY_FETCHERS[league["sport"]](game_id):
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

    return alerts


def render_alert_bar(alert: dict, elapsed: float, variant: str = "a") -> None:
    """Same stretch/slide toast intro as news.render_alert_bar (see its
    own comment + theme.py's toast-*-intro keyframes) — a per-team
    color bar (Jays blue / Habs red) carrying both team logos, the
    score, and the actual play that just happened, instead of a plain
    text headline."""
    bar_class = "sports-alert-bar-mlb" if alert["sport"] == "mlb" else "sports-alert-bar-nhl"
    delay = f"animation-delay: -{elapsed:.2f}s;"
    label_text = f"{alert['team_label']} UPDATE"
    description = html.escape(alert["description"])
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
