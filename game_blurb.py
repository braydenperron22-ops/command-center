"""Pregame/postgame AI blurbs for the jumbotron's own 3 teams (Jays/
Habs/Saints) — session request: "make a pre and postgame ai overview
thats only generated once. give it a bunch of info from the espn API
and have it do a pre and post game blurb," then "use gemini" (same
"one feature gets its own model" pattern as morning_briefing.py's own
Gemini-exclusive routing — everywhere else in this app is Groq-
primary, this one isn't).

Each blurb is written exactly once per game — not re-rolled on a
timer, not regenerated on every 5s rerun or on a fresh browser/kiosk
session — and remembered in a module-level dict keyed by game_id,
persisted_state-backed the same way groq_client/gemini_client's own
periodic caches are (loaded once at import, saved on every new
success). Originally a plain in-process dict with no cloud backing —
"a blurb for a game that's already over has no value surviving a
redeploy" seemed right in isolation, but session report, the first day
this app ever hit Gemini's free-tier rate limit: a mid-game redeploy/
restart wiped this cache mid-window, so the very next rerun paid for a
brand new Gemini call to re-write the exact same blurb it had already
generated minutes earlier — for however many restarts happened while
that one game's window was still open. Surviving a restart is the
whole point now, not an afterthought.

ESPN's summary endpoint (scores_client.fetch_summary, already used for
win probability/leaders elsewhere) is the source for everything this
module's context-gathering pulls beyond the score itself: records,
this season's head-to-head series, injuries, the betting line, and —
postgame only — the real recap headline and box-score leader.
sports_client.py's own MLB Stats API/NHL API data doesn't carry any of
this (it's a different data source entirely — see that module's own
docstring)."""

import gemini_client
import persisted_state
import scores_client

MAX_INJURIES_PER_TEAM = 3
MAX_OUTPUT_TOKENS = 150
# Comfortably above any realistic same-season count (3 tracked teams,
# roughly one game a day between them) — a safety net against
# unbounded growth, not something that trims real data in normal use.
MAX_CACHED_BLURBS = 200


def _load_cache(key: str) -> dict[str, str]:
    raw = persisted_state.load(key, {})
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


_pregame_cache: dict[str, str] = _load_cache("game_blurb_pregame_cache")
_postgame_cache: dict[str, str] = _load_cache("game_blurb_postgame_cache")


def _remember(cache: dict[str, str], persist_key: str, key: str, text: str) -> None:
    cache[key] = text
    if len(cache) > MAX_CACHED_BLURBS:
        # Plain dicts preserve insertion order — drop the oldest entry,
        # same bounded-eviction shape news.py's own headline-dedup dict
        # already uses.
        cache.pop(next(iter(cache)))
    persisted_state.save(persist_key, cache)


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _stakes_line(status: dict | None) -> str | None:
    """Real season-stakes context for OUR team — division position,
    wild-card standing, and playoff odds — from the same fetch_jays()/
    fetch_habs()/fetch_saints() dict sports_alerts.takeover_state()
    already computed for whichever game is featured (threaded through
    from pages_jumbotron._blurb_html for both pregame and postgame —
    a preview says why the race matters going in, a recap says what
    this result meant for it).

    Session request: "give it a season context... what are the teams
    fighting for... what's the importance of this game." The existing
    facts below (records, probable starters, odds) say who's playing
    and how they've been doing, but nothing about why tonight actually
    matters — which is exactly what read as generic ("exciting
    matchup," "watch it live") regardless of the real stakes.

    None whenever status itself is None (this game isn't one of the 3
    tracked teams' own — shouldn't happen given the call site, but no
    crash either way) or nothing in it resolves to a real line (e.g.
    NFL's wildcard is always None — see fetch_saints()'s own comment on
    why that's a deliberately lighter integration)."""
    if not status:
        return None
    parts = []
    our_row = next((r for r in status.get("standings") or [] if r.get("is_team")), None)
    division = status.get("division_name")
    if our_row and division:
        gb = our_row.get("extra")
        gb_text = f", {gb} GB" if gb not in (None, "-", "") else ""
        parts.append(f"{_ordinal(our_row['rank'])} in {division} ({our_row['wins']}-{our_row['losses']}{gb_text})")
    wildcard = status.get("wildcard") or {}
    if wildcard.get("rank") is not None:
        value, unit = wildcard.get("value"), wildcard.get("unit", "")
        gap_text = "holding a spot" if not value else f"{value} {unit} back"
        parts.append(f"Wild Card rank {wildcard['rank']} ({gap_text})")
    odds = status.get("playoff_odds") or {}
    if odds.get("display"):
        parts.append(f"{odds['display']} chance to make the playoffs")
    return "; ".join(parts) if parts else None


