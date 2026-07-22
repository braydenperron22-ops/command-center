"""One auto-generated sentence combining weather, precipitation, air
quality/wildfire, commute, today's agenda, and household status —
instead of reading five separate tiles and mentally combining them
yourself. Only shown during MORNING_WINDOW.

Which facts make the cut and in what order is still decided entirely
by the *_clause functions below, each returning (priority, text) —
that logic is untouched. Historically the picked texts were then just
semicolon-joined from many distinct hand-written phrasings per
condition (see the *_LINES lists below) so it read as actually written
about today, not a form letter. Session request ("revamp the morning
brief" with a free AI) added a step on top: render() now asks Gemini
(_ai_sentence, gemini_client.generate) to weave those same picked
texts into real flowing prose instead of a mechanical join — the
*_LINES pool still exists and is still what gets picked from and
fed to the AI, and is also the exact fallback if the AI call fails for
any reason (missing key, rate limit, network), so this never depends
on a third-party service staying up. Picked-text selection is stable
for the whole day (seeded by the date + a salt per category, not
re-randomized every rerun); the AI phrasing is cached per exact prompt
for GENERATE_CACHE_TTL_SECONDS (see gemini_client), so it also doesn't
reword itself every 5s rerun.

Global, not page-local (like commute_reminder.render_leave_headline) —
the whole point is catching you during the actual morning routine,
regardless of which of the 10 rotating pages happens to be up.
"""

import functools
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from astral import LocationInfo
from astral.sun import sun

