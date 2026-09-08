"""The Brayden Index (BRDN) — a fictional, AI-driven "stock price" for
Brayden himself, treating his life as if it were a publicly traded
company. Session request: "I want an LLM to act as the equivalent of
the market's collective intelligence... simulate how hypothetical
shareholders and analysts would react" — explicitly NOT a weighted sum
of inputs. The whole point is a forward-looking market, not a
balance-sheet snapshot, so the model has to reason about what's
bullish/bearish, what's already priced in vs. genuinely new, and
produce a price move, sentiment, catalysts, and commentary the way a
real market reprices a stock on news, not just report today's numbers.

Same two-phase "evolving understanding" shape as morning_briefing.py's
_learned_notes: a persisted free-text note of what the market
currently believes/has priced in about Brayden, read BEFORE each
cycle's reasoning and rewritten AFTER — so next cycle's reaction is
genuinely relative to what's already been absorbed, not a fresh
re-reaction to the same known facts every single hour.

Routed to gemini_client specifically, not groq_client — this is the
single most reasoning-heavy judgment call in the app (weighing
"already priced in" against new information, synthesizing bullish/
bearish across a dozen unrelated signal types), and morning_briefing's
own docstring already established Gemini as the stronger reasoner of
the two free models available here.

maybe_reprice(now, readings) is meant to be called once per rerun,
unconditional of page (see app.py's own call site, right next to
sleep_tracker.maybe_push_wind_down) — cheap on almost every call since
gemini_client.generate_periodic's own REFRESH_SECONDS throttle means
the real reasoning call only actually fires once an hour regardless of
how often this runs.
"""

import json
import time
from datetime import datetime, timedelta

import streamlit as st

import air_quality_client
import calendar_client
import cpp_payment_dates
import ec_alerts
import fuel_price_client
import gemini_client
import market_internals
import market_yf_client
import ntfy_client
import payday_schedule
import persisted_state
import portfolio_client
import regime
import td_quarter_schedule
import wildfire_client
from config import USER_PROFILE
from icons import label_for
import weather_client

LAUNCH_PRICE = 10.00
REFRESH_SECONDS = 60 * 60  # hourly — session request: "as frequently as hourly"
MAX_HISTORY_POINTS = 2000  # comfortably years of hourly history before ever needing to trim further

# A single bad/unbounded AI response can never be allowed to send the
# price to $0 or to $9,000 — this clamp applies regardless of what the
# model itself returns, same "never trust a raw AI number without a
# sanity bound" discipline morning_briefing/pages_conflicts already use
# elsewhere in this app.
MAX_PCT_CHANGE = 10.0

# A move at or above this, from the MOST RECENT cycle specifically,
# earns the headline-rotation/push treatment — see
# big_move_headline_candidate and maybe_reprice's own push call below.
BIG_MOVE_THRESHOLD_PCT = 4.0

_SENTIMENTS = {"Bullish", "Bearish", "Neutral", "Mixed"}
_DIRECTIONS = {"bullish", "bearish"}
_MAGNITUDES = {"minor", "moderate", "major"}

# Loaded once at import into module globals, same discipline as every
# other persisted cache in this app (see persisted_state.py's own
# docstring on why re-loading on every call would be a real Upstash
# budget problem) — mutated in place, saved only on a genuine change.
_price: float = persisted_state.load("brdn_price", LAUNCH_PRICE)
_history: list[dict] = persisted_state.load("brdn_history", [])
_last_report: dict | None = persisted_state.load("brdn_last_report", None)
_expectations: str = persisted_state.load("brdn_expectations", "")
# The exact raw AI response text last actually applied to price/history
# — generate_periodic returns the SAME cached string on every call
# within its own hour-long throttle window, so without this guard
# maybe_reprice would re-apply the identical pct_change on every rerun
# for the rest of that hour, compounding it each time. Only a genuinely
# NEW cached string (a real new cycle) is ever applied.
_last_applied_raw: str | None = persisted_state.load("brdn_last_applied_raw", None)

if not _history:
    # The literal IPO — one point, right now, at the launch price. The
    # very next real maybe_reprice() cycle is free to move off this
    # immediately (see this module's own docstring on why sitting
    # inertly at exactly $10.00 for a full hour would be wrong — the
    # user's own example: "joining TD could have been a major positive
    # catalyst and caused a large initial repricing").
    _history = [{"ts": time.time(), "price": LAUNCH_PRICE}]
    persisted_state.save("brdn_history", _history)


