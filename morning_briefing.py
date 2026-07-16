"""One auto-generated sentence combining weather, precipitation, air
quality/wildfire, commute, today's agenda, and household status —
instead of reading five separate tiles and mentally combining them
yourself. Only shown during MORNING_WINDOW.

Deliberately built from many distinct phrasings per condition (not one
template with values plugged in) so it reads as actually written about
today, not a form letter — see the *_LINES lists below. Which variant
gets picked is stable for the whole day (seeded by the date + a salt
per category, not re-randomized every rerun), so it doesn't visibly
change every 5 seconds, but still varies day to day even when the
underlying numbers land in the same bucket twice in a row.

Global, not page-local (like commute_reminder.render_leave_headline) —
the whole point is catching you during the actual morning routine,
regardless of which of the 10 rotating pages happens to be up.
"""

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from astral import LocationInfo
from astral.sun import sun

import calendar_client
import commute_client
import commute_reminder
import ec_alerts
import ec_radar
import fuel_price_client
import market_yf_client
import payday_schedule
import waste_schedule
import wildfire_client
from config import AQI_SHOW_THRESHOLD, COMMUTE_DESTINATION, TIMEZONE, WEATHER_LAT, WEATHER_LON
from scenery import condition_category

MORNING_WINDOW_START_HOUR = 5
MORNING_WINDOW_END_HOUR = 10

# Was 3 — widened so a morning that's genuinely eventful (an active
# alert AND rain closing in AND a packed calendar) can actually say all
# of it, instead of silently dropping whichever lost the priority sort.
MAX_CLAUSES = 5

# Duplicated from weather_client rather than imported — same convention
# as this app's other small per-module geo/time math (see ec_radar.py's
# own haversine/bearing helpers): this only needs day length, not a full
# weather fetch, so it's cheaper and more self-contained to compute it
# locally than to widen weather_client's return contract for one caller.
_LOCATION = LocationInfo(latitude=WEATHER_LAT, longitude=WEATHER_LON, timezone=TIMEZONE)

# Every *_LINES list below got a big expansion (a handful of variants
# each -> a couple dozen) — a small pool made the same handful of
# sentences reappear often enough (this is seeded per-day, not
# re-rolled every rerun, but the pool still gets sampled ~365 times a
# year per category) that it started reading like a template with
# blanks filled in rather than something actually written about today.
# More real variants, not smarter templating, is what actually fixes
# that — so these are still each individually written full sentences,
# not fragments recombined at runtime (that trades one kind of
# repetition for a subtler one: mismatched fragments reading slightly
# off). Line count is weighted by how often each category fires — the
# temperature bands and clear-sky line run every single day, so they
# got the most variants; something like the alert wrapper phrase
# (which already inherits real variety from EC's own title text) needed
# the least.
GREETINGS = [
    "", "", "", "", "", "", "", "", "", "",
    "Morning — ", "Good morning. ", "Rise and shine — ", "Here's the rundown: ",
    "Morning. ", "Hey, morning — ", "Top of the morning — ", "Here's where things stand: ",
    "Quick rundown — ", "Alright, here's today: ", "Morning briefing: ", "Here's what's up — ",
    "Kicking off the day — ", "First things first — ",
]