import air_quality_client
import calendar_client
import commute_client
import commute_reminder
import ec_alerts
import fuel_price_client
import gemini_client
import market_yf_client
import payday_schedule
import waste_schedule
import wildfire_client
from config import AQI_SHOW_THRESHOLD, COMMUTE_DESTINATION, TIMEZONE, USER_FIRST_NAME, WEATHER_LAT, WEATHER_LON

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
    "",
    "",
    "",
    "",
    "Hey — ",
    "Good day — ",
    "Morning, friend — ",
    "Here goes — ",
    "Alright — ",
    "Right then — ",
    "Let's see — ",
    "Okay, here's the scoop: ",
    "Fresh update — ",
    "Straight to it: ",
    "No time to waste — ",
    "Here's the deal: ",
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
    "{temp}°C and rising fast — {high}°C by the time the day's done",
    "blazing already, {temp}°C now, {high}°C on deck",
    "{temp}°C out, the kind of heat that makes shade valuable — {high}°C later",
    "scorching start, {temp}°C, climbing toward {high}°C",
    "{temp}°C right now, and {high}°C is still coming — pace yourself today",
    "heat index territory already, {temp}°C, {high}°C by afternoon",
    "{high}°C on tap, and {temp}°C this early confirms it's a hot one",
    "{temp}°C out there — the fans are earning their keep, {high}°C later",
    "another scorcher, {temp}°C now, topping {high}°C",
    "{temp}°C already at this hour, {high}°C waiting in the wings",
    "real heat today, {temp}°C now, {high}°C the ceiling",
    "{temp}°C out, thick and hot, {high}°C by later",
    "the mercury's climbing fast — {temp}°C now, {high}°C ahead",
    "{temp}°C this morning, sweat-through-your-shirt hot by {high}°C",
    "{high}°C is the forecast, {temp}°C right now says it's on track",
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
    "{temp}°C out, a genuinely lovely warm morning, {high}°C by later",
    "warm and inviting, {temp}°C now, {high}°C on the way",
    "{temp}°C already, the good kind of warm, {high}°C by afternoon",
    "summer's doing its job today — {temp}°C now, {high}°C later",
    "{temp}°C out there, warm enough to enjoy, {high}°C ahead",
    "comfortable heat today, {temp}°C now, climbing to {high}°C",
    "{high}°C expected, and {temp}°C this morning is a warm head start",
    "{temp}°C right now, ideal outdoor weather building toward {high}°C",
    "warm morning air, {temp}°C now, {high}°C later on",
    "{temp}°C out, warm without tipping into uncomfortable, {high}°C ahead",
    "a genuinely good-weather day, {temp}°C now, {high}°C by afternoon",
    "{temp}°C already — shorts and t-shirt weather, {high}°C coming",
    "nice warm start, {temp}°C, {high}°C expected by later",
    "{temp}°C out there, warm and easy, {high}°C on the way",
    "{high}°C today, and {temp}°C now sets the tone nicely",
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
    "{temp}°C out, right in the sweet spot",
    "{temp}°C this morning, nothing to adjust plans around",
    "a plain, pleasant {temp}°C to start things off",
    "{temp}°C right now, {high}°C later, an easy day weather-wise",
    "nothing notable temperature-wise — {temp}°C now",
    "{temp}°C out there, the kind of mild you barely notice",
    "middle-ground weather, {temp}°C now, {high}°C by afternoon",
    "{temp}°C this morning, comfortably in between hot and cold",
    "an agreeable {temp}°C to kick off the day",
    "{temp}°C out, mild enough to not think about it twice",
    "{high}°C expected, {temp}°C right now keeping it mild",
    "{temp}°C now, a calm, undramatic start to the day",
    "nothing to report weather-wise, {temp}°C and holding steady",
    "{temp}°C out there — pleasant, forgettable, fine",
    "a solidly average {temp}°C this morning, {high}°C later",
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
    "{temp}°C out, a little bite in the morning air",
    "cooler than yesterday probably, {temp}°C now, {high}°C by later",
    "{temp}°C right now, sweater weather for the early hours",
    "a crisp {temp}°C to start, warming to {high}°C",
    "{temp}°C out there, not cold exactly, but cool enough to notice",
    "morning chill today, {temp}°C now, {high}°C coming",
    "{temp}°C this morning, a light jacket wouldn't hurt",
    "cool air out there, {temp}°C now, {high}°C by afternoon",
    "{temp}°C right now — refreshing rather than uncomfortable",
    "a cooler start than usual, {temp}°C, {high}°C later",
    "{temp}°C out, the good kind of cool, {high}°C ahead",
    "brisk but manageable, {temp}°C this morning",
    "{temp}°C now, cool enough for coffee to actually help",
    "a fresh {temp}°C out there, {high}°C by later",
    "{temp}°C right now, cool mornings, warmer afternoons — {high}°C",
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
    "{temp}°C out there, no sugar-coating it — dress warm",
    "a real cold morning, {temp}°C now, {high}°C the best it gets",
    "{temp}°C right now, gloves-and-hat kind of cold",
    "deep into cold territory, {temp}°C this morning",
    "{temp}°C out, the kind of cold that stings for a second",
    "bundle-up weather, {temp}°C now, {high}°C by later",
    "{temp}°C this morning — winter's making its point",
    "a biting {temp}°C out there, {high}°C the ceiling today",
    "{temp}°C right now, proper cold, no way around it",
    "cold enough to see your breath, {temp}°C this morning",
    "{temp}°C out, dress in layers today, {high}°C later",
    "a hard cold morning, {temp}°C now",
    "{temp}°C right now — the car's going to protest starting",
    "genuinely frigid out there, {temp}°C, {high}°C by afternoon",
    "{temp}°C this morning, winter's fully committed today",
]

