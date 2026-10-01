"""Net Worth page — session follow-up after the tile crammed onto the
Portfolio page turned out to be too tight to actually see, "especially
with the morning brief on": "I'd make it its own page, to be honest."
Same hand-reported data as before (see net_worth_tracker.py's own
docstring for why this can't be pulled automatically), just given a
whole page's worth of room instead of one secondary tile.

Not part of the normal PAGES rotation yet (see config.py's own PAGES
comment on this pattern — pages_timeline.py started the same way)
— reachable via ?page=net_worth and the screen picker, same
"new, not yet lived with" treatment, not because it needs hiding.
"""

from datetime import datetime

import streamlit as st

import net_worth_tracker
import tiles

_CHART_COLOR = {"good": "#3DFF7A", "bad": "#FF5C4D"}


def render() -> None:
    st.markdown('<div class="page-title">Net Worth</div>', unsafe_allow_html=True)

    nw_history = net_worth_tracker.history()
    latest = net_worth_tracker.latest()
    if latest is None:
        st.markdown(
            '<div class="tile"><div class="tile-prev">Nothing reported yet — '
            'tell me a number and it shows up here.</div></div>',
            unsafe_allow_html=True,
        )
        return

    change = net_worth_tracker.change_from_previous()
    change_html = ""
    if change is not None:
        amt, pct = change["amount_change"], change["pct_change"]
        direction_class = "market-up" if amt >= 0 else "market-down"
        sign = "+" if amt >= 0 else ""
        pct_text = f" ({sign}{pct:.1f}%)" if pct is not None else ""
        change_html = (
            f'<span class="tile-value {direction_class}" style="font-size:1.8rem; margin-left:0.8rem;">'
            f'{sign}${amt:,.2f}{pct_text}</span>'
        )
    as_of = datetime.strptime(latest["date"], "%Y-%m-%d").strftime("%B %Y")

    amounts = [e["amount"] for e in nw_history]
    chart_html = ""
    if len(amounts) >= 2:
        tone = "good" if amounts[-1] >= amounts[0] else "bad"
        # Same bigger-centerpiece treatment as pages_brayden_index.py's
        # own chart (brighter good/bad hues, thicker stroke) — this is
        # now the single focal point of a whole page, not a secondary
        # tile squeezed under two others.
        chart_html = tiles.sparkline_svg(
            amounts, tone, width=900, height=220,
            color=_CHART_COLOR.get(tone), stroke_width=3.0,
        )

    st.markdown(
        f'<div class="tile" style="padding:1.5rem 1.8rem;">'
        f'<div class="tile-label">CURRENT NET WORTH</div>'
        f'<div class="tile-value-row">'
        f'<div class="tile-value" style="font-size:3rem;">${latest["amount"]:,.2f}{change_html}</div>'
        f'</div>'
        f'<div class="tile-prev">as of {as_of}, hand-reported</div>'
        f'<div style="margin-top:1rem;">{chart_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if len(nw_history) < 2:
        return

    first_entry = nw_history[0]
    high_entry = max(nw_history, key=lambda e: e["amount"])
    low_entry = min(nw_history, key=lambda e: e["amount"])
    total_change = latest["amount"] - first_entry["amount"]
    total_pct = (total_change / first_entry["amount"] * 100) if first_entry["amount"] else None
    total_sign = "+" if total_change >= 0 else ""
    total_class = "market-up" if total_change >= 0 else "market-down"
    first_label = datetime.strptime(first_entry["date"], "%Y-%m-%d").strftime("%b %Y")
    high_label = datetime.strptime(high_entry["date"], "%Y-%m-%d").strftime("%b %Y")
    low_label = datetime.strptime(low_entry["date"], "%Y-%m-%d").strftime("%b %Y")

    stat_cols = st.columns(3)
    _stats = [
        (f"SINCE {first_label.upper()}", f"{total_sign}${total_change:,.2f}" + (f" ({total_sign}{total_pct:.0f}%)" if total_pct is not None else ""), total_class),
        ("ALL-TIME HIGH", f"${high_entry['amount']:,.2f}", None),
        ("ALL-TIME LOW", f"${low_entry['amount']:,.2f}", None),
    ]
    _sub = {0: "", 1: f"{high_label}", 2: f"{low_label}"}
    for i, (label, value, tone_class) in enumerate(_stats):
        with stat_cols[i]:
            value_class = f"tile-value {tone_class}" if tone_class else "tile-value"
            st.markdown(
                f'<div class="tile">'
                f'<div class="tile-label">{label}</div>'
                f'<div class="{value_class}" style="font-size:1.6rem;">{value}</div>'
                + (f'<div class="tile-prev">{_sub[i]}</div>' if _sub[i] else "")
                + f'</div>',
                unsafe_allow_html=True,
            )

    # Deliberately no full month-by-month list below this — the chart
    # above already encodes the whole history visually, these three
    # stats cover the numbers worth calling out, and this list would
    # only ever grow (every month, forever) on a kiosk page that's
    # supposed to never scroll. A raw table of 30+ months a few years
    # from now would blow this page's own "fits in the frame" budget
    # for no real gain over just looking at the line.