HEAT_LINES = [
    "it's already {temp}°C — bracing for a scorcher, high near {high}°C",
    "{temp}°C and climbing, today's shaping up to be a hot one up to {high}°C",
    "heat's on early, {temp}°C now and headed for {high}°C by afternoon",
    "{temp}°C already — today's going to be a sweaty one, {high}°C expected",
    "hot one today, {temp}°C already with {high}°C on tap",
    "full-on heat today — {temp}°C now, climbing to {high}°C",
    "{temp}°C at this hour, so today's a genuine scorcher, {high}°C by afternoon",
    "no gentle warm-up today, straight to {temp}°C with {high}°C coming",
    "{high}°C is the plan today, and it's already {temp}°C to prove it",
    "today's a stay-in-the-shade kind of day — {temp}°C now, {high}°C later",
    "heat wave energy — {temp}°C already, topping out around {high}°C",
    "{temp}°C and it's still morning — {high}°C by the afternoon",
    "brutal one coming, {temp}°C now on the way to {high}°C",
    "the AC's earning its keep today — {temp}°C already, {high}°C expected",
    "{temp}°C right out of the gate, and {high}°C is where it's heading",
    "summer's not holding back — {temp}°C now, {high}°C by afternoon",
    "hydrate today — {temp}°C already, {high}°C on the way",
    "{high}°C high expected, and {temp}°C right now backs that up",
    "sticky and hot, {temp}°C at the moment, {high}°C coming",
    "today's the kind of hot where {temp}°C this early means {high}°C later",
]
WARM_LINES = [
    "warm start at {temp}°C, climbing to {high}°C — good day to be outside",
    "{temp}°C this morning, {high}°C expected, proper shorts weather",
    "a warm one on tap, {temp}°C now on the way to {high}°C",
    "{temp}°C out already, nice and warm, topping out near {high}°C",
    "solid warm-weather day ahead — {temp}°C now, {high}°C later",
    "{temp}°C and pleasant, {high}°C by afternoon",
    "good patio weather today, {temp}°C now heading to {high}°C",
    "{high}°C expected today, and it's already a comfortable {temp}°C",
    "warm morning, {temp}°C, should hit {high}°C later on",
    "{temp}°C right now — a genuinely nice warm day shaping up, {high}°C ahead",
    "t-shirt weather, {temp}°C already, {high}°C coming this afternoon",
    "today's warm without being oppressive — {temp}°C now, {high}°C high",
    "{temp}°C out there, a solid warm start to the day",
    "nice stretch of warmth today, {temp}°C now, {high}°C later",
    "{high}°C on the docket, {temp}°C already backs it up",
    "warm and easy today — {temp}°C now, climbing toward {high}°C",
    "{temp}°C this morning, the good kind of warm, {high}°C by afternoon",
    "outdoor-plans weather — {temp}°C now, {high}°C expected",
    "{temp}°C already and only getting warmer, {high}°C by later",
    "a genuinely pleasant warm day ahead, {temp}°C now, {high}°C to come",
]
MILD_LINES = [
    "a comfortable {temp}°C to start the day",
    "{temp}°C out there, pretty pleasant, high of {high}°C expected",
    "mild morning, {temp}°C, nothing to complain about",
    "{temp}°C right now, easy weather, {high}°C by afternoon",
    "{temp}°C out — about as mild as it gets",
    "nothing dramatic weather-wise today, {temp}°C now, {high}°C later",
    "{temp}°C this morning, a perfectly ordinary, pleasant day ahead",
    "mild and easy, {temp}°C now, {high}°C expected",
    "{temp}°C out there — a low-key, comfortable day shaping up",
    "middle-of-the-road weather today, {temp}°C now, {high}°C by afternoon",
    "{temp}°C right now, nothing to plan around either way",
    "a fairly unremarkable, comfortable {temp}°C this morning",
    "{high}°C expected today, and {temp}°C right now is a mild start",
    "no extremes today — {temp}°C now, {high}°C later",
    "{temp}°C out, easygoing weather all around",
    "mild enough to not think twice about it — {temp}°C now",
    "{temp}°C this morning, {high}°C by afternoon, business as usual",
    "steady, mild {temp}°C to kick off the day",
    "{temp}°C right now — comfortable, unremarkable, fine",
    "an easy {temp}°C morning, {high}°C expected later",
]
COOL_LINES = [
    "cooler start, {temp}°C — worth a jacket on your way out",
    "{temp}°C this morning, a bit brisk before it warms to {high}°C",
    "chilly-ish, {temp}°C now, {high}°C by afternoon",
    "{temp}°C out, cool enough for a light layer",
    "brisk morning, {temp}°C right now, {high}°C expected later",
    "{temp}°C out there — grab a jacket for the early hours",
    "cool start to the day, {temp}°C now, warming to {high}°C",
    "{temp}°C this morning, a bit of a bite in the air",
    "not quite warm yet — {temp}°C now, {high}°C by afternoon",
    "{temp}°C out, a proper cool-morning feel",
    "a light-jacket kind of morning, {temp}°C now",
    "{temp}°C right now, cool but not cold, {high}°C coming later",
    "the morning air's got a chill, {temp}°C now",
    "{temp}°C out there — cool enough to notice, {high}°C by afternoon",
    "crisp start today, {temp}°C now, {high}°C expected",
    "{temp}°C this morning, definitely a layer-up situation early on",
    "cool and clear at {temp}°C, {high}°C by later",
    "{temp}°C out — nothing serious, just a cool morning edge",
    "a bit nippy out, {temp}°C now, warming toward {high}°C",
    "{temp}°C right now, cool enough for long sleeves",
]
COLD_LINES = [
    "it's {temp}°C — bundle up before you head out",
    "{temp}°C this morning, proper cold, high only {high}°C",
    "cold one, {temp}°C now, dress for it",
    "{temp}°C out there, winter's not messing around today",
    "{temp}°C right now — genuinely cold, {high}°C is the best it gets",
    "layer up, {temp}°C out there this morning",
    "{temp}°C now, a real cold snap kind of day",
    "cold and no way around it — {temp}°C this morning",
    "{temp}°C out, high of only {high}°C — dress warm",
    "winter's fully in charge today, {temp}°C now",
    "{temp}°C right now, the kind of cold that earns a real coat",
    "brutal start, {temp}°C this morning, {high}°C the ceiling",
    "{temp}°C out there — mittens weather",
    "cold snap continues, {temp}°C now, {high}°C by afternoon",
    "{temp}°C this morning, exposed skin is not the move today",
    "deep cold out there, {temp}°C right now",
    "{temp}°C now — today's a stay-bundled-up day, {high}°C high",
    "genuinely frigid, {temp}°C this morning",
    "{temp}°C out, the car's going to need a minute to warm up",
    "cold enough to feel it immediately — {temp}°C right now",
]