# Radar-based arrival/clearing line lists (RADAR_RAIN_LINES,
# RADAR_SNOW_LINES, ARRIVED_RAIN_LINES, ARRIVED_SNOW_LINES) removed
# along with ec_radar.precip_status itself at the user's own request —
# the EC forecast-percentage lines below are what's left.
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
    "{chance}% chance of rain in the forecast, around {time}",
    "rain's possible around {time} today, {chance}% odds",
    "forecast's flagging rain near {time}, {chance}% likely",
    "{chance}% chance today, rain expected around {time}",
    "keep it in mind — {chance}% chance of rain near {time}",
    "rain might show up around {time}, {chance}% chance per the forecast",
    "{chance}% odds of rain later today, {time} is the target",
    "forecast calls for a {chance}% shot at rain around {time}",
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
    "{chance}% chance of snow in the forecast, around {time}",
    "snow's possible around {time} today, {chance}% odds",
    "forecast's flagging snow near {time}, {chance}% likely",
    "{chance}% chance today, snow expected around {time}",
    "keep it in mind — {chance}% chance of snow near {time}",
    "snow might show up around {time}, {chance}% chance per the forecast",
    "{chance}% odds of snow later today, {time} is the target",
    "forecast calls for a {chance}% shot at snow around {time}",
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
    "blue skies for now, nothing brewing",
    "radar's clean, nothing to report",
    "a dry stretch continues, nothing incoming",
    "no weather drama today, by the look of it",
    "clear conditions holding, nothing on the way",
    "nothing wet in the forecast right now",
    "skies are cooperating today, no rain in sight",
    "radar's about as quiet as it gets",
    "dry weather holding steady today",
    "no precipitation anywhere close, radar-wise",
    "a clean weather day ahead, nothing tracking in",
    "clear straight through, nothing to plan around",
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
    "smoke's the likely culprit today, AQI {aqi}, source fire {distance:.0f}km out",
    "{aqi} AQI this morning — wildfire smoke drifting in from about {distance:.0f}km away",
    "air's hazy again, {aqi} on the scale, nearest fire roughly {distance:.0f}km off",
    "wildfire smoke's the story today, {aqi} AQI, {distance:.0f}km from the source",
    "{aqi} AQI, likely smoke — closest active fire about {distance:.0f}km out",
    "hazy conditions continue, {aqi} AQI, fire source {distance:.0f}km away",
    "smoke's drifting in again, {aqi} on the AQI scale, {distance:.0f}km out",
    "{distance:.0f}km away and still affecting the air here — {aqi} AQI today",
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
    "{aqi} on the AQI scale — keep outdoor time modest today",
    "air's a bit thick today, {aqi} AQI",
    "{aqi} AQI this morning, mildly elevated",
    "worth a glance — air quality's at {aqi} today",
    "{aqi} on the scale, nothing severe but noticeable",
    "air quality's ticked up to {aqi} today",
    "{aqi} AQI right now, a touch worse than ideal",
    "not the freshest air today, {aqi} on the AQI scale",
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
    "heavy traffic this morning, {delay} minutes over normal to {destination}{reason}",
    "the drive's going to cost you — {delay} extra minutes to {destination}{reason}",
    "{delay} minutes of real delay heading to {destination} today{reason}",
    "roads are jammed, {delay} minutes over usual to {destination}{reason}",
    "plan for a slow one — {delay} minutes extra to {destination}{reason}",
    "traffic's genuinely bad, {delay} minutes over normal to {destination}{reason}",
    "{delay} minutes tacked onto the drive to {destination} today{reason}",
    "a rough commute ahead, {delay} extra minutes to {destination}{reason}",
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
    "{duration} minutes to {destination}, a touch slower than usual",
    "nothing serious, {delay} minutes over normal to {destination}",
    "{duration} min to {destination} today, minor slowdown",
    "a small bit of traffic, {delay} minutes added to {destination}",
    "{duration} minutes to {destination}, marginally slower than normal",
    "light delay today, {delay} min over usual to {destination}",
    "{duration} min total to {destination} — nothing to worry about",
    "slightly slower drive, {delay} minutes over normal to {destination}",
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
    "{duration} minutes to {destination}, textbook normal",
    "clean drive today, {duration} min to {destination}",
    "{duration} minutes to {destination} — couldn't ask for better",
    "roads are wide open, {duration} min to {destination}",
    "{duration} minutes to {destination}, nothing in the way",
    "an uneventful drive today, {duration} min to {destination}",
    "{duration} minutes to {destination}, right as expected",
    "smooth as it gets, {duration} min to {destination}",
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
    "{count} things lined up today, {first_event} leads it off at {time}",
    "a packed calendar — {count} events, starting with {first_event} at {time}",
    "{count} on today's docket, {first_event} first at {time}",
    "today's full, {count} things scheduled, {first_event} at {time} to open",
    "{count} entries on the calendar, kicking off with {first_event} at {time}",
    "lots going on — {count} events today, {first_event} at {time} first",
    "{count} things to work through today, {first_event} at {time} starts it",
    "a busy calendar today, {count} items, {first_event} leading at {time}",
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
    "{first_event} at {time} — that's really it for today",
    "today's light, just {first_event} at {time} to plan around",
    "{first_event} at {time}, and otherwise the day's open",
    "one thing on deck today — {first_event} at {time}",
    "{first_event} at {time} is the only fixed point today",
    "not much scheduled, {first_event} at {time} is it",
    "{first_event} at {time}, nothing else on the calendar",
    "just {first_event} at {time} today, plenty of open time otherwise",
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
    "completely open today, nothing on the books",
    "the calendar's got nothing today",
    "a genuinely free day ahead",
    "nothing scheduled at all today",
    "wide open — no commitments today",
    "today's a blank page, calendar-wise",
    "not one thing booked today",
    "the day's entirely yours, nothing planned",
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
    "{kind} day today, bins out before you head out",
    "heads up — {kind} pickup today",
    "today's {kind} day, don't forget the bins",
    "{kind} day — worth a reminder before tonight",
    "bins out for {kind} day today",
    "{kind} pickup today, keep it in mind",
    "don't forget — it's {kind} day",
    "{kind} day today, bins out tonight without fail",
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
    "good news first: it's payday",
    "payday's here today",
    "the paycheck lands today",
    "today's a payday, worth noting",
    "nice timing — payday's today",
    "it's officially payday today",
    "payday today, if that changes your morning",
    "today's the biweekly payday",
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
    "payday's tomorrow, for what it's worth",
    "tomorrow's the payday",
    "one day out from payday",
    "payday lands tomorrow",
    "almost payday — tomorrow's the day",
    "the paycheck's due tomorrow",
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
    "{price:.1f}¢/L today — a pricier stretch at the pump",
    "gas prices sitting at {price:.1f}¢/L, worth conserving today",
    "{price:.1f}¢/L right now, eco driving actually pays off today",
    "prices are elevated, {price:.1f}¢/L — maybe skip the fill-up",
    "{price:.1f}¢/L at the pump today, a bit above the norm",
    "fuel's pricier today at {price:.1f}¢/L",
    "{price:.1f}¢/L right now — worth easing off the accelerator today",
    "gas is up to {price:.1f}¢/L, hold off on filling up if you can",
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
    "heads up today: {title}",
    "important: {title}",
    "flagging this: {title}",
    "keep this on your radar: {title}",
    "worth your attention: {title}",
    "a real one today — {title}",
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
    "S&P's off to a green start, +{pct}%",
    "markets are trading up, +{pct}% so far",
    "a positive open, S&P +{pct}%",
    "green so far this morning, up {pct}%",
    "markets are cooperating today, +{pct}%",
    "S&P's ahead by {pct}% this morning",
    "a good sign for the market, +{pct}% so far",
    "up {pct}% out of the gate this morning",
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
    "S&P's off to a red start, -{pct}%",
    "markets are trading down, -{pct}% so far",
    "a negative open, S&P -{pct}%",
    "red so far this morning, down {pct}%",
    "markets aren't cooperating today, -{pct}%",
    "S&P's behind by {pct}% this morning",
    "a rough sign for the market, -{pct}% so far",
    "down {pct}% out of the gate this morning",
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
    "markets are directionless this morning",
    "S&P's essentially flat to start",
    "not much happening in the markets yet",
    "a non-event morning for the S&P",
    "markets are stuck in place so far",
    "nothing decisive in the markets this morning",
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
    "daylight keeps building, {delta} minutes more than yesterday",
    "{delta} minutes gained since yesterday, sunset now at {sunset}",
    "the light's stretching further, {delta} minutes more today",
    "more daylight again today, {delta} minutes up from yesterday",
    "{delta} minutes added to the daylight today",
    "sunset's crept later — {sunset}, {delta} minutes more than yesterday",
    "the days keep lengthening, {delta} minutes gained",
    "{delta} more minutes of light today than yesterday",
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
    "daylight keeps shrinking, {delta} minutes less than yesterday",
    "{delta} minutes lost since yesterday, sunset now at {sunset}",
    "the light's retreating, {delta} minutes less today",
    "less daylight again today, {delta} minutes down from yesterday",
    "{delta} minutes shaved off the daylight today",
    "sunset's crept earlier — {sunset}, {delta} minutes less than yesterday",
    "the days keep shortening, {delta} minutes lost",
    "{delta} fewer minutes of light today than yesterday",
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


