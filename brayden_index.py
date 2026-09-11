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
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

import air_quality_client
import calendar_client
import commute_reminder
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
import road_conditions
import road_conditions_511
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
# Session request: "I can use [the terminal] to look back on my
# progression in life... does the price history have unlimited
# history, or is there a fixed lookback?" The honest answer at the time
# this was asked: the old value here (2000) was never actually "years"
# despite its own comment claiming that — real cadence is REFRESH_
# SECONDS by day but NIGHT_REFRESH_SECONDS overnight (~19-20 reprices/
# day once that throttle is accounted for), so 2000 points was really
# only ~3-4 months of runway before the oldest points started silently
# dropping off — a genuine bug in the comment's own math, not just a
# stale number. This is meant to be a real long-term personal record
# ("still very early in life"), so sized generously: 450,000 points is
# ~50 years even at a WORST-CASE hourly-24/7 cadence (no credit taken
# for the night-mode throttle actually applying) — realistically far
# longer than that in practice. Still a hard ceiling, not truly
# unbounded — a safety net against a future bug that reprices far more
# often than intended ever silently growing this (and the single JSON
# blob persisted_state writes on every append) without limit.
MAX_HISTORY_POINTS = 450_000

# Session request: "the stock AI has been extremely conservative and
# cant really express itself outside of moves with a denomination of
# 0.05%... make it smarter and more decisive as well as give it free
# range to trade my index without limits." The old ±10% symmetric
# clamp here is gone — it wasn't actually what was producing the tiny
# 0.05%-ish moves (the model itself was choosing those, see _build_
# prompt's own comment on what changed there), but it WAS an explicit
# ceiling with no upside for genuine conviction on real news, and
# removing it is the literal ask. What's left below isn't a limit on
# decisiveness, it's basic math: price * (1 + pct/100) hits zero or
# goes negative once pct reaches -100%, which would corrupt every
# downstream $ format/sparkline/cycle_pct_change calc, not just
# produce "a big move." -99% is as close to that wall as a move can
# get while the price stays a real, nonzero, positive number.
# Deliberately NO ceiling at all on the upside.
MIN_PCT_CHANGE = -99.0

# A move at or above this, from the MOST RECENT cycle specifically,
# earns the headline-rotation/push treatment — see
# big_move_headline_candidate and maybe_reprice's own push call below.
BIG_MOVE_THRESHOLD_PCT = 4.0

# Session request: "I want it to catch on to patterns... shareholders
# in real life don't wait for data to come out, they build expectations
# before it actually comes out." That only works with real memory —
# _last_report used to be overwritten every cycle with nothing kept
# from before it, so the AI was reasoning fresh with zero precedent
# every single time. _report_history is the fix: every real cycle's
# outcome (move, sentiment, catalysts) gets appended here, not just the
# latest one — see maybe_reprice's own persistence block below. Capped
# generously (500 ≈ a few weeks of hourly cycles) since this is cheap
# structured data, not prose; _HISTORY_DIGEST_LIMIT is the much smaller
# slice actually fed into any one prompt (see _recent_history_digest),
# keeping token cost sane regardless of how long the full archive gets.
MAX_REPORT_HISTORY = 500
_HISTORY_DIGEST_LIMIT = 15

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
# {"ts", "price", "pct_change", "sentiment", "catalysts"} per real cycle,
# oldest first — see MAX_REPORT_HISTORY's own comment above.
_report_history: list[dict] = persisted_state.load("brdn_report_history", [])

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


def report_history(limit: int = 8) -> list[dict]:
    """Last `limit` real cycles, MOST RECENT FIRST — for
    pages_brayden_index.py's own recent-history section. Cheap, no
    AI/network cost. Deliberately a small default (8) — this renders
    without a scroll container (kiosk is non-interactive; anything
    below the fold in a scrolling list is permanently invisible on a
    TV), so it stays a short glanceable list, not a full log — the
    full archive (see MAX_REPORT_HISTORY) is what actually feeds the
    AI's own pattern-recognition, not what's shown on screen."""
    return list(reversed(_report_history[-limit:]))


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