def current() -> dict:
    """{"price", "prior_price", "change", "pct_change", "sentiment", "tone"} —
    cheap, no AI/network cost, safe to call every rerun (ticker/headline
    callers do exactly that)."""
    if _last_report and len(_history) >= 2:
        pct = _last_report.get("pct_change", 0.0)
        prior = _history[-2]["price"]
        sentiment = _last_report.get("sentiment", "Neutral")
    else:
        prior = LAUNCH_PRICE
        pct = ((_price - prior) / prior * 100) if prior else 0.0
        sentiment = "Neutral"
    change = _price - prior
    tone = "good" if change > 0 else "bad" if change < 0 else "neutral"
    return {
        "price": _price,
        "prior_price": prior,
        "change": change,
        "pct_change": pct,
        "sentiment": sentiment,
        "tone": tone,
    }


def history() -> list[float]:
    """Plain price series, oldest first — sparkline-ready (see
    tiles.sparkline_svg)."""
    return [h["price"] for h in _history]


def last_report() -> dict | None:
    return _last_report


def expectations() -> str:
    return _expectations


def _gather_signals(now: datetime, readings: dict | None) -> str:
    """A plain bulleted fact block, same shape as morning_briefing's own
    fact strings — each source independently guarded so one failure
    never blanks the whole prompt, same discipline as every other
    feature-gathering loop in this app. Deliberately reuses the same
    CLIENT-level functions morning_briefing's own clauses call, not
    those clauses themselves (private to that module) — see this
    feature's own plan for why."""
    facts: list[str] = []

    try:
        portfolio = portfolio_client.fetch_portfolio()
        if portfolio:
            facts.append(f"Net worth (all accounts, CAD): ${portfolio['total_cad']:,.0f}")
    except Exception:
        pass
    try:
        daily = portfolio_client.daily_change()
        if daily:
            facts.append(f"Portfolio change today: {daily['pct']:+.2f}% (${daily['amount']:+,.0f})")
    except Exception:
        pass
    try:
        week = portfolio_client.fetch_period_change(7)
        if week:
            facts.append(f"Portfolio change over 7 days: {week['pct']:+.2f}%")
    except Exception:
        pass
    try:
        month = portfolio_client.fetch_period_change(30)
        if month:
            facts.append(f"Portfolio change over 30 days: {month['pct']:+.2f}%")
    except Exception:
        pass
    try:
        activities = portfolio_client.fetch_activities(limit=8) or []
        real_activity = [a for a in activities if not a.get("is_transfer")]
        if real_activity:
            lines = "; ".join(
                f"{a['type'].title()} ${abs(a['amount']):,.0f} ({a['account']}, {a['date']})"
                for a in real_activity[:6]
            )
            facts.append(f"Recent real cash-flow activity (transfers between his own accounts excluded): {lines}")
    except Exception:
        pass
    try:
        gas = fuel_price_client.eco_mode_status()
        if gas:
            standing = "above" if gas["eco_recommended"] else "below"
            facts.append(f"Gas price: {gas['price']:.1f}¢/L ({standing} the 10-year real-terms median)")
    except Exception:
        pass
    try:
        calendars = st.secrets.get("CALENDARS")
        if calendars:
            today_events = calendar_client.todays_events(calendars, now.date())
            if today_events:
                lines = "; ".join(e["summary"] for e in today_events[:6])
                facts.append(f"Today's calendar: {lines}")
            upcoming = []
            for d in range(1, 8):
                day = now.date() + timedelta(days=d)
                for e in calendar_client.todays_events(calendars, day):
                    if e["summary"] != "Work":
                        upcoming.append(f"{e['summary']} ({day.isoformat()})")
            if upcoming:
                facts.append("Upcoming non-work events (next 7 days): " + "; ".join(upcoming[:8]))
    except Exception:
        pass
    try:
        payday = payday_schedule.next_payday(now.date())
        if payday["days_until"] <= 3:
            facts.append(f"Payday in {payday['days_until']} day(s)")
    except Exception:
        pass
    try:
        cpp = cpp_payment_dates.next_payment_date(now.date())
        if cpp and cpp["days_until"] <= 3:
            facts.append(f"CPP/OAS pension payment day in {cpp['days_until']} day(s) (branch traffic)")
    except Exception:
        pass
    try:
        quarter = td_quarter_schedule.next_quarter_start(now.date())
        if quarter["days_until"] <= 3:
            facts.append(f"New TD fiscal quarter (his own sales counter resets) in {quarter['days_until']} day(s)")
    except Exception:
        pass
    try:
        weather = weather_client.fetch_weather()
        if weather:
            condition = label_for(weather["weather_code"])
            facts.append(f"Current weather: {weather['temp_c']:.0f}°C, {condition}")
    except Exception:
        pass
    try:
        alerts = ec_alerts.fetch_alerts()
        if alerts:
            facts.append("Active severe weather alert: " + alerts[0].get("title", "severe weather alert"))
    except Exception:
        pass
    try:
        aqi_data = air_quality_client.fetch_air_quality()
        us_aqi = (aqi_data or {}).get("us_aqi")
        if us_aqi and us_aqi > 100:
            facts.append(f"Air quality index: {air_quality_client.level(us_aqi)}/10")
    except Exception:
        pass
    try:
        wildfire = wildfire_client.nearest_wildfire()
        if wildfire:
            facts.append(f"Nearest active wildfire: {wildfire['distance_km']:.0f} km away")
    except Exception:
        pass
    try:
        status = market_yf_client.market_status(now)
        symbol = market_yf_client.primary_symbol(status)
        quote = market_yf_client.quote_for(symbol)
        if quote:
            facts.append(f"Broad market ({symbol}) today: {quote['intraday']:+.2f}%")
        expected_move = market_yf_client.expected_daily_move_pct()
        if expected_move:
            facts.append(f"Market's own priced-in expected daily move right now: ±{expected_move:.2f}%")
    except Exception:
        pass
    try:
        if readings:
            confidence = market_internals.fear_greed_index()
            credit = market_internals.price_ratio("HYG", "LQD")
            breadth = market_internals.price_ratio("RSP", "SPY")
            regime_data = regime.classify(readings, confidence, credit, breadth)
            if regime_data:
                facts.append(f"Broader macro/economic backdrop: {regime_data['narrative']}")
    except Exception:
        pass

    facts.append(f"Standing personal context (job/vehicle/finances/life, unchanging fact sheet): {USER_PROFILE}")
    return "\n".join(f"- {f}" for f in facts)


