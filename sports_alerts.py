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

Session request: "add blue jays/habs news headlines that appear in the
feed with the same rules as game updates" — general team news (trades,
injuries, roster moves), not just live scoring plays, pulled from
Google News (same RSS-search approach as conflict_news.py, no key
needed) and filtered through news.is_clickbait so teaser junk doesn't
slip in. These feed into this exact same get_new_alerts()/
render_alert_bar() pipeline with `"type": "news"` instead of
`"score"`/`"final"` — same kind="sports", same flash_color, so they
pick up the identical blue/red Govee flash a live scoring play gets
(app.py's score_flash check only looks at kind, not type), just
without a score/opponent logo to show.
"""

import hashlib
import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests
import streamlit as st

import fetch_throttle
import news
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

TEAM_NEWS_RSS_URL = "https://news.google.com/rss/search"
# Team news doesn't need scoring-play-level freshness — a trade or injury
# story is still "new" an hour later, so this polls far less aggressively
# than LIVE_FEED_CACHE_TTL_SECONDS.
TEAM_NEWS_CACHE_TTL_SECONDS = 10 * 60
# Same "ordered dict as a bounded set" pattern as MAX_SEEN_PLAYS above.
MAX_SEEN_TEAM_NEWS = 200
# Without a `when:` clause, Google News returns its own general "top
# results" for the query — confirmed live this pulls in weeks-old
# stories alongside today's, which both misdates pages_sports.py's own
# "X ago" display (see its _render_team_news) and would let a genuinely
# stale story slip through the toast's baseline as if new the first
# time this query happens to surface it. Same `when:Nd` operator
# conflict_news.py already uses, just a tighter window — a trade/injury
# story is still relevant a few days later, but the Google searches
# themselves should stay scoped to "recent," not "ever written."
TEAM_NEWS_WINDOW_DAYS = 3

# Sports-specific junk that news.is_clickbait (tuned for finance
# headlines) has no reason to know about — session feedback: "a little
# too many bad headlines are creeping through." Every term/pattern here
# came from a real headline observed in the live pool, grouped by what
# kind of non-news it is. The bar for this feed is "something actually
# happened to the team" (a trade, an injury, a signing, a death, a
# roster move) — not per-game content, which the live scoring alerts
# and the Sports page's own scoreboard already cover far better.
TEAM_NEWS_EXCLUDE_TERMS = [
    # Per-game clip/recap churn — MLB.com emits several of these per
    # game ("Game Story, Scores/Highlights", "Condensed Game: TB@TOR",
    # "Japanese Highlights", "Key takeaways: Rays 7, Blue Jays 1"),
    # plus Google sometimes surfaces the Spanish-language mirror of the
    # same recap ("Resumen", "Jugadas destacadas").
    "highlights", "condensed game", "game story", "game recap",
    "game stats", "box score", "key takeaways", "gameday live",
    "live updates", "play in game", "breaking down", "on facing",
    "roundup", "preview", "catching up with", "resumen",
    "jugadas destacadas",
    # Pregame/viewing/ticket-sales service content ("Where to watch...
    # TV channel, start time, streaming", "Buy Tickets for Rays vs.
    # Blue Jays", ESPN's bare "Pregame" stubs).
    "where to watch", "tv channel", "streaming", "start time",
    "buy tickets", "tickets for", "pregame",
    # Betting content that slips past news.py's phrase-level terms
    # ("Odds, Betting Lines, Expert picks, Game Projections, DFS
    # Projections and Player Prop Projections", "Top MLB Bets: YRFI
    # Picks"). In a team-news feed, a bare "odds"/"bets" is betting
    # content essentially always — no "odds of making the playoffs"
    # false-positive has shown up, and losing one would be fine.
    "odds", "betting", "bets", "expert picks", "player prop",
    "parlay", "moneyline", "dfs", "sportsline", "majorwager",
    # Quote-aggregation content mills — outlets whose entire model is
    # re-packaging one player quote per article. Google News bakes the
    # source name into every title as a " - Source" suffix, so the
    # outlet name alone reliably marks these regardless of phrasing.
    "heavy.com", "fansided", "athlon sports", "larry brown sports",
    "sportskeeda", "clutchpoints", "the spun", "essentially sports",
    "yardbarker",
    # The quote-churn phrasing itself, for the same articles coming
    # through outlets not listed above ("Gets Candid About...", "Drops
    # Honest Quote", "Makes Feelings Clear", "Shares Heartfelt
    # Message", "Breaks Silence").
    "gets candid", "drops honest", "drops blunt", "makes feelings clear",
    "breaks silence", "sounds off", "heartfelt", "turning heads",
    "fans react", "social media reacts", "nobody saw coming",
    "must-watch",
]
TEAM_NEWS_EXCLUDE_PATTERNS = [
    # Listicle/hot-take leads — "2 Reasons Why Blue Jays' Playoff Hopes
    # Are Dwindling", "One Thing Must Change for the Blue Jays".
    # news.py's own listicle patterns are stock-specific, so the sports
    # shapes need their own.
    re.compile(r"^(?:\d+|one|two|three|four|five)\s+(?:reasons?|things?|takeaways?|ways?|keys?|observations?)\b"),
    re.compile(r"^ranking\b"),
    # "X Reacts After...", "Dylan Cease Reacts to..." — a reaction to
    # the news is not the news.
    re.compile(r"\breacts?\s+(?:after|to)\b"),
    # "Mets' Bo Bichette Sends Blue Jays Message..." — content-mill
    # narrativizing, never a report of an actual event.
    re.compile(r"\bsends?\b.{0,40}\bmessage\b"),
    # MLB.com's per-play video-clip stubs — "Kevin Gausman against the
    # Rays - MLB.com", "Dylan Cease's outing against the Rays -
    # MLB.com". Anchored to the MLB.com source suffix so a real
    # newspaper story that merely contains "against the" mid-sentence
    # isn't caught; MLB.com's own genuine news doesn't use this shape.
    re.compile(r"\bagainst the\b[^-]*- mlb\.com$"),
    # More clip stubs: "Dylan Cease strikes out seven vs. Rays".
    re.compile(r"\bstrikes? out\b.{0,20}\b(?:vs|against)\b"),
    # Scoreline-recap titles — "Oh captain, my captain: Rays 7, Blue
    # Jays 1". A "Team N, Team N" scoreline in the headline is always a
    # game recap. \d{1,2}\b can't half-match a 4-digit year (no word
    # boundary between digits), so date parentheticals like "(Oct 20,
    # 2026)" don't false-positive.
    re.compile(r"\b\w+(?:\s\w+){0,2}\s\d{1,2},\s\w+(?:\s\w+){0,2}\s\d{1,2}\b"),
    # "Top 10 Prospects"-style numbered rankings (digits only — "Top
    # Three Potential Fits" is trade-rumor content worth keeping).
    re.compile(r"\btop \d+\b"),
    # Link-roundup posts ("Sick Puck Links: Suzuki Expectations; ...").
    # A term can't catch this one: _contains_any's trailing \b never
    # matches between ":" and a space (both non-word chars).
    re.compile(r"\blinks:"),
    # "Mic'd up: Mike Condon" clip stubs — . instead of a literal
    # apostrophe so both the straight and curly variants match.
    re.compile(r"\bmic.d up\b"),
]


def _is_team_news_junk(headline: str) -> bool:
    h = headline.lower()
    if news._contains_any(h, TEAM_NEWS_EXCLUDE_TERMS):
        return True
    return any(p.search(h) for p in TEAM_NEWS_EXCLUDE_PATTERNS)

# "logo" calls sports_client's own team-id-keyed URL builders directly
# rather than pulling "team_logo" off fetch_jays()/fetch_habs()'s status
# dict — that status is None entirely in the off-season (see fetch_jays'
# own docstring), and a trade/roster story is exactly the kind of team
# news that keeps happening then, so the news alert's logo can't depend
# on a live game/season existing the way the scoring-play alerts above
# already do.
_LEAGUES = [
    {
        "sport": "mlb", "label": "BLUE JAYS", "fetch_status": sports_client.fetch_jays,
        "flash_color": FLASH_BLUE, "news_query": '"Toronto Blue Jays"',
        "logo": sports_client._mlb_logo_url(sports_client.MLB_TEAM_ID),
    },
    {
        "sport": "nhl", "label": "CANADIENS", "fetch_status": sports_client.fetch_habs,
        "flash_color": FLASH_RED, "news_query": '"Montreal Canadiens"',
        "logo": sports_client._nhl_logo_url(sports_client.NHL_TEAM_ABBR),
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


def _parse_pub_date(raw: str) -> datetime | None:
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


@st.cache_data(ttl=TEAM_NEWS_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_team_news_raw(query: str) -> list[dict]:
    """Same Google News RSS search approach as conflict_news.py — no key
    needed, and a quoted team-name search already surfaces real trade/
    injury/roster stories without a dedicated MLB/NHL news API. Filtered
    through news.is_clickbait (same as conflict_news.py's own use of
    that shared check) plus _is_team_news_junk above for the sports-
    specific churn that a finance-tuned filter has no terms for."""
    params = {"q": f"{query} when:{TEAM_NEWS_WINDOW_DAYS}d", "hl": "en-US", "gl": "US", "ceid": "US:en"}
    try:
        fetch_throttle.wait_turn()
        resp = requests.get(TEAM_NEWS_RSS_URL, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.content)
    except (requests.RequestException, ElementTree.ParseError):
        return []
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if title and not news.is_clickbait(title) and not _is_team_news_junk(title):
            items.append({"headline": title, "published": _parse_pub_date(item.findtext("pubDate") or "")})
    return items


def team_news_headlines() -> list[dict]:
    """Every currently-live Jays/Habs news headline — {"headline",
    "published", "sport", "team_label", "team_logo", "flash_color"} —
    across both teams, no seen-tracking/baseline applied. This is the
    raw pool: get_new_alerts() below layers dedup + baseline on top of
    exactly this to decide what's toast-worthy, and pages_sports.py
    calls this directly for its own persistent, browsable feed (same
    split as news.fetch_headlines() vs news.get_new_alerts())."""
    items = []
    for league in _LEAGUES:
        for item in _fetch_team_news_raw(league["news_query"]):
            items.append(
                {
                    **item,
                    "sport": league["sport"],
                    "team_label": league["label"],
                    "team_logo": league["logo"],
                    "flash_color": league["flash_color"],
                }
            )
    return items


def get_new_alerts() -> list[dict]:
    """New scoring plays since the last check, across whichever of the
    Jays/Habs games is actually live right now — {"kind": "sports",
    "sport", "team_label", "team_logo", "opponent_logo", "team_score",
    "opp_score", "description", "flash_color"} — plus new Jays/Habs team
    news headlines (same dict shape, "type": "news", no opponent_logo/
    scores). Baseline established per game_id on its first sighting
    (same reasoning as news.get_new_alerts): a game only just going
    live, or the dashboard opening mid-game, shouldn't replay every
    scoring play that already happened as if it just did — team news
    gets its own equivalent baseline below, for the same reason. Call at
    most once per rerun — like news.get_new_alerts, marking a play/
    headline "seen" is a side effect."""
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
                        "type": "score",
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

    # Team news: same seen-hash/baseline pattern as news.get_new_alerts,
    # kept in its own session-state keys so a headline's "seen" status
    # here is independent of the general News page's own tracking (a
    # Jays trade story could easily qualify for both feeds).
    seen_news = st.session_state.setdefault("seen_team_news", {})
    news_baseline_done = st.session_state.get("team_news_baseline_done", False)
    news_alerts = []
    for item in team_news_headlines():
        h = hashlib.sha1(item["headline"].encode()).hexdigest()
        if h in seen_news:
            continue
        seen_news[h] = True
        if len(seen_news) > MAX_SEEN_TEAM_NEWS:
            seen_news.pop(next(iter(seen_news)))
        if not news_baseline_done:
            continue
        news_alerts.append(
            {
                "kind": "sports",
                "type": "news",
                "sport": item["sport"],
                "team_label": item["team_label"],
                "team_logo": item["team_logo"],
                "description": item["headline"],
                "flash_color": item["flash_color"],
                "published": item["published"],
            }
        )
    st.session_state["team_news_baseline_done"] = True
    # Same reasoning as news.get_new_alerts: a batch spanning both teams
    # (or a feed recovering from an outage) should queue in real
    # publish-time order, not fixed _LEAGUES iteration order.
    news_alerts.sort(key=lambda a: a["published"] or datetime.min.replace(tzinfo=timezone.utc))
    alerts.extend(news_alerts)

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
    score, plus either the play that just happened (a live scoring
    update), the final result (session request: "make an end of game
    alert"), or a general team news headline (session request: "add
    blue jays/habs news headlines... with the same rules as game
    updates" — same color bar and single team logo, no opponent/score
    since a trade or injury story doesn't have either), instead of a
    plain text headline."""
    bar_class = "sports-alert-bar-mlb" if alert["sport"] == "mlb" else "sports-alert-bar-nhl"
    delay = f"animation-delay: -{elapsed:.2f}s;"
    description = html.escape(alert["description"])
    if alert.get("type") == "news":
        label_text = f"{alert['team_label']} NEWS"
        st.markdown(
            f'<div class="{bar_class}">'
            f'<span class="news-breaking-label toast-label-anim-{variant}" style="{delay}">{label_text}</span>'
            f'<span class="sports-alert-score toast-headline-anim-{variant}" style="{delay}">'
            f'<img src="{alert["team_logo"]}" /></span>'
            f'<span class="news-alert-headline toast-headline-anim-{variant}" style="{delay}">{description}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        return
    label_text = f"{alert['team_label']} {'FINAL' if alert.get('type') == 'final' else 'UPDATE'}"
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
