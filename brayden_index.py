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
from zoneinfo import ZoneInfo

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
from config import TIMEZONE, USER_PROFILE
from icons import label_for
import weather_client

LAUNCH_PRICE = 10.00
REFRESH_SECONDS = 60 * 60  # hourly — session request: "as frequently as hourly"
# Session request: "exempt [BRDN] from jumbotron and periodic updates
# (every 3 hours) in night mode." Two separate, deliberate departures
# from how every other Gemini-routed feature in this app behaves
# (see gemini_client.generate_periodic's own allow_during_game
# docstring for the jumbotron half):
#   - jumbotron/game-time pause: exempt entirely, not just slowed —
#     BRDN isn't competing for the same screen real estate a toast or
#     the jumbotron itself is, so there's no reason for a game to
#     silence it the way it silences things that WOULD compete.
#   - overnight pause (groq_client.ai_pulls_paused, dusk-to-dawn):
#     deliberately NOT wired in as a hard block the way morning_
#     briefing/every other feature respects it. Explicit user choice —
#     a genuinely quiet night still gets a couple of real updates
#     instead of going fully dark until dawn, at roughly a third of
#     the daytime call volume.
NIGHT_REFRESH_SECONDS = 3 * 60 * 60  # 3 hours, only while night mode is active
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

# Session request: "let's do it, the quarterly notification... a copy
# of my data on LinkedIn as well as a little verbal update... framed as
# a quarterly employment report." No live LinkedIn/social feed exists
# or ever will (that request was explicitly declined — automated
# scraping/login is both against LinkedIn's own ToS and a hard no for
# entering credentials on Brayden's behalf regardless of who's asking).
# This is the honest middle ground actually discussed: a quarterly
# push reminding him to pull his own LinkedIn data export and give a
# plain-language update, which THEN gets recorded here via
# record_employment_report — either typed straight into the dashboard
# (pages_brayden_index.py) or relayed through Claude in chat. Real
# calendar quarters (Jan/Apr/Jul/Oct), not TD's own fiscal quarters
# (td_quarter_schedule.py, Feb/May/Aug/Nov) — this is meant to read as
# an ordinary "Q1 2027" employment report, not TD-specific.
_employment_report: dict | None = persisted_state.load("brdn_employment_report", None)

if not _history:
    # The literal IPO — one point, right now, at the launch price. The
    # very next real maybe_reprice() cycle is free to move off this
    # immediately (see this module's own docstring on why sitting
    # inertly at exactly $10.00 for a full hour would be wrong — the
    # user's own example: "joining TD could have been a major positive
    # catalyst and caused a large initial repricing").
    _history = [{"ts": time.time(), "price": LAUNCH_PRICE}]
    persisted_state.save("brdn_history", _history)


def _day_open_price() -> float:
    """The reference price current()'s headline change/pct_change is
    measured against — the last known price from before today began
    (today's effective open), matching how a real stock's daily %
    change is always measured (against the prior close, never against
    "a few minutes/hours ago"). Session report: "it's showing up
    0.3%... that's over the hour, not the day's return... it should
    always be based on where the market opened that day... it shouldn't
    bounce between hour to hour... meanwhile it's still down from where
    it opened today" — the old version measured change against the
    LAST CYCLE only, which could read green even while the whole day
    was still net negative. One pricing session = local midnight to
    local midnight, same TIMEZONE convention every other date boundary
    in this app uses. Falls back to the earliest known price if
    history doesn't reach back before today yet (BRDN's first day —
    today's open IS the IPO price in that case, which is exactly
    right)."""
    midnight_local = datetime.now(ZoneInfo(TIMEZONE)).replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_ts = midnight_local.timestamp()
    prior = [h["price"] for h in _history if h["ts"] < midnight_ts]
    if prior:
        return prior[-1]
    return _history[0]["price"] if _history else LAUNCH_PRICE


