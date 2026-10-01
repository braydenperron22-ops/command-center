"""Portfolio page: real Wealthsimple balances via SnapTrade (session
request: "import portfolio value from wealthsimple into my dashboard").
Split out to its own page from Markets — session feedback the combined
tile read too big/heavy sharing a page with the compact instrument
grid, and this has since grown its own multi-period detail that
deserves the room.

Wealthsimple has no public API of its own; SnapTrade is the account-
aggregation layer several consumer portfolio-tracker apps (Blossom
included) already use to connect to it — see portfolio_client.py for
the actual fetch/consolidation/period-change logic.

Session request, full page review: "I don't really want the
transaction log anymore for the most part I just kind of want the
overall balance the trend... I want to add two weeks, a month, six
months, year to date, and then one full year. I want to see the
average trend of my balance... consolidate into one clean dashboard
that fits in the entire frame." RECENT ACTIVITY is gone entirely; the
old single 6-month sparkline is now six range cards (1D/2W/1M/6M/YTD/
1Y), each its own real % change plus a sparkline for exactly that
window, all sliced from one shared 365-day cached fetch (portfolio_
client.cached_value_history) — no new API load per range. Same
review found and fixed a real backend bug in the account breakdown
itself (see portfolio_client.ACCOUNT_ID_DISPLAY_NAMES's own comment)
— this page just reads the corrected data.
"""

import html
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

import net_worth_tracker
import portfolio_client
import tiles
from config import TIMEZONE

# Kiosk viewed from across a room — bigger than this app's default
# market-metric sizing (1.3rem/0.85rem), which was tuned for Markets'
# dense 7-column grid, not a single full-width page like this one.
_METRIC_LABEL_STYLE = "font-size:1.05rem;"
_METRIC_VALUE_STYLE = "font-size:1.7rem; font-weight:600;"

# (label, fetch_changes() key, lookback for slicing cached_value_history —
# an int day-count, "ytd" for calendar-year-to-date, or None for 1-day,
# which has too few points for a sparkline to mean anything and just
# uses the existing day-change stat instead). Order is display order.
_RANGES = [
    ("1 DAY", "1d", None),
    ("2 WEEKS", "2w", 14),
    ("1 MONTH", "1m", 30),
    ("6 MONTHS", "6m", 182),
    ("YEAR TO DATE", "ytd", "ytd"),
    ("1 YEAR", "1y", 365),
]


def _period_metric(label: str, pct: float | None, amount: float | None = None) -> str:
    if pct is None:
        return (
            f'<div class="market-metric"><span class="market-metric-label" style="{_METRIC_LABEL_STYLE}">{label}</span>'
            f'<span class="market-metric-value" style="{_METRIC_VALUE_STYLE}">—</span></div>'
        )
    direction_class = "market-up" if pct >= 0 else "market-down"
    sign = "+" if pct >= 0 else ""
    amount_html = (
        f' <span class="market-metric-sub" style="opacity:0.7;">({sign}${abs(amount):,.2f})</span>'
        if amount is not None
        else ""
    )
    return (
        f'<div class="market-metric"><span class="market-metric-label" style="{_METRIC_LABEL_STYLE}">{label}</span>'
        f'<span class="market-metric-value {direction_class}" style="{_METRIC_VALUE_STYLE}">{sign}{pct:.2f}%{amount_html}</span></div>'
    )


def _slice_history(value_history: list[tuple[str, float]], lookback) -> list[float]:
    """Just the values (portfolio_client's own sparkline shape) from
    `lookback` days ago (or Jan 1 of this year for "ytd") through now —
    real calendar-date slicing of the one shared 365-day fetch, not an
    index guess, so a range with sparser real data points still cuts at
    the right date instead of the wrong depth."""
    if not value_history:
        return []
    if lookback == "ytd":
        cutoff = date(datetime.now(ZoneInfo(TIMEZONE)).year, 1, 1).isoformat()
    else:
        cutoff = (date.today() - timedelta(days=lookback)).isoformat()
    return [v for d, v in value_history if d >= cutoff]


