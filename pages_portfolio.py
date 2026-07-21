"""Portfolio page: real Wealthsimple balances via SnapTrade (session
request: "import portfolio value from wealthsimple into my dashboard").
Split out to its own page from Markets — session feedback the combined
tile read too big/heavy sharing a page with the compact instrument
grid, and this has since grown its own multi-period detail (1D/6M/YTD)
that deserves the room.

Wealthsimple has no public API of its own; SnapTrade is the account-
aggregation layer several consumer portfolio-tracker apps (Blossom
included) already use to connect to it — see portfolio_client.py for
the actual fetch/consolidation/period-change logic.
"""

import html
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

import portfolio_client
from config import TIMEZONE


# Kiosk viewed from across a room — bigger than this app's default
# market-metric sizing (1.3rem/0.85rem), which was tuned for Markets'
# dense 7-column grid, not a single full-width page like this one.
_METRIC_LABEL_STYLE = "font-size:1.05rem;"
_METRIC_VALUE_STYLE = "font-size:1.7rem; font-weight:600;"

# Session feedback: a plain sentence per row ("Invested $18.00 · RRSP ·
# Jul 16") read as an undifferentiated wall of gray text — no way to
# tell a dividend from a withdrawal without reading every word. Each
# type gets its own colored tag instead, scannable at a glance; label
# text stays short and consistent rather than reusing SnapTrade's own
# freeform "description" sentences.
_ACTIVITY_TAGS = {
    "CONTRIBUTION": ("INVESTED", "#A78BFA"),  # this page's own accent — new money into the portfolio
    "WITHDRAWAL": ("WITHDRAWAL", "#FF9F0A"),
    "DIVIDEND": ("DIVIDEND", "#32D74B"),
    "INTEREST": ("INTEREST", "#30D5C8"),
    "BUY": ("BUY", "#5AC8FA"),
    "SELL": ("SELL", "#64D2FF"),
}


def _period_metric(label: str, pct: float | None) -> str:
    if pct is None:
        return (
            f'<div class="market-metric"><span class="market-metric-label" style="{_METRIC_LABEL_STYLE}">{label}</span>'
            f'<span class="market-metric-value" style="{_METRIC_VALUE_STYLE}">—</span></div>'
        )
    direction_class = "market-up" if pct >= 0 else "market-down"
    sign = "+" if pct >= 0 else ""
    return (
        f'<div class="market-metric"><span class="market-metric-label" style="{_METRIC_LABEL_STYLE}">{label}</span>'
        f'<span class="market-metric-value {direction_class}" style="{_METRIC_VALUE_STYLE}">{sign}{pct:.2f}%</span></div>'
    )


