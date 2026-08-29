"""Jumbotron pregame warm-up show — session request: "make it almost
like a show, like a pregame show," inspired by a real NHL broadcast
pregame the user attended (Habs @ Senators) where a recalled call-up
making his NHL debut (Jacob Fowler) was flagged as a player to watch,
and it made the game memorable. Replaces the pregame board's old plain
"AI Preview" blurb (game_blurb.get_pregame_blurb) and "Top Performers"
single-stat card (scores_client.leaders_with_headshots via pages_
jumbotron._top_performers_html) with a rotating set of up to 15 real
storyline cards — a player's photo, team, a real stat line, and a
short AI-written storyline underneath, plus team-level stat cards
(e.g. "the Habs have scored the most in the NHL over their last 10
games").

Same one-shot-per-game_id architecture as game_blurb.py (written once,
remembered across reruns/browser sessions/process restarts via
persisted_state — see that module's own docstring for why surviving a
restart matters), but routed to openai/gpt-oss-120b on its own
dedicated Groq account instead of Gemini — the user's own explicit
choice for this feature specifically, since that account (the same
one pages_conflicts.py's _ai_overview already uses) is lightly used
and this feature never needs to touch the main Groq budget the rest
of the app depends on. Structured JSON-array output, same parse-
robustness shape pages_conflicts.py's own multi-item AI response
already uses (strip code fences, skip malformed individual entries
rather than failing the whole batch).

Data sources: espn_extras.py (transactions, team news, league-wide
leaders, and — session follow-up, a Lead UI/UX Designer + Sports
Broadcast Producer brief adding "Hot Streaks, Cold Streaks, Career-
High/Career-Best Years, Fall-Off Seasons" — real per-game logs and
season-by-season career history, confirmed live against real players
in all 3 sports while planning this, none used anywhere else in this
app before now) plus scores_client.fetch_summary/leaders_with_headshots
(already used by game_blurb.py — injuries, game-day roster/boxscore,
records, venue/odds, and this specific game's own stat leaders with
real headshots).

Card shape (see _prompt/_parse): {"type", "name", "tag" (a short
punchy category like "HOT HAND"/"CAREER HIGH"/"THE CALL-UP" — see
_tag_category's own docstring for how this maps to a real color),
"headline" (one bold statement), "stat_line" (one real high-impact
metric as a phrase, not a number), "storyline", "photo"}. The Angle
Priority Matrix (recent action > streaks/volatility > career/macro
trends) and a "selective framing" rule are both baked into the prompt
itself — a streak or career-trajectory angle is never forced onto a
card just because the data exists for that player.

Every card's photo is either a REAL ESPN headshot (matched back to the
same structured data fed to the prompt — leaders_with_headshots/
injuries both carry real athlete headshots) or, when a storyline came
from a source with no attached photo (a transaction or a news
headline — ESPN's own transactions feed is plain prose, no athlete id
to look up a headshot from), the team's own logo instead — never an
invented or broken image, matching this app's "never fake what isn't
real" rule everywhere else."""

import json
import re

import espn_extras
import groq_client
import persisted_state
import scores_client
import sports_client

MAX_CARDS = 15
# Session follow-up: "deeper statistical context — Hot Streaks, Cold
# Streaks, Career-High/Career-Best Years, and Fall-Off/Regressive
# Seasons." Bounds how many players get the extra 2 real ESPN calls
# each (gamelog + career stats) — game_leaders is typically 6-8 real
# entries already (this specific game's own real stat leaders), a
# reasonable, real-data-driven cap rather than an arbitrary one.
MAX_TREND_LOOKUPS = 8
# Same shared "chatgpt" Groq account/budget pages_conflicts.py's own
# gpt-oss-120b call already runs on — identical constants, not
# independently re-tuned, since both features draw from the same real
# per-minute ceiling.
GPT_OSS_TPM_LIMIT = 8_000
GPT_OSS_SAFETY_MARGIN = 700
GPT_OSS_MIN_OUTPUT_TOKENS = 1_500

MAX_CACHED_GAMES = 200  # same bounded-eviction shape game_blurb.py's own cache uses

