"""Market-volatility toast: alerts when the S&P 500 (or its futures,
outside cash-market hours) is trading outside the one-day range the
options market itself is currently pricing in.

Session request: "change the three standard deviation rule. Take the
VIX value, divide it by sixteen, that gives us the expected daily
market move in either direction. Based on that number, if the market
is trading outside of that band, then you can broadcast it as an
alert... it's dynamically shifting based on what the market is
pricing in." See market_yf_client.expected_daily_move_pct/
volatility_band_status for the actual VIX/16 math — this module is
just the "should this become a one-shot toast today" gate on top of
that shared calculation, same as every other "kind": "weather" toast
source in this app.

"if the futures are included in this... it should also trigger an
alert, so the morning brief is also included" — get_new_alerts() below
runs off market_yf_client.primary_symbol(status), which already swaps
to ES=F futures outside cash-market hours (see that module's own
open/closed/weekend swap), so a pre-market futures move outside the
band alerts here exactly the same way a cash-hours move does; no
separate futures-only path needed. morning_briefing.py's own
_markets_clause additionally surfaces this fact in the brief itself.

Once-per-trading-day gate, not "once ever seen": the VIX-derived band
is only meaningful for TODAY's own pricing, so a fresh alert is
correct the moment a new trading day opens outside its own new band —
unlike the backlog-suppression gate other toast sources need (news,
email, road closures), there's no "is this actually new or just old
backlog" question to guard against here, since "today's move so far"
is current by construction. Per-instance state, same as this app's
other one-shot toasts (road closures, precip) — each kiosk announces
its own first crossing rather than sharing one global "seen" flag."""

from datetime import datetime

import market_yf_client
import ntfy_client
import persisted_state

_STATE_KEY = "market_volatility_alert_state"
_state: dict = dict(persisted_state.load_per_instance(_STATE_KEY, {"date": None, "alerted": False}))


def get_new_alerts(now: datetime) -> list[dict]:
    global _state
    status = market_yf_client.market_status(now)
    if status == "weekend":
        return []
    symbol = market_yf_client.primary_symbol(status)
    quote = market_yf_client.quote_for(symbol)
    if not quote or quote["intraday"] is None:
        return []
    band = market_yf_client.volatility_band_status(quote["intraday"])
    if not band:
        return []

    today_str = now.date().isoformat()
    changed = False
    if _state.get("date") != today_str:
        _state = {"date": today_str, "alerted": False}
        changed = True

    if not band["outside_band"] or _state["alerted"]:
        if changed:
            persisted_state.save_per_instance(_STATE_KEY, _state)
        return []

    _state["alerted"] = True
    persisted_state.save_per_instance(_STATE_KEY, _state)

    pct = quote["intraday"]
    direction = "up" if pct >= 0 else "down"
    label = "S&P 500 futures" if status == "closed" else "S&P 500"
    headline = f"{label} swinging {direction} {abs(pct):.1f}% — outside its priced-in range"
    # Session request: "make it so that literally all of the important
    # things get an alert." Once-per-trading-day by construction (see
    # this module's own docstring) — genuinely rare, genuinely real
    # money moving outside what the options market itself expected, not
    # routine noise.
    ntfy_client.send(title="Market Volatility", message=headline, priority="high", tags="bar_chart")
    return [
        {
            "kind": "weather",
            "severity": "warning",
            "label": "Market Volatility",
            "headline": headline,
            "summary": f"VIX implies a ±{band['expected_move_pct']:.1f}% day; today's move already blew past that.",
        }
    ]
