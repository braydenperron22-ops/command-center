"""Structured transaction feed for Brayden's own three tracked teams
(Blue Jays/Canadiens/Saints — the same trio ticker.py's playoff-odds
item and morning_briefing._TRACKED_TEAM_FETCHERS already use) — trades,
signings, extensions, releases, and roster moves, filtered out of
ESPN's own transaction log, which is dominated day to day by routine
in-season roster mechanics: rehab assignments, injured-list shuffling,
minor-league option/recall churn, waiver-claim paperwork.

Session request: "Add a unified structured transaction feed for MLB,
NHL, NFL. Focus on actual transactions rather than news articles...
Do not turn this into a news feed." Follow-up: "filter out the noise
from the transaction API." Then, after a first pass came back too
narrow (a hard 3+ year contract-length bar meant even a real, notable
one-year "prove it" deal for an established NHL player got excluded
right alongside an anonymous AHL depth signing — no way to tell them
apart from ESPN's own text alone): "change it up. just make it for my
teams and make the restrictions looser." Scoping to 3 specific teams
instead of all 30-32 per league is what actually solves the original
volume problem — a hard numeric threshold was never really needed once
the feed isn't league-wide anymore, and it was already provably wrong
on real examples (Kirby Dach's real 2026 one-year Canadiens deal). The
remaining denylist below only excludes what's genuinely NOT roster-
composition news even for a single tracked team: in-season minor-
league shuffling and injury-list mechanics, not real player movement.

Real data source: site.api.espn.com's own transactions endpoint — the
same free public API family already powering sports_client.py's
scores/standings, confirmed live for all three leagues. No server-side
team filter exists on this endpoint (checked live — a `team=` query
param silently does nothing), so this fetches a deep enough page
(200) to reliably contain each tracked team's own recent entries and
filters client-side by team.displayName.

No dollar figures or contract-value detail exist anywhere in this
feed (checked against ~100 real live entries across all three leagues
before building this) — unlike the session's own example mockup
("$X / X years"). Rather than guess or invent a number, this only
ever shows what the description actually states and leaves dollar
amounts out entirely — same "never invent a fact" rule every other
data source in this app already follows."""

from datetime import datetime

import requests
import streamlit as st

import fetch_throttle
import persisted_state
import sports_client

_LEAGUE_URLS = {
    "mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/transactions",
    "nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/transactions",
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/transactions",
}
LEAGUE_EMOJI = {"mlb": "⚾", "nhl": "🏒", "nfl": "🏈"}
# Reuses the exact same tracked-team names morning_briefing.py's own
# _TRACKED_TEAM_FETCHERS and ticker.py's playoff-odds item already use
# — this app never needs to re-decide which teams "the" teams are.
_TRACKED_TEAMS = {
    "mlb": sports_client.MLB_TEAM_NAME,
    "nhl": sports_client.NHL_TEAM_NAME,
    "nfl": sports_client.NFL_TEAM_NAME,
}
FETCH_DEPTH = 200  # deep enough that a single tracked team's own transactions reliably appear (confirmed live: 6-11 real hits per team at this depth)
CACHE_TTL_SECONDS = 15 * 60

# Any of these anywhere in a description means in-season roster
# mechanics, not real roster-composition news — checked against the
# WHOLE description, so a multi-clause entry like "Recalled X.
# Optioned Y." is excluded even though a clause in isolation might
# sound eventful. Deliberately narrow now that this is scoped to 3
# teams instead of an entire league: a waiver claim, a two-way deal,
# an overseas loan, or a player getting waived are all real answers to
# "did anything happen with my team" and stay in; only genuinely
# mechanical in-season shuffling (which minor-league affiliate/roster
# status a player has RIGHT NOW, injury-list paperwork, or the "future
# considerations" RFA-compensation filing that ESPN reports as if it
# were a real trade from both teams' sides at once) is excluded.
_NOISE_PHRASES = [
    "rehab assignment",
    "-day il", "injured list", "injured reserve",
    "outright to",
    "for assignment",
    "minor league contract", "minor-league contract",
    "recalled ", "optioned ", "selected the contract",
    "future considerations",
]