# About half of these weave in {direction} (e.g. "northwest") — the
# bearing from Corbeil to the nearest echo, which ec_radar.precip_status
# now surfaces (see its docstring: this is where the storm currently
# IS, not which way it's moving). The other half deliberately skip it —
# every single line naming a direction would just trade one repetitive
# pattern for another.
RADAR_RAIN_LINES = [
    "radar's picking up rain heading your way, could hit in about {eta} min",
    "rain's closing in on the radar, roughly {eta} minutes out",
    "heads up, rain looks to be moving in from the {direction}, ETA around {eta} minutes",
    "radar's showing rain on approach, about {eta} minutes off",
    "rain's tracking toward you from the {direction}, roughly {eta} minutes away",
    "there's rain on the radar closing in, {eta} minutes or so",
    "incoming rain out of the {direction}, radar puts it around {eta} minutes out",
    "radar's caught rain moving in — {eta} minutes, give or take",
    "worth knowing: rain's approaching from the {direction}, about {eta} minutes away",
    "rain's on its way in per the radar, {eta} minutes out",
    "radar shows a cell heading in from the {direction}, rain in roughly {eta} minutes",
    "{eta} minutes and change before that rain out of the {direction} gets here",
]
RADAR_SNOW_LINES = [
    "radar's picking up snow heading your way, could hit in about {eta} min",
    "snow's closing in on the radar, roughly {eta} minutes out",
    "heads up, snow looks to be moving in from the {direction}, ETA around {eta} minutes",
    "radar's showing snow on approach, about {eta} minutes off",
    "snow's tracking toward you from the {direction}, roughly {eta} minutes away",
    "there's snow on the radar closing in, {eta} minutes or so",
    "incoming snow out of the {direction}, radar puts it around {eta} minutes out",
    "radar's caught snow moving in — {eta} minutes, give or take",
    "worth knowing: snow's approaching from the {direction}, about {eta} minutes away",
    "snow's on its way in per the radar, {eta} minutes out",
    "radar shows a system heading in from the {direction}, snow in roughly {eta} minutes",
    "{eta} minutes and change before that snow out of the {direction} gets here",
]
ARRIVED_RAIN_LINES = [
    "rain's here now, radar's got it clearing in about {eta} min",
    "it's raining now, should clear up in roughly {eta} minutes",
    "rain's arrived — radar has it moving out in about {eta} minutes",
    "it's coming down now, expect it to clear in {eta} minutes or so",
    "rain's here, but it shouldn't stick around — clearing in about {eta} min",
    "wet out there right now, radar says {eta} minutes until it clears",
    "rain's moved in — {eta} minutes till it's through",
    "it's actively raining, radar's tracking it clearing in {eta} min",
    "rain's on top of you now, {eta} minutes before it lets up",
    "yep, it's raining — should ease off in about {eta} minutes",
]
ARRIVED_SNOW_LINES = [
    "snow's here now, radar's got it clearing in about {eta} min",
    "it's snowing now, should clear up in roughly {eta} minutes",
    "snow's arrived — radar has it moving out in about {eta} minutes",
    "it's coming down now, expect it to clear in {eta} minutes or so",
    "snow's here, but it shouldn't stick around — clearing in about {eta} min",
    "snowing out there right now, radar says {eta} minutes until it clears",
    "snow's moved in — {eta} minutes till it's through",
    "it's actively snowing, radar's tracking it clearing in {eta} min",
    "snow's on top of you now, {eta} minutes before it lets up",
    "yep, it's snowing — should ease off in about {eta} minutes",
]
FORECAST_RAIN_LINES = [
    "rain's in the forecast today, {chance}% chance around {time} — grab an umbrella on your way out",
    "looks like rain later, {chance}% chance near {time}",
    "{chance}% chance of rain today, expected around {time}",
    "rain's possible today, {chance}% chance around {time}",
    "forecast's calling for rain, {chance}% chance near {time} — worth a plan B",
    "{chance}% odds of rain today, looks like around {time}",
    "keep an umbrella handy — {chance}% chance of rain around {time}",
    "rain's on the forecast for around {time}, {chance}% chance",
    "{chance}% chance of getting wet today, sometime near {time}",
    "not a guarantee, but {chance}% chance of rain around {time}",
    "forecast has rain penciled in for {time}, {chance}% chance",
    "{chance}% chance of rain later — {time} is the window",
    "might want a jacket with a hood — {chance}% chance of rain near {time}",
    "rain's forecast for around {time} today, {chance}% likely",
]
FORECAST_SNOW_LINES = [
    "snow's in the forecast today, {chance}% chance around {time} — plan accordingly",
    "looks like snow later, {chance}% chance near {time}",
    "{chance}% chance of snow today, expected around {time}",
    "snow's possible today, {chance}% chance around {time}",
    "forecast's calling for snow, {chance}% chance near {time} — plan the drive accordingly",
    "{chance}% odds of snow today, looks like around {time}",
    "keep the boots handy — {chance}% chance of snow around {time}",
    "snow's on the forecast for around {time}, {chance}% chance",
    "{chance}% chance of snow today, sometime near {time}",
    "not a lock, but {chance}% chance of snow around {time}",
    "forecast has snow penciled in for {time}, {chance}% chance",
    "{chance}% chance of snow later — {time} is the window",
    "might want to budget extra drive time — {chance}% chance of snow near {time}",
    "snow's forecast for around {time} today, {chance}% likely",
]
CLEAR_SKY_LINES = [
    "skies look clear for now",
    "no rain in the forecast, small mercies",
    "dry morning ahead, nothing on the radar",
    "clear skies today, nothing weather-wise to plan around",
    "nothing but dry weather on tap today",
    "no precipitation in sight, radar's quiet",
    "clean forecast today — no rain, no snow",
    "dry and clear, nothing to report weather-wise",
    "radar's empty, should be a dry one",
    "nothing coming in on the radar right now",
    "forecast's clear straight through — no rain expected",
    "a dry day ahead, skies looking clear",
    "no wet weather in the cards today",
    "clear and quiet out there, radar-wise",
    "today's shaping up dry, nothing on the horizon",
    "no umbrella needed today, by the look of it",
    "skies are clear, nothing brewing on radar",
    "dry conditions expected all day",
]