# sport_key ("mlb"/"nhl"/"nfl", pages_jumbotron.py's own convention) ->
# (ESPN sport slug, ESPN league slug, our ESPN team id, a league-wide
# leader category confirmed live to actually return data for that
# sport — see espn_extras.fetch_league_leaders's own docstring on why
# this can't be hardcoded to one category across all 3 sports).
_SPORT_META = {
    "mlb": {"sport": "baseball", "league": "mlb", "team_id": sports_client.MLB_ESPN_TEAM_ID, "leader_cat": "homeRuns"},
    "nhl": {"sport": "hockey", "league": "nhl", "team_id": sports_client.NHL_ESPN_TEAM_ID, "leader_cat": "points"},
    "nfl": {"sport": "football", "league": "nfl", "team_id": sports_client.NFL_TEAM_ID, "leader_cat": "passingYards"},
}


def _load_cache() -> dict[str, list[dict]]:
    raw = persisted_state.load("pregame_storylines_cache", {})
    return raw if isinstance(raw, dict) else {}


_cache: dict[str, list[dict]] = _load_cache()


def _remember(key: str, cards: list[dict]) -> None:
    _cache[key] = cards
    if len(_cache) > MAX_CACHED_GAMES:
        _cache.pop(next(iter(_cache)))
    persisted_state.save("pregame_storylines_cache", _cache)


# ESPN's own headshot CDN path is /players/full/{id}.{ext} across
# every sport confirmed this session (MLB/NHL/NFL) — real athlete ids
# were never exposed by scores_client.leaders_with_headshots/fetch_
# summary's own injuries shape, but they're sitting right there in
# every headshot URL those already return, so pulling the id back out
# is simpler than threading a new field through 2 other modules for
# a value they already effectively carry.
_HEADSHOT_ID_RE = re.compile(r"/players/full/(\d+)\.")


def _athlete_id_from_headshot(url: str | None) -> str | None:
    if not url:
        return None
    m = _HEADSHOT_ID_RE.search(url)
    return m.group(1) if m else None


def _clean_leader_name(who: str) -> str:
    """scores_client.leaders_with_headshots's own "who" field is
    "{name} · {team abbr}" (see that function's own f-string) — real
    bug, caught live: _photo_lookup used to key its dict off this
    exact string including the " · SEA" suffix, but the AI's own
    "name" output (correctly just the player's name, per the prompt's
    own instruction) never had that suffix, so every single game-
    leader-sourced card silently missed its real photo despite one
    being available. Stripped once here and reused everywhere this
    module reads a leader's name, so the material block, the trend
    lookups, and the photo dict all agree on the same clean string."""
    return who.split(" · ")[0].strip() if who else who


def _gather_trends(sport_key: str, game_leaders: list[dict]) -> list[dict]:
    """Real recent-form (last 10 games) and career-pace (this season
    vs. this player's own past seasons) context for tonight's actual
    matchup leaders specifically — see espn_extras.recent_game_trend/
    career_trajectory's own docstrings for exactly how each is
    computed and why. Scoped to game_leaders (real players IN tonight's
    game) rather than league_leaders (real players who mostly aren't)
    — a hot/cold streak or career-year storyline only means something
    tied to a player who's actually playing tonight. [] whenever
    nothing here has an id to look up (see _athlete_id_from_headshot's
    own comment) or neither function found anything real to report —
    most players, most nights, correctly produce nothing."""
    out = []
    for leader in game_leaders[:MAX_TREND_LOOKUPS]:
        aid = _athlete_id_from_headshot(leader.get("hshot"))
        if not aid:
            continue
        meta = _SPORT_META[sport_key]
        try:
            recent = espn_extras.recent_game_trend(meta["sport"], meta["league"], aid)
            trajectory = espn_extras.career_trajectory(meta["sport"], meta["league"], aid)
        except Exception:
            continue
        if recent or trajectory:
            out.append({"name": _clean_leader_name(leader.get("who")), "recent": recent, "trajectory": trajectory})
    return out


