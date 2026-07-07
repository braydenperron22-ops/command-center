"""Market Internals: risk-appetite and credit gauges — a VIX-based
confidence composite, equal-weight-vs-index volatility, and two classic
credit/breadth ratios (HYG/LQD, RSP/SPY). See market_internals.py for
the exact formulas and data sourcing, including why VIXEQ/VIX is the
one metric here with a slowly-accumulating rather than immediate trend.
"""

import streamlit as st

import market_internals as mi
import tiles

CONFIDENCE_EXPLANATION = (
    "Two VIX-based decay curves — one on today's VIX, one on its 30-day average, "
    "each capped 0-99 — averaged together. Low VIX pushes this toward 99 "
    "(complacent); high VIX pushes it toward 0 (fearful)."
)
VIXEQ_EXPLANATION_EXPANDING = "Expanding — a differentiated, stock-specific market: individual names moving on their own news, not in lockstep."
VIXEQ_EXPLANATION_COMPRESSING = "Compressing toward the index — rising correlation, stocks moving together. Often shows up during broad macro stress."
VIXEQ_EXPLANATION_FLAT = "Stable relationship between constituent-level and index-level volatility."
HYG_LQD_EXPLANATION_UP = "Risk-On — high-yield credit outperforming investment-grade. Credit markets aren't pricing in much stress."
HYG_LQD_EXPLANATION_DOWN = "Risk-Off — flight to quality in credit markets. Often leads equity weakness."
HYG_LQD_EXPLANATION_FLAT = "Credit risk appetite holding steady."
RSP_SPY_EXPLANATION_UP = "Broadening — this rally has real participation beyond a handful of mega-caps."
RSP_SPY_EXPLANATION_DOWN = "Narrowing — gains concentrated in a handful of mega-caps. A classic late-cycle fragility signal."
RSP_SPY_EXPLANATION_FLAT = "Market breadth holding steady."


def _metric_row(label: str, value: str) -> str:
    return (
        f'<div class="market-metric"><span class="market-metric-label">{label}</span>'
        f'<span class="market-metric-value">{value}</span></div>'
    )


def _confidence_band(value: float) -> tuple[str, str]:
    if value >= 75:
        return "Extreme Complacency", "neutral"
    if value >= 55:
        return "Confident", "good"
    if value >= 45:
        return "Neutral", "neutral"
    if value >= 25:
        return "Cautious", "bad"
    return "Fearful", "bad"