def current_signals(now: datetime, readings: dict | None = None) -> str:
    """Public read-only wrapper around _gather_signals — the exact same
    fact sheet the AI reasons from this cycle, for a caller that wants
    to actually SHOW it (pages_brdn_terminal.py's own "raw signals"
    panel) rather than just consume it in a prompt. Same transparency
    principle "what the market believes"/"recent track record" already
    run on, just one layer closer to the metal. `readings` optional
    (None just quietly skips the one macro/regime fact that needs it —
    see _gather_signals' own try/except around that block) since a page
    calling this typically won't have FRED readings on hand the way
    app.py's own top-level scope does."""
    return _gather_signals(now, readings)


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
        # Session request, following up on the road/ice-conditions
        # additions: "important emails should be included." Reuses
        # email_client.morning_brief_summary — already exactly this
        # shape (subject + sender for genuinely important mail only,
        # same classifier the toast system uses, 24h lookback, capped)
        # rather than building a second reader; None cleanly covers
        # "unconfigured" and "nothing important came through" alike, no
        # separate check needed. Deliberately the classified/filtered
        # feed, not email_client.interest_signal_block's raw unfiltered
        # one (built for a different consumer, morning_briefing's
        # hobby-pattern inference) — subject+sender only here too, never
        # full message content.
        #
        # Imported HERE, not at module level — real live incident:
        # top-level `import email_client` pulled its own deep transitive
        # chain (email_client -> groq_client -> gemini_client ->
        # sports_alerts -> scores_client -> data_health) into
        # brayden_index's own import, which app.py imports EARLIER
        # (line ~20) than its own existing top-level `import
        # email_client` (line ~25) already does elsewhere. That handful
        # of lines earlier was enough to newly hit what's almost
        # certainly a Streamlit Cloud cold-start filesystem race (the
        # same unreproducible-locally KeyError-at-import pattern seen
        # twice before this session on two different unrelated modules)
        # — confirmed live: the whole app went down, not just this
        # page, immediately after this import was added, and recovered
        # once it moved here. A local import costs nothing (Python
        # caches the module after the first real import — app.py's own
        # already runs by the time any page actually calls this) and
        # keeps this module's own import-time footprint exactly what it
        # was before this feature existed.
        import email_client
        email_summary = email_client.morning_brief_summary(now)
        if email_summary:
            facts.append(f"Email: {email_summary}")
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
        next_report = _next_report_due(now.date())
        if next_report["days_until"] <= _QUARTERLY_REPORT_LOOKAHEAD_DAYS:
            # A known, scheduled, dated event — same shape as a real
            # market knowing an FOMC meeting date in advance. Purely a
            # calendar fact; nothing here tells the model to hedge,
            # de-risk, or hold conviction ahead of it — see this
            # constant's own comment for why that's deliberate.
            facts.append(
                f"Next quarterly employment report due in {next_report['days_until']} day(s) "
                f"({next_report['quarter_label']}) — a scheduled, anticipated check-in on "
                f"Brayden's career/professional standing, not a surprise event"
            )
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
        # Session request: "the AI should have access to this stuff" —
        # following the commute hybrid-routing work (commute_reminder.
        # commute_status/is_congested), a real logistics friction point
        # is exactly the kind of "unexpected development" this whole
        # module is built to react to, same reasoning as a road closure
        # or severe weather alert below. Only surfaced when it's
        # actually congested (same AMBER_DELAY_THRESHOLD_SECONDS bar the
        # Today page's own amber card uses) — a normal, undelayed
        # commute isn't a fact worth spending a signal slot on every
        # single cycle.
        commute = commute_reminder.commute_status(now)
        if commute and commute["is_congested"]:
            route = commute["route"]
            delay_minutes = round(route["delay_seconds"] / 60)
            if route.get("incident"):
                reason = f" ({route['incident']})"
            elif route.get("predicted"):
                reason = " (a recurring pattern, not a fresh incident)"
            else:
                reason = ""
            dest_label = commute["destination"]["label"]
            facts.append(
                f"Commute to {dest_label} currently running +{delay_minutes} min behind from "
                f"traffic{reason} — a real logistics friction point today"
            )
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
        # Session request: "literally every single possible source that
        # we could have should be fed to the AI... outside conditions...
        # the opportunity cost." Two real, already-plumbed-elsewhere-in-
        # this-app signals that genuinely belong here — not "every file
        # in the repo," picked because they're already directly tied to
        # Brayden's actual day, same bar every other fact in this
        # function already clears (weather/AQI/wildfire above). Left
        # OUT on purpose: generic world/conflict news and broad macro
        # headlines (regime.classify's own narrative below already
        # covers "broader backdrop" — this module is deliberately NOT a
        # macro news ticker), email content (privacy-sensitive enough to
        # want an explicit yes rather than assume), and sports
        # fandom (a real stretch for serious "what affects his actual
        # day" reasoning, versus vibes) — flagged to Brayden rather than
        # silently included or excluded.
        road_issues = road_conditions_511.road_issues_near_commute(now)
        if road_issues:
            issue = road_issues[0]
            roadway = road_conditions_511.readable_roadway(issue["roadway"]) or "a nearby road"
            facts.append(f"Active road issue on his commute route: {roadway} — {issue['type']}")
    except Exception:
        pass
    try:
        weather_for_ice = weather_client.fetch_weather()
        if weather_for_ice and road_conditions.ice_risk(
            weather_for_ice["temp_c"], weather_for_ice.get("forecast_low_c"), weather_for_ice
        ):
            facts.append("Black ice / slick road risk right now — a real safety factor for his commute today")
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