def _build_prompt(now: datetime, readings: dict | None) -> str:
    signals = _gather_signals(now, readings)
    recent = _history[-8:]
    if len(recent) >= 2:
        recent_prices = ", ".join(f"${h['price']:.2f}" for h in recent)
    else:
        recent_prices = "none yet — just IPO'd at $10.00, this is the first real pricing decision"
    expectations_text = _expectations or "(no prior expectations recorded yet — this is early in the index's history)"
    return (
        "You are the collective market — the pooled judgment of every hypothetical shareholder and analyst — "
        "pricing BRDN, a fictional publicly traded \"stock\" that represents one real person, Brayden, as if his "
        "whole life and trajectory were a company. This is NOT a net-worth tracker and NOT a weighted sum of the "
        "inputs below. React the way a real market reprices a real stock on news: something already priced in "
        "should barely move the price at all; a genuinely new or unexpected development (good or bad) should move "
        "it more; a temporary/noisy blip should move it less than a real structural change to his actual "
        "trajectory. Most cycles, with nothing major happening, should be small moves (well under 1-2%) — save "
        "bigger moves for genuinely significant news.\n\n"
        f"Current price: ${_price:.2f}. Recent price history, oldest to newest: {recent_prices}.\n\n"
        f"What the market currently believes about Brayden / already has priced in (your own note from last "
        f"cycle): {expectations_text}\n\n"
        f"Fresh signals since the last cycle:\n{signals}\n\n"
        "Decide: (1) a percentage price move for this cycle, between -10 and +10, (2) overall sentiment, "
        "(3) up to 4 named catalysts (bullish or bearish) that actually drove this cycle's move, each with a "
        "magnitude, (4) one or two sentences of shareholder/analyst commentary in the voice of a real market "
        "reacting to real news — not a summary of the facts, a REACTION to them, (5) an updated version of your "
        "own \"what the market now believes\" note for next cycle: carry forward whatever's still true, fold in "
        "whatever's newly priced in.\n\n"
        "Respond with ONLY JSON, no markdown fences, no other text, in exactly this shape:\n"
        '{"pct_change": 0.0, "sentiment": "Bullish", "catalysts": '
        '[{"label": "...", "direction": "bullish", "magnitude": "minor", "note": "..."}], '
        '"commentary": "...", "updated_expectations": "..."}'
    )


