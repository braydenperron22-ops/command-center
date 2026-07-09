"""Tracks what the market has done since a genuinely market-moving
headline (Fed/BoC policy or a macro shock) was first seen — the same
"is this substantial enough to matter" gate `classify()` already applies
to those two categories, just pointed at the market's actual reaction
afterward instead of a specific company's price (headline_tickers.py's
job). Shown as a small inline badge on the News page, same visual
language as that ticker badge.

Uses whichever instrument currently best represents "the market" — the
same open/closed/weekend swap (index / futures) already driving the
Markets page and the Govee light — rather than always the raw index,
which barely moves outside regular trading hours and would make a Fed
statement that breaks overnight look like nothing happened. That same
symbol is locked in at the moment a headline is first seen and reused
for every later "current price" read of THAT headline, rather than
re-picked from whatever the status happens to be by the time you're
reading it — otherwise a headline that broke pre-market and is still
showing hours later would end up comparing a futures baseline against
a spot-index current price, picking up the futures/spot basis as if it
were real market movement.
"""

import market_yf_client

# Only these two categories get a baseline captured — a company's
# earnings or a merger headline moving "the market" as a whole isn't a
# meaningful causal claim the way a Fed decision or a macro shock is.
REACTION_CATEGORIES = {"Fed/BoC", "Macro Shock"}


def reaction_symbol() -> str | None:
    """None on weekends — crypto (this status's normal stand-in on the
    Markets page and the Govee light) isn't a meaningful proxy for how
    equities are reacting to Fed or macro news, so it's better to show
    no badge at all than one mislabeled "S&P" while actually tracking
    Bitcoin."""
    status = market_yf_client.market_status()
    if status == "weekend":
        return None
    return market_yf_client.primary_symbol(status)


def price_for(symbol: str) -> float | None:
    quote = market_yf_client.quote_for(symbol)
    if not quote or not quote.get("history"):
        return None
    return quote["history"][-1]


def reaction_badge_html(symbol: str | None, baseline_price: float | None) -> str:
    """A small pill like "S&P +0.4% since" — "" if no baseline was
    captured for this headline (wrong category, or it broke on a
    weekend) or either price is currently unavailable."""
    if symbol is None or baseline_price is None:
        return ""
    current = price_for(symbol)
    if current is None:
        return ""
    pct = (current / baseline_price - 1) * 100
    direction = "market-up" if pct >= 0 else "market-down"
    sign = "+" if pct >= 0 else ""
    return f'<span class="headline-ticker-badge {direction}">S&amp;P {sign}{pct:.1f}% since</span>'
