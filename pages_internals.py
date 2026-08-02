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
    ... make it so its 10 labels instead of just 5," then refined:
    "the context labels should only be one word you can expand beyond
    just fear and greed." Each of CNN's five real published bands
    (Extreme Fear <25, Fear 25-44, Neutral 45-54, Greed 55-74, Extreme
    Greed 75+) is split in half, keeping the same four threshold points
    (25/45/55/75) so "good"/"bad"/"neutral" tone/color is unchanged —
    but rather than "Mild Fear"/"Slight Greed"-style two-word compounds,
    each band gets its own distinct single word drawn from real,
    commonly-used market-sentiment vocabulary (the same "Fear"/"Greed"/
    "Euphoria"/"Panic" language financial press already uses for these
    exact states, not invented terms) — ordered fear -> greed:
    Panic, Dread, Fear, Worry, Caution, Calm, Hope, Optimism, Greed,
    Euphoria."""
    if value >= 87.5:
        return "Euphoria", "good"
    if value >= 75:
        return "Greed", "good"
    if value >= 65:
        return "Optimism", "good"
    if value >= 55:
        return "Hope", "good"
    if value >= 50:
        return "Calm", "neutral"
    if value >= 45:
        return "Caution", "neutral"
    if value >= 35:
        return "Worry", "bad"
    if value >= 25:
        return "Fear", "bad"
    if value >= 12.5:
        return "Dread", "bad"
    return "Panic", "bad"


# Session follow-up: "every context label should have different colours
# attached to it" — the 3-bucket good/bad/neutral tone above is still
# what the shared .tile-accent-* top strip uses (consistent with the
# other 3 tiles on this page, which really do only have 3 states each),
# but the word itself now gets its own distinct color per band instead
# of reusing the same red/blue/green three times over. A single warm-to
# -cool sweep (red -> orange -> amber -> yellow -> green), the same
# red-to-green language every fear/greed dial already uses, rather than
# introducing an unrelated hue like blue for the middle bands.
_BAND_COLOR = {
    "Panic": "#E0302A",
    "Dread": "#F0483A",
    "Fear": "#FF6B35",
    "Worry": "#FF9A3D",
    "Caution": "#FFC145",
    "Calm": "#E4D651",
    "Hope": "#B9D953",
    "Optimism": "#8CCB4E",
    "Greed": "#56B84B",
    "Euphoria": "#22A64A",
}


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
    band_color = _BAND_COLOR[band_label]
    # Session follow-up: "instead of saying rising or falling just show
    # the amount its risen or fallen by in the last week" (data["one_
    # week_ago"], same field feargreedmeter.com's own payload / the
    # computed fallback's 5-trading-day-back reading already carry),
    # then refined further: "change the +1 this week to show an up or
    # down arrow instead more obvious and make it green or red based on
    # how its moving." A bold filled triangle (▲/▼) reads more clearly
    # at a glance than the previous thin ↑/↓, and it's colored on its
    # own — green for a rising score, red for falling — independent of
    # band_color above, since "the number moved up" and "which mood
    # band we're in" are two different facts that can disagree (e.g.
    # still in Fear territory but moving toward Greed). Omitted
    # entirely, same "just omit it" rule every other optional reading
    # on this page follows, on the rare chance a week-ago value isn't
    # available yet.
    one_week_ago = data.get("one_week_ago")
    if one_week_ago is not None:
        change = value - float(one_week_ago)
        if change > 0:
            change_arrow, change_color = "▲", "#32D74B"
        elif change < 0:
            change_arrow, change_color = "▼", "#FF6961"
        else:
            change_arrow, change_color = "●", "#ECECF1"
        change_html = (
            f'<span class="internals-verdict-sep">·</span>'
            f'<span style="color:{change_color}">{change_arrow} {abs(change):.0f} this week</span>'
        )
    else:
        change_html = ""
    context = GAUGE_CONTEXT_EXTERNAL if data.get("source") == "external" else GAUGE_CONTEXT_COMPUTED

    st.markdown(
        f"""<div class="tile tile-accent-{tone} confidence-hero" style="--tile-accent: {band_color};">
            <div class="tile-label">FEAR &amp; GREED INDEX</div>
            <div class="confidence-value">{value:.0f}</div>
            <div class="internals-verdict"><span style="color:{band_color}">{band_label}</span>{change_html}</div>
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
    st.markdown('<div class="internals-section-gap"></div>', unsafe_allow_html=True)

    cols = st.columns(3)
    with cols[0]:
        _render_cape_tile()
    with cols[1]:
        _render_ratio_tile(HYG_LQD_TILE, "HYG", "LQD")
    with cols[2]:
        _render_ratio_tile(RSP_SPY_TILE, "RSP", "SPY")
