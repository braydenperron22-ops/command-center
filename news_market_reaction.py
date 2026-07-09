"""Tracks what the S&P 500 has done since a genuinely market-moving
headline (Fed/BoC policy or a macro shock) was first seen — the same
"is this substantial enough to matter" gate `classify()` already applies
to those two categories, just pointed at the market's actual reaction
afterward instead of a specific company's price (headline_tickers.py's
job). Shown as a small inline badge on the News page, same visual
language as that ticker badge.
"""

import market_yf_client

# Only these two categories get a baseline captured — a company's
# earnings or a merger headline moving "the market" as a whole isn't a
# meaningful causal claim the way a Fed decision or a macro shock is.
REACTION_CATEGORIES = {"Fed/BoC", "Macro Shock"}


def current_spx_price() -> float | None:
    """Latest close from the same cached quote the Markets page and the
    Govee light's color both already use — free once anything's warmed
    the cache, no dedicated fetch."""
    quote = market_yf_client.quote_for("^GSPC")
    if not quote or not quote.get("history"):
        return None
    return quote["history"][-1]


def reaction_badge_html(baseline_price: float | None) -> str:
    """A small pill like "S&P +0.4% since" — "" if no baseline was
    captured for this headline (wrong category) or either price is
    currently unavailable."""
    if baseline_price is None:
        return ""
    current = current_spx_price()
    if current is None:
        return ""
    pct = (current / baseline_price - 1) * 100
    direction = "market-up" if pct >= 0 else "market-down"
    sign = "+" if pct >= 0 else ""
    return f'<span class="headline-ticker-badge {direction}">S&amp;P {sign}{pct:.1f}% since</span>'