def track_record_summary(limit: int = _HISTORY_DIGEST_LIMIT) -> dict | None:
    """{"n", "bullish_n", "bearish_n", "flat_n", "net_drift_pct"} over
    the last `limit` real cycles, or None with no history yet. Shared
    by _recent_history_digest (the AI's own view, at _HISTORY_DIGEST_
    LIMIT) and pages_brayden_index.py (Brayden's view — pass the SAME
    limit the page's own row list uses, so the summary always matches
    what's actually shown beneath it, not some other window). net_drift
    _pct is the real price ratio across the window (recent[-1] vs.
    recent[0]'s own price), not a naive sum of the individual per-cycle
    percentages — summing would overstate real compounding."""
    if not _report_history:
        return None
    recent = _report_history[-limit:]
    bullish_n = sum(1 for e in recent if e["pct_change"] > 0)
    bearish_n = sum(1 for e in recent if e["pct_change"] < 0)
    start_price = recent[0]["price"]
    net_drift_pct = (recent[-1]["price"] / start_price - 1) * 100 if start_price else 0.0
    return {
        "n": len(recent),
        "bullish_n": bullish_n,
        "bearish_n": bearish_n,
        "flat_n": len(recent) - bullish_n - bearish_n,
        "net_drift_pct": net_drift_pct,
    }


def _recent_history_digest(limit: int = _HISTORY_DIGEST_LIMIT) -> str:
    """A compact, chronological digest of the last `limit` real cycles —
    timestamp, move, sentiment, and named catalysts — fed into every
    prompt so the AI can reason by PRECEDENT instead of reacting fresh
    every cycle with no memory of the last one. Session request:
    "shareholders in real life don't wait for data to come out... they
    build expectations before it comes out" — that only works with a
    real memory to build those expectations FROM. Catalyst labels only,
    not full commentary — this is meant to read as a track record (what
    happened, how big, how it was framed), not a re-read of the
    original prose each time.

    Follow-up session request: an aggregate self-awareness stat on top
    of the itemized list — "make it smarter." A cycle-by-cycle list
    alone still makes the AI eyeball drift by hand; track_record_
    summary's real net-drift number plus a bullish/bearish/flat tally
    gives it — and the critique pass, which reuses this same digest —
    a genuine "have I been drifting one direction without enough new
    reasons to justify it" check, not just raw material to notice that
    itself."""
    stats = track_record_summary(limit)
    if stats is None:
        return "(no cycle history yet — this is early in the index's life)"
    recent = _report_history[-limit:]
    drift_sign = "+" if stats["net_drift_pct"] >= 0 else ""
    summary = (
        f"Summary of these {stats['n']} cycles: net cumulative drift {drift_sign}{stats['net_drift_pct']:.2f}%, "
        f"{stats['bullish_n']} bullish / {stats['bearish_n']} bearish / {stats['flat_n']} flat cycles. If that "
        f"drift has been building steadily in one direction without a real new reason each time, be honest with "
        f"yourself about whether it's still justified or the market's just been drifting on its own momentum."
    )
    lines = []
    for entry in recent:
        when = datetime.fromtimestamp(entry["ts"], tz=ZoneInfo(TIMEZONE)).strftime("%b %d %H:%M")
        sign = "+" if entry["pct_change"] >= 0 else ""
        catalysts = entry.get("catalysts") or []
        if catalysts:
            cat_text = "; ".join(f"{c['label']} ({c['direction']}, {c['magnitude']})" for c in catalysts)
        else:
            cat_text = "no named catalysts"
        lines.append(f"{when}: {sign}{entry['pct_change']:.2f}% ({entry['sentiment']}) — {cat_text}")
    return summary + "\n\n" + "\n".join(f"- {l}" for l in lines)