def _trend_card(label: str, pct: float | None, values: list[float]) -> str:
    if pct is None:
        pct_html = '<span class="market-metric-value" style="font-size:1.25rem;">—</span>'
    else:
        direction_class = "market-up" if pct >= 0 else "market-down"
        sign = "+" if pct >= 0 else ""
        pct_html = (
            f'<span class="market-metric-value {direction_class}" '
            f'style="font-size:1.25rem; font-weight:600;">{sign}{pct:.2f}%</span>'
        )
    spark_html = ""
    if len(values) >= 2:
        tone = "good" if values[-1] >= values[0] else "bad"
        spark_html = tiles.sparkline_svg(values, tone, width=120, height=36)
    return (
        f'<div class="tile" style="padding:1rem 1.1rem;">'
        f'<div class="market-metric-label" style="font-size:0.85rem; opacity:0.75; margin-bottom:0.3rem;">{label}</div>'
        f'{pct_html}'
        f'<div style="margin-top:0.4rem;">{spark_html}</div>'
        f'</div>'
    )


def _holding_row(position: dict) -> str:
    symbol = html.escape(position["symbol"])
    description = position.get("description")
    detail = f" · {html.escape(description)}" if description else ""
    units = position["units"]
    units_label = f"{units:,.4f}".rstrip("0").rstrip(".") if units % 1 else f"{units:,.0f}"
    market_value = position.get("market_value")
    open_pnl = position.get("open_pnl")
    if market_value is not None:
        value_html = f'<span class="market-metric-value" style="{_METRIC_VALUE_STYLE}">${market_value:,.2f}</span>'
        if open_pnl is not None:
            pnl_class = "market-up" if open_pnl >= 0 else "market-down"
            pnl_sign = "+" if open_pnl >= 0 else ""
            value_html += (
                f' <span class="market-metric-sub {pnl_class}" style="opacity:0.85;">'
                f'({pnl_sign}${abs(open_pnl):,.2f})</span>'
            )
    else:
        # A real position with no live price yet — session context: a
        # brand-new self-directed account's first trade can show up in
        # get_user_account_positions before SnapTrade has a fresh quote
        # for it. units alone (not a fabricated "$0.00") so this never
        # reads as the position being worthless.
        value_html = f'<span class="market-metric-value" style="{_METRIC_VALUE_STYLE}">—</span>'
    return (
        f'<div class="market-metric">'
        f'<span class="market-metric-label" style="{_METRIC_LABEL_STYLE}">{symbol}{detail} · {units_label} sh</span>'
        f'{value_html}'
        f'</div>'
    )