def _render_confidence_hero() -> None:
    data = mi.confidence_index()
    if not data:
        st.markdown(
            '<div class="tile"><div class="tile-label">MARKET CONFIDENCE INDEX</div>'
            '<div class="tile-prev">data unavailable</div></div>',
            unsafe_allow_html=True,
        )
        return

    value = data["value"]
    band_label, tone = _confidence_band(value)
    arrow, trend_tone = mi.trend(value, data["prior_value"], higher_is_good=True)
    accent_class = f"tile-accent-{tone}"
    badge_class = f"badge-{tone}"
    sparkline = tiles.sparkline_svg(data["history"], tone)

    st.markdown(
        f"""<div class="tile {accent_class}">
            <div class="tile-label">MARKET CONFIDENCE INDEX</div>
            <div class="tile-value">{value:.0f}</div>
            <div class="badge {badge_class}">{band_label}</div>
            {_metric_row("VIX", f"{data['current_vix']:.2f}")}
            {_metric_row("VIX 30-Day Average", f"{data['vix_30dma']:.2f}")}
            {_metric_row("1-Month Trend", arrow)}
            <div class="confidence-sparkline-wrap">{sparkline}</div>
            <div class="severity-caption">{CONFIDENCE_EXPLANATION}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def _render_vixeq_tile() -> None:
    data = mi.vixeq_vix_ratio()
    if not data:
        st.markdown(
            '<div class="tile"><div class="tile-label">VIXEQ / VIX</div>'
            '<div class="tile-prev">data unavailable</div></div>',
            unsafe_allow_html=True,
        )
        return

    if data["history_days"] < 3:
        st.markdown(
            f"""<div class="tile">
                <div class="tile-label">VIXEQ / VIX</div>
                <div class="tile-value">{data['value']:.2f}</div>
                <div class="tile-prev">Constituent vs. index volatility</div>
                {_metric_row("VIXEQ", f"{data['vixeq']:.2f}")}
                {_metric_row("VIX", f"{data['vix']:.2f}")}
                <div class="severity-caption">Yahoo only exposes a live snapshot for VIXEQ, not history — trend
                builds from one real data point recorded daily as this runs.
                {data['history_days']} day(s) collected so far.</div>
            </div>""",
            unsafe_allow_html=True,
        )
        return

    arrow, tone = mi.trend(data["value"], data["prior_value"], higher_is_good=True)
    caption = {
        "good": VIXEQ_EXPLANATION_EXPANDING,
        "bad": VIXEQ_EXPLANATION_COMPRESSING,
        "neutral": VIXEQ_EXPLANATION_FLAT,
    }[tone]
    sparkline = tiles.sparkline_svg(data["history"], tone)

    st.markdown(
        f"""<div class="tile tile-accent-{tone}">
            <div class="tile-label">VIXEQ / VIX</div>
            <div class="tile-value">{data['value']:.2f}</div>
            <div class="badge badge-{tone}">{arrow}</div>
            {_metric_row("VIXEQ", f"{data['vixeq']:.2f}")}
            {_metric_row("VIX", f"{data['vix']:.2f}")}
            <div class="market-sparkline-wrap">{sparkline}</div>
            <div class="severity-caption">{caption} ({data['history_days']} days of history)</div>
        </div>""",
        unsafe_allow_html=True,
    )


def _render_ratio_tile(label: str, symbol_a: str, symbol_b: str, caption_up: str, caption_down: str, caption_flat: str) -> None:
    data = mi.price_ratio(symbol_a, symbol_b)
    if not data:
        st.markdown(
            f'<div class="tile"><div class="tile-label">{label}</div>'
            '<div class="tile-prev">data unavailable</div></div>',
            unsafe_allow_html=True,
        )
        return

    arrow, tone = mi.trend(data["value"], data["prior_value"], higher_is_good=True)
    caption = {"good": caption_up, "bad": caption_down, "neutral": caption_flat}[tone]
    sparkline = tiles.sparkline_svg(data["history"], tone)

    st.markdown(
        f"""<div class="tile tile-accent-{tone}">
            <div class="tile-label">{label}</div>
            <div class="tile-value">{data['value']:.3f}</div>
            <div class="badge badge-{tone}">{arrow}</div>
            {_metric_row("1-Month Change", f"{(data['value'] / data['prior_value'] - 1) * 100:+.2f}%")}
            <div class="market-sparkline-wrap">{sparkline}</div>
            <div class="severity-caption">{caption}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def render() -> None:
    st.markdown('<div class="page-title page-title-internals">Market Internals</div>', unsafe_allow_html=True)

    _render_confidence_hero()
    st.markdown('<div style="height: 0.3rem;"></div>', unsafe_allow_html=True)

    cols = st.columns(3)
    with cols[0]:
        _render_vixeq_tile()
    with cols[1]:
        _render_ratio_tile(
            "HYG / LQD", "HYG", "LQD",
            HYG_LQD_EXPLANATION_UP, HYG_LQD_EXPLANATION_DOWN, HYG_LQD_EXPLANATION_FLAT,
        )
    with cols[2]:
        _render_ratio_tile(
            "RSP / SPY", "RSP", "SPY",
            RSP_SPY_EXPLANATION_UP, RSP_SPY_EXPLANATION_DOWN, RSP_SPY_EXPLANATION_FLAT,
        )