def _precip_clause(now: datetime, weather: dict) -> tuple[int, str] | None:
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
    # 1-10 level, same as the hero badge (see air_quality_client.level)
    # — this used to quote the raw 0-500 AQI number, which would now
    # silently disagree with the badge showing the same reading.
    aqi_level = air_quality_client.level(aqi)
    wildfire = wildfire_client.nearest_wildfire()
    if wildfire is not None:
        text = _pick(WILDFIRE_LINES, now, "air").format(aqi=aqi_level, distance=wildfire["distance_km"])
        return 8, text
    return 5, _pick(AQI_ONLY_LINES, now, "air").format(aqi=aqi_level)


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


@functools.lru_cache(maxsize=8)
def _day_length_minutes(day) -> float:
    """Cached — this is called twice (today, yesterday) on every rerun
    for the whole MORNING_WINDOW (up to ~3600 reruns/day at the 5s
    autorefresh interval), but astral's sun() calculation only actually
    changes once a calendar day. maxsize=8 evicts old dates on its own
    (LRU) rather than needing any manual bookkeeping for a long-running
    process — this only ever needs the last couple of days anyway."""
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


AI_REFRESH_SECONDS = 5 * 60  # session request: "for the daily morning brief... every five minutes is great" — see gemini_client.generate_periodic