def render() -> None:
    st.markdown('<div class="page-title page-title-portfolio">My Portfolio</div>', unsafe_allow_html=True)

    portfolio = portfolio_client.fetch_portfolio()
    if portfolio is None:
        # Shows the actual failure (see portfolio_client.last_error) —
        # confirmed live this integration is genuinely fiddly to set up
        # correctly (four separate secrets, a real external API), and a
        # single generic "not configured or unreachable" message made a
        # real live outage impossible to diagnose without direct access
        # to this app's own server logs, which nobody but the deployed
        # process itself ever sees.
        error = portfolio_client.last_error()
        detail = html.escape(error) if error else "not configured yet"
        st.markdown(
            f'<div class="tile"><div class="tile-prev">SnapTrade: {detail}</div></div>',
            unsafe_allow_html=True,
        )
        return

    total_cad = portfolio["total_cad"]
    other = portfolio["other_currency_totals"]
    other_text = " · ".join(f"{amt:,.2f} {cur}" for cur, amt in other.items())
    subtitle = "Wealthsimple" + (f" · {other_text}" if other_text else "")

    # cached_changes(), not fetch_changes() directly — this page render
    # must never be the thing that triggers a real (possibly ~14s,
    # cold-cache) SnapTrade fetch; see portfolio_client's own module
    # comment for the live bug this caused.
    changes = portfolio_client.cached_changes() or {}
    day_change = portfolio_client.daily_change()
    change_html = ""
    if day_change is not None:
        day_change_pct, day_change_amount = day_change["pct"], day_change["amount"]
        direction_class = "market-up" if day_change_pct >= 0 else "market-down"
        sign = "+" if day_change_pct >= 0 else ""
        change_html = (
            f'<span class="tile-value {direction_class}" style="font-size:1.4rem; margin-left:0.6rem;">'
            f'{sign}{day_change_pct:.2f}% ({sign}${abs(day_change_amount):,.2f})</span>'
        )

    # Real, individually-tracked accounts only (see portfolio_client.
    # ACCOUNT_ID_DISPLAY_NAMES) — sorted descending by balance.
    rows = "".join(
        f'<div class="market-metric"><span class="market-metric-label" style="{_METRIC_LABEL_STYLE}">{a["name"]}</span>'
        f'<span class="market-metric-value" style="{_METRIC_VALUE_STYLE}">${a["amount"]:,.2f}</span></div>'
        for a in portfolio["accounts"]
    )

    value_history = portfolio_client.cached_value_history() or []

    # Left: total + account breakdown + holdings. Right: the six trend
    # range cards. This kiosk page never scrolls, so both columns have
    # to actually fit — no activity feed competing for room anymore.
    totals_col, trend_col = st.columns([1, 1.15])

    with totals_col:
        st.markdown(
            f'<div class="tile">'
            f'<div class="tile-label">TOTAL VALUE</div>'
            f'<div class="tile-value-row">'
            f'<div class="tile-value">${total_cad:,.2f}{change_html}</div>'
            f'</div>'
            f'<div class="tile-prev">{subtitle}</div>'
            f'{rows}'
            f'</div>',
            unsafe_allow_html=True,
        )

        positions = portfolio_client.cached_positions()
        if positions:
            holdings_html = "".join(
                f'<div class="market-metric-label" style="opacity:0.7; margin-top:0.4rem;">{html.escape(name)}</div>'
                + "".join(_holding_row(p) for p in held)
                for name, held in positions.items()
            )
            st.markdown(
                f'<div class="tile">'
                f'<div class="tile-label">HOLDINGS</div>'
                f"{holdings_html}"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Session request: "I report my net worth every month... I'd
        # love to have my net worth show up on one of the pages." Hand-
        # reported (see net_worth_tracker.py's own docstring for why —
        # no export/API exists on the phone-app side), so deliberately
        # a small, separate tile rather than blended into the live
        # Wealthsimple total above it — different data, different
        # trust level, shouldn't read as the same live number. Kept to
        # one compact line (this page's own "fits in the entire frame"
        # constraint) rather than a full trend card like the real
        # portfolio history gets.
        latest = net_worth_tracker.latest()
        if latest is not None:
            change = net_worth_tracker.change_from_previous()
            change_html = ""
            if change is not None:
                amt, pct = change["amount_change"], change["pct_change"]
                direction_class = "market-up" if amt >= 0 else "market-down"
                sign = "+" if amt >= 0 else ""
                pct_text = f" ({sign}{pct:.1f}%)" if pct is not None else ""
                change_html = (
                    f'<span class="tile-value {direction_class}" style="font-size:1.1rem; margin-left:0.6rem;">'
                    f'{sign}${amt:,.2f}{pct_text}</span>'
                )
            as_of = datetime.strptime(latest["date"], "%Y-%m-%d").strftime("%b %Y")
            st.markdown(
                f'<div class="tile">'
                f'<div class="tile-label">NET WORTH</div>'
                f'<div class="tile-value-row">'
                f'<div class="tile-value">${latest["amount"]:,.2f}{change_html}</div>'
                f'</div>'
                f'<div class="tile-prev">as of {as_of}, hand-reported</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    with trend_col:
        st.markdown('<div class="market-metric-label" style="opacity:0.7; margin-bottom:0.5rem;">TREND</div>', unsafe_allow_html=True)
        card_cols = st.columns(3)
        for i, (label, key, lookback) in enumerate(_RANGES):
            with card_cols[i % 3]:
                if key == "1d":
                    pct = day_change["pct"] if day_change else changes.get("1d")
                    values: list[float] = []
                else:
                    pct = changes.get(key)
                    values = _slice_history(value_history, lookback)
                st.markdown(_trend_card(label, pct, values), unsafe_allow_html=True)