def _gather_material(sport_key: str, match: dict | None) -> dict:
    """Every real fact this feature draws from, gathered once per call
    — transactions/news/league-leaders from espn_extras (this module's
    own new data), plus whatever match/fetch_summary already has
    (injuries, this game's own leaders w/ headshots, records, venue,
    odds — the exact same source game_blurb.py's blurb already reads),
    plus (session follow-up) real recent-form/career-pace trends for
    tonight's own matchup leaders (see _gather_trends's own docstring).
    {} fields throughout rather than raising — a thin payload on a
    quiet day just means fewer real cards, never a crash (same
    graceful-degradation rule every other AI-context builder in this
    app already follows)."""
    meta = _SPORT_META[sport_key]
    summary = scores_client.fetch_summary(match) if match else {}
    game_leaders = scores_client.leaders_with_headshots(match) if match else []
    return {
        "transactions": espn_extras.fetch_transactions(meta["sport"], meta["league"], meta["team_id"]),
        "news": espn_extras.fetch_team_news(meta["sport"], meta["league"], meta["team_id"]),
        "league_leaders": espn_extras.fetch_league_leaders(meta["sport"], meta["league"], [meta["leader_cat"]]),
        "game_leaders": game_leaders,
        "injuries": summary.get("injuries") or [],
        "competition": (match or {}).get("competition") or {},
        "trends": _gather_trends(sport_key, game_leaders),
    }


def _photo_lookup(material: dict) -> dict[str, str]:
    """{lowercased real player name: real ESPN headshot URL} — built
    from every structured (not free-text) source in `material`, so a
    card the AI writes about one of these exact people can be matched
    back to a real photo rather than needing its own separate lookup.
    Transactions/news are free-text prose with no athlete id attached
    (confirmed live while researching this feature) — a card sourced
    from one of those has no entry here, and the render layer falls
    back to the team logo instead, same "never fake what isn't real"
    rule as everywhere else."""
    photos: dict[str, str] = {}
    for leader in material["game_leaders"]:
        who, hshot = leader.get("who"), leader.get("hshot")
        if who and hshot:
            # Registered under both the raw "{name} · {abbr}" string
            # (scores_client.leaders_with_headshots's own format, kept
            # in the material text below for real team-context value)
            # and the cleaned bare name — the prompt tells the AI to
            # use the name "as it appears," but a reasoning model
            # reasonably strips the " · TEAM" suffix as metadata
            # anyway (confirmed live), so this matches either way
            # rather than depending on which one it picks.
            photos[who.lower()] = hshot
            photos[_clean_leader_name(who).lower()] = hshot
    for block in material["injuries"]:
        for inj in block.get("injuries") or []:
            athlete = inj.get("athlete") or {}
            name = athlete.get("displayName") or athlete.get("shortName")
            hshot = athlete.get("headshot")
            if isinstance(hshot, dict):
                hshot = hshot.get("href")
            if name and hshot:
                photos[name.lower()] = hshot
    # League leaders (espn_extras.fetch_league_leaders) don't carry a
    # headshot at all — only name/team/stat (see that function's own
    # docstring on what it resolves). Real signal for the prompt
    # either way; a card sourced from one falls back to a team logo
    # below, same as a transaction/news-sourced one does.
    return photos


def _team_logos(competition: dict) -> dict[str, str]:
    """{lowercased team display name: real ESPN team logo URL} — the
    fallback photo for any card whose subject isn't in _photo_lookup
    (a transaction/news-sourced player, or a team-level stat card)."""
    logos = {}
    for c in competition.get("competitors") or []:
        team = c.get("team") or {}
        name = team.get("displayName")
        logo = team.get("logo")
        if name and logo:
            logos[name.lower()] = logo
    return logos