def _activity_row(activity: dict, today_local) -> str:
    activity_date = datetime.fromisoformat(activity["date"].replace("Z", "+00:00"))
    activity_date_local = activity_date.astimezone(ZoneInfo(TIMEZONE))
    date_label = f"{activity_date_local.strftime('%b')} {activity_date_local.day}"
    # Already a short display name (FHSA/TFSA/RRSP/EMERGENCY FUND — see
    # portfolio_client.ACCOUNT_DISPLAY_NAMES), nothing left to trim here.
    account = html.escape(activity["account"])
    amount = activity["amount"]
    direction_class = "market-up" if amount >= 0 else "market-down"
    sign = "+" if amount >= 0 else "-"

    tag_label, tag_color = _ACTIVITY_TAGS.get(activity["type"], (activity["type"], "#ABB2C4"))
    tag_html = f'<span class="activity-tag" style="color:{tag_color}; border-color:{tag_color};">{tag_label}</span>'
    # Session request: a pulsing red dot on anything dated today — the
    # automated-investing accounts do their own thing all day with no
    # other heads-up, so "did something happen today" needs to be
    # answerable at a glance rather than by reading every date. Compared
    # in local time, not the API's own UTC trade_date, so a transaction
    # late in the evening (well past UTC's own midnight rollover) still
    # correctly reads as "today."
    today_dot_html = '<span class="activity-today-dot"></span>' if activity_date_local.date() == today_local else ""
    # The one piece of detail a bare category tag can't carry — which
    # security a trade/dividend actually touched. Nothing extra for
    # CONTRIBUTION/WITHDRAWAL/INTEREST: the tag plus the amount already
    # says everything there is to say about those.
    symbol = activity.get("symbol")
    detail = f" · {html.escape(symbol)}" if symbol else ""

    return (
        f'<div class="market-metric activity-row">'
        f'<span class="activity-row-left">{today_dot_html}{tag_html}'
        f'<span class="market-metric-label">{account}{detail} · {date_label}</span></span>'
        f'<span class="market-metric-value {direction_class}">{sign}${abs(amount):,.2f}</span>'
        f"</div>"
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
    # No account count here — the breakdown below only ever lists the 4
    # tracked accounts (see portfolio_client.ACCOUNT_DISPLAY_NAMES)
    # while this total still includes MSB, so a literal "N accounts"
    # count would misleadingly imply the rows below sum to this total.
    subtitle = "Wealthsimple" + (f" · {other_text}" if other_text else "")

    changes = portfolio_client.fetch_changes() or {}
    day_change_pct = changes.get("1d")
    change_html = ""
    if day_change_pct is not None:
        direction_class = "market-up" if day_change_pct >= 0 else "market-down"
        sign = "+" if day_change_pct >= 0 else ""
        change_html = f'<span class="tile-value {direction_class}" style="font-size:1.4rem; margin-left:0.6rem;">{sign}{day_change_pct:.2f}%</span>'

    # Already just the 4 tracked/renamed accounts, sorted descending by
    # balance (see portfolio_client.ACCOUNT_DISPLAY_NAMES).
    rows = "".join(
        f'<div class="market-metric"><span class="market-metric-label" style="{_METRIC_LABEL_STYLE}">{a["name"]}</span>'
        f'<span class="market-metric-value" style="{_METRIC_VALUE_STYLE}">${a["amount"]:,.2f}</span></div>'
        for a in portfolio["accounts"]
    )

    # Totals (left) and activity (right) side by side — this kiosk's
    # own page never scrolls, so stacking all three tiles vertically
    # (session feedback) pushed Recent Activity below the visible
    # screen on the actual monitor. A 2-column split keeps totals and
    # transactions both on screen at once.
    totals_col, activity_col = st.columns(2)

    with totals_col:
        # One flat line, no embedded newlines/indentation — same bug
        # class fixed in pages_radar.py this session: an interpolated
        # piece being "" whenever there's nothing to show (no accounts,
        # no change_html) would leave a blank line mid-HTML on a
        # multi-line f-string and get the whole tile rendered as
        # literal text instead of parsed.
        #
        # Plain .tile-value (2.6rem), not the market-hero-value override
        # (1.9rem) that Markets uses to fit 7 columns side by side —
        # this page has no neighboring tiles to squeeze against.
        st.markdown(
            f'<div class="tile">'
            f'<div class="tile-label">TOTAL VALUE</div>'
            f'<div class="tile-value">${total_cad:,.2f}{change_html}</div>'
            f'<div class="tile-prev">{subtitle}</div>'
            f'{rows}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # 6-month/YTD periods exclude any account whose own history
        # doesn't reach back that far (see
        # portfolio_client._period_change_pct) — newer accounts just
        # don't have an opinion yet rather than reading as 0% growth,
        # which would be a lie about money that was never actually
        # invested for that long.
        st.markdown(
            f'<div class="tile">'
            f'<div class="tile-label">PERFORMANCE</div>'
            f'{_period_metric("1 Day", changes.get("1d"))}'
            f'{_period_metric("6 Month", changes.get("6m"))}'
            f'{_period_metric("YTD", changes.get("ytd"))}'
            f'</div>',
            unsafe_allow_html=True,
        )

    with activity_col:
        # PORTFOLIO_INVESTMENT/WRITE_OFF/FEE rows already filtered out
        # at the source (see portfolio_client._ACTIVITY_TYPES), and
        # only the 4 tracked accounts are included at all — what's left
        # is real deposits/withdrawals/trades/dividends/interest, the
        # things actually worth glancing at. A bigger limit than before
        # now that activity has its own dedicated column instead of
        # competing with two other tiles for vertical space.
        activities = portfolio_client.fetch_activities(limit=14)
        if activities:
            today_local = datetime.now(ZoneInfo(TIMEZONE)).date()
            activity_rows = "".join(_activity_row(a, today_local) for a in activities)
            st.markdown(
                f'<div class="tile">'
                f'<div class="tile-label">RECENT ACTIVITY</div>'
                f"{activity_rows}"
                f"</div>",
                unsafe_allow_html=True,
            )