WILDFIRE_LINES = [
    "air quality's rough today ({aqi}) — looks like smoke from a wildfire about {distance:.0f}km out",
    "hazy out, {aqi} AQI, likely wildfire smoke drifting in from roughly {distance:.0f}km away",
    "air's not great this morning ({aqi}), wildfire smoke nearby, closest fire about {distance:.0f}km off",
    "AQI's at {aqi} today, smoke from a fire around {distance:.0f}km out is the likely cause",
    "wildfire smoke's rolling in — AQI at {aqi}, source fire roughly {distance:.0f}km away",
    "{aqi} AQI this morning, probably smoke drifting from {distance:.0f}km out",
    "hazy skies again, AQI {aqi}, a wildfire about {distance:.0f}km away seems to be the culprit",
    "smoke's affecting the air today ({aqi} AQI), nearest fire roughly {distance:.0f}km off",
    "air quality's taken a hit, {aqi} AQI — wildfire smoke from about {distance:.0f}km out",
    "{aqi} on the AQI scale this morning, wildfire smoke the likely reason, {distance:.0f}km away",
    "not the cleanest air today, {aqi} AQI, smoke traced to a fire {distance:.0f}km out",
    "wildfire smoke again — {aqi} AQI, fire's about {distance:.0f}km away",
]
AQI_ONLY_LINES = [
    "air quality's elevated today ({aqi}) — maybe skip the outdoor workout",
    "AQI's sitting at {aqi}, a bit rough for being outside long",
    "air's not at its best today, AQI {aqi}",
    "{aqi} on the AQI scale — nothing severe, but worth noting",
    "air quality's a bit off today, sitting at {aqi}",
    "AQI's up to {aqi} this morning, keep that in mind if you're active outside",
    "not the cleanest air today — AQI reading {aqi}",
    "{aqi} AQI this morning, a touch elevated",
    "air quality's mildly worse than usual, {aqi} on the scale",
    "worth knowing — AQI's at {aqi} today",
    "{aqi} AQI right now, nothing alarming but noticeable",
    "air's a little heavier today, AQI sitting at {aqi}",
]

