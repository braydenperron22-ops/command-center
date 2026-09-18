"""Personal birthdays — session request: "make it so September 18th is
always flagged as Chloe's birthday. I want to make sure I don't forget."
Same "next occurrence of a fixed annual date" shape as holidays_client.
next_holiday/seasons_client.next_season_start/td_quarter_schedule.
next_quarter_start/cpp_payment_dates.next_payment_date/waste_schedule.
next_pickup — a plain hand-maintained list, not a calendar feed: there's
no external source for "whose birthday is this," this app's own
USER_PROFILE (config.py) is already the precedent for hand-maintained
personal facts like this.
"""

from datetime import date

# Add more here the same way if needed — {"label", "month", "day"}.
# Chloe: config.USER_PROFILE's own "long-term relationship with
# girlfriend Chloe."
BIRTHDAYS = [
    {"label": "Chloe's birthday", "month": 9, "day": 18},
]


def next_birthday(today: date) -> dict | None:
    """{"label", "date", "days_until"} for the soonest birthday on/after
    today, wrapping to next year once this year's date has passed —
    same shape as holidays_client.next_holiday, for the same hero-badge
    gating in app.py (today, or tomorrow after EVENING_BADGE_HOUR).
    None only if BIRTHDAYS is empty."""
    best = None
    for b in BIRTHDAYS:
        try:
            this_year = date(today.year, b["month"], b["day"])
        except ValueError:
            continue  # a real Feb 29 birthday in a non-leap year — skip rather than crash
        occurrence = this_year if this_year >= today else date(today.year + 1, b["month"], b["day"])
        days_until = (occurrence - today).days
        if best is None or days_until < best["days_until"]:
            best = {"label": b["label"], "date": occurrence, "days_until": days_until}
    return best
