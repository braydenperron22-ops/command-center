"""Market Internals: the real live Fear & Greed Index (see
market_internals.py — pulled straight from feargreedmeter.com's own
computed state, CNN's own site blocks non-browser requests outright),
plus two supporting credit/breadth ratios and the Shiller CAPE ratio.

Session request: "wipe it" — the previous version's hand-tuned VIX
exponential-decay "Confidence Index" and its VIXEQ/VIX tile (which
needed weeks of locally-accumulated history that almost certainly
reset on every redeploy) are both gone. The gauge is the headline —
bigger type, its own row, real historical context underneath — with
the three supporting tiles below it, not equal-weight peers.
"""

import streamlit as st

import market_internals as mi

GAUGE_EXPLANATION_EXTERNAL = (
    "Real-time Fear &amp; Greed Index from feargreedmeter.com, tracking the same seven-factor "
    "methodology CNN's own index uses."
)
GAUGE_EXPLANATION_COMPUTED = (
    "feargreedmeter.com is unreachable right now, so this is a fallback: four of CNN's own seven "
    "Fear &amp; Greed components — Momentum, Volatility, Junk Bond Demand, and Safe Haven Demand — "
    "each scored by how far it's deviated from its own 1-year norm, averaged equally."
)
HYG_LQD_EXPLANATION_UP = "Risk-On — high-yield credit outperforming investment-grade."
HYG_LQD_EXPLANATION_DOWN = "Risk-Off — flight to quality in credit markets. Often leads equity weakness."
HYG_LQD_EXPLANATION_FLAT = "Credit risk appetite holding steady."
RSP_SPY_EXPLANATION_UP = "Broadening — this rally has real participation beyond a handful of mega-caps."
RSP_SPY_EXPLANATION_DOWN = "Narrowing — gains concentrated in a handful of mega-caps."
RSP_SPY_EXPLANATION_FLAT = "Market breadth holding steady."


def _gauge_band(value: float) -> tuple[str, str]:
    """CNN's own five bands, and their own intuitive fear=red/greed=green
    coloring — unlike the old page's asymmetric treatment (which colored
    high confidence "neutral" rather than "good"), both ends of a
    genuinely balanced fear<->greed scale get their obvious color."""
    if value >= 75:
        return "Extreme Greed", "good"
    if value >= 55:
        return "Greed", "good"
    if value >= 45:
        return "Neutral", "neutral"
    if value >= 25:
        return "Fear", "bad"
    return "Extreme Fear", "bad"


def _render_gauge_hero() -> None:
    data = mi.fear_greed_index()
    if not data:
        st.markdown(
            '<div class="tile"><div class="tile-label">FEAR &amp; GREED INDEX</div>'
            '<div class="tile-prev">data unavailable</div></div>',
            unsafe_allow_html=True,
        )
        return

    value = data["value"]
    band_label, tone = _gauge_band(value)
    yesterday = data.get("yesterday")
    arrow, _ = mi.trend(value, yesterday if yesterday is not None else data["prior_value"], higher_is_good=True)
    accent_class = f"tile-accent-{tone}"
    badge_class = f"badge-{tone}"
    caption = GAUGE_EXPLANATION_EXTERNAL if data.get("source") == "external" else GAUGE_EXPLANATION_COMPUTED

    st.markdown(
        f"""<div class="tile {accent_class} confidence-hero">
            <div class="tile-label">FEAR &amp; GREED INDEX</div>
            <div class="confidence-value">{value:.0f}</div>
            <div class="badge {badge_class}">{band_label} · {arrow}</div>
            <div class="severity-caption">{caption}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def _render_cape_tile() -> None:
    data = mi.shiller_cape()
    if not data or data.get("value") is None:
        st.markdown(
            '<div class="tile"><div class="tile-label">SHILLER CAPE</div>'
            '<div class="tile-prev">data unavailable</div></div>',
            unsafe_allow_html=True,
        )
        return

    value = data["value"]
    diff_pct = (value - mi.CAPE_HISTORICAL_AVERAGE) / mi.CAPE_HISTORICAL_AVERAGE * 100
    tone = "bad" if diff_pct > 15 else "good" if diff_pct < -15 else "neutral"
    direction = "above" if diff_pct >= 0 else "below"

    st.markdown(
        f"""<div class="tile tile-accent-{tone} internals-ratio-tile">
            <div class="tile-label">SHILLER CAPE</div>
            <div class="tile-value">{value:.1f}</div>
            <div class="badge badge-{tone}">{abs(diff_pct):.0f}% {direction} historical average</div>
            <div class="severity-caption">Cyclically-adjusted P/E — S&amp;P 500 price over 10-year
            average inflation-adjusted earnings. Compared against {mi.CAPE_HISTORICAL_AVERAGE},
            the long-run average for the full series back to 1881.</div>
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

    st.markdown(
        f"""<div class="tile tile-accent-{tone} internals-ratio-tile">
            <div class="tile-label">{label}</div>
            <div class="tile-value">{data['value']:.3f}</div>
            <div class="badge badge-{tone}">{arrow}</div>
            <div class="severity-caption">{caption}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def render() -> None:
    st.markdown('<div class="page-title page-title-internals">Market Internals</div>', unsafe_allow_html=True)

    _render_gauge_hero()
    st.markdown('<div style="height: 0.4rem;"></div>', unsafe_allow_html=True)

    cols = st.columns(3)
    with cols[0]:
        _render_cape_tile()
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
