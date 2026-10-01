"""Monthly net worth tracking — session request: "I report my net worth
every month... I'd love to have my net worth show up on one of the
pages." Checked live: the phone app this gets tracked in (Worth
Tracker) has no export/API/webhook/Shortcuts integration at all, only
cross-device sync within its own app — confirmed via its own site, no
DIY automation to build here (and this project already learned that
lesson once, see the abandoned Shortcuts-to-Upstash webhook for health
data). So this is hand-reported, same shape as the TD shift-calendar
screenshots: the user reports a number in chat once a month, gets
recorded immediately, no code change or redeploy needed for the entry
itself — just a direct persisted_state.save() the same way any other
real-time Upstash write in this app already happens.

Deliberately NOT the same thing as pages_portfolio.py's real-time
Wealthsimple balance — net worth is broader (cash, debt, anything
outside Wealthsimple) and hand-reported monthly, not fetched live.
Shown as its own clearly separate section on that page rather than
folded into or confused with the live investment cards above it.
"""

from datetime import date

import persisted_state

_HISTORY_KEY = "net_worth_history"
_history: list[dict] = persisted_state.load(_HISTORY_KEY, [])


def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def record(amount: float, today: date | None = None) -> None:
    """Records one month's reported net worth — overwrites any existing
    entry for the same calendar month (a correction, not a second
    entry) rather than appending a duplicate, so a late or amended
    report never produces two points for one month on the trend."""
    global _history
    today = today or date.today()
    month_key = _month_key(today)
    entry = {"date": today.isoformat(), "month": month_key, "amount": amount}
    _history = [e for e in _history if e.get("month") != month_key]
    _history.append(entry)
    _history.sort(key=lambda e: e["month"])
    persisted_state.save(_HISTORY_KEY, _history)


def recorded_this_month(today: date) -> bool:
    return any(e.get("month") == _month_key(today) for e in _history)


def due_badge(today: date) -> bool:
    """True from the 1st of the month until this month's entry is
    actually recorded — no artificial end date (unlike the morning-only
    garbage/payday badges), since a monthly task reported "whenever you
    get to it" should keep nagging if it's late, not quietly vanish
    after one morning. Never true before the 1st (nothing to report
    yet) or once this month's already been recorded."""
    return not recorded_this_month(today)


def history() -> list[dict]:
    """{"date", "month", "amount"} per recorded month, oldest first."""
    return list(_history)


def latest() -> dict | None:
    return _history[-1] if _history else None


def change_from_previous() -> dict | None:
    """{"amount_change", "pct_change"} between the two most recent
    recorded months, or None before there are at least two to compare."""
    if len(_history) < 2:
        return None
    current, previous = _history[-1]["amount"], _history[-2]["amount"]
    amount_change = current - previous
    pct_change = (amount_change / previous * 100) if previous else None
    return {"amount_change": amount_change, "pct_change": pct_change}
