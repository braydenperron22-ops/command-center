"""Baseball Savant's Statcast percentile-rankings leaderboard, feeding
the jumbotron matchup card's "OVERALL" stat.

Started from a session request: "instead of the last fifteen OPS...
replace it with the average of every single one of their percentiles"
— a straight average across every column Savant has (arm strength,
sprint speed, bat speed, fastball spin, all of it, batting and
pitching alike). A follow-up question reconsidered that: "does this
truly bring up the full story?" The problem: that average mixed real
*value* (xwOBA, barrel%, xERA — outcomes) with raw *tools* (exit
velocity, bat speed, arm strength, fastball spin — physical
measurements with no run value of their own). A pitcher sitting 99mph
with nasty spin but getting hit hard would score well on tools despite
performing badly — a scouting grade bleeding into what was supposed to
be a performance grade.

The fix, per that follow-up ("build your own score based on only the
metrics you think matter"): _VALUE_METRIC_COLUMNS below restricts the
average to columns that are genuinely value/outcome-denominated —
expected-outcome stats (xwOBA/xBA/xSLG/xISO/xOBP), contact-quality
rates (barrel%, hard-hit%), plate-discipline rates (K%/BB%/whiff%/
chase%), OAA for batters (a real defensive run-value stat, unlike
sprint speed or arm strength which are just measurements), and xERA for
pitchers. Dropped: raw exit velocity/max EV (physical readings, mostly
redundant with barrel%/hard-hit% already covering "quality of
contact"), arm strength, sprint speed, bat speed, squared-up rate,
swing length, fastball velo/spin, curve spin (tools, not value), and
the raw `brl` count (correlates with playing time, not skill — brl_
percent is the rate version and is kept).

Genuinely different shape from sports_client.py's own MLB Stats API
calls (a league-wide season leaderboard, not a single game/player
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
the kept columns is meaningful here — no re-flipping or re-weighting
needed, Savant already did that work; this module only narrows which
columns get averaged.
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

# Value/outcome-denominated columns only — see this module's own
# docstring for why raw tool/mechanic readings (exit velocity, arm
# strength, sprint speed, bat speed, fastball/curve spin, the raw brl
# count) are deliberately left out even though Savant's own CSV carries
# them. Column sets differ per type (a pitcher's table has xERA/
# fastball-stuff columns instead of a batter's sprint speed/OAA/bat
# speed), so each gets its own explicit list rather than one shared set.
_VALUE_METRIC_COLUMNS = {
    "batter": {
        "xwoba", "xba", "xslg", "xiso", "xobp",
        "brl_percent", "hard_hit_percent",
        "k_percent", "bb_percent", "whiff_percent", "chase_percent",
        "oaa",
    },
    "pitcher": {
        "xwoba", "xba", "xslg", "xiso", "xobp",
        "brl_percent", "hard_hit_percent",
        "k_percent", "bb_percent", "whiff_percent", "chase_percent",
        "xera",
    },
}

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


def _overall_percentile(player_type: str, player_id: int) -> int | None:
    row = _percentile_table(player_type).get(player_id)
    if not row:
        return None
    keep = _VALUE_METRIC_COLUMNS[player_type]
    values = []
    for key, value in row.items():
        if key not in keep:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return round(sum(values) / len(values)) if values else None


def batter_overall_percentile(player_id: int) -> int | None:
    """Straight (unweighted) average of this batter's value/outcome
    percentile columns only (see _VALUE_METRIC_COLUMNS) — xwOBA-family,
    barrel%, hard-hit%, plate discipline, and OAA — rounded to a whole
    number, "kinda like an overall in NHL 25 or MLB The Show." None if
    the batter has no row yet (e.g. a just-called-up rookie Savant
    hasn't processed a leaderboard entry for) or none of the kept
    columns are populated."""
    return _overall_percentile("batter", player_id)


def pitcher_overall_percentile(player_id: int) -> int | None:
    """Same idea as batter_overall_percentile, off the separate pitcher
    percentile-rankings table's own value columns (xwOBA-family against,
    barrel%/hard-hit% allowed, plate discipline, xERA) — deliberately
    not fastball velo/spin/curve spin, which are stuff/tool readings,
    not performance value (see this module's own docstring)."""
    return _overall_percentile("pitcher", player_id)
