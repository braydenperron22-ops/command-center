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

import streamlit as st

import portfolio_client


def _period_metric(label: str, pct: float | None) -> str:
    if pct is None:
        return f'<div class="market-metric"><span class="market-metric-label">{label}</span><span class="market-metric-value">—</span></div>'
    direction_class = "market-up" if pct >= 0 else "market-down"
    sign = "+" if pct >= 0 else ""
    return (
        f'<div class="market-metric"><span class="market-metric-label">{label}</span>'
        f'<span class="market-metric-value {direction_class}">{sign}{pct:.2f}%</span></div>'
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
    subtitle = f"Wealthsimple · {len(portfolio['accounts'])} accounts" + (f" · {other_text}" if other_text else "")

    changes = portfolio_client.fetch_changes() or {}
    day_change_pct = changes.get("1d")
    change_html = ""
    if day_change_pct is not None:
        direction_class = "market-up" if day_change_pct >= 0 else "market-down"
        sign = "+" if day_change_pct >= 0 else ""
        change_html = f'<span class="tile-value {direction_class}" style="font-size:1rem; margin-left:0.6rem;">{sign}{day_change_pct:.2f}%</span>'

    rows = "".join(
        f'<div class="market-metric"><span class="market-metric-label">{a["name"]}</span>'
        f'<span class="market-metric-value">${a["amount"]:,.2f}</span></div>'
        for a in portfolio["accounts"]
    )
    # One flat line, no embedded newlines/indentation — same bug class
    # fixed in pages_radar.py this session: an interpolated piece being
    # "" whenever there's nothing to show (no accounts, no change_html)
    # would leave a blank line mid-HTML on a multi-line f-string and get
    # the whole tile rendered as literal text instead of parsed.
    st.markdown(
        f'<div class="tile">'
        f'<div class="tile-label">TOTAL VALUE</div>'
        f'<div class="tile-value market-hero-value">${total_cad:,.2f}{change_html}</div>'
        f'<div class="tile-prev">{subtitle}</div>'
        f'{rows}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # 6-month/YTD periods exclude any account whose own history doesn't
    # reach back that far (see portfolio_client._period_change_pct) —
    # newer accounts (FHSA/RRSP here) just don't have an opinion yet
    # rather than reading as 0% growth, which would be a lie about
    # money that was never actually invested for that long.
    st.markdown(
        f'<div class="tile">'
        f'<div class="tile-label">PERFORMANCE</div>'
        f'{_period_metric("1 Day", changes.get("1d"))}'
        f'{_period_metric("6 Month", changes.get("6m"))}'
        f'{_period_metric("YTD", changes.get("ytd"))}'
        f'</div>',
        unsafe_allow_html=True,
    )