COMMUTE_BAD_LINES = [
    "commute's rough this morning, {delay} extra minutes{reason}",
    "roads are backed up, {delay} min of delay heading to {destination}{reason}",
    "give yourself extra time, {delay} minutes of traffic on the way to {destination}{reason}",
    "traffic's bad today, {delay} extra minutes to {destination}{reason}",
    "heads up, {delay} minutes of delay on the way to {destination}{reason}",
    "rough morning on the roads, {delay} extra minutes to {destination}{reason}",
    "commute's going to run long — {delay} minutes over normal to {destination}{reason}",
    "{delay} minutes of extra traffic heading to {destination} today{reason}",
    "leave earlier than usual — {delay} minutes of delay to {destination}{reason}",
    "the roads aren't cooperating, {delay} extra minutes to {destination}{reason}",
    "significant delay this morning, {delay} minutes over normal to {destination}{reason}",
    "budget extra time — {delay} minutes of traffic to {destination}{reason}",
    "not a fast one today, {delay} minutes over usual heading to {destination}{reason}",
    "{delay} minutes slower than normal to {destination} this morning{reason}",
]
COMMUTE_MINOR_LINES = [
    "a few extra minutes on the roads today, {duration} min total to {destination}",
    "light traffic, {delay} min slower than usual heading to {destination}",
    "minor delay today, {duration} minutes total to {destination}",
    "roads are a little slower than usual, {duration} min to {destination}",
    "nothing major, just {delay} extra minutes to {destination}",
    "{duration} minutes to {destination} today, a touch slower than normal",
    "slight traffic this morning, {delay} min added to {destination}",
    "a small delay heading to {destination}, {duration} minutes total",
    "{delay} minutes over normal to {destination} — not bad",
    "roads are mostly fine, just {delay} minutes slower to {destination}",
    "a bit of traffic, {duration} min to {destination} this morning",
    "{duration} minutes to {destination}, only slightly off pace today",
]
COMMUTE_CLEAR_LINES = [
    "roads are clear, {duration} min to {destination} like normal",
    "smooth drive in today, {duration} minutes to {destination}",
    "no delays on the way to {destination}, {duration} min as usual",
    "clear roads this morning, {duration} minutes to {destination}",
    "commute's running normal, {duration} min to {destination}",
    "nothing standing between you and {destination} today — {duration} minutes",
    "traffic's cooperating, {duration} min to {destination}",
    "{duration} minutes to {destination}, business as usual",
    "easy drive today, {duration} min to {destination}",
    "roads look good this morning, {duration} minutes to {destination}",
    "no surprises on the way to {destination}, {duration} min",
    "{duration} minutes to {destination} — right on schedule",
    "smooth sailing to {destination} today, {duration} min",
    "commute's a non-event today, {duration} minutes to {destination}",
]

AGENDA_BUSY_LINES = [
    "packed day, {count} things on the calendar, starting with {first_event} at {time}",
    "busy one today, {count} on the books, kicking off with {first_event} at {time}",
    "{count} things on the calendar today, first up is {first_event} at {time}",
    "full schedule today — {count} events, starting with {first_event} at {time}",
    "busy day ahead, {count} on the calendar, {first_event} first at {time}",
    "lots on today, {count} things lined up, {first_event} kicks it off at {time}",
    "{count} events on the books today, leading with {first_event} at {time}",
    "today's stacked — {count} things, first one's {first_event} at {time}",
    "a full plate today, {count} on the calendar, {first_event} at {time} to start",
    "{count} things to get through today, starting with {first_event} at {time}",
    "no quiet day today — {count} events, first is {first_event} at {time}",
    "busy calendar today, {count} entries, opening with {first_event} at {time}",
]
AGENDA_LIGHT_LINES = [
    "just {first_event} at {time} on the calendar today",
    "light schedule, {first_event} at {time} is the main thing today",
    "not much on today, just {first_event} at {time}",
    "one thing on the calendar — {first_event} at {time}",
    "today's fairly open, just {first_event} at {time}",
    "{first_event} at {time} is really the only thing today",
    "light day, {first_event} at {time} is on the books",
    "just the one event today — {first_event} at {time}",
    "{first_event} at {time}, otherwise the day's yours",
    "not a busy one — {first_event} at {time} is it",
    "the calendar's quiet aside from {first_event} at {time}",
    "{first_event} at {time} is the sole thing on today's agenda",
]
AGENDA_EMPTY_LINES = [
    "calendar's wide open today",
    "nothing on the agenda, a rare quiet one",
    "no events today, a blank slate",
    "the calendar's completely clear today",
    "nothing scheduled — a genuinely free day",
    "not a single thing on the calendar today",
    "today's yours, nothing booked",
    "a clean slate today, calendar-wise",
    "no meetings, no events, nothing today",
    "the day's wide open, nothing planned",
    "zero commitments on the calendar today",
    "nothing pulling at your schedule today",
    "a rare open day — nothing on the books",
    "the calendar's empty today, for once",
]