def _records_line(competition: dict) -> str | None:
    parts = []
    for c in competition.get("competitors", []):
        name = (c.get("team") or {}).get("displayName")
        record = scores_client.team_record(c)
        if name and record:
            parts.append(f"{name} ({record})")
    return " vs. ".join(parts) if len(parts) == 2 else None


def _venue_broadcast_line(competition: dict) -> str | None:
    venue = (competition.get("venue") or {}).get("fullName")
    names = [n for b in competition.get("broadcasts") or [] for n in b.get("names", [])]
    parts = [venue] if venue else []
    if names:
        parts.append("on " + "/".join(dict.fromkeys(names)))  # dict.fromkeys: de-dupe, keep order
    return " ".join(parts) if parts else None


def _series_line(summary: dict) -> str | None:
    for s in summary.get("seasonseries") or []:
        if s.get("summary"):
            return s["summary"]
    return None


def _probables_line(competition: dict) -> str | None:
    """MLB only — a competitor's "probables" entry is the probable
    starting pitcher with their own W-L/ERA line; there's no equivalent
    single "starter" concept for NHL/NFL, so this is None there, not an
    error."""
    names = []
    for c in competition.get("competitors", []):
        for p in c.get("probables") or []:
            athlete = (p.get("athlete") or {}).get("fullName")
            if athlete:
                names.append(f"{athlete}{f' {p['record']}' if p.get('record') else ''}")
    return " vs. ".join(names) if len(names) == 2 else None


def _odds_line(summary: dict) -> str | None:
    picks = summary.get("pickcenter") or []
    if not picks:
        return None
    details, over_under = picks[0].get("details"), picks[0].get("overUnder")
    parts = [f"line: {details}"] if details else []
    if over_under:
        parts.append(f"O/U {over_under}")
    return " · ".join(parts) if parts else None


def _injuries_lines(summary: dict) -> list[str]:
    out = []
    for block in summary.get("injuries") or []:
        team = (block.get("team") or {}).get("displayName")
        names = []
        for inj in (block.get("injuries") or [])[:MAX_INJURIES_PER_TEAM]:
            athlete = (inj.get("athlete") or {}).get("displayName")
            status = inj.get("status")
            if athlete:
                names.append(f"{athlete} ({status})" if status else athlete)
        if team and names:
            out.append(f"{team} injuries: {', '.join(names)}")
    return out


def _recap_line(summary: dict) -> str | None:
    """Postgame only — ESPN's own recap headline description, handed to
    the AI as source material to write its own sentence from, not
    quoted directly (same as every other AI feature in this app writing
    in its own voice rather than reusing someone else's copy)."""
    for h in summary.get("headlines") or []:
        if h.get("description"):
            return h["description"]
    return None


def _final_score_line(competition: dict) -> str | None:
    parts = []
    for c in competition.get("competitors", []):
        name, score = (c.get("team") or {}).get("displayName"), c.get("score")
        if name and score is not None:
            parts.append(f"{name} {score}")
    return " – ".join(parts) if len(parts) == 2 else None


def _leader_line(competition: dict) -> str | None:
    leader = scores_client.game_leader(competition)
    return f"{leader['name']}: {leader['stat_line']}" if leader else None


def _gather_context(
    sport_key: str,
    away_name: str,
    home_name: str,
    postgame: bool,
    stakes: str | None = None,
    stakes_label: str = "Season stakes",
    match: dict | None = None,
) -> str | None:
    """A short, plain-text bullet list of real ESPN facts for this
    matchup — None if ESPN simply doesn't carry this game
    (find_espn_competition's own "skip this feature" case) or if
    nothing at all came back usable. Every line is independently
    optional (a field ESPN doesn't have for this sport/game just isn't
    added), so a thin payload still produces a shorter, still-honest
    blurb rather than a mostly-empty prompt.

    `stakes` (see _stakes_line) is listed first, ahead of the plain
    matchup facts — it's the one line that answers "why does tonight
    matter," so the AI sees it before anything else.

    `match` — pass a pre-resolved {"event_id","competition","sport",
    "league"} dict (scores_client.fetch_playoff_round_games already
    hands one back per game) to skip the name-matching lookup below
    entirely. get_pregame_blurb/get_postgame_blurb's own tracked-team
    callers don't have one of these lying around cheaply, so they still
    look it up by name here same as always; get_neutral_pregame_blurb/
    get_neutral_postgame_blurb do, and skipping the lookup for them
    isn't just an optimization — away_name/home_name for a neutral game
    are scores_client's own shortDisplayName ("Blue Jays"), not the
    full displayName find_espn_competition matches on ("Toronto Blue
    Jays"), so relying on that lookup for a neutral game risks silently
    finding nothing even though the competition data was already in
    hand."""
    if match is None:
        match = scores_client.find_espn_competition(sport_key, away_name, home_name)
        if match is None:
            return None
    summary = scores_client.fetch_summary(match)
    competition = match["competition"]

    lines = []
    if stakes:
        lines.append(f"{stakes_label}: {stakes}")
    for label, value in (
        ("Records", _records_line(competition)),
        ("Venue/broadcast", _venue_broadcast_line(competition)),
        ("Season series", _series_line(summary)),
        ("Probable starters", _probables_line(competition)),
        ("Betting line", _odds_line(summary)),
    ):
        if value:
            lines.append(f"{label}: {value}")
    lines.extend(_injuries_lines(summary))

    if postgame:
        for label, value in (
            ("Final", _final_score_line(competition)),
            ("Standout performance", _leader_line(competition)),
            ("What happened", _recap_line(summary)),
        ):
            if value:
                lines.append(f"{label}: {value}")

    return "\n".join(lines) if lines else None


