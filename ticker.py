"""Builds the bottom ticker: release-calendar countdowns plus, since
session feedback that the previous version needed "better utility"
than just dates, live "stat" items reusing data already fetched
elsewhere in this app — market index/commodity/FX % change (same
instruments the Markets page itself shows), the portfolio's own 1-day
total, and a live Jays/Habs score when either is actually playing.
Two distinct item shapes flow through the same scrolling strip: a
"release" item (a future date/countdown) and a "stat" item (a live
value, no date) — see render_html for how each renders.
"""

from datetime import date, datetime, timedelta

import streamlit as st
import yfinance as yf

import fetch_throttle
import market_yf_client
import portfolio_client
import sports_client
from flags import flag_for
import fred_client
from config import (
    COUNTDOWN_WINDOW_HOURS,
    EARNINGS_TICKER_WATCHLIST,
    INDICATORS,
    MARKET_INSTRUMENTS_ALWAYS,
    MARKET_INSTRUMENTS_CLOSED,
    MARKET_INSTRUMENTS_OPEN,
    MARKET_INSTRUMENTS_WEEKEND,
)

MONTH_DAY = "%b %d"
EARNINGS_CACHE_TTL_SECONDS = 24 * 60 * 60  # a real earnings date rarely moves day to day

_STATUS_INSTRUMENTS = {
    "open": MARKET_INSTRUMENTS_OPEN,
    "closed": MARKET_INSTRUMENTS_CLOSED,
    "weekend": MARKET_INSTRUMENTS_WEEKEND,
}

_last_good_earnings: dict[str, str] = {}  # ticker -> ISO date string


def _estimate_next(as_of: str, cadence_days: int) -> str:
    """Roll a cadence forward from the last data point until it's in the future.

    Used only for Canada series, where neither FRED nor StatCan expose a
    forward release calendar — this is a best-effort guess, not official.
    """
    d = date.fromisoformat(as_of)
    today = date.today()
    while d <= today:
        d += timedelta(days=cadence_days)
    return d.isoformat()


@st.cache_data(ttl=EARNINGS_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_earnings_date_raw(ticker: str) -> str | None:
    fetch_throttle.wait_turn()
    cal = yf.Ticker(ticker).calendar
    dates = cal.get("Earnings Date") if cal else None
    return min(dates).isoformat() if dates else None


def _fetch_earnings_date(ticker: str) -> str | None:
    global _last_good_earnings
    try:
        result = _fetch_earnings_date_raw(ticker)
    except Exception:
        return _last_good_earnings.get(ticker)
    if result:
        _last_good_earnings[ticker] = result
    return result or _last_good_earnings.get(ticker)


def build_earnings_schedule() -> list[dict]:
    """Next earnings date for a small curated watchlist (see config.
    EARNINGS_TICKER_WATCHLIST) — same item shape build_schedule already
    produces, so render_html below needs no changes to show both kinds
    together. Only future dates make it in; yfinance's calendar can
    still carry an already-passed date for a day or two after it
    actually happens rather than immediately rolling to the next one."""
    today = date.today()
    items = []
    for ticker in EARNINGS_TICKER_WATCHLIST:
        iso_date = _fetch_earnings_date(ticker)
        if not iso_date or date.fromisoformat(iso_date) < today:
            continue
        items.append({
            "type": "release",
            "country": "us",
            "label": f"{ticker} Earnings",
            "date": iso_date,
            "confirmed": True,
        })
    return items


def build_schedule(readings: dict, api_key: str) -> list[dict]:
    """readings: {(country, key): reading_dict} already fetched for the tiles."""
    items = []
    for country, indicators in INDICATORS.items():
        for ind in indicators:
            reading = readings.get((country, ind["key"]))
            if ind.get("source") == "statcan" or "release_id" not in ind:
                if not reading:
                    continue
                next_date = _estimate_next(reading["as_of"], ind["release_cadence_days"])
                confirmed = False
            else:
                next_date = fred_client.fetch_next_release_date(ind["release_id"], api_key)
                confirmed = True
                if not next_date:
                    continue
            items.append({
                "type": "release",
                "country": country,
                "label": ind["label"],
                "date": next_date,
                "confirmed": confirmed,
            })

    items.sort(key=lambda it: it["date"])
    return items


def build_market_stat_items() -> list[dict]:
    """Live intraday % change for the same instruments the Markets page
    itself shows (see config.MARKET_INSTRUMENTS_*, swapped by session
    status exactly like that page's own STATUS_INSTRUMENTS) — the one
    thing a ticker has classically always meant, and the one thing the
    previous version of this ticker had none of: every item in it was a
    forward-looking release date, nothing live."""
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
                "type": "stat",
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
        return {"type": "stat", "text": total_text, "tone": "neutral"}
    sign = "+" if pct >= 0 else ""
    return {
        "type": "stat",
        "text": f"{total_text} ({sign}{pct:.2f}%)",
        "tone": "good" if pct >= 0 else "bad",
    }


def build_sports_stat_items() -> list[dict]:
    """Live Jays/Habs score, only while either is actually playing —
    [] otherwise. Same reasoning as the market/portfolio stats above:
    ambient status visible from any page, not just when the Sports/
    Scores page happens to be up on this kiosk's own rotation."""
    items = []
    for label, fetch_status in (("BLUE JAYS", sports_client.fetch_jays), ("CANADIENS", sports_client.fetch_habs)):
        status = fetch_status()
        game = status["game"] if status else None
        if not game or game["state"] != "live":
            continue
        opponent_word = "vs" if game["is_home"] else "@"
        text = f'{label} {game["team_score"]}-{game["opp_score"]} {opponent_word} {game["opponent"]} (LIVE)'
        items.append({"type": "stat", "text": text, "tone": "neutral"})
    return items


def render_html(items: list[dict], now: datetime) -> str:
    if not items:
        return ""
    parts = []
    for it in items:
        if it.get("type") == "stat":
            # Live value, no date/countdown — tone (good/bad/neutral)
            # colors it the same green/red/plain language the rest of
            # this app already uses for a % change, so it reads
            # consistently with e.g. the Markets page it's mirroring.
            parts.append(f'<span class="ticker-item ticker-item-{it["tone"]}">{it["text"]}</span>')
            continue

        release_date = date.fromisoformat(it["date"])
        # FRED/StatCan don't expose a release time, so assume the typical
        # 8:30 AM slot most US/Canada statistical releases use — good
        # enough for an approximate countdown, not a precise alert.
        target = datetime.combine(release_date, datetime.min.time()) + timedelta(hours=8, minutes=30)
        hours_away = (target - now).total_seconds() / 3600
        suffix = "" if it["confirmed"] else " (est.)"
        flag_svg = f'<span class="ticker-flag">{flag_for(it["country"])}</span>'

        if 0 <= hours_away <= COUNTDOWN_WINDOW_HOURS:
            h = int(hours_away)
            m = int((hours_away - h) * 60)
            body = f'{flag_svg} {it["label"]} — in {h}h {m:02d}m{suffix}'
            parts.append(f'<span class="ticker-item ticker-item-soon">{body}</span>')
        else:
            d = target.strftime(MONTH_DAY)
            parts.append(f'<span class="ticker-item">{flag_svg} {it["label"]} — {d}{suffix}</span>')

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
