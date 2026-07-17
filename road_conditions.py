"""Black-ice / slick-road risk for the commute tile — near-freezing air
temperature combined with a real moisture signal (live radar
precipitation, current rain/snow, or a real forecast chance of it) is
the standard "watch for ice" combination transportation agencies use,
distinct from a plain cold reading alone: pavement lags air temperature
in both directions, so a road can still be icy a couple degrees above
freezing, and dry-and-cold on its own carries none of the same risk.

No new API calls or vendor — built entirely from weather/radar data
this app already fetches for the hero row and rain badge.
"""

import ec_radar
from config import RAIN_PROBABILITY_THRESHOLD

# Air temperature band where a wet or recently-wet road can plausibly
# still be icy — wider than "at or below 0°C" on purpose, since
# pavement temperature lags air temperature by a couple degrees either
# side of freezing, not just at the moment it's exactly 0.
ICE_RISK_LOW_C = -5.0
ICE_RISK_HIGH_C = 3.0


def ice_risk(current_temp_c: float | None, forecast_low_c: float | None, weather: dict) -> bool:
    """True when BOTH a near-freezing temperature (current OR today's
    forecast low — an early-morning drive can hit the daily low even
    on a day that warms up later) AND a real moisture signal are
    present together. Either alone isn't risky: cold-and-dry has no
    ice to speak of, and rain when it's 15°C just doesn't freeze."""
    temps = [t for t in (current_temp_c, forecast_low_c) if t is not None]
    if not temps or not any(ICE_RISK_LOW_C <= t <= ICE_RISK_HIGH_C for t in temps):
        return False

    # Live radar catches precipitation already happening; the forecast
    # chance catches what's expected but hasn't shown up on radar yet
    # (still further out than radar's own ~25km/6-min catch-up window).
    if ec_radar.precip_status("rain") is not None or ec_radar.precip_status("snow") is not None:
        return True
    chance = weather.get("precip_chance")
    return chance is not None and chance >= RAIN_PROBABILITY_THRESHOLD
