"""Baseball Savant's Statcast percentile-rankings leaderboard — session
request: "instead of the last fifteen OPS... I want you to replace it
with the average of every single one of their percentiles. This gives
us a holistic view of how good that player is, not only just batting,
but on the field as well" (arm strength, sprint speed, and outs-above-
average are fielding/running metrics, not batting ones, which is the
whole point of averaging ALL of them rather than hand-picking a hitting
stat). Genuinely different shape from sports_client.py's own MLB Stats
API calls (a league-wide season leaderboard, not a single game/player
lookup), same reasoning ufc_client.py's own docstring gives for being
its own module rather than squeezed into sports_client.py.

No official API (confirmed: baseballsavant.mlb.com has no documented
public endpoint), but the same page that renders the percentile-rank
bar chart on a player's own Savant page has a working CSV export button
behind it — confirmed live: `/leaderboard/percentile-rankings?type=
batter&year=2026&team=&csv=true` returns a real CSV, one row per
player, every column ALREADY expressed as a 0-100 percentile with
Savant's own "goodness" orientation baked in (100 = best for that
player in that metric, 0 = worst) rather than a raw stat value — e.g.
a pitcher's strikeout-rate-allowed percentile and his walk-rate-allowed
percentile are both already flipped so that 100 means "good for a
pitcher" in both, not "high strikeout number" vs "high walk number"
inconsistently. That's exactly why a plain unweighted average across
every column is meaningful here (matches the session request's "don't
alter the number at all" — no re-flipping or re-weighting needed,
Savant already did that work).
"""

import csv
import io
from datetime import datetime

import requests
import streamlit as st

import fetch_throttle

PERCENTILE_URL = "https://baseballsavant.mlb.com/leaderboard/percentile-rankings"
# Season leaderboard, not live game data — moves once/day at most as
# games go final and stats get processed, nothing like the 5-10s cadence
# the live matchup card's other fetches need. A long TTL keeps this to
# one real request per several hours regardless of how often the
# jumbotron itself reruns.
CACHE_TTL_SECONDS = 6 * 60 * 60

# Columns present on every row that aren't themselves a percentile
# metric — excluded from the average, everything else in the row is
# included, whatever Savant happens to have added or removed lately
# (see this module's own docstring on why "every single one" is taken
# literally rather than a hand-picked subset).
_NON_METRIC_COLUMNS = {"player_name", "player_id", "year"}

_last_good_table: dict[str, dict[int, dict]] = {}


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_percentile_table_raw(player_type: str, year: int) -> dict[int, dict]:
    fetch_throttle.wait_turn()
    resp = requests.get(
        PERCENTILE_URL,
        params={"type": player_type, "year": year, "team": "", "csv": "true"},
        timeout=15,
    )
    resp.raise_for_status()
    # Savant's CSV export leads with a UTF-8 BOM — resp.text leaves it
    # as a literal ﻿ glued onto the first header ("player_name"
    # comes back as '﻿"player_name"'), which silently breaks
    # nothing structurally (every column still lines up positionally)
    # but makes the player_name key unreachable by its expected name.
    # decode("utf-8-sig") strips it; confirmed live this is the only
    # header affected (every other column parses clean either way).
    reader = csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig")))
    return {int(row["player_id"]): row for row in reader if row.get("player_id")}


def _percentile_table(player_type: str) -> dict[int, dict]:
    year = datetime.now().year
    try:
        table = _fetch_percentile_table_raw(player_type, year)
    except Exception:
        return _last_good_table.get(player_type, {})
    _last_good_table[player_type] = table
    return table


def batter_overall_percentile(player_id: int) -> int | None:
    """Straight (unweighted) average of every percentile column Savant
    has for this batter this season, rounded to a whole number — "kinda
    like an overall in NHL 25 or MLB The Show." None if the batter has
    no row yet (e.g. a just-called-up rookie Savant hasn't processed a
    leaderboard entry for) or every column on his row is blank."""
    row = _percentile_table("batter").get(player_id)
    if not row:
        return None
    values = []
    for key, value in row.items():
        if key in _NON_METRIC_COLUMNS:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return round(sum(values) / len(values)) if values else None
