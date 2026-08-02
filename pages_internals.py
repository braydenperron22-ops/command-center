"""Market Internals: the real live Fear & Greed Index (see
market_internals.py — pulled straight from feargreedmeter.com's own
computed state, CNN's own site blocks non-browser requests outright),
plus two supporting credit/breadth ratios and the Shiller CAPE ratio.

Verdict-first layout — session feedback: "I like the big numbers...
I should be able to understand what the numbers mean at a glance and
not have these super tiny little context bars that I cannot read
unless I'm an inch away from the monitor." Every tile leads with a
big plain-English verdict in its tone color (RISK-ON / NARROW RALLY /
EXPENSIVE) with the raw number kept big right above it, and one short
readable context line — not the paragraph-length small-print captions
this page used to fine-print at the bottom of each tile. Labels name
the concept first and the ticker math second ("CREDIT APPETITE ·
HYG/LQD") for the same reason.
"""

import streamlit as st

import market_internals as mi

GAUGE_CONTEXT_EXTERNAL = "The market's mood right now — the same seven-factor index CNN publishes."
GAUGE_CONTEXT_COMPUTED = "Estimated from four of CNN's seven factors — feargreedmeter.com is unreachable."

# Per-tone verdict + one-line context for each supporting tile. The
# verdict is the headline; the context line is the "so what."
HYG_LQD_TILE = {
    "label": "CREDIT APPETITE · HYG/LQD",
    "good": ("RISK-ON", "Junk bonds outperforming — credit markets aren't worried."),
    "bad": ("RISK-OFF", "Money fleeing to safer bonds — often leads stocks lower."),
    "neutral": ("STEADY", "Credit risk appetite holding about level."),
}
RSP_SPY_TILE = {
    "label": "RALLY BREADTH · RSP/SPY",
    "good": ("BROADENING", "Most stocks are joining in — real participation."),
    "bad": ("NARROWING", "A handful of mega-caps doing all the lifting."),
    "neutral": ("STEADY", "Market breadth holding about level."),
}


def _gauge_band(value: float) -> tuple[str, str]:
    """Ten bands instead of CNN's own five — session request: "expand on
    the typical Extreme Fear, Fear, Neutral, Greed, Extreme Greed bars
    ... make it so its 10 labels instead of just 5." Each of CNN's five
    real published bands (Extreme Fear <25, Fear 25-44, Neutral 45-54,
    Greed 55-74, Extreme Greed 75+) is split in half rather than
    redrawing the boundaries from scratch, so the same four threshold
    points (25/45/55/75) still decide "good"/"bad"/"neutral" tone/color
    exactly as before — only the label text gets finer-grained, the
    coloring behavior is unchanged. Symmetric naming (Extreme/Severe/
    [plain]/Mild/Slight, mirrored on each side of the midpoint) rather
    than CNN's own asymmetric band widths translating awkwardly into
    ten uneven names."""
    if value >= 87.5:
        return "Extreme Greed", "good"
    if value >= 75:
        return "Severe Greed", "good"
    if value >= 65:
        return "Greed", "good"
    if value >= 55:
        return "Mild Greed", "good"
    if value >= 50:
        return "Slight Greed", "neutral"
    if value >= 45:
        return "Slight Fear", "neutral"
    if value >= 35:
        return "Mild Fear", "bad"
    if value >= 25:
        return "Fear", "bad"
    if value >= 12.5:
        return "Severe Fear", "bad"
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
    raw_arrow, _ = mi.trend(value, yesterday if yesterday is not None else data["prior_value"], higher_is_good=True)
    # Session report: "it says Fear (arrow up rising) which is actually
    # not fearful so make it not sound counterintuitive." trend()'s own
    # "↑ Rising"/"↓ Falling" describes the raw NUMBER — but a rising
    # score means LESS fear (moving toward Greed, not deeper into it),
    # so "Fear · ↑ Rising" read as if fear itself were increasing, the
    # opposite of what's true. Same fix the ratio tiles below already
    # use for this exact class of problem (just the arrow glyph, paired
    # with a direction-aware word instead of "Rising"/"Falling") —
    # "Toward Greed"/"Toward Fear" is correct in every band and never
    # contradicts whichever label happens to be showing.
    glyph = raw_arrow.split()[0]
    if glyph == "↑":
        direction = "Toward Greed"
    elif glyph == "↓":
        direction = "Toward Fear"
    else:
        direction = "Flat"
    context = GAUGE_CONTEXT_EXTERNAL if data.get("source") == "external" else GAUGE_CONTEXT_COMPUTED

    st.markdown(
        f"""<div class="tile tile-accent-{tone} confidence-hero">
            <div class="tile-label">FEAR &amp; GREED INDEX</div>
            <div class="confidence-value">{value:.0f}</div>
            <div class="internals-verdict internals-verdict-{tone}">{band_label} · {glyph} {direction}</div>
            <div class="internals-context">{context}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def _render_cape_tile() -> None:
    data = mi.shiller_cape()
    if not data or data.get("value") is None:
        st.markdown(
            '<div class="tile"><div class="tile-label">VALUATION · SHILLER CAPE</div>'
            '<div class="tile-prev">data unavailable</div></div>',
            unsafe_allow_html=True,
        )
        return

    value = data["value"]
    diff_pct = (value - mi.CAPE_HISTORICAL_AVERAGE) / mi.CAPE_HISTORICAL_AVERAGE * 100
    if diff_pct > 15:
        verdict, tone = "EXPENSIVE", "bad"
    elif diff_pct < -15:
        verdict, tone = "CHEAP", "good"
    else:
        verdict, tone = "FAIR VALUE", "neutral"
    direction = "above" if diff_pct >= 0 else "below"
    context = f"Stocks priced {abs(diff_pct):.0f}% {direction} their long-run average, vs 145 years of earnings."

    st.markdown(
        f"""<div class="tile tile-accent-{tone} internals-ratio-tile">
            <div class="tile-label">VALUATION · SHILLER CAPE</div>
            <div class="tile-value">{value:.1f}</div>
            <div class="internals-verdict internals-verdict-{tone}">{verdict}</div>
            <div class="internals-context">{context}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def _render_ratio_tile(tile: dict, symbol_a: str, symbol_b: str) -> None:
    data = mi.price_ratio(symbol_a, symbol_b)
    if not data:
        st.markdown(
            f'<div class="tile"><div class="tile-label">{tile["label"]}</div>'
            '<div class="tile-prev">data unavailable</div></div>',
            unsafe_allow_html=True,
        )
        return

    arrow, tone = mi.trend(data["value"], data["prior_value"], higher_is_good=True)
    verdict, context = tile[tone]
    # Just the arrow glyph, not trend()'s full "↑ Rising" wording — the
    # verdict word next to it already says what the direction means.
    st.markdown(
        f"""<div class="tile tile-accent-{tone} internals-ratio-tile">
            <div class="tile-label">{tile['label']}</div>
            <div class="tile-value">{data['value']:.3f}</div>
            <div class="internals-verdict internals-verdict-{tone}">{arrow.split()[0]} {verdict}</div>
            <div class="internals-context">{context}</div>
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
        _render_ratio_tile(HYG_LQD_TILE, "HYG", "LQD")
    with cols[2]:
        _render_ratio_tile(RSP_SPY_TILE, "RSP", "SPY")
