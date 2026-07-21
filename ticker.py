"""Builds the bottom ticker — a pure live-stat strip. Originally a
release-date countdown ticker; session feedback that it needed "better
utility" first added live stats alongside the dates, then a follow-up
("remove the dates for data, [they're] just not [as] informational and
as good as the other options") dropped the date/countdown machinery
entirely. Every item here is a live value reusing data already fetched
elsewhere in this app — nothing here makes its own new network request
beyond what those modules' own callers already pay for.
"""

import market_internals
import market_yf_client
import portfolio_client
import sports_client
import air_quality_client
import fuel_price_client
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
