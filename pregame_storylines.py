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
leaders — all 3 confirmed live against real Jays/Habs/Saints data
while planning this, none used anywhere else in this app before now)
plus scores_client.fetch_summary/leaders_with_headshots (already used
by game_blurb.py — injuries, game-day roster/boxscore, records,
venue/odds, and this specific game's own stat leaders with real
headshots).

Every card's photo is either a REAL ESPN headshot (matched back to the
same structured data fed to the prompt — leaders_with_headshots/
injuries both carry real athlete headshots) or, when a storyline came
from a source with no attached photo (a transaction or a news
headline — ESPN's own transactions feed is plain prose, no athlete id
to look up a headshot from), the team's own logo instead — never an
invented or broken image, matching this app's "never fake what isn't
real" rule everywhere else."""

import json

import espn_extras
import groq_client
import persisted_state
import scores_client
import sports_client

MAX_CARDS = 15
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


def _gather_material(sport_key: str, match: dict | None) -> dict:
    """Every real fact this feature draws from, gathered once per call
    — transactions/news/league-leaders from espn_extras (this module's
    own new data), plus whatever match/fetch_summary already has
    (injuries, this game's own leaders w/ headshots, records, venue,
    odds — the exact same source game_blurb.py's blurb already reads).
    {} fields throughout rather than raising — a thin payload on a
    quiet day just means fewer real cards, never a crash (same
    graceful-degradation rule every other AI-context builder in this
    app already follows)."""
    meta = _SPORT_META[sport_key]
    summary = scores_client.fetch_summary(match) if match else {}
    return {
        "transactions": espn_extras.fetch_transactions(meta["sport"], meta["league"], meta["team_id"]),
        "news": espn_extras.fetch_team_news(meta["sport"], meta["league"], meta["team_id"]),
        "league_leaders": espn_extras.fetch_league_leaders(meta["sport"], meta["league"], [meta["leader_cat"]]),
        "game_leaders": scores_client.leaders_with_headshots(match) if match else [],
        "injuries": summary.get("injuries") or [],
        "competition": (match or {}).get("competition") or {},
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
            photos[who.lower()] = hshot
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
    return "\n".join(lines)


def _prompt(team_label: str, away_name: str, home_name: str, opponent: str, material: dict) -> str:
    block = _material_block(material)
    return (
        f"You're building a pregame warm-up show for {team_label} vs {opponent} ({away_name} at {home_name}), "
        f"the same kind of thing a real broadcast does before puck drop/first pitch/kickoff — a set of real "
        f"storylines and players to watch, not a dry recap.\n\n"
        f"Below are real facts pulled straight from ESPN — recent roster moves, team news, league-wide "
        f"stat leaders, tonight's own matchup leaders, and injuries. Use ONLY what's actually listed — "
        f"never invent a transaction, stat, injury, or storyline that isn't in this material. If a fact "
        f"below describes something genuinely notable (a call-up making a debut, a trade, a player leading "
        f"the league in something, a real hot or cold streak, a return from injury), that's exactly the "
        f"kind of thing to turn into a card — routine roster paperwork with nothing interesting about it "
        f"doesn't need its own card. IMPORTANT: the league-wide leaders section lists players from around "
        f"the whole league for context/comparison — most of them are NOT on {away_name} or {home_name} and "
        f"are not playing tonight. Check each player's own team abbreviation before writing about them; "
        f"never say or imply someone is playing in, affecting, or facing off in tonight's game unless "
        f"their team abbreviation actually matches {away_name} or {home_name}.\n\n"
        f"{block}\n\n"
        f"Produce up to {MAX_CARDS} cards, fewer if the material above doesn't genuinely support more — "
        f"never pad with generic filler to hit the number. Each card is EITHER about one specific player "
        f"(a real name from the material above) OR one team-level stat (our team or {opponent}). This is a "
        f"full-screen broadcast graphic, one card on screen at a time — give it real weight, like a "
        f"professional pregame show lower-third, not a caption. For each card give:\n"
        f'- "type": "player" or "team"\n'
        f'- "name": the exact real name (player\'s real name, or the team\'s real display name) as it '
        f"appears in the material above — this is used to look up a real photo, so it must match exactly\n"
        f'- "role": a short real descriptor (position + context, e.g. "RHP · Recalled from AAA", or blank '
        f'for a team card)\n'
        f'- "stats": 2-4 REAL individual NUMBERS from the material as separate {{"label", "value"}} pairs — '
        f'"value" is always a short number/figure (a stat like 2.35, a record like "66-70", a percentage), '
        f'"label" is a short all-caps-style caption for it (e.g. [{{"label": "ERA", "value": "2.35"}}, '
        f'{{"label": "K", "value": "12"}}, {{"label": "STARTS", "value": "3"}}] or, for a league leader\'s '
        f'full stat line, pick out the 2-4 that matter most rather than cramming everything in). This is '
        f"NOT the place for a player name, an injury status, or any other non-numeric fact — those belong "
        f'in "role" or "storyline" instead, never as a "stats" value. Never invent a stat that isn\'t in '
        f"the material — fewer real stats beats a made-up one, and it's fine to leave stats empty for a "
        f"card whose real material is a name/status/headline rather than a number (e.g. an injury-return "
        f"or call-up card with no numeric stat line to show yet).\n"
        f'- "storyline": 2-3 sentences, broadcast pregame-show voice, explaining why this is worth '
        f"watching tonight — this has real room now, use it, don't pad it thin\n\n"
        f'Respond with ONLY a JSON array, no markdown fences, no other text, in exactly this shape:\n'
        f'[{{"type": "player", "name": "CJ Van Eyk", "role": "RHP · Recalled from AAA", '
        f'"stats": [{{"label": "ERA", "value": "2.35"}}, {{"label": "STARTS", "value": "3"}}], '
        f'"storyline": "..."}}]'
    )


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
        role = str(item.get("role") or "").strip()
        stats = []
        for s in (item.get("stats") or [])[:4]:
            try:
                label, value = str(s["label"]).strip(), str(s["value"]).strip()
            except (KeyError, TypeError):
                continue
            if label and value:
                stats.append({"label": label, "value": value})
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
                "role": role,
                "stats": stats,
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