GARBAGE_LINES = [
    "bins go out tonight, it's {kind} day",
    "don't forget: {kind} day today",
    "{kind} day today — bins out before you forget",
    "reminder: today's {kind} day",
    "{kind} pickup is today, bins out tonight",
    "it's {kind} day — don't miss it",
    "don't let it slip: {kind} day is today",
    "{kind} day today, worth setting a reminder for tonight",
    "bins out tonight — it's {kind} day",
    "today's the day — {kind} pickup",
]
PAYDAY_TODAY_LINES = [
    "and it's payday today",
    "bonus: it's payday today",
    "also — payday hits today",
    "small win today: it's payday",
    "today's payday, if that helps the morning",
    "payday lands today",
    "the good news: payday's today",
    "today's a payday, for what it's worth",
    "on the bright side, it's payday today",
    "payday today — that's something",
    "today's the day the paycheck lands",
    "silver lining: payday's today",
]
PAYDAY_TOMORROW_LINES = [
    "payday's tomorrow",
    "one more day till payday",
    "payday hits tomorrow",
    "almost there — payday's tomorrow",
    "tomorrow's payday",
    "payday's just a day away",
    "hang in there, payday's tomorrow",
    "the paycheck lands tomorrow",
    "one more sleep till payday",
    "tomorrow brings payday",
]
GAS_ECO_LINES = [
    "gas ticked up to {price:.1f}¢, might hold off on filling up if you can",
    "prices are up ({price:.1f}¢/L), eco mode's worth it today",
    "gas is a bit pricier right now at {price:.1f}¢/L — maybe hold off on filling up",
    "{price:.1f}¢/L at the pump today, worth waiting if you can",
    "prices climbed to {price:.1f}¢/L — eco driving pays off today",
    "gas is up to {price:.1f}¢/L, might be worth topping up later instead",
    "{price:.1f}¢/L right now — a pricier day to fill up",
    "worth noting: gas is at {price:.1f}¢/L today, a bit above average",
    "fuel's up to {price:.1f}¢/L — eco mode earns its keep today",
    "{price:.1f}¢/L at the pump — maybe stretch the tank a bit longer",
]

ALERT_LINES = [
    "heads up: {title}",
    "worth knowing this morning — {title}",
    "one to watch: {title}",
    "important today: {title}",
    "before anything else — {title}",
    "keep this in mind today: {title}",
    "worth flagging: {title}",
    "today's notable one: {title}",
    "don't skip this: {title}",
    "on the radar today: {title}",
]

MARKET_UP_LINES = [
    "markets are green so far, S&P +{pct}%",
    "S&P's up {pct}% this morning",
    "green start for the market, up {pct}%",
    "markets opened well, S&P +{pct}%",
    "a positive start to trading, up {pct}%",
    "S&P's in the green, +{pct}% so far",
    "markets are up {pct}% this morning",
    "a good sign so far — S&P +{pct}%",
    "green across the board so far, +{pct}%",
    "S&P's climbing, up {pct}% this morning",
    "solid open for the market, +{pct}%",
    "markets kicking off positive, S&P +{pct}%",
    "up {pct}% so far — a decent start",
    "S&P's ahead {pct}% this morning",
]
MARKET_DOWN_LINES = [
    "markets are red this morning, S&P -{pct}%",
    "S&P's down {pct}% so far",
    "a rough start for the market, off {pct}%",
    "markets opened weak, S&P -{pct}%",
    "red across the board so far, down {pct}%",
    "S&P's slipping, off {pct}% this morning",
    "not a great start — markets down {pct}%",
    "a soft open for the market, -{pct}%",
    "markets kicking off negative, S&P -{pct}%",
    "down {pct}% so far — a shaky start",
    "S&P's behind {pct}% this morning",
    "markets are in the red, down {pct}%",
    "a bit of a pullback this morning, -{pct}%",
    "S&P's off to a rough start, -{pct}%",
]
MARKET_FLAT_LINES = [
    "markets are flat this morning",
    "S&P's roughly unchanged so far",
    "nothing dramatic in the markets today",
    "markets are quiet so far this morning",
    "S&P's holding steady to start",
    "flat open for the market today",
    "not much movement in the markets so far",
    "markets are treading water this morning",
    "a quiet start for the S&P today",
    "no real direction in the markets yet",
    "markets are sitting still so far",
    "S&P's barely moved this morning",
]

