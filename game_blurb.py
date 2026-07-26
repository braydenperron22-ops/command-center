"""Pregame/postgame AI blurbs for the jumbotron's own 3 teams (Jays/
Habs/Saints) — session request: "make a pre and postgame ai overview
thats only generated once. give it a bunch of info from the espn API
and have it do a pre and post game blurb," then "use gemini" (same
"one feature gets its own model" pattern as morning_briefing.py's own
Gemini-exclusive routing — everywhere else in this app is Groq-
primary, this one isn't).

Each blurb is written exactly once per game — not re-rolled on a
timer, not regenerated on every 5s rerun or on a fresh browser/kiosk
session — and remembered in a plain module-level dict keyed by
game_id for the rest of this process's life. Same "generate once,
remember forever this run" shape as sports_alerts.py's own seen/
baseline_done dicts, just for AI text instead of alert dedup.
Deliberately NOT persisted_state-backed like morning_briefing's own
daily dedup: a blurb for a game that's already over has no value
surviving a redeploy, so there's nothing worth spending Upstash's
budget on here.

ESPN's summary endpoint (scores_client.fetch_summary, already used for
win probability/leaders elsewhere) is the source for everything this
module's context-gathering pulls beyond the score itself: records,
this season's head-to-head series, injuries, the betting line, and —
postgame only — the real recap headline and box-score leader.
sports_client.py's own MLB Stats API/NHL API data doesn't carry any of
this (it's a different data source entirely — see that module's own
docstring)."""

import gemini_client
import scores_client

MAX_INJURIES_PER_TEAM = 3
MAX_OUTPUT_TOKENS = 150

_pregame_cache: dict[str, str] = {}
_postgame_cache: dict[str, str] = {}


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


def _gather_context(sport_key: str, away_name: str, home_name: str, postgame: bool) -> str | None:
    """A short, plain-text bullet list of real ESPN facts for this
    matchup — None if ESPN simply doesn't carry this game
    (find_espn_competition's own "skip this feature" case) or if
    nothing at all came back usable. Every line is independently
    optional (a field ESPN doesn't have for this sport/game just isn't
    added), so a thin payload still produces a shorter, still-honest
    blurb rather than a mostly-empty prompt."""
    match = scores_client.find_espn_competition(sport_key, away_name, home_name)
    if match is None:
        return None
    summary = scores_client.fetch_summary(match)
    competition = match["competition"]

    lines = []
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
        f"{opponent}, for a fan about to watch the game. Use ONLY the facts below — never invent "
        f"a stat, injury, or storyline that isn't listed. Natural broadcast-preview voice, not a "
        f"dry list of the facts themselves.\n\n{context}"
    )


def _postgame_prompt(team_label: str, opponent: str, context: str) -> str:
    return (
        f"Write a short postgame recap (2-3 sentences, no more) for {team_label} vs {opponent}, "
        f"for a fan who just watched the game. Use ONLY the facts below — never invent a play or "
        f"stat that isn't listed. Natural broadcast-recap voice, not a dry list of the facts "
        f"themselves.\n\n{context}"
    )


def get_pregame_blurb(sport_key: str, game_id, team_label: str, away_name: str, home_name: str, opponent: str) -> str | None:
    """Generated exactly once per game_id, then remembered for the rest
    of this process — a fresh browser session or kiosk reload does NOT
    regenerate it (see this module's own docstring on why there's no
    persisted_state backing here). None whenever ESPN doesn't have this
    game or the AI call itself fails — the caller just shows nothing,
    same as every other optional jumbotron panel."""
    key = f"{sport_key}_{game_id}"
    if key in _pregame_cache:
        return _pregame_cache[key]
    context = _gather_context(sport_key, away_name, home_name, postgame=False)
    if context is None:
        return None
    text = gemini_client.generate(_pregame_prompt(team_label, opponent, context), max_output_tokens=MAX_OUTPUT_TOKENS)
    if text is not None:
        _pregame_cache[key] = text
    return text


def get_postgame_blurb(sport_key: str, game_id, team_label: str, away_name: str, home_name: str, opponent: str) -> str | None:
    """Same one-shot-per-game_id shape as get_pregame_blurb above, in
    its own cache/key space (a doubleheader's two games, or the same
    game_id showing up in both a pregame and postgame call across the
    day, never collide)."""
    key = f"{sport_key}_{game_id}"
    if key in _postgame_cache:
        return _postgame_cache[key]
    context = _gather_context(sport_key, away_name, home_name, postgame=True)
    if context is None:
        return None
    text = gemini_client.generate(_postgame_prompt(team_label, opponent, context), max_output_tokens=MAX_OUTPUT_TOKENS)
    if text is not None:
        _postgame_cache[key] = text
    return text