def _parse(raw: str) -> dict | None:
    """Same defensive shape as pages_conflicts._parse — json.loads inside
    try/except, every field validated before it's trusted, None on
    anything that doesn't check out (maybe_reprice treats that as "skip
    this cycle," never as license to guess)."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        pct_change = float(data["pct_change"])
        sentiment = str(data["sentiment"]).strip().title()
        commentary = str(data["commentary"]).strip()
        updated_expectations = str(data["updated_expectations"]).strip()
        raw_catalysts = data.get("catalysts") or []
    except (KeyError, TypeError, ValueError):
        return None
    if sentiment not in _SENTIMENTS or not commentary or not updated_expectations:
        return None

    catalysts = []
    for c in raw_catalysts:
        try:
            label = str(c["label"]).strip()
            direction = str(c["direction"]).strip().lower()
            magnitude = str(c.get("magnitude", "moderate")).strip().lower()
            note = str(c.get("note", "")).strip()
        except (KeyError, TypeError):
            continue
        if not label or direction not in _DIRECTIONS:
            continue
        catalysts.append({
            "label": label,
            "direction": direction,
            "magnitude": magnitude if magnitude in _MAGNITUDES else "moderate",
            "note": note,
        })

    return {
        "pct_change": pct_change,
        "sentiment": sentiment,
        "catalysts": catalysts,
        "commentary": commentary,
        "updated_expectations": updated_expectations,
    }


def maybe_reprice(now: datetime, readings: dict | None = None) -> None:
    """Call once per rerun, unconditional of page (see app.py's own call
    site, right next to sleep_tracker.maybe_push_wind_down). Cheap on
    almost every call — gemini_client.generate_periodic's own
    REFRESH_SECONDS throttle means the real reasoning call only actually
    fires once an hour regardless of how often this runs, and the
    _last_applied_raw guard below means even a genuine new response is
    only ever applied to price/history once."""
    # _history is mutated in place (append/del below), never reassigned
    # wholesale, so it doesn't need to be declared global here.
    global _price, _last_report, _expectations, _last_applied_raw
    prompt = _build_prompt(now, readings)
    raw = gemini_client.generate_periodic("brayden_index", REFRESH_SECONDS, prompt, temperature=0.4, max_output_tokens=600)
    if raw is None or raw == _last_applied_raw:
        return  # AI unavailable this call, or this hour's cycle was already applied — nothing new to do

    parsed = _parse(raw)
    # Marked seen BEFORE checking parse success — a malformed response
    # is the SAME cached text for the rest of this hour, so without
    # this, a bad response would get uselessly re-parsed (and re-fail)
    # on every rerun until the next real cycle, instead of just once.
    _last_applied_raw = raw
    persisted_state.save("brdn_last_applied_raw", _last_applied_raw)
    if parsed is None:
        return

    pct = max(-MAX_PCT_CHANGE, min(MAX_PCT_CHANGE, parsed["pct_change"]))
    new_price = round(_price * (1 + pct / 100), 4)
    ts = time.time()

    _price = new_price
    _history.append({"ts": ts, "price": new_price})
    del _history[:-MAX_HISTORY_POINTS]
    _last_report = {
        "sentiment": parsed["sentiment"],
        "pct_change": pct,
        "catalysts": parsed["catalysts"],
        "commentary": parsed["commentary"],
        "updated_at": ts,
    }
    _expectations = parsed["updated_expectations"]

    persisted_state.save("brdn_price", _price)
    persisted_state.save("brdn_history", _history)
    persisted_state.save("brdn_last_report", _last_report)
    persisted_state.save("brdn_expectations", _expectations)

    if abs(pct) >= BIG_MOVE_THRESHOLD_PCT:
        try:
            verb = "surged" if pct > 0 else "plunged"
            tag = "chart_with_upwards_trend" if pct > 0 else "chart_with_downwards_trend"
            ntfy_client.send(
                title="BRDN alert",
                message=f"BRDN {verb} {abs(pct):.1f}% to ${new_price:.2f} — {parsed['commentary']}",
                priority="high",
                tags=tag,
            )
        except Exception:
            pass


# Session request: "every morning, I want to get a brief of what's
# going on with my stock price, probably around market open — nine
# thirty would be sick... why it's moving, what they're pricing in,
# what the catalyst is." A window, not an exact minute match — the
# outer script's own rerun cadence (~65-120s) can't guarantee landing
# on the literal 9:30:00 tick, same reasoning as every other clock-
# time-gated feature in this app. Capped at _MORNING_BRIEF_LATEST_HOUR
# rather than firing whenever the kiosk next wakes up — a "market open"
# brief showing up mid-afternoon because the kiosk was asleep through
# market open isn't the feature that was asked for; skipping for the
# day is more honest than a stale late push (same reasoning
# commute_reminder.LATEST_FIRE_MINUTES already uses).
_MORNING_BRIEF_HOUR = 9
_MORNING_BRIEF_MINUTE = 30
_MORNING_BRIEF_LATEST_HOUR = 11
_MORNING_BRIEF_PUSHED_KEY = "brdn_morning_brief_pushed_date"


def maybe_push_morning_brief(now: datetime, readings: dict | None = None) -> None:
    """Once per real calendar day, in the 9:30-11:00am window. Calls
    maybe_reprice first so market open gets a genuinely fresh read
    rather than reusing however-old the last hourly cycle happens to
    be — that call is itself a no-op if under an hour has passed since
    the last real cycle (see its own docstring), so this never disturbs
    the normal hourly rhythm or costs an extra AI call on its own.
    Reuses the already-computed commentary/expectations from that
    cycle rather than asking the AI a second, separate question — the
    hourly prompt already produces exactly the "why it moved" reaction
    and "what's priced in" note this brief wants, no new reasoning call
    needed."""
    minutes_now = now.hour * 60 + now.minute
    window_start = _MORNING_BRIEF_HOUR * 60 + _MORNING_BRIEF_MINUTE
    window_end = _MORNING_BRIEF_LATEST_HOUR * 60
    if not (window_start <= minutes_now < window_end):
        return
    today = now.date().isoformat()
    if persisted_state.load(_MORNING_BRIEF_PUSHED_KEY, None) == today:
        return

    maybe_reprice(now, readings)
    if _last_report is None:
        return

    data = current()
    arrow = "▲" if data["change"] > 0 else "▼" if data["change"] < 0 else "●"
    sign = "+" if data["pct_change"] >= 0 else ""
    title = f'BRDN ${data["price"]:.2f} {arrow} {sign}{data["pct_change"]:.2f}% — {data["sentiment"]}'
    commentary = _last_report.get("commentary", "")
    message = f"{commentary}\n\nPriced in: {_expectations}" if _expectations else commentary

    # Marked before the send call, not conditioned on its success — same
    # convention commute_reminder's own milestone push dedup already
    # uses (see its own comment): a transient ntfy failure shouldn't
    # turn into a retry-storm on every rerun for the rest of the window.
    persisted_state.save(_MORNING_BRIEF_PUSHED_KEY, today)
    try:
        ntfy_client.send(title=title, message=message, priority="default", tags="bar_chart")
    except Exception:
        pass


def big_move_headline_candidate(now: datetime) -> dict | None:
    """Red-headline rotation candidate — same shape every source in
    headline_rotation.py uses (see market_circuit_breaker.
    circuit_breaker_headline_candidate for an identical static, non-
    countdown precedent). No age check of its own: this is only ever
    true off the MOST RECENT cycle's move, and the next hourly cycle
    naturally replaces _last_report with that cycle's own (almost
    always much smaller) move — so this self-expires within one hour on
    its own, tighter than headline_rotation's shared 2-hour hold would
    be anyway."""
    if _last_report is None:
        return None
    pct = _last_report.get("pct_change", 0.0)
    if abs(pct) < BIG_MOVE_THRESHOLD_PCT:
        return None
    direction = "surges" if pct > 0 else "plunges"
    css_class = "rotation-notice" if pct > 0 else "rotation-warning"
    return {
        "text": f"BRDN {direction} {abs(pct):.1f}% to ${_price:.2f}",
        "css_class": css_class,
        "target_ms": None,
        "template": "{}",
        "zero_text": None,
    }