# Deliberately the lowest-priority clause of all of them (see its
# priority=1 below) — it's always available (every day has a sunrise and
# sunset), so without a low priority it would crowd out genuinely
# time-sensitive info on a busy morning. It's here for the quieter days,
# to tie the daily routine to the bigger, slower cycle behind it.
DAYLIGHT_GAINING_LINES = [
    "days are stretching out — {delta} more minutes of daylight than yesterday, sunset at {sunset}",
    "gaining daylight now, {delta} minutes more than yesterday",
    "the days keep growing, {delta} extra minutes of light today",
    "daylight's on the increase, {delta} minutes more than yesterday",
    "{delta} more minutes of daylight today than yesterday",
    "the days are getting longer, {delta} minutes gained since yesterday",
    "more light today — {delta} extra minutes versus yesterday, sunset at {sunset}",
    "daylight keeps expanding, {delta} minutes more than yesterday",
    "picking up {delta} minutes of daylight from yesterday",
    "sunset's later today — {sunset}, {delta} minutes more daylight than yesterday",
    "the daylight stretch continues, {delta} minutes gained",
    "{delta} minutes of extra daylight today, sunset creeping to {sunset}",
]
DAYLIGHT_LOSING_LINES = [
    "days are shrinking — {delta} fewer minutes of daylight than yesterday, sunset at {sunset}",
    "losing daylight now, {delta} minutes less than yesterday",
    "the days are contracting, {delta} fewer minutes of light today",
    "daylight's on the decline, {delta} minutes less than yesterday",
    "{delta} fewer minutes of daylight today than yesterday",
    "the days are getting shorter, {delta} minutes lost since yesterday",
    "less light today — {delta} fewer minutes versus yesterday, sunset at {sunset}",
    "daylight keeps shrinking, {delta} minutes less than yesterday",
    "losing {delta} minutes of daylight from yesterday",
    "sunset's earlier today — {sunset}, {delta} minutes less daylight than yesterday",
    "the daylight retreat continues, {delta} minutes lost",
    "{delta} fewer minutes of daylight today, sunset creeping to {sunset}",
]


def _pick(options: list[str], now: datetime, salt: str) -> str:
    rng = random.Random(f"{now.date().isoformat()}-{salt}")
    return rng.choice(options)


def _weather_clause(now: datetime, weather: dict) -> tuple[int, str] | None:
    temp = weather.get("temp_c")
    high = weather.get("forecast_high_c")
    if temp is None:
        return None
    high_text = f"{high:.0f}" if high is not None else f"{temp:.0f}"
    fmt = {"temp": f"{temp:.0f}", "high": high_text}
    if temp >= 30:
        lines = HEAT_LINES
    elif temp >= 22:
        lines = WARM_LINES
    elif temp >= 12:
        lines = MILD_LINES
    elif temp >= 0:
        lines = COOL_LINES
    else:
        lines = COLD_LINES
    return 3, _pick(lines, now, "weather").format(**fmt)


def _precip_clause(now: datetime, weather: dict, category: str) -> tuple[int, str] | None:
    status = ec_radar.precip_status("snow" if category == "snow" else "rain")
    if status is not None and status["minutes"] is not None:
        is_snow = category == "snow"
        if status["state"] == "arrived":
            lines = ARRIVED_SNOW_LINES if is_snow else ARRIVED_RAIN_LINES
        else:
            lines = RADAR_SNOW_LINES if is_snow else RADAR_RAIN_LINES
        return 8, _pick(lines, now, "precip").format(eta=status["minutes"], direction=status["direction_word"])

    rain_at = weather.get("rain_at")
    chance = weather.get("precip_chance")
    if rain_at is not None and chance is not None:
        is_snow = weather.get("precip_kind") == "snow"
        lines = FORECAST_SNOW_LINES if is_snow else FORECAST_RAIN_LINES
        time_text = rain_at.strftime("%I:%M %p").lstrip("0")
        return 7, _pick(lines, now, "precip").format(chance=chance, time=time_text)

    return 1, _pick(CLEAR_SKY_LINES, now, "precip")


def _air_clause(now: datetime, air_quality: dict | None) -> tuple[int, str] | None:
    aqi = air_quality.get("us_aqi") if air_quality else None
    if aqi is None or aqi <= AQI_SHOW_THRESHOLD:
        return None
    wildfire = wildfire_client.nearest_wildfire()
    if wildfire is not None:
        text = _pick(WILDFIRE_LINES, now, "air").format(aqi=round(aqi), distance=wildfire["distance_km"])
        return 8, text
    return 5, _pick(AQI_ONLY_LINES, now, "air").format(aqi=round(aqi))


def _commute_clause(now: datetime) -> tuple[int, str] | None:
    destination = commute_reminder.todays_destination(now)
    using_default = destination is COMMUTE_DESTINATION
    data = commute_client.route(None if using_default else destination)
    if not data:
        return None
    duration = round(data["duration_seconds"] / 60)
    delay = round(data["delay_seconds"] / 60)
    dest_label = destination["label"]
    if delay >= 10:
        reason = f", mostly {data['incident']}" if data.get("incident") else ""
        text = _pick(COMMUTE_BAD_LINES, now, "commute").format(
            delay=delay, destination=dest_label, reason=reason
        )
        return 6, text
    if delay >= 1:
        text = _pick(COMMUTE_MINOR_LINES, now, "commute").format(delay=delay, duration=duration, destination=dest_label)
        return 4, text
    text = _pick(COMMUTE_CLEAR_LINES, now, "commute").format(duration=duration, destination=dest_label)
    return 2, text


