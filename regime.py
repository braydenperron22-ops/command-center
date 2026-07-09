"""Synthesizes the individual signals already computed elsewhere in this
app — Home page's macro indicator trends, Internals page's risk-appetite
gauges — into one persistent, plain-language read of where things stand.

Deliberately NOT a formal business-cycle model (Early/Mid/Late/Recession
labels imply absolute-level context this app doesn't track, like where
unemployment actually sits versus full employment — that needs a
reference point beyond "above or below its own 6-month trend"). Instead
this is a transparent composite of the *directions* everything is
already trending in, plus whether market risk appetite is confirming or
diverging from that macro story — itself a genuinely useful signal
(complacent markets against deteriorating data, or a risk-off market
against improving data, are each worth noticing on their own).

US-anchored: every risk-appetite input here (VIX, HYG/LQD, RSP/SPY) is
already US-only elsewhere in this app, so synthesizing across countries
would mean comparing US risk appetite to Canadian growth data — not a
coherent single read. Canada still gets its own indicator tiles on the
Home page; this is an additional layer, not a replacement.
"""

GROWTH_LABELS = {1: "strengthening", 0: "steady", -1: "weakening"}
INFLATION_LABELS = {1: "hot", 0: "stable", -1: "cooling"}
POLICY_LABELS = {1: "tightening", 0: "holding", -1: "easing"}


def _direction(reading: dict | None, invert: bool = False) -> int:
    """above trend -> +1, below -> -1, in-line/missing -> 0. `invert`
    flips it for indicators where "below trend" is the favorable signal
    (unemployment falling is strength, not weakness)."""
    if not reading:
        return 0
    sign = {"above": 1, "below": -1, "in-line": 0}[reading["classification"]]
    return -sign if invert else sign


def _trend_direction(current: float, prior: float) -> int:
    if current > prior:
        return 1
    if current < prior:
        return -1
    return 0


def classify(
    readings: dict,
    confidence: dict | None,
    credit: dict | None,
    breadth: dict | None,
) -> dict | None:
    """`readings` is app.py's existing {(country, key): reading} dict —
    only ("us", ...) entries are used. `confidence`/`credit`/`breadth`
    are market_internals.confidence_index() / price_ratio("HYG","LQD") /
    price_ratio("RSP","SPY") — each already has "value"/"prior_value".
    None if the four macro indicators this needs aren't all available
    yet (e.g. FRED hasn't loaded on a fresh start)."""
    gdp = readings.get(("us", "gdp"))
    unemployment = readings.get(("us", "unemployment"))
    cpi = readings.get(("us", "cpi"))
    policy = readings.get(("us", "policy_rate"))
    if not (gdp and unemployment and cpi and policy):
        return None

    growth_score = _direction(gdp) + _direction(unemployment, invert=True)
    growth = 1 if growth_score > 0 else (-1 if growth_score < 0 else 0)
    inflation = _direction(cpi)
    policy_dir = _direction(policy)

    risk_inputs = [d for d in (confidence, credit, breadth) if d]
    risk_score = sum(_trend_direction(d["value"], d["prior_value"]) for d in risk_inputs)
    risk = 0
    if risk_inputs:
        risk = 1 if risk_score > 0 else (-1 if risk_score < 0 else 0)

    # "Good" macro here means growth not weakening and inflation not
    # accelerating — the plain-language bar for "the story is fine."
    macro_positive = growth >= 0 and inflation <= 0
    risk_positive = risk >= 0
    confirms = macro_positive == risk_positive

    narrative = (
        f"Growth {GROWTH_LABELS[growth]}, inflation {INFLATION_LABELS[inflation]}, "
        f"Fed {POLICY_LABELS[policy_dir]}"
    )
    if risk_inputs:
        narrative += f" — risk appetite {'confirms' if confirms else 'diverges'}"

    return {
        "growth": growth,
        "inflation": inflation,
        "policy": policy_dir,
        "risk": risk if risk_inputs else None,
        "confirms": confirms if risk_inputs else None,
        "narrative": narrative,
    }
