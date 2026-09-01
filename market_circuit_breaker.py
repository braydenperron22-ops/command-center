"""Real NYSE Market-Wide Circuit Breaker (MWCB) detection — session
request: "market circuit breaker events. They're super rare, but I
think it's bound to be super duper important if it were to happen."

Official NYSE Rule 7.12 thresholds, cross-checked live 2026-08-31
against NYSE's own MWCB FAQ and SEC investor.gov: a decline of 7%
(Level 1), 13% (Level 2), or 20% (Level 3) in the S&P 500 INDEX (the
cash index specifically — the rule is about ^GSPC, not futures) from
the PRIOR TRADING DAY's closing value. Level 1/2 actually halt
market-wide trading for 15 minutes only when triggered before 3:25pm
ET; at or after 3:25pm the decline is still real but doesn't trigger a
halt. Level 3 halts trading for the remainder of the day whenever it
happens.

Deliberately NOT market_yf_client.quote_for()'s own "intraday" field —
that's computed against TODAY's own Open (or a same-close fallback
only when Open itself is missing, see that module's own comment), not
the prior day's close specifically the real MWCB rule requires. This
reuses that same function's already-fetched "history" (a plain
chronological list of closes, one real yfinance call, no new fetch)
and computes % change against history[-2] — the actual prior trading
day's close — directly.

Deliberately no AI rewrite anywhere in this module, unlike this app's
other conversational toast sources (weather, road closures) — the
event is rare enough that AI-prompt caching wouldn't meaningfully help,
and for something this rare and high-stakes, a plain, unambiguous,
always-available sentence beats a paraphrase that could occasionally
misstate a number or go missing during a real AI outage."""

from datetime import datetime
from zoneinfo import ZoneInfo

import market_yf_client
import ntfy_client
import persisted_state

SYMBOL = "^GSPC"  # the real cash S&P 500 index — MWCB is specifically about this, not futures

# Checked most-severe-first — a single-day move can only ever cross
# multiple thresholds at once during a genuinely historic crash, and
# the highest one crossed is the real, correct level to report.
_LEVEL_THRESHOLDS_PCT = [(-20.0, 3), (-13.0, 2), (-7.0, 1)]
_LEVEL_LABELS = {1: "Level 1", 2: "Level 2", 3: "Level 3"}

# Halts only actually happen before this ET cutoff (Level 3 excepted —
# it halts the rest of the day whenever it triggers). Same real-ET
# conversion pattern market_yf_client.market_status already
# establishes (a naive now.hour/now.minute comparison bit this exact
# codebase once, live, when a threaded `now` landed on a UTC server —
# see that function's own comment) rather than assuming this app's own
# local zone already equals ET without checking.
_HALT_CUTOFF_HOUR_ET = 15
_HALT_CUTOFF_MINUTE_ET = 25


def _pct_change_from_prior_close(history: list[float]) -> float | None:
    if len(history) < 2:
        return None
    latest, prior = history[-1], history[-2]
    if not prior:
        return None
    return (latest - prior) / prior * 100


def _level_for_pct(pct: float) -> int | None:
    for threshold, level in _LEVEL_THRESHOLDS_PCT:
        if pct <= threshold:
            return level
    return None


def _halts_trading(now: datetime, level: int) -> bool:
    if level == 3:
        return True
    eastern = now.replace(tzinfo=ZoneInfo("America/Toronto")).astimezone(ZoneInfo("America/New_York"))
    return (eastern.hour, eastern.minute) < (_HALT_CUTOFF_HOUR_ET, _HALT_CUTOFF_MINUTE_ET)


# Per-instance, same as this app's other one-shot market/weather/road
# toasts — each kiosk announces its own first crossing. "level" is the
# HIGHEST level triggered so far today (0 = none) — only a genuinely
# NEW, higher level fires a fresh alert; the same level re-measured on
# a later rerun (the market sitting at -8% for an hour, say) isn't a
# new event. "pct" is kept alongside purely so the persistent red
# headline (circuit_breaker_headline_candidate below) can still show a
# real number without re-fetching, even long after the live price may
# have moved again.
_STATE_KEY = "market_circuit_breaker_state"
_state: dict = dict(persisted_state.load_per_instance(_STATE_KEY, {"date": None, "level": 0, "pct": None}))


def _today_reset(now: datetime) -> None:
    global _state
    today_str = now.date().isoformat()
    if _state.get("date") != today_str:
        _state = {"date": today_str, "level": 0, "pct": None}