# The denylist alone isn't enough — a description with none of the
# noise phrases above AND none of these shouldn't default to
# "interesting" just by surviving the denylist (a front-office hire,
# say, or something with entirely unfamiliar phrasing).
_SIGNAL_PHRASES = [
    "traded", "acquired", "signed", "agreed to terms", "contract extension",
    "released", "waived", "claimed", "loaned", "activated", "reinstated",
]


def _is_significant(description: str) -> bool:
    text = description.lower()
    if any(phrase in text for phrase in _NOISE_PHRASES):
        return False
    return any(phrase in text for phrase in _SIGNAL_PHRASES)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_raw(league: str) -> list[dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(
        _LEAGUE_URLS[league], params={"limit": FETCH_DEPTH}, timeout=10, headers={"User-Agent": "Mozilla/5.0"}
    )
    resp.raise_for_status()
    return resp.json().get("transactions", [])


_last_good: dict[str, list[dict]] = {}


def _fetch_league(league: str) -> list[dict]:
    try:
        raw = _fetch_raw(league)
    except Exception:
        return _last_good.get(league, [])
    _last_good[league] = raw
    return raw


def significant_transactions(league: str, limit: int = 10) -> list[dict]:
    """[{"id", "date", "description", "team"}] for Brayden's own
    tracked team in this league only — real roster moves, newest first
    (ESPN's own order), capped at `limit`. "id" is a synthetic dedup
    key (date+description — ESPN gives no stable transaction id of its
    own), stable enough since an exact repeat would mean the same real
    event, not a coincidence."""
    tracked_team = _TRACKED_TEAMS[league]
    raw = _fetch_league(league)
    out = []
    for t in raw:
        team = t.get("team") or {}
        if team.get("displayName") != tracked_team:
            continue
        desc = t.get("description") or ""
        if not _is_significant(desc):
            continue
        out.append({"id": f"{league}:{t.get('date')}:{desc}", "date": t.get("date"), "description": desc})
        if len(out) >= limit:
            break
    return out


# Session request: "filter out the noise" (see above) covers WHICH
# transactions count; this part covers WHEN one becomes a toast — a
# real backlog-suppression problem (unlike financial_plumbing_client's
# "is the system stressed right now," a trade that happened days ago
# showing up for the first time on a kiosk restart is genuinely old
# news, not a fresh alert) — same baseline-gate shape road_conditions_
# 511.get_new_alerts uses, and the same bug class that one caught
# fixed from the start here: the gate runs before anything else, per
# league, unconditionally, so it always completes on the first real
# check regardless of how many (or how few) significant transactions
# exist at that moment.
_SEEN_KEY = "league_transactions_seen"
_BASELINE_KEY = "league_transactions_baseline_done"
_seen: dict = dict(persisted_state.load_per_instance(_SEEN_KEY, {}))
_baseline_done: dict = dict(persisted_state.load_per_instance(_BASELINE_KEY, {}))
MAX_SEEN = 300


def get_new_alerts(now: datetime) -> list[dict]:
    global _seen, _baseline_done
    alerts = []
    seen_changed = False
    baseline_changed = False
    for league in _LEAGUE_URLS:
        try:
            transactions = significant_transactions(league, limit=15)
        except Exception:
            continue
        if not _baseline_done.get(league):
            for t in transactions:
                _seen[t["id"]] = True
            _baseline_done[league] = True
            baseline_changed = True
            continue
        for t in transactions:
            if t["id"] in _seen:
                continue
            _seen[t["id"]] = True
            seen_changed = True
            if len(_seen) > MAX_SEEN:
                _seen.pop(next(iter(_seen)))
            alerts.append(
                {
                    "kind": "weather",
                    "severity": "statement",
                    "label": f"{LEAGUE_EMOJI[league]} {_TRACKED_TEAMS[league]}",
                    "headline": t["description"],
                }
            )
    if baseline_changed:
        persisted_state.save_per_instance(_BASELINE_KEY, _baseline_done)
    if seen_changed:
        persisted_state.save_per_instance(_SEEN_KEY, _seen)
    return alerts