def _material_block(material: dict) -> str:
    lines = []
    if material["transactions"]:
        lines.append("Recent transactions:")
        for t in material["transactions"][:8]:
            lines.append(f"- {t['date'].strftime('%b %-d')}: {t['description']}")
    if material["news"]:
        lines.append("Recent team news headlines:")
        for n in material["news"]:
            lines.append(f"- {n['headline']}" + (f" — {n['description']}" if n["description"] else ""))
    for cat, entries in material["league_leaders"].items():
        # Explicit "NOT necessarily in tonight's game" framing — real
        # bug, caught live: without this, the AI wrote a storyline for
        # Matt Olson (Atlanta) claiming "the Mariners will lean on his
        # bat," inventing a roster spot he doesn't have just because he
        # was listed near this game's own material.
        lines.append(f"League-wide {cat} leaders right now (these players are NOT necessarily on either team playing tonight — check the team abbreviation before implying someone is in this game):")
        for e in entries:
            lines.append(f"- {e['name']} ({e['team_abbr']}): {e['display']}")
    if material["game_leaders"]:
        lines.append("Statistical leaders in tonight's specific matchup:")
        for leader in material["game_leaders"]:
            lines.append(f"- {leader['who']}: {leader['cat']} — {leader['stat']}")
    for block in material["injuries"]:
        team = (block.get("team") or {}).get("displayName")
        names = []
        for inj in (block.get("injuries") or [])[:3]:
            athlete = (inj.get("athlete") or {}).get("displayName")
            status = inj.get("status")
            if athlete:
                names.append(f"{athlete} ({status})" if status else athlete)
        if team and names:
            lines.append(f"{team} injuries: {', '.join(names)}")
    for c in material["competition"].get("competitors") or []:
        name, record = (c.get("team") or {}).get("displayName"), scores_client.team_record(c)
        if name and record:
            lines.append(f"{name} record: {record}")
    # Session follow-up: "deeper statistical context — Hot Streaks,
    # Cold Streaks, Career-High/Career-Best Years, and Fall-Off/
    # Regressive Seasons." Real, computed (not AI-invented) recent-form
    # and career-pace numbers for tonight's own matchup leaders — see
    # _gather_trends's own docstring for exactly what's real here and
    # what it's scoped to.
    if material["trends"]:
        lines.append(
            "Real computed recent-form and career-trajectory data for specific players in tonight's game "
            "(from actual game logs and season-by-season history, not estimated):"
        )
        for t in material["trends"]:
            parts = []
            if t["recent"]:
                stat_bits = ", ".join(f"{v} {k}" for k, v in t["recent"]["stats"].items())
                parts.append(f"last {t['recent']['games']} games: {stat_bits}")
            if t["trajectory"]:
                tr = t["trajectory"]
                word = "a genuine career year" if tr["direction"] == "career_year" else "a real fall-off"
                pace_word = "value" if tr["label"] in ("AVG", "OPS", "OBP", "SLG") else "pace"
                parts.append(
                    f"{tr['label']} {pace_word} {tr['current_pace']} this season ({tr['games_played']} games) vs. "
                    f"career-best {tr['career_best']} in {tr['career_best_year']} — {word}"
                )
            if parts:
                lines.append(f"- {t['name']}: " + "; ".join(parts))
    return "\n".join(lines)


