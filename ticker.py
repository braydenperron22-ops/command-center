"""Builds the bottom ticker — a pure live-stat strip. Originally a
release-date countdown ticker; session feedback that it needed "better
utility" first added live stats alongside the dates, then a follow-up
("remove the dates for data, [they're] just not [as] informational and
as good as the other options") dropped the date/countdown machinery
entirely. Every item here is a live value reusing data already fetched
elsewhere in this app — nothing here makes its own new network request
beyond what those modules' own callers already pay for.
"""

import commute_client
import market_internals
import market_yf_client
import portfolio_client
import prediction_markets_client
import sports_client
import air_quality_client
import fuel_price_client
import wildfire_client
from flags import flag_for
from config import (
    INDICATORS,
    MARKET_INSTRUMENTS_ALWAYS,
    MARKET_INSTRUMENTS_CLOSED,
    MARKET_INSTRUMENTS_OPEN,
    MARKET_INSTRUMENTS_WEEKEND,
)

_STATUS_INSTRUMENTS = {
    "open": MARKET_INSTRUMENTS_OPEN,
    "closed": MARKET_INSTRUMENTS_CLOSED,
    "weekend": MARKET_INSTRUMENTS_WEEKEND,
}


def build_market_stat_items() -> list[dict]:
    """Live intraday % change for the same instruments the Markets page
    itself shows (see config.MARKET_INSTRUMENTS_*, swapped by session
    status exactly like that page's own STATUS_INSTRUMENTS)."""
    status = market_yf_client.market_status()
    instruments = _STATUS_INSTRUMENTS[status] + MARKET_INSTRUMENTS_ALWAYS
    items = []
    for inst in instruments:
        quote = market_yf_client.quote_for(inst["symbol"])
        if not quote or quote["intraday"] is None:
            continue
        pct = quote["intraday"]
        sign = "+" if pct >= 0 else ""
        items.append(
            {
                "text": f'{inst["label"]} {sign}{pct:.2f}%',
                "tone": "good" if pct >= 0 else "bad",
            }
        )
    return items


def build_portfolio_stat_item() -> dict | None:
    """Today's portfolio total + 1-day change — the same numbers the
    Portfolio page's own TOTAL VALUE tile shows, visible from every
    page via the ticker instead of only while actually on that page.
    None if the integration isn't configured/reachable (same as that
    page's own empty state)."""
    portfolio = portfolio_client.fetch_portfolio()
    if not portfolio:
        return None
    pct = (portfolio_client.fetch_changes() or {}).get("1d")
    total_text = f'Portfolio ${portfolio["total_cad"]:,.2f}'
    if pct is None:
        return {"text": total_text, "tone": "neutral"}
    sign = "+" if pct >= 0 else ""
    return {"text": f"{total_text} ({sign}{pct:.2f}%)", "tone": "good" if pct >= 0 else "bad"}


def build_sports_stat_items() -> list[dict]:
    """Live Jays/Habs score, only while either is actually playing —
    [] otherwise. Ambient status visible from any page, not just when
    the Sports/Scores page happens to be up on this kiosk's own
    rotation."""
    items = []
    for label, fetch_status in (("BLUE JAYS", sports_client.fetch_jays), ("CANADIENS", sports_client.fetch_habs)):
        status = fetch_status()
        game = status["game"] if status else None
        if not game or game["state"] != "live":
            continue
        opponent_word = "vs" if game["is_home"] else "@"
        text = f'{label} {game["team_score"]}-{game["opp_score"]} {opponent_word} {game["opponent"]} (LIVE)'
        items.append({"text": text, "tone": "neutral"})
    return items