def current() -> dict:
    """{"price", "day_open_price", "change", "pct_change",
    "cycle_pct_change", "sentiment", "tone"} — cheap, no AI/network
    cost, safe to call every rerun (ticker/headline callers do exactly
    that). "change"/"pct_change" are the DAY's cumulative move (see
    _day_open_price) — every display in this app (corner ticker, page
    hero tile, ticker-tape stat item) reads these two, so fixing them
    here fixes all of them at once. "cycle_pct_change" is kept
    separately, straight from the last report, for anything that
    specifically wants "how much did the LAST cycle move it" rather
    than the day's cumulative figure — big_move_headline_candidate and
    the big-move push in maybe_reprice both want exactly that (a sharp
    single-hour swing is newsworthy on its own, regardless of where the
    day's cumulative number sits), so they deliberately keep reading
    _last_report directly rather than this field."""
    day_open = _day_open_price()
    change = _price - day_open
    pct_change = (change / day_open * 100) if day_open else 0.0
    cycle_pct_change = _last_report.get("pct_change", 0.0) if _last_report else 0.0
    sentiment = _last_report.get("sentiment", "Neutral") if _last_report else "Neutral"
    tone = "good" if change > 0 else "bad" if change < 0 else "neutral"
    return {
        "price": _price,
        "day_open_price": day_open,
        "change": change,
        "pct_change": pct_change,
        "cycle_pct_change": cycle_pct_change,
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


def employment_report() -> dict | None:
    """{"quarter_label", "summary", "filed_at"} for whatever was last
    filed via record_employment_report, or None before the first one
    ever lands. Read by pages_brayden_index.py to show what's on file,
    and by quarterly_report_status to know whether THIS quarter's
    report has already been filed."""
    return _employment_report


def next_reprice_estimate(night_mode_active: bool = False) -> dict:
    """{"seconds_until", "pct_elapsed", "due"} — an ESTIMATE, not a
    guarantee. Session request: "when does the AI reprice... a little
    gauge to show when the next reprice is." The real next cycle fires
    on the first outer rerun after the real cadence (REFRESH_SECONDS,
    or NIGHT_REFRESH_SECONDS while night_mode_active — must match
    whatever maybe_reprice itself is actually using, or this estimate
    would be flatly wrong for a third of every day) has genuinely
    elapsed since the last one — that check only runs on the outer
    script's own ~65-120s rerun cadence, so the real cycle can land up
    to a minute or two after this estimate's own zero-mark, never to
    the literal second. Anchored to the last successfully APPLIED cycle
    (_last_report["updated_at"]) — not generate_periodic's own internal
    cache timestamp, which is captured a moment earlier in the same
    call and close enough not to matter for a countdown display — or
    the IPO timestamp if no real cycle has landed yet."""
    refresh_seconds = NIGHT_REFRESH_SECONDS if night_mode_active else REFRESH_SECONDS
    if _last_report is not None:
        anchor = _last_report["updated_at"]
    elif _history:
        anchor = _history[0]["ts"]
    else:
        anchor = time.time()
    elapsed = time.time() - anchor
    seconds_until = max(0.0, refresh_seconds - elapsed)
    pct_elapsed = min(1.0, max(0.0, elapsed / refresh_seconds)) if refresh_seconds else 1.0
    return {"seconds_until": seconds_until, "pct_elapsed": pct_elapsed, "due": seconds_until <= 0}


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

    try:
        if _employment_report:
            quarter = _employment_report["quarter_label"]
            summary = _employment_report["summary"]
            if _employment_report.get("is_baseline"):
                # Session request, the very first report ever filed:
                # "this is technically not new data... I don't want my
                # stock to jump ten percent tomorrow." Never surfaced as
                # fresh, regardless of age — reads as settled background
                # from the moment it lands, same as long-priced-in
                # context. Real quarterly reports below still get the
                # normal fresh-then-fades treatment.
                facts.append(
                    f"Baseline employment context on file ({quarter}, backfilled career "
                    f"snapshot — NOT new information, already fully priced in, do not "
                    f"treat as a fresh catalyst on its own): {summary}"
                )
            else:
                age_days = (now.timestamp() - _employment_report["filed_at"]) / 86400
                if age_days <= _EMPLOYMENT_REPORT_FRESH_DAYS:
                    # Fresh — labeled explicitly as real, self-reported
                    # news so the AI weighs it the way it would any
                    # other genuinely new development, not routine
                    # background. Deliberately NOT told to treat this as
                    # automatically major — a quiet quarter with nothing
                    # real to report is itself a legitimate (small-move)
                    # outcome, same "don't force a number, let the
                    # market actually decide" principle this whole
                    # module already runs on.
                    facts.append(
                        f"Just-filed {quarter} employment report (fresh, self-reported by "
                        f"Brayden via his own LinkedIn export + a verbal update — weigh "
                        f"like real news, not routine background): {summary}"
                    )
                else:
                    facts.append(f"Last filed employment report ({quarter}, already priced in): {summary}")
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


def maybe_reprice(now: datetime, readings: dict | None = None, night_mode_active: bool = False) -> None:
    """Call once per rerun, unconditional of page (see app.py's own call
    site, right next to sleep_tracker.maybe_push_wind_down). Cheap on
    almost every call — gemini_client.generate_periodic's own throttle
    (REFRESH_SECONDS normally, NIGHT_REFRESH_SECONDS while
    night_mode_active — see that constant's own comment for why BRDN
    slows down rather than fully stopping overnight) means the real
    reasoning call only actually fires that often regardless of how
    often this runs, and the _last_applied_raw guard below means even a
    genuine new response is only ever applied to price/history once.
    `night_mode_active` should be app.py's own already-computed
    _night_mode_active — not re-derived here, see NIGHT_REFRESH_SECONDS'
    own comment for why this doesn't just call groq_client.
    ai_pulls_paused directly the way every other Gemini feature does."""
    # _history is mutated in place (append/del below), never reassigned
    # wholesale, so it doesn't need to be declared global here.
    global _price, _last_report, _expectations, _last_applied_raw
    prompt = _build_prompt(now, readings)
    refresh_seconds = NIGHT_REFRESH_SECONDS if night_mode_active else REFRESH_SECONDS
    raw = gemini_client.generate_periodic(
        "brayden_index", refresh_seconds, prompt, temperature=0.4, max_output_tokens=600, allow_during_game=True
    )
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

    # night_mode_active always False here on purpose, not just the
    # default — this window (9:30-11am) can never genuinely overlap
    # night mode, which always ends by sunrise.
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


# Session request: the quarterly employment report — a nudge to pull a
# real LinkedIn data export and give a verbal update, NOT a scraper
# (see this module's own state-block comment above for why nothing
# automated touches LinkedIn/social accounts here). Ordinary calendar
# quarters, fired within the first few days of Jan/Apr/Jul/Oct — same
# "surfaced only if within N days" window discipline payday_schedule/
# cpp_payment_dates/td_quarter_schedule already use in _gather_signals,
# not a single exact-day check that a sleeping/redeploying kiosk could
# silently miss entirely for the whole quarter.
_QUARTERLY_REPORT_MONTHS = (1, 4, 7, 10)
_QUARTERLY_REPORT_WINDOW_DAYS = 5
_QUARTERLY_REPORT_PUSHED_KEY = "brdn_quarterly_report_pushed_quarter"
# How long a filed report reads as fresh, newsworthy input to
# _gather_signals before fading to quiet already-priced-in background —
# see that function's own employment-report block below.
_EMPLOYMENT_REPORT_FRESH_DAYS = 14


def _quarter_label(d) -> str:
    """d is a date or datetime — 'Q1 2027' etc, ordinary calendar
    quarters. Deliberately separate from td_quarter_schedule's own
    fiscal-quarter labels (Feb/May/Aug/Nov) — this is meant to read as
    a normal employment report, not a TD-specific one."""
    quarter_num = (d.month - 1) // 3 + 1
    return f"Q{quarter_num} {d.year}"


def maybe_push_quarterly_report(now: datetime) -> None:
    """Once per real calendar quarter, in the first
    _QUARTERLY_REPORT_WINDOW_DAYS days of Jan/Apr/Jul/Oct. Fires the
    reminder only — filing itself always happens through
    record_employment_report, whether typed into the dashboard or
    relayed by Claude after Brayden reports back in chat, since there's
    no way for this app to read what actually changed on its own."""
    if now.month not in _QUARTERLY_REPORT_MONTHS or now.day > _QUARTERLY_REPORT_WINDOW_DAYS:
        return
    quarter = _quarter_label(now.date())
    if persisted_state.load(_QUARTERLY_REPORT_PUSHED_KEY, None) == quarter:
        return
    # Marked before the send call, same reasoning as the morning-brief
    # push just above — a transient ntfy failure shouldn't retry every
    # rerun for the rest of the window.
    persisted_state.save(_QUARTERLY_REPORT_PUSHED_KEY, quarter)
    try:
        ntfy_client.send(
            title=f"BRDN {quarter} Employment Report due",
            message=(
                f"Time to file the {quarter} employment report for BRDN. Grab a "
                "copy of your LinkedIn data (Settings > Data Privacy > Get a copy "
                "of your data) and give a quick verbal rundown of what's changed — "
                "role, comp, standing, anything career-relevant. File it on the "
                "BRDN page, or just tell Claude and it'll get recorded — either "
                "way it feeds straight into the next repricing."
            ),
            priority="default",
            tags="briefcase",
        )
    except Exception:
        pass


def record_employment_report(summary: str, now: datetime, is_baseline: bool = False) -> bool:
    """Files THIS quarter's employment report — the actual content
    (LinkedIn highlights + verbal update) landing in persisted state so
    _gather_signals can hand it to the next repricing cycle as a
    signal. False (no-op) on blank input; True on a genuine file.
    Overwrites the same quarter's own prior entry if called again
    before the quarter rolls over (a correction/addition, not a second
    report) rather than accumulating duplicates.

    is_baseline — session request: the very first report ever filed,
    built from Brayden's real LinkedIn profile, explicitly framed as
    catch-up context rather than news: "this is technically not new
    data... I don't want my stock to jump ten percent tomorrow." A
    baseline report is NEVER surfaced as fresh/newsworthy in
    _gather_signals regardless of how recently it was filed — it reads
    the same as long-since-priced-in background from the moment it
    lands. Ordinary quarterly reports (is_baseline=False, the default)
    keep the normal fresh-then-fades behavior."""
    global _employment_report
    text = summary.strip()
    if not text:
        return False
    _employment_report = {
        "quarter_label": _quarter_label(now.date()),
        "summary": text,
        "filed_at": now.timestamp(),
        "is_baseline": is_baseline,
    }
    persisted_state.save("brdn_employment_report", _employment_report)
    return True


def quarterly_report_status(now: datetime) -> dict:
    """{"current_quarter", "filed_this_quarter"} — cheap, no AI/network
    cost, for pages_brayden_index.py to show whether this quarter's
    report is still outstanding."""
    current_quarter = _quarter_label(now.date())
    filed = bool(_employment_report) and _employment_report.get("quarter_label") == current_quarter
    return {"current_quarter": current_quarter, "filed_this_quarter": filed}


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