def _prompt(team_label: str, away_name: str, home_name: str, opponent: str, material: dict) -> str:
    block = _material_block(material)
    return (
        f"You are a Lead Sports Broadcast Producer building a pregame warm-up show for {team_label} vs "
        f"{opponent} ({away_name} at {home_name}) — the same kind of thing a real broadcast does before "
        f"puck drop/first pitch/kickoff, a set of real storylines and players to watch, not a dry recap.\n\n"
        f"Below are real facts pulled straight from ESPN — recent roster moves, team news, league-wide "
        f"stat leaders, tonight's own matchup leaders, injuries, and (for some of tonight's own players) "
        f"real computed recent-form and career-trajectory numbers. Use ONLY what's actually listed — never "
        f"invent a transaction, stat, streak, career comparison, injury, or storyline that isn't in this "
        f"material. IMPORTANT: the league-wide leaders section lists players from around the whole league "
        f"for context/comparison — most of them are NOT on {away_name} or {home_name} and are not playing "
        f"tonight. Check each player's own team abbreviation before writing about them; never say or imply "
        f"someone is playing in, affecting, or facing off in tonight's game unless their team abbreviation "
        f"actually matches {away_name} or {home_name}.\n\n"
        f"{block}\n\n"
        f"ANGLE PRIORITY — when material supports more than one true angle for the same player, prefer in "
        f"this order: (1) high-impact/recent action — a recall, a debut, a major reinstatement, a late "
        f"lineup change; (2) performance volatility — a real hot streak (5+ games of real production) or a "
        f"pronounced slump; (3) macro milestones — a real career-high pace or a real fall-off against this "
        f"player's own career benchmarks. SELECTIVE FRAMING — do NOT force a streak or career-trajectory "
        f"angle onto every card just because the data exists for that player; only use it when it's "
        f"genuinely the most compelling real angle for tonight. A card doesn't need a streak/trajectory "
        f"angle at all if a call-up, trade, or injury-return story is the stronger real one.\n\n"
        f"Produce up to {MAX_CARDS} cards, fewer if the material above doesn't genuinely support more — "
        f"never pad with generic filler to hit the number. Each card is EITHER about one specific player "
        f"(a real name from the material above) OR one team-level stat (our team or {opponent}). This is a "
        f"full-screen broadcast graphic, one card on screen at a time — give it real stadium-grade weight, "
        f"like a professional pregame show lower-third, not a caption. For each card give:\n"
        f'- "type": "player" or "team"\n'
        f'- "name": the exact real name (player\'s real name, or the team\'s real display name) as it '
        f"appears in the material above — this is used to look up a real photo, so it must match exactly\n"
        f'- "tag": 2-3 words MAX, high-energy uppercase, the category of storyline this is — e.g. '
        f'"HOT HAND", "COLD STREAK", "BOUNCE-BACK WATCH", "CAREER HIGH", "FALL-OFF WATCH", "THE CALL-UP", '
        f'"TRADE ACQUISITION", "BACK FROM INJURY", "MATCHUP LEADER". Pick whichever real category actually '
        f"fits this card's material — don't force one of these examples if a better 2-3 word tag fits the "
        f"real story better.\n"
        f'- "headline": one bold, punchy statement, 4-7 words, real broadcast-graphic energy (not a full '
        f'sentence, no ending period) — e.g. "Locked In At The Plate", "Making His NHL Debut Tonight"\n'
        f'- "stat_line": ONE real high-impact metric, as a short punchy phrase, not a bare number — e.g. '
        f'"8 HRs In Last 12 Games", "Pacing For 35 HR (Career Best)", "0-For-14 At The Plate", "Recalled '
        f'From Buffalo (AAA)". Pull this from the real material above; never invent a figure that isn\'t '
        f"there. If there's genuinely no single number worth leading with (e.g. a pure call-up/trade story "
        f'with no stat line yet), a short real status phrase is fine instead (e.g. "First MLB Call-Up").\n'
        f'- "storyline": EXACTLY 1 or 2 sentences, punchy and analytical, connecting this player/team\'s '
        f"real current form or trajectory directly to tonight's matchup — not a generic bio.\n\n"
        f'Respond with ONLY a JSON array, no markdown fences, no other text, in exactly this shape:\n'
        f'[{{"type": "player", "name": "CJ Van Eyk", "tag": "THE CALL-UP", '
        f'"headline": "Fresh Arm Joins The Bullpen", "stat_line": "Recalled From Buffalo (AAA)", '
        f'"storyline": "..."}}]'
    )


# Session follow-up's own tag examples ("HOT HAND" vs "BOUNCE-BACK
# WATCH") each imply a real color meaning — kept as a keyword
# classifier over whatever free-text tag the AI actually wrote, rather
# than a separate enum field the AI would have to keep in sync with
# its own "tag" text (one field to get right, not two that could
# disagree). Order matters: checked top to bottom, first match wins.
_TAG_CATEGORY_KEYWORDS = [
    # "cold" checked BEFORE "hot" — real bug, caught live: "COLD
    # STREAK" contains the substring "STREAK", one of hot's own
    # keywords, so checking hot first miscategorized a real cold-
    # streak tag with the hot (wrong) color. "HOT"-family tags never
    # contain "COLD", so this order has no equivalent reverse collision.
    ("cold", ("COLD", "SLUMP", "BOUNCE", "REGRESS", "FALL-OFF", "FALL OFF", "COOL")),
    ("hot", ("HOT", "STREAK", "SURGE", "ROLL")),
    ("career", ("CAREER", "MILESTONE", "BEST", "RECORD")),
    ("callup", ("CALL-UP", "CALLUP", "DEBUT", "RECALL", "TRADE", "ACQUISITION", "SIGNING")),
    ("injury", ("INJURY", "IL", "RETURN", "REINSTATED", "ACTIVATED")),
]