def build_playoff_odds_stat_items() -> list[dict]:
    """Session request: "add more stuff to the ticker" — ESPN's own
    playoff-odds simulation (see sports_client._espn_playoff_odds), one
    per tracked team, using the exact same fetch_jays()/fetch_habs()/
    fetch_saints() dict this file's own build_sports_stat_items and
    game_blurb's season-stakes context already pull "playoff_odds" from
    — no new fetch shape, just a third caller of data this app already
    has fully plumbed. Unlike the live-score item above, not gated on a
    game being underway right now — a team's playoff push is a season-
    long story, worth a glance any time, not just mid-game. [] entirely
    for a team that's out of season (status itself is None) or whose
    odds haven't posted yet (NHL/NFL in the off-season — see
    fetch_habs/fetch_saints' own comments on why "percent"/"display"
    come back None then even though the team itself is still "in
    season" by these fetchers' own SEASON_WINDOW_DAYS)."""
    items = []
    for label, fetch_status in (
        ("BLUE JAYS", sports_client.fetch_jays),
        ("CANADIENS", sports_client.fetch_habs),
        ("SAINTS", sports_client.fetch_saints),
    ):
        status = fetch_status()
        odds = (status or {}).get("playoff_odds") or {}
        if not odds.get("display"):
            continue
        items.append({"text": f'{label} Playoff Odds {odds["display"]}', "tone": "neutral"})
    return items


def build_commute_stat_item() -> dict | None:
    """Real-time drive time to the default commute destination — the
    same TomTom-backed number pages_today._commute_html shows, "no
    delays" (good/green) vs. a real traffic delay with its own reason
    when TomTom has one (bad/red) — same wording/threshold convention
    as that tile. None whenever TOMTOM_API_KEY isn't configured or the
    route fetch itself failed (commute_client.route's own None case),
    same as that tile's own empty state."""
    data = commute_client.route(None)
    if not data:
        return None
    minutes = round(data["duration_seconds"] / 60)
    delay_minutes = round(data["delay_seconds"] / 60)
    if delay_minutes >= 1:
        reason = f" ({data['incident']})" if data.get("incident") else ""
        return {"text": f"Commute {minutes} min (+{delay_minutes} min traffic{reason})", "tone": "bad"}
    return {"text": f"Commute {minutes} min (no delays)", "tone": "good"}


def build_indicator_stat_items(readings: dict) -> list[dict]:
    """Current value — not a future release date — for every tracked
    FRED/StatCan macro indicator (CPI, unemployment, GDP, policy rate,
    10-year yield, US + Canada). Reuses the exact same `readings` dict
    already fetched for the Home page's own indicator tiles, so this
    costs nothing extra; empty (not an error) whenever readings itself
    is empty, e.g. no FRED_API_KEY configured."""
    items = []
    for country, indicators in INDICATORS.items():
        for ind in indicators:
            reading = readings.get((country, ind["key"]))
            if not reading or reading.get("current") is None:
                continue
            flag_svg = f'<span class="ticker-flag">{flag_for(country)}</span>'
            text = f'{flag_svg} {ind["label"]} {reading["current"]:.2f}{ind["unit"]}'
            items.append({"text": text, "tone": "neutral"})
    return items


def build_internals_stat_items() -> list[dict]:
    """Market Internals' own headline numbers (see
    market_internals.py/pages_internals.py) — the Fear & Greed gauge,
    Shiller CAPE, and the HYG/LQD credit and RSP/SPY breadth ratios —
    visible from any page instead of only the one rotation slot
    Internals gets. Neutral tone throughout: unlike a plain % change,
    none of these are a simple "up good, down bad" — pages_internals.py
    itself only ever interprets them with a whole explanatory sentence,
    not a color."""
    items = []
    gauge = market_internals.fear_greed_index()
    if gauge:
        items.append({"text": f'Fear & Greed {gauge["value"]:.0f}', "tone": "neutral"})
    cape = market_internals.shiller_cape()
    if cape and cape.get("value") is not None:
        items.append({"text": f'Shiller CAPE {cape["value"]:.1f}', "tone": "neutral"})
    hyg_lqd = market_internals.price_ratio("HYG", "LQD")
    if hyg_lqd:
        items.append({"text": f'HYG/LQD {hyg_lqd["value"]:.3f}', "tone": "neutral"})
    rsp_spy = market_internals.price_ratio("RSP", "SPY")
    if rsp_spy:
        items.append({"text": f'RSP/SPY {rsp_spy["value"]:.3f}', "tone": "neutral"})
    return items