def _gather_context(now: datetime, readings: dict | None) -> dict:
    """Everything a repricing decision needs, gathered exactly ONCE per
    cycle — signals is real network+computation work (_gather_signals
    hits portfolio/weather/market clients), so a second, skeptical pass
    reasoning about the SAME cycle (see _build_critique_prompt) must
    reuse this, not silently redo every one of those calls a second
    time just to re-derive text it already has."""
    recent = _history[-8:]
    if len(recent) >= 2:
        recent_prices = ", ".join(f"${h['price']:.2f}" for h in recent)
    else:
        recent_prices = "none yet — just IPO'd at $10.00, this is the first real pricing decision"
    return {
        "signals": _gather_signals(now, readings),
        "recent_prices": recent_prices,
        "expectations_text": _expectations or "(no prior expectations recorded yet — this is early in the index's history)",
        "history_digest": _recent_history_digest(),
    }


def _build_prompt(context: dict) -> str:
    return (
        "You are the collective market — the pooled judgment of every hypothetical shareholder and analyst — "
        "pricing BRDN, a fictional publicly traded \"stock\" that represents one real person, Brayden, as if his "
        "whole life and trajectory were a company. This is NOT a net-worth tracker and NOT a weighted sum of the "
        "inputs below. React the way a real market reprices a real stock on news: something already priced in "
        "should barely move the price at all; a genuinely new or unexpected development (good or bad) should move "
        "it more; a temporary/noisy blip should move it less than a real structural change to his actual "
        "trajectory. The SIZE of the move should track the SIZE of the news, in both directions — a quiet cycle "
        "with nothing real happening can and should be tiny (even 0.0%), but don't default to a small number out "
        "of habit or hedge every cycle down to a fraction of a percent just to feel safe. When the signals below "
        "actually support it, move the price decisively — real markets swing hard on real news, and a "
        "shareholder base watching this ticker should be able to tell, just from the size of the move, that "
        "something genuinely happened. There is no fixed ceiling or floor on how far this can move in a single "
        "cycle — trade with real conviction, not caution for its own sake.\n\n"
        f"Current price: ${_price:.2f}. Recent price history, oldest to newest: {context['recent_prices']}.\n\n"
        f"What the market currently believes about Brayden / already has priced in (your own note from last "
        f"cycle): {context['expectations_text']}\n\n"
        f"Your own recent cycle-by-cycle track record, oldest to newest — this is real memory, not a log to "
        f"ignore. A real market that's seen a pattern before reacts to it differently the next time: less "
        f"surprised, already half-expecting it, sometimes barely moving at all. If a similar catalyst shows up "
        f"below and you can see it (or something like it) already happened recently in this history, treat it "
        f"as familiar, not fresh news — react the way a market that remembers would. If nothing like the current "
        f"signals has shown up recently, that absence is itself informative — this genuinely would be new. If "
        f"you notice your own recent moves clustering tightly around the same tiny magnitude cycle after cycle "
        f"even though the underlying signals are actually shifting, that's a sign you've been under-expressing "
        f"conviction, not a pattern to keep matching:\n"
        f"{context['history_digest']}\n\n"
        f"Fresh signals since the last cycle:\n{context['signals']}\n\n"
        "Decide: (1) a percentage price move for this cycle — no fixed range, whatever magnitude the evidence "
        "actually supports, positive or negative, (2) overall sentiment, "
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


# Session request: "a genuine second self critique pass is not a
# terrible idea" — following up on being told plainly this roughly
# doubles BRDN's own AI call volume per cycle (still once per
# REFRESH_SECONDS/NIGHT_REFRESH_SECONDS, just two calls instead of one
# each time, not two SEPARATE cadences) before agreeing to it. A second
# Gemini call, same context (reused from _gather_context, not
# recomputed), shown the FIRST pass's own proposed JSON and asked to
# play skeptical risk manager: does the move actually match the named
# catalysts and recent precedent, or does it over/underreact? Returns
# the SAME JSON shape so it reuses _parse() unchanged — either a
# deliberate confirmation of the original numbers, or a revised
# version. Never a hard requirement: maybe_reprice falls back to the
# unreviewed first pass if this call fails or returns something
# unparseable, exactly the same "a failure skips the improvement, never
# the whole cycle" discipline every other AI call in this app follows.
def _build_critique_prompt(context: dict, proposal: dict) -> str:
    proposed_json = json.dumps({
        "pct_change": proposal["pct_change"],
        "sentiment": proposal["sentiment"],
        "catalysts": proposal["catalysts"],
        "commentary": proposal["commentary"],
        "updated_expectations": proposal["updated_expectations"],
    })
    return (
        "You are a risk manager reviewing another analyst's just-proposed repricing of BRDN, a fictional "
        "\"stock\" representing one real person, Brayden. Your job is NOT to write a fresh take — it's to "
        "sanity-check THIS specific proposal against the same evidence they had, and either confirm it or "
        "correct it if it doesn't actually hold up. Session note, because a past version of this review "
        "consistently erred one direction: this is NOT a mandate to be cautious or to shrink numbers by default "
        "— an analyst who's too timid to size a move to the real news is making the same mistake as one who "
        "overreacts, just in the other direction, and you should correct it exactly as readily.\n\n"
        f"Current price: ${_price:.2f}. Recent price history, oldest to newest: {context['recent_prices']}.\n\n"
        f"What the market already believed going into this cycle: {context['expectations_text']}\n\n"
        f"Recent cycle-by-cycle track record, oldest to newest — use this to judge whether the proposal is "
        f"properly weighing precedent (has something like this happened before and already been mostly priced "
        f"in?) rather than treating everything as equally fresh. If these recent moves are all clustered near "
        f"zero regardless of what the signals said, that's itself evidence of under-reaction to correct, not "
        f"a baseline to protect:\n{context['history_digest']}\n\n"
        f"Fresh signals this cycle was reacting to:\n{context['signals']}\n\n"
        f"The proposed repricing you're reviewing:\n{proposed_json}\n\n"
        "Check specifically, weighing both directions equally: (1) does the pct_change actually match the "
        "direction and combined magnitude of the named catalysts — not a rigid sum, but a real gut-check, is a "
        "big number backed by only minor catalysts, or is a small, hedged number attached to something that "
        "actually reads as major? (2) does it properly account for the recent track record — is it overreacting "
        "to something that's already happened repeatedly and should be mostly priced in by now, or "
        "underreacting/playing it safe on something genuinely new? (3) is the move proportionate to what's "
        "actually in the signals, in EITHER direction — a quiet cycle should stay small, but a cycle with real "
        "news deserves a real, decisive number, not a fraction of a percent out of habit.\n\n"
        "If the proposal genuinely holds up, return it back essentially unchanged. If it doesn't, return your "
        "own corrected version — you're not required to preserve any of its numbers or wording, only to be "
        "consistent with the same evidence; correcting an under-sized move upward is just as valid an outcome "
        "of this review as correcting an oversized one down. Respond with ONLY JSON, no markdown fences, no "
        "other text, in exactly this shape:\n"
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
    ai_pulls_paused directly the way every other Gemini feature does.

    Session request: "a genuine second self critique pass is not a
    terrible idea" — once a real new cycle is confirmed below (the
    SAME gate that already limits this to once per REFRESH_SECONDS/
    NIGHT_REFRESH_SECONDS), a second Gemini call reviews the first
    pass's own proposal before it's applied (see _build_critique_prompt
    for what it actually checks). This doubles the AI calls PER REAL
    CYCLE, not the cadence itself — still only once an hour (or once
    per 3h overnight), just two calls instead of one each time. The
    critique is best-effort: any failure (unavailable, unparseable)
    falls back to the unreviewed first pass rather than blocking the
    cycle — same discipline as every other AI call in this app."""
    # _history/_report_history are mutated in place (append/del below),
    # never reassigned wholesale, so neither needs to be declared global
    # here.
    global _price, _last_report, _expectations, _last_applied_raw
    context = _gather_context(now, readings)
    prompt = _build_prompt(context)
    refresh_seconds = NIGHT_REFRESH_SECONDS if night_mode_active else REFRESH_SECONDS
    # Session request: "make it smarter and more decisive" — 0.4 was
    # low enough to keep producing near-identical, tightly hedged
    # numbers cycle after cycle (the actual "0.05% denomination"
    # complaint). Bumped alongside the prompt rewrite above — this
    # alone wouldn't fix an anchored prompt, but a decisive prompt at a
    # low temperature can still keep collapsing back toward the same
    # safe-looking number every time; more headroom for real variance
    # is the other half of the fix.
    raw = gemini_client.generate_periodic(
        "brayden_index", refresh_seconds, prompt, temperature=0.75, max_output_tokens=600, allow_during_game=True
    )
    if raw is None or raw == _last_applied_raw:
        return  # AI unavailable this call, or this hour's cycle was already applied — nothing new to do

    proposal = _parse(raw)
    # Marked seen BEFORE checking parse success — a malformed response
    # is the SAME cached text for the rest of this hour, so without
    # this, a bad response would get uselessly re-parsed (and re-fail)
    # on every rerun until the next real cycle, instead of just once.
    _last_applied_raw = raw
    persisted_state.save("brdn_last_applied_raw", _last_applied_raw)
    if proposal is None:
        return

    # The critique call is a plain generate(), not generate_periodic —
    # it's tied to THIS specific new cycle (already confirmed genuinely
    # new by the guard above), not its own separate wall-clock cadence.
    # Bumped alongside the prompt rewrite above (see _build_critique_
    # prompt's own comment) — 0.3 on a role explicitly framed as
    # "skeptical risk manager" was a second, compounding pull toward
    # small numbers on top of an already-low-temperature first pass.
    # Still a bit steadier than the primary call's 0.75 (its actual job
    # is a consistency check against the same evidence, not fresh
    # creative reaction), but no longer stacking two separate
    # conservatism levers on every cycle.
    critique_raw = gemini_client.generate(
        _build_critique_prompt(context, proposal), temperature=0.55, max_output_tokens=600, allow_during_game=True
    )
    critique = _parse(critique_raw) if critique_raw else None
    parsed = critique if critique is not None else proposal

    pct = max(MIN_PCT_CHANGE, parsed["pct_change"])
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

    # Session request: "I want it to catch on to patterns... build
    # expectations before data comes out." Every real cycle's outcome
    # gets appended here — not just kept in _last_report, which the
    # very next cycle would overwrite — so _recent_history_digest (see
    # _build_prompt) has real precedent to reason from. Catalysts only,
    # not the full commentary prose — see that function's own docstring
    # for why.
    _report_history.append({
        "ts": ts,
        "price": new_price,
        "pct_change": pct,
        "sentiment": parsed["sentiment"],
        "catalysts": parsed["catalysts"],
    })
    del _report_history[:-MAX_REPORT_HISTORY]

    persisted_state.save("brdn_price", _price)
    persisted_state.save("brdn_history", _history)
    persisted_state.save("brdn_last_report", _last_report)
    persisted_state.save("brdn_expectations", _expectations)
    persisted_state.save("brdn_report_history", _report_history)

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
# time-gated feature in this app. _MORNING_BRIEF_LATEST_HOUR is the
# "on time" window's own end, not a hard cutoff anymore — see the
# catch-up constant/comment right below for why.
_MORNING_BRIEF_HOUR = 9
_MORNING_BRIEF_MINUTE = 30
_MORNING_BRIEF_LATEST_HOUR = 11
# Session report, a real missed brief: "I didn't receive a single
# morning brief today." The original design deliberately gave the
# on-time window no retry at all — skipping for the day, reasoned as
# "more honest than a stale late push" (same shape as commute_reminder.
# LATEST_FIRE_MINUTES). That reasoning holds for WHY the on-time window
# itself stays a window, not an all-day free-for-all — but it also
# meant a single Gemini hiccup anywhere in that one 90-minute stretch
# silently killed the brief for the entire day, with nothing logging or
# surfacing it. This adds a real same-day fallback instead of removing
# the on-time framing: if _MORNING_BRIEF_LATEST_HOUR passes with
# nothing sent, it keeps trying on the next successful cycle up to this
# later cutoff — still cuts off well before end-of-day, since a
# "morning brief" landing at 11pm would be its own kind of dishonest.
_MORNING_BRIEF_CATCHUP_LATEST_HOUR = 18
_MORNING_BRIEF_PUSHED_KEY = "brdn_morning_brief_pushed_date"


def maybe_push_morning_brief(now: datetime, readings: dict | None = None) -> None:
    """Once per real calendar day: on time in the 9:30-11:00am window,
    or as a same-day catch-up up to _MORNING_BRIEF_CATCHUP_LATEST_HOUR
    if the on-time window was missed entirely (see that constant's own
    comment). Calls maybe_reprice first so this gets a genuinely fresh
    read rather than reusing however-old the last hourly cycle happens
    to be — that call is itself a no-op if under an hour has passed
    since the last real cycle (see its own docstring), so this never
    disturbs the normal hourly rhythm or costs an extra AI call on its
    own. Reuses the already-computed commentary/expectations from that
    cycle rather than asking the AI a second, separate question — the
    hourly prompt already produces exactly the "why it moved" reaction
    and "what's priced in" note this brief wants, no new reasoning call
    needed."""
    minutes_now = now.hour * 60 + now.minute
    window_start = _MORNING_BRIEF_HOUR * 60 + _MORNING_BRIEF_MINUTE
    on_time_end = _MORNING_BRIEF_LATEST_HOUR * 60
    catchup_end = _MORNING_BRIEF_CATCHUP_LATEST_HOUR * 60
    if not (window_start <= minutes_now < catchup_end):
        return
    today = now.date().isoformat()
    if persisted_state.load(_MORNING_BRIEF_PUSHED_KEY, None) == today:
        return
    is_catchup = minutes_now >= on_time_end

    # night_mode_active always False here on purpose, not just the
    # default — this window (9:30am-6pm at the latest) can never
    # genuinely overlap night mode.
    maybe_reprice(now, readings)
    if _last_report is None:
        return

    data = current()
    arrow = "▲" if data["change"] > 0 else "▼" if data["change"] < 0 else "●"
    sign = "+" if data["pct_change"] >= 0 else ""
    title = f'BRDN ${data["price"]:.2f} {arrow} {sign}{data["pct_change"]:.2f}% — {data["sentiment"]}'
    commentary = _last_report.get("commentary", "")
    message = f"{commentary}\n\nPriced in: {_expectations}" if _expectations else commentary
    if is_catchup:
        # Honest framing, not silently pretending this is the normal
        # 9:30am read — same reasoning the original "skip rather than
        # send a stale late push" design already valued, just applied
        # to a push that now genuinely goes out instead of an all-day
        # silent gap.
        message = "(This morning's window was missed — catching up now.)\n\n" + message

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
# Session request: "I would argue the employment report is probably the
# biggest catalyst by far... my own little Federal Reserve decision...
# I wonder if the AI is gonna try and hedge the result." Answered
# honestly first — it structurally couldn't, since nothing ever told it
# a report was coming — then built on request. How far ahead the NEXT
# report's due date gets surfaced as a known, scheduled fact in
# _gather_signals (see that function's own block below), same "surfaced
# only if within N days" discipline as payday/CPP/TD-quarter, just a
# longer window since this is a quarterly event, not a biweekly one.
# Deliberately just a calendar fact, not an instruction to hedge or
# dampen volatility — the model decides what, if anything, to do with
# "this is scheduled and anticipated," same "market decides" principle
# every other signal in this module already runs on.
_QUARTERLY_REPORT_LOOKAHEAD_DAYS = 7


def _quarter_label(d) -> str:
    """d is a date or datetime — 'Q1 2027' etc, ordinary calendar
    quarters. Deliberately separate from td_quarter_schedule's own
    fiscal-quarter labels (Feb/May/Aug/Nov) — this is meant to read as
    a normal employment report, not a TD-specific one."""
    quarter_num = (d.month - 1) // 3 + 1
    return f"Q{quarter_num} {d.year}"


def _next_report_due(today: date) -> dict:
    """{"date", "days_until", "quarter_label"} for the NEXT quarter
    boundary strictly after `today` — same construction as
    td_quarter_schedule.next_quarter_start (build this-year's and next-
    year's own candidate dates, take the smallest one still ahead)
    rather than walking forward from an anchor. Strictly `> today`, not
    `>=` — once today IS a boundary day, that quarter's own filing
    window/push/status machinery already covers "due now"; this helper
    is only ever about the one still ahead, so it doesn't double up
    with that on the boundary day itself."""
    candidates = [date(today.year, m, 1) for m in _QUARTERLY_REPORT_MONTHS]
    candidates += [date(today.year + 1, m, 1) for m in _QUARTERLY_REPORT_MONTHS]
    due = min(c for c in candidates if c > today)
    return {"date": due, "days_until": (due - today).days, "quarter_label": _quarter_label(due)}


def next_report_due(today: date) -> dict:
    """Public wrapper around _next_report_due — pages_brdn_terminal.py's
    own "next Q report" readout, so it doesn't reach into a leading-
    underscore internal directly. See that function's own docstring for
    the actual semantics."""
    return _next_report_due(today)


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


# Session request: "during big market-shifting moments... we can see
# the dashboard, like the Bloomberg terminal... I think that'd be kinda
# sick." Same BIG_MOVE_THRESHOLD_PCT already used for the push
# notification (maybe_reprice) and the headline rotation candidate just
# above — this is that SAME signal earning a bigger stage, not a new
# arbitrary bar. A much shorter recency window than that headline's own
# hour-long hold, though — hijacking the entire screen is a far bigger
# interruption than one more rotating banner, so this needs to hand
# normal rotation back on its own quickly rather than camping there.
TAKEOVER_DURATION_SECONDS = 5 * 60


def big_move_takeover_active(now: datetime) -> bool:
    """Whether BRDN just had a genuinely big move recent enough to
    justify app.py pulling up the full terminal page automatically,
    in place of whatever the passive rotation would otherwise be
    showing.

    Session correction: "I feel like you should be based on a daily
    threshold... my stock is down almost two percent today, shareholders
    don't like me." Used to only ever look at the last cycle's own move
    (_last_report["pct_change"]) — real for one sharp single-hour swing,
    but blind to a day that just grinds steadily down across many
    smaller cycles without any single one ever crossing the bar on its
    own, which is exactly as real a "big move" to an actual shareholder.
    Now checks BOTH: the last cycle's own move AND today's cumulative
    move (current()["pct_change"] — the same day-open-anchored figure
    every other display in this app, corner ticker included, already
    shows), taking whichever is larger in magnitude. Deliberately NOT
    extended to big_move_headline_candidate or the push notification in
    maybe_reprice (both still last-cycle-only, unchanged) — a
    persistently bad day would otherwise re-fire an hourly phone push
    all day, a real, higher-cost channel this wasn't asked to make
    noisier; this takeover and the headline banner are both cheap to
    repeat/self-expiring, a push to your phone is not. Ask if you want
    the same daily-move check on either of those too.

    Self-expiring the same way big_move_headline_candidate already is:
    once the NEXT cycle replaces _last_report — big or not — this
    naturally goes false on its own, no separate "have I shown this
    already" state needed. Still gated on a FRESH cycle having just
    landed (updated_at within TAKEOVER_DURATION_SECONDS) even though the
    day-cumulative half of this check isn't itself tied to any one
    cycle — a persistently bad day will keep re-earning a brief takeover
    once per hourly cycle for as long as it stays bad, same "hand
    rotation back quickly" cadence as before, just able to trigger more
    often now. app.py is the one that decides how this ranks against an
    actual live jumbotron game or night mode (see its own routing
    comment) — this only ever answers "is BRDN itself currently in a
    big-move moment," nothing about screen priority."""
    if _last_report is None:
        return False
    cycle_pct = _last_report.get("pct_change", 0.0)
    day_pct = current()["pct_change"]
    move_pct = day_pct if abs(day_pct) >= abs(cycle_pct) else cycle_pct
    if abs(move_pct) < BIG_MOVE_THRESHOLD_PCT:
        return False
    updated_at = _last_report.get("updated_at")
    if updated_at is None:
        return False
    return (now.timestamp() - updated_at) <= TAKEOVER_DURATION_SECONDS
