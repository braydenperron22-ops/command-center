"""Builds the bottom release-calendar ticker: next known/estimated release per indicator."""

from datetime import date, datetime, timedelta

import streamlit as st
import yfinance as yf

import fetch_throttle
from flags import flag_for
import fred_client
from config import COUNTDOWN_WINDOW_HOURS, EARNINGS_TICKER_WATCHLIST, INDICATORS

MONTH_DAY = "%b %d"
EARNINGS_CACHE_TTL_SECONDS = 24 * 60 * 60  # a real earnings date rarely moves day to day

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
                "country": country,
                "label": ind["label"],
                "date": next_date,
                "confirmed": confirmed,
            })

    items.sort(key=lambda it: it["date"])
    return items


def render_html(items: list[dict], now: datetime) -> str:
    if not items:
        return ""
    parts = []
    for it in items:
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