def _agenda_clause(now: datetime) -> tuple[int, str] | None:
    calendars = st.secrets.get("CALENDARS")
    if not calendars:
        return None
    events = [e for e in calendar_client.todays_events(calendars, now.date()) if not e["all_day"]]
    if not events:
        return 1, _pick(AGENDA_EMPTY_LINES, now, "agenda")
    events.sort(key=lambda e: e["start"])
    first = events[0]
    time_text = first["start"].strftime("%I:%M %p").lstrip("0")
    if len(events) >= 3:
        text = _pick(AGENDA_BUSY_LINES, now, "agenda").format(
            count=len(events), first_event=first["summary"], time=time_text
        )
        return 5, text
    text = _pick(AGENDA_LIGHT_LINES, now, "agenda").format(first_event=first["summary"], time=time_text)
    return 3, text


def _household_clause(now: datetime) -> tuple[int, str] | None:
    # Payday today outranks everything else in this clause — genuinely
    # the best household news any of these branches can carry, same
    # "today or tomorrow" gating as the hero-row badge (see app.py).
    payday = payday_schedule.next_payday(now.date())
    if payday["days_until"] == 0:
        return 6, _pick(PAYDAY_TODAY_LINES, now, "household")
    pickup = waste_schedule.next_pickup(now.date())
    if pickup["days_until"] == 0:
        return 4, _pick(GARBAGE_LINES, now, "household").format(kind=pickup["kind"].lower())
    if payday["days_until"] == 1:
        return 3, _pick(PAYDAY_TOMORROW_LINES, now, "household")
    gas = fuel_price_client.eco_mode_status()
    if gas and gas["eco_recommended"]:
        return 2, _pick(GAS_ECO_LINES, now, "household").format(price=gas["price"])
    return None


def _alert_clause(now: datetime) -> tuple[int, str] | None:
    alerts = ec_alerts.fetch_alerts()
    if not alerts:
        return None
    text = _pick(ALERT_LINES, now, "alert").format(title=alerts[0]["title"])
    return 10, text


def _markets_clause(now: datetime) -> tuple[int, str] | None:
    status = market_yf_client.market_status(now)
    if status == "weekend":
        return None
    symbol = market_yf_client.primary_symbol(status)
    quote = market_yf_client.quote_for(symbol)
    if not quote or quote["intraday"] is None:
        return None
    pct = quote["intraday"]
    fmt = {"pct": f"{abs(pct):.1f}"}
    if pct >= 0.15:
        lines = MARKET_UP_LINES
    elif pct <= -0.15:
        lines = MARKET_DOWN_LINES
    else:
        lines = MARKET_FLAT_LINES
    return 3, _pick(lines, now, "markets").format(**fmt)


def _day_length_minutes(day) -> float:
    s = sun(_LOCATION.observer, date=day, tzinfo=ZoneInfo(TIMEZONE))
    return (s["sunset"] - s["sunrise"]).total_seconds() / 60


def _daylight_clause(now: datetime, weather: dict) -> tuple[int, str] | None:
    sunset = weather.get("sunset")
    if sunset is None:
        return None
    try:
        today_len = _day_length_minutes(now.date())
        yesterday_len = _day_length_minutes(now.date() - timedelta(days=1))
    except Exception:
        return None
    delta = round(today_len - yesterday_len)
    if delta == 0:
        return None
    fmt = {"delta": abs(delta), "sunset": sunset.strftime("%I:%M %p").lstrip("0")}
    lines = DAYLIGHT_GAINING_LINES if delta > 0 else DAYLIGHT_LOSING_LINES
    return 1, _pick(lines, now, "daylight").format(**fmt)


def render(now: datetime, weather: dict | None, air_quality: dict | None) -> None:
    if not (MORNING_WINDOW_START_HOUR <= now.hour < MORNING_WINDOW_END_HOUR):
        return
    if not weather:
        return

    category = condition_category(weather["weather_code"])
    clauses = []
    for fn, args in (
        (_alert_clause, (now,)),
        (_weather_clause, (now, weather)),
        (_precip_clause, (now, weather, category)),
        (_air_clause, (now, air_quality)),
        (_commute_clause, (now,)),
        (_agenda_clause, (now,)),
        (_household_clause, (now,)),
        (_markets_clause, (now,)),
        (_daylight_clause, (now, weather)),
    ):
        try:
            result = fn(*args)
        except Exception:
            result = None
        if result is not None:
            clauses.append(result)

    if not clauses:
        return
    clauses.sort(key=lambda c: c[0], reverse=True)
    picked = [text for _, text in clauses[:MAX_CLAUSES]]
    sentence = "; ".join(picked)
    sentence = sentence[0].upper() + sentence[1:] + "."
    greeting = _pick(GREETINGS, now, "greeting")

    st.markdown(f'<div class="morning-briefing">{greeting}{sentence}</div>', unsafe_allow_html=True)