def build_prediction_market_stat_items() -> list[dict]:
    """One compact item per tracked central bank (see
    prediction_markets_client.BANKS), naming the market's current
    single most-likely outcome for its next meeting and that outcome's
    own probability — the same rolling-contract data the Predictions
    page shows in full, just the headline number here.

    Session request: "instead of having their acronym in the bottom
    bar, just have their flag" — same flag_for()/.ticker-flag pattern
    build_indicator_stat_items already uses for US/Canada, reusing
    BANK_FLAG_CODES rather than each bank's acronym. "color the bottom
    bar the same way it's colored on the [Predictions] page" — tone is
    bucket_direction() itself ("cut"/"hike" get the new ice/fire ticker
    classes below, "hold" reuses the existing plain "neutral" one)
    rather than good/bad, since a rate direction isn't "good or bad
    news" the way a market move is.

    One extra item beyond the per-bank roster: a plain-language reading
    of prediction_markets_client.global_consensus() — session request:
    "a global central bank outcome and odds... put it in the ticker
    tape too," the same aggregate the Predictions page's own new tile
    below the bank list shows. A 🌐 stands in for a flag (it isn't any
    one country's number — session follow-up: "make it a global
    emoji," in place of the plain text "GLOBAL" every other item's real
    flag icon used to be the odd one out next to); same tone convention
    as every other item here."""
    items = []
    for bank in prediction_markets_client.BANKS:
        odds = prediction_markets_client.current_odds(bank)
        if not odds:
            continue
        bucket, prob = prediction_markets_client.most_likely_outcome(odds)
        label = prediction_markets_client.BUCKET_LABELS[bucket]
        direction = prediction_markets_client.bucket_direction(bucket)
        tone = direction if direction in ("cut", "hike") else "neutral"
        flag_svg = f'<span class="ticker-flag">{flag_for(prediction_markets_client.BANK_FLAG_CODES[bank])}</span>'
        items.append({"text": f'{flag_svg} {label} {prob * 100:.0f}%', "tone": tone})

    consensus = prediction_markets_client.global_consensus()
    if consensus:
        direction = consensus["direction"]
        tone = direction if direction in ("cut", "hike") else "neutral"
        label = prediction_markets_client.DIRECTION_LABELS[direction]
        items.append({"text": f'🌐 {label} {consensus["probability"] * 100:.0f}%', "tone": tone})
    return items


def build_gas_stat_item() -> dict | None:
    """North Bay gas price — the same number the Household page's own
    tile shows (see fuel_price_client.eco_mode_status)."""
    status = fuel_price_client.eco_mode_status()
    if not status:
        return None
    return {"text": f'Gas {status["price"]:.1f}¢/L', "tone": "neutral"}


def build_aqi_stat_item() -> dict | None:
    """Current US AQI — the same reading the hero-row badge shows once
    it crosses AQI_SHOW_THRESHOLD, surfaced here regardless of whether
    it's crossed that "worth a badge" bar."""
    data = air_quality_client.fetch_air_quality()
    if not data or data.get("us_aqi") is None:
        return None
    return {"text": f'AQI {data["us_aqi"]:.0f}', "tone": "neutral"}


def build_wildfire_stat_item() -> dict | None:
    """Nearest detected wildfire, only when wildfire_client.
    nearest_wildfire itself has something real to say — outside
    wildfire season, or on a day with nothing within its own
    SHOW_RADIUS_KM, this is None entirely (same quiet-by-default
    behavior app.py's own AQI-badge intensity effect and morning_
    briefing's mention of it already rely on). Neutral tone, same as
    AQI/gas above — a proximity fact, not a call on how worried to be
    about it (no distance-tier judgment currently exists to color it
    by)."""
    wildfire = wildfire_client.nearest_wildfire()
    if not wildfire:
        return None
    return {"text": f'Wildfire {wildfire["distance_km"]:.0f} km away', "tone": "neutral"}


def render_html(items: list[dict]) -> str:
    if not items:
        return ""
    parts = [f'<span class="ticker-item ticker-item-{it["tone"]}">{it["text"]}</span>' for it in items]
    # Duplicate the content once so the marquee loop has no visible seam.
    strip = '<span class="ticker-sep">•</span>'.join(parts)
    return f"""
    <div class="ticker-bar">
        <div class="ticker-track">
            <div class="ticker-content">{strip}</div>
            <div class="ticker-content" aria-hidden="true">{strip}</div>
        </div>
    </div>
    """