def get_new_alerts(now: datetime) -> list[dict]:
    """A real toast the moment the S&P 500 crosses a genuinely NEW,
    higher circuit-breaker level today — [] on every ordinary day (the
    overwhelming majority; this has happened only a handful of times
    in real market history). Only checked while the cash market is
    actually open — a pre/post-market or futures move isn't what the
    real MWCB rule is about, and comparing against a stale prior-day
    quote outside those hours would be meaningless anyway.

    "kind": "weather" (this app's shared top-priority toast lane, same
    reasoning every other non-weather "weather"-kind source here
    already uses — lightning/road-closures/aviation), "severity":
    "extreme" — the same top rotation-critical tier real tornado/
    hurricane alerts get, deliberately: this is at least as rare and
    consequential as those. "important": True unconditionally — every
    level here is real news, not something to scope down the way road
    construction vs. a full closure was; this always flashes the
    bedroom light (govee_lighting's breaking_alert_elapsed mechanism,
    same as real breaking news) and it can never happen overnight
    anyway (market hours only), so no night-bypass question even
    arises the way it did for storm_phase."""
    global _state
    status = market_yf_client.market_status(now)
    if status != "open":
        return []
    quote = market_yf_client.quote_for(SYMBOL)
    if not quote or not quote.get("history"):
        return []
    pct = _pct_change_from_prior_close(quote["history"])
    if pct is None:
        return []
    level = _level_for_pct(pct)

    _today_reset(now)
    if level is None or level <= _state["level"]:
        return []

    _state["level"] = level
    _state["pct"] = pct
    persisted_state.save_per_instance(_STATE_KEY, _state)

    label = _LEVEL_LABELS[level]
    pct_str = f"{abs(pct):.1f}%"
    halts = _halts_trading(now, level)
    if level == 3:
        detail = "Trading is halted market-wide for the rest of the day."
    elif halts:
        detail = "Trading is halted market-wide for 15 minutes."
    else:
        detail = "It's after 3:25pm ET, so this doesn't trigger a trading halt, but the decline itself is real."
    headline = f"Circuit Breaker: {label} triggered — S&P 500 down {pct_str}"
    summary = (
        f"This is a market circuit breaker alert. A {label} circuit breaker has been triggered — "
        f"the S&P 500 is down {pct_str} from yesterday's close. {detail}"
    )
    # Session request: "make it so that literally all of the important
    # things get an alert" — this has never fired live (see this
    # module's own docstring) but is exactly the kind of thing that
    # request means: rarer and more consequential than anything else in
    # this app that already pushes. Urgent/bypasses DND unconditionally,
    # same as this alert's own "extreme" severity/menacing overlay —
    # nothing about a real circuit breaker is a can-wait-until-morning
    # event.
    ntfy_client.send(title="Market Circuit Breaker", message=headline, priority="urgent", tags="rotating_light")
    return [
        {
            "kind": "weather",
            "severity": "extreme",
            "label": "Circuit Breaker",
            "headline": headline,
            "summary": summary,
            "important": True,
            # "extreme" severity alone already gets the full-screen
            # menacing overlay (app.py's kioskShowMenaceOverlay keys off
            # the weather-alert-bar-extreme CSS class, not this flag) —
            # this separately drives the never-fully-silent volume
            # floor real severe weather gets. Functionally moot here
            # (a circuit breaker can only trigger during real market
            # hours, never overnight, so the quiet-hours volume curve
            # never actually applies) but set for correctness/honesty
            # rather than silently defaulting to the "routine" curve.
            "severe": True,
        }
    ]


def circuit_breaker_headline_candidate(now: datetime) -> dict | None:
    """Red-headline rotation candidate — same {"text", "css_class",
    "target_ms", "template", "zero_text"} shape every other source in
    headline_rotation.py uses. Shows for as long as that module's own
    2-hour eligibility window keeps it up after first detection (same
    as every other source there), NOT re-checked against the CURRENT
    live price — a real circuit-breaker event is a historic fact about
    today regardless of whether the index later partially recovers, so
    this only asks "did a level trigger today," not "is it still below
    threshold right now." rotation-critical unconditionally, same
    reasoning as get_new_alerts's own "extreme" severity above."""
    _today_reset(now)
    if _state["level"] <= 0:
        return None
    label = _LEVEL_LABELS[_state["level"]]
    pct = _state.get("pct")
    pct_str = f"{abs(pct):.1f}%" if pct is not None else "a real, sharp decline"
    text = f"Circuit Breaker: {label} triggered today — S&P 500 down {pct_str}"
    return {"text": text, "css_class": "rotation-critical", "target_ms": None, "template": "{}", "zero_text": None}