def _pregame_prompt(team_label: str, opponent: str, context: str) -> str:
    return (
        f"Write a short, exciting pregame preview (2-3 sentences, no more) for {team_label} vs "
        f"{opponent}, for a fan about to watch the game. If a 'Season stakes' fact is listed below, "
        f"lead with THAT — the division race, wild card chase, or playoff push it describes — as "
        f"the real reason tonight matters, rather than just narrating who's playing and where to "
        f"watch. Use ONLY the facts below — never invent a stat, injury, standing, or storyline "
        f"that isn't listed. Natural broadcast-preview voice, not a dry list of the facts "
        f"themselves.\n\n{context}"
    )


def _postgame_prompt(team_label: str, opponent: str, context: str) -> str:
    return (
        f"Write a short postgame recap (2-3 sentences, no more) for {team_label} vs {opponent}, "
        f"for a fan who just watched the game. If a 'Season stakes' fact is listed below, weave in "
        f"what this result actually means for that race — a step forward, a step back, still very "
        f"much alive, whatever the facts support — rather than just restating the final score and "
        f"the box-score highlight. Use ONLY the facts below — never invent a play, stat, or "
        f"standing that isn't listed. Natural broadcast-recap voice, not a dry list of the facts "
        f"themselves.\n\n{context}"
    )


def get_pregame_blurb(
    sport_key: str, game_id, team_label: str, away_name: str, home_name: str, opponent: str, status: dict | None = None
) -> str | None:
    """Generated exactly once per game_id, then remembered across
    reruns, browser sessions, AND process restarts (see this module's
    own docstring on why that last part matters now). None whenever
    ESPN doesn't have this game or the AI call itself fails — the
    caller just shows nothing, same as every other optional jumbotron
    panel.

    `status` is the same fetch_jays()/fetch_habs()/fetch_saints() dict
    pages_jumbotron._blurb_html already has in scope (from sports_
    alerts.takeover_state()) — optional and pregame-only, see
    _stakes_line's own docstring for why."""
    key = f"{sport_key}_{game_id}"
    if key in _pregame_cache:
        return _pregame_cache[key]
    context = _gather_context(sport_key, away_name, home_name, postgame=False, stakes=_stakes_line(status))
    if context is None:
        return None
    text = gemini_client.generate(_pregame_prompt(team_label, opponent, context), max_output_tokens=MAX_OUTPUT_TOKENS)
    if text is not None:
        _remember(_pregame_cache, "game_blurb_pregame_cache", key, text)
    return text


def get_postgame_blurb(
    sport_key: str, game_id, team_label: str, away_name: str, home_name: str, opponent: str, status: dict | None = None
) -> str | None:
    """Same one-shot-per-game_id shape as get_pregame_blurb above, in
    its own cache/key space (a doubleheader's two games, or the same
    game_id showing up in both a pregame and postgame call across the
    day, never collide).

    `status` — same fetch_jays()/fetch_habs()/fetch_saints() dict as
    get_pregame_blurb's own — lets the recap say what the result
    actually meant for the race, not just what happened in the game
    itself. See _stakes_line's own docstring for the session request
    behind this."""
    key = f"{sport_key}_{game_id}"
    if key in _postgame_cache:
        return _postgame_cache[key]
    context = _gather_context(sport_key, away_name, home_name, postgame=True, stakes=_stakes_line(status))
    if context is None:
        return None
    # The one deliberate exception to gemini_client.generate's own
    # game-time pause (see its docstring) — this call only exists
    # DURING that window, right as a tracked game goes final, so
    # pausing it along with everything else would mean it almost never
    # fires.
    text = gemini_client.generate(
        _postgame_prompt(team_label, opponent, context), max_output_tokens=MAX_OUTPUT_TOKENS, allow_during_game=True
    )
    if text is not None:
        _remember(_postgame_cache, "game_blurb_postgame_cache", key, text)
    return text