def _ai_sentence(picked: list[str]) -> str | None:
    """Same picked clause texts, woven by Gemini into one or two
    flowing sentences instead of the mechanical semicolon-join below —
    session request: "revamp the morning brief" with a free AI, then
    "i want the daily recap to have a jarvis type energy from iron
    man," then a further correction once that landed too stiff: "a
    little too dry tbh.. maybe give it a fun and sarcastic personality.
    it should be enjoyable to read in the morning. make it slightly
    dark lol." Facts and their priority ordering are untouched (still
    decided entirely by the *_clause functions above); this only
    changes how they're phrased. Owns its own opening address now
    (render() below skips the separately-picked random GREETINGS
    prefix whenever this succeeds, so there's nothing left for the AI's
    own in-character opener to clash with; GREETINGS is now only used
    on the fallback path). Real calls throttled to once per
    AI_REFRESH_SECONDS regardless of how often render() calls this
    (every 5s during the whole morning window) — see gemini_client.
    generate_periodic. None (falls back to the plain join + a random
    greeting) on any failure with nothing usable already cached."""
    facts = "; ".join(picked)
    prompt = (
        f"You are {USER_FIRST_NAME}'s personal AI assistant, in the spirit of J.A.R.V.I.S. from "
        "Iron Man — sharp, hyper-competent, quick with a comeback — but leaned toward genuinely "
        "fun and sarcastic rather than stiff or overly formal. This needs to be enjoyable to read "
        "first thing in the morning: real jokes, a playful jab, a slightly dark/morbid sense of "
        "humor is welcome and encouraged — nothing mean-spirited AT "
        f"{USER_FIRST_NAME}, just a wry, "
        "bleak-humor take on the day's mundane realities (traffic, weather, a full calendar, red "
        "markets — all fair game for a joke). Not corporate, not a stiff butler. You may open "
        "with a brief in-character address if it fits naturally. The humor comes entirely from "
        "how things are delivered, never from anything invented — do not add or invent any fact "
        "not given below; every fact must actually appear.\n\n"
        "Combine the following facts into one flowing sentence, or two short sentences if that "
        f"reads better. Address {USER_FIRST_NAME} by name naturally somewhere in the text. Start "
        "with a capital letter and end with a period. Facts: " + facts
    )
    return gemini_client.generate_periodic("morning_briefing_sentence", AI_REFRESH_SECONDS, prompt)


def render(now: datetime, weather: dict | None, air_quality: dict | None) -> None:
    if not (MORNING_WINDOW_START_HOUR <= now.hour < MORNING_WINDOW_END_HOUR):
        return
    if not weather:
        return

    clauses = []
    for fn, args in (
        (_alert_clause, (now,)),
        (_weather_clause, (now, weather)),
        (_precip_clause, (now, weather)),
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
    try:
        sentence = _ai_sentence(picked)
    except Exception:
        sentence = None
    if sentence is not None:
        # JARVIS opens the line himself (see _ai_sentence's own
        # docstring) — no separate randomized greeting prefix here, or
        # it would collide with his own in-character address.
        st.markdown(f'<div class="morning-briefing">{sentence}</div>', unsafe_allow_html=True)
        return

    sentence = "; ".join(picked)
    sentence = sentence[0].upper() + sentence[1:] + "."
    greeting = _pick(GREETINGS, now, "greeting")
    st.markdown(f'<div class="morning-briefing">{greeting}{sentence}</div>', unsafe_allow_html=True)