def _tag_category(tag: str) -> str:
    """Which of a small set of real color categories this tag belongs
    to, by keyword — "hot"/"cold"/"career"/"callup"/"injury"/"default".
    Pure presentation grouping (see theme.py's own .jumbo-storyline-tag-*
    classes) — never changes what's actually shown, only its color."""
    upper = tag.upper()
    for category, keywords in _TAG_CATEGORY_KEYWORDS:
        if any(kw in upper for kw in keywords):
            return category
    return "default"


def _parse(raw_text: str, photos: dict[str, str], logos: dict[str, str]) -> list[dict] | None:
    raw = raw_text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, list):
        return None

    cards = []
    for item in parsed[:MAX_CARDS]:
        try:
            card_type = str(item["type"]).lower()
            name = str(item["name"]).strip()
            storyline = str(item["storyline"]).strip()
        except (KeyError, TypeError):
            continue
        if card_type not in ("player", "team") or not name or not storyline:
            continue
        tag = str(item.get("tag") or "").strip().upper()
        headline = str(item.get("headline") or "").strip()
        stat_line = str(item.get("stat_line") or "").strip()
        # Real headshot if this exact name matched a structured source
        # (leaders_with_headshots/injuries), or a real team logo if the
        # name itself IS one of today's two teams (a team-level card,
        # or — rarely — a player card the AI named after its own team
        # rather than a person). Deliberately NOT a blanket "our own
        # logo" fallback for anything still unmatched (e.g. a league-
        # wide leader who plays for neither of today's 2 teams,
        # confirmed live: Kyle Schwarber plays for Philadelphia, not
        # either team in a Jays/Mariners game) — showing a real photo
        # for the WRONG team is actively misleading, worse than no
        # photo at all. None here means the render layer falls back to
        # a neutral placeholder, not a specific-but-wrong team.
        photo = photos.get(name.lower()) or logos.get(name.lower())
        cards.append(
            {
                "type": card_type,
                "name": name,
                "tag": tag,
                "tag_category": _tag_category(tag) if tag else "default",
                "headline": headline,
                "stat_line": stat_line,
                "storyline": storyline,
                "photo": photo,
            }
        )
    return cards or None


def get_storyline_cards(
    sport_key: str,
    game_id,
    team_label: str,
    away_name: str,
    home_name: str,
    opponent: str,
    match: dict | None,
) -> list[dict] | None:
    """Generated exactly once per game_id, then remembered across
    reruns/browser sessions/process restarts (same persisted_state-
    backed shape as game_blurb.py — see this module's own docstring
    for why that matters). None whenever there's nothing real to work
    with (no ESPN match found and no fallback material at all) or the
    AI call itself fails — the caller falls back to nothing shown,
    same as every other optional jumbotron panel.

    `away_name`/`home_name` are real full ESPN display names (e.g.
    "Toronto Blue Jays") — a team-level card's own logo lookup matches
    directly against `material["competition"]`'s own 2 competitors, so
    no separate "our team" name is needed here."""
    key = f"{sport_key}_{game_id}"
    if key in _cache:
        return _cache[key]
    material = _gather_material(sport_key, match)
    if not any([material["transactions"], material["news"], material["league_leaders"], material["game_leaders"], material["injuries"]]):
        return None
    prompt = _prompt(team_label, away_name, home_name, opponent, material)
    estimated_input_tokens = len(prompt) // 4
    max_output_tokens = max(GPT_OSS_MIN_OUTPUT_TOKENS, GPT_OSS_TPM_LIMIT - GPT_OSS_SAFETY_MARGIN - estimated_input_tokens)
    text = groq_client.generate(
        prompt, temperature=0.6, max_output_tokens=max_output_tokens, model=groq_client.GPT_OSS_MODEL, reasoning_effort="medium"
    )
    if text is None:
        return None
    photos = _photo_lookup(material)
    logos = _team_logos(material["competition"])
    cards = _parse(text, photos, logos)
    if cards is not None:
        _remember(key, cards)
    return cards