# Session request: "during the semis and the finals... regardless of
# if my team is out or not, I wanna watch every game of those series...
# as the featured game" (same rich board as the tracked-team games, not
# a stripped-down one — the follow-up confirming that, once asked).
# get_pregame_blurb/get_postgame_blurb above are written from OUR
# team's perspective start to finish (team_label vs. opponent, stakes
# tied to our own playoff race) — neither concept exists for two teams
# we have no stake in, so this is a real parallel pair, not a thin
# wrapper: evenhanded "away at home" framing, and "why tonight matters"
# is the series itself (round + real series score, see
# _series_stakes_line) rather than a division/wild-card race.


def _series_stakes_line(round_text: str | None, series_summary: str | None) -> str | None:
    """The neutral-blurb equivalent of _stakes_line above — round name
    plus the real series score once it's started (e.g. "West Final —
    EDM leads series 2-1"), both straight from ESPN (see scores_client.
    fetch_playoff_round_games's own docstring on where these come
    from). None only when round_text itself is None (shouldn't happen
    given the call site — sports_alerts._neutral_playoff_candidates
    already filtered to real semis-or-later games — but no crash
    either way)."""
    if not round_text:
        return None
    label = round_text.split(" - Game")[0].strip()
    return f"{label} — {series_summary}" if series_summary else label


def _neutral_pregame_prompt(away_name: str, home_name: str, context: str) -> str:
    return (
        f"Write a short, exciting pregame preview (2-3 sentences, no more) for {away_name} at "
        f"{home_name}, for a fan who follows the league but isn't rooting for either team tonight. "
        f"If a 'Series stakes' fact is listed below, lead with THAT — the round and series score it "
        f"describes — as the real reason tonight matters, rather than just narrating who's playing "
        f"and where to watch. Use ONLY the facts below — never invent a stat, injury, standing, or "
        f"storyline that isn't listed. Natural broadcast-preview voice, evenhanded between both "
        f"teams, not a dry list of the facts themselves.\n\n{context}"
    )


def _neutral_postgame_prompt(away_name: str, home_name: str, context: str) -> str:
    return (
        f"Write a short postgame recap (2-3 sentences, no more) for {away_name} at {home_name}, for "
        f"a fan who follows the league but wasn't rooting for either team. If a 'Series stakes' fact "
        f"is listed below, weave in what this result means for the series — a step closer to "
        f"elimination, a series tied up, a sweep completed, whatever the facts support — rather than "
        f"just restating the final score and the box-score highlight. Use ONLY the facts below — "
        f"never invent a play, stat, or standing that isn't listed. Natural broadcast-recap voice, "
        f"evenhanded between both teams, not a dry list of the facts themselves.\n\n{context}"
    )


def get_neutral_pregame_blurb(
    sport_key: str, game_id, away_name: str, home_name: str, match: dict, round_text: str | None, series_summary: str | None
) -> str | None:
    """Neutral equivalent of get_pregame_blurb above — same one-shot-
    per-game_id cache (shared dict/key space: a real game_id is never
    both a tracked-team game and a neutral one, so there's no collision
    risk in sharing it)."""
    key = f"{sport_key}_{game_id}"
    if key in _pregame_cache:
        return _pregame_cache[key]
    context = _gather_context(
        sport_key, away_name, home_name, postgame=False,
        stakes=_series_stakes_line(round_text, series_summary), stakes_label="Series stakes", match=match,
    )
    if context is None:
        return None
    text = gemini_client.generate(_neutral_pregame_prompt(away_name, home_name, context), max_output_tokens=MAX_OUTPUT_TOKENS)
    if text is not None:
        _remember(_pregame_cache, "game_blurb_pregame_cache", key, text)
    return text


def get_neutral_postgame_blurb(
    sport_key: str, game_id, away_name: str, home_name: str, match: dict, round_text: str | None, series_summary: str | None
) -> str | None:
    """Neutral equivalent of get_postgame_blurb above — see its own
    docstring for the game-time-pause exception, which applies here
    too."""
    key = f"{sport_key}_{game_id}"
    if key in _postgame_cache:
        return _postgame_cache[key]
    context = _gather_context(
        sport_key, away_name, home_name, postgame=True,
        stakes=_series_stakes_line(round_text, series_summary), stakes_label="Series stakes", match=match,
    )
    if context is None:
        return None
    text = gemini_client.generate(
        _neutral_postgame_prompt(away_name, home_name, context), max_output_tokens=MAX_OUTPUT_TOKENS, allow_during_game=True
    )
    if text is not None:
        _remember(_postgame_cache, "game_blurb_postgame_cache", key, text)
    return text
