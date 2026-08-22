"""Static configuration: FRED series, weather location, thresholds."""

# Whose dashboard this is — session request: have the AI-written morning
# briefing (morning_briefing._ai_sentence) address him by name.
USER_FIRST_NAME = "Brayden"

# Standing personal context fed into the morning briefing's own prompt
# (morning_briefing._ai_sentence) — session question: "would it benefit
# to train the ai on who i am?" Fine-tuning isn't the right lever for
# facts that don't change call to call (see that discussion) — this is
# just a richer, persistent context block the same prompt already
# draws on for genuine connections, not a model retrain. Hand-maintained
# here; update by hand if anything in it changes.
USER_PROFILE = (
    "Personal Banking Associate at TD Bank in North Bay, Ontario. Born September 22, 2006. "
    "Drives a 2014 Honda Civic LX. Long-term relationship with girlfriend Chloe. Lives with "
    "parents; has a Golden Retriever (Auggie) and a cat (Wicket). Plays goaltender in hockey, "
    "1st base in co-ed softball and on TD's own corporate team, and golf (scramble format). "
    "Manages the Halifax Huskies in a virtual hockey sim league and follows the UFC. Tracks a "
    "personal loan payoff target for October 1, 2026. At TD, a shift starting at 8:30 AM is an "
    "opening shift; a shift starting or ending at an odd time like 6:30 or 8:30 PM is typically "
    "a closing shift — worth naming as such (not just reading out the raw start time) when it's "
    "actually one of these."
)

# Session report: "[radar] data just looks wrong, says there should be
# rain on my location rn but theres nothing." Root cause traced to two
# separate coordinate gaps stacked on top of each other: this constant
# used to be a rough "Corbeil, Ontario" town centroid, 5.2km from the
# real home address (confirmed live via haversine distance) — and EC's
# own forecast-text station (ec_forecast.EC_STATION_LAT/LON, the
# nearest one that publishes rain-probability text at all) sits a
# further 18.8km beyond THAT. A very localized shower over the distant
# station reads as "rain now" in the text while the radar map — closer
# to the truth, and now closer to home too — correctly shows nothing
# nearby. This constant can only close the first gap (there's no closer
# EC forecast station to swap in for the second), but it should still
# be the real, precisely-geocoded home address rather than a rounded
# town point, same as COMMUTE_ORIGIN's own coordinate already is.
WEATHER_LAT = 46.228058
WEATHER_LON = -79.245407
TIMEZONE = "America/Toronto"

UV_HIGH_THRESHOLD = 5
# "Feels like" only earns a hero badge once it diverges enough from the
# actual temperature to matter — a couple degrees of humidex/wind
# chill rounding is routine and reads as a bogus/noisy badge rather
# than a genuinely useful signal; 7 is a real, noticeable divergence.
FEELS_LIKE_DIVERGENCE_THRESHOLD_C = 7
RAIN_PROBABILITY_THRESHOLD = 49  # percent, for the "Rain in Xh" nowcast label — driven by EC's own hourly forecast (ec_forecast.py)
RAIN_LOOKAHEAD_HOURS = 12
# US AQI scale: 0-50 Good, 51-100 Moderate, 101-150 Unhealthy for
# Sensitive Groups, 151+ Unhealthy. Show the badge from Moderate
# onward — the whole point is a glance-only "is this worth thinking
# about" signal, not silence right up until it's bad.
AQI_SHOW_THRESHOLD = 50
AQI_EXTREME = 200  # AQI at which the badge reaches full saturated color

# Environment Canada's public alert regions are free, no-key ATOM feeds at
# weather.gc.ca/rss/battleboard/{code}_e.xml — "onrm119" is the North Bay -
# Powassan - Mattawa region (found via weather.gc.ca/warnings/report_e.html
# for North Bay's coordinates).
EC_ALERT_REGION_CODE = "onrm119"
# Same region, spelled out — MSC GeoMet's weather-alerts OGC API
# (ec_storm_timing.py) matches by this exact name (its own
# "feature_name_en" field) rather than the battleboard's short code,
# confirmed live to be the identical string.
EC_ALERT_REGION_NAME = "North Bay - Powassan - Mattawa"

# Our own fallback extreme-heat/extreme-cold banner only shows when EC has
# no official alert active — thresholds are a rough approximation of EC's
# own criteria for this region (a genuine EC warning always takes priority
# and has more precise, locally-tuned criteria than we can replicate here).
EXTREME_HEAT_THRESHOLD_C = 28
EXTREME_COLD_THRESHOLD_C = -28

# Once a breaking (red) headline comes in, it holds the top banner for up
# to this long, or until the next red headline replaces it — whichever
# comes first.
TOP_ALERT_HOLD_SECONDS = 2 * 60 * 60

# If the RSS feeds were unreachable for a while and then recover, every
# headline still in the feed that was never marked "seen" during the
# outage arrives as a single burst — without a cap, that becomes hours of
# backlog playing through the bottom toast bar at TOAST_SECONDS each. Only
# the most recent items from any one burst are worth surfacing as if they
# just broke; the rest are still marked seen (won't re-alert later) but
# skipped rather than queued.
MAX_BURST_ALERTS = 6

ROTATION_SECONDS = 5 * 60
# How often the Scores page flips to the next active league (MLB/NHL/
# NFL) — deliberately much shorter than PAGE_ROTATION_SECONDS
# (5 min): the Scores page itself is only ever on screen for one
# PAGE_ROTATION_SECONDS window before the kiosk rotates away entirely,
# so cycling leagues on that same 5-minute cadence would mean a given
# visit only ever shows ONE league. This needs to be short enough that
# a single visit to the page actually cycles through all of them.
SCORES_LEAGUE_ROTATION_SECONDS = 20

# Standard-deviation band used to classify a reading vs its trailing trend
HOT_COOL_THRESHOLD = 0.75

# A reading this many standard deviations from trend gets a "significant move" flash
SIGNIFICANT_Z = 2.5

# Each indicator: FRED series id, display label, unit, frequency-aware
# transform ("yoy" = compute YoY % change from an index; "level" = use
# the raw series value as-is, e.g. already a rate/percent).
#
# good_direction: which deviation from trend is economically favorable for
# THIS indicator — "up" (above trend is good, e.g. GDP growth), "down"
# (below trend is good, e.g. unemployment or inflation cooling), or None
# for indicators where "above/below trend" has no inherent good/bad
# reading (policy rate, bond yields depend entirely on context) — those
# are shown as neutral rather than forced into a false hot/cold judgment.
INDICATORS = {
    "us": [
        {"key": "cpi", "label": "CPI (YoY)", "series_id": "CPIAUCSL", "transform": "yoy", "unit": "%", "release_id": 10, "good_direction": "down"},
        {"key": "unemployment", "label": "Unemployment Rate", "series_id": "UNRATE", "transform": "level", "unit": "%", "release_id": 50, "good_direction": "down"},
        {"key": "gdp", "label": "Real GDP (YoY)", "series_id": "GDPC1", "transform": "yoy", "unit": "%", "release_id": 53, "good_direction": "up"},
        {"key": "policy_rate", "label": "Fed Funds Rate", "series_id": "FEDFUNDS", "transform": "level", "unit": "%", "release_id": 18, "good_direction": None},
        {"key": "yield_10y", "label": "10-Year Yield", "series_id": "DGS10", "transform": "level", "unit": "%", "release_id": 18, "good_direction": None},
    ],
    "ca": [
        {"key": "cpi", "label": "CPI (YoY)", "source": "statcan", "vector_id": 41690973, "transform": "yoy", "unit": "%", "release_cadence_days": 30, "good_direction": "down"},
        {"key": "unemployment", "label": "Unemployment Rate", "series_id": "LRUNTTTTCAM156S", "transform": "level", "unit": "%", "release_cadence_days": 30, "good_direction": "down"},
        {"key": "gdp", "label": "Real GDP (YoY)", "series_id": "NGDPRSAXDCCAQ", "transform": "yoy", "unit": "%", "release_cadence_days": 91, "good_direction": "up"},
        {"key": "policy_rate", "label": "BoC Overnight Rate", "series_id": "IRSTCI01CAM156N", "transform": "level", "unit": "%", "release_cadence_days": 49, "good_direction": None},
        {"key": "yield_10y", "label": "10-Year Yield", "series_id": "IRLTLT01CAM156N", "transform": "level", "unit": "%", "release_cadence_days": 30, "good_direction": None},
    ],
}

COUNTRY_META = {
    "us": {"name": "United States"},
    "ca": {"name": "Canada"},
}

# Simple YTD return strip. FRED has no direct S&P/TSX 60 series, so Canada
# uses its OECD share-price index for Canada as a close proxy — labeled
# honestly rather than as the literal TSX 60.
MARKET_INDEX = {
    "us": {"label": "S&P 500", "series_id": "SP500"},
    "ca": {"label": "Canada Share Price Index (TSX proxy)", "series_id": "SPASTT01CAM661N"},
}

# FRED has no Canada 2-year yield series, so the 10Y-2Y spread (classic
# recession-warning signal) is US-only — shown as a quiet extra line inside
# the existing 10-Year Yield tile rather than a 6th tile, to keep both
# countries' grids symmetric.
YIELD_SPREAD_SERIES_ID = "T10Y2Y"

# --- Multi-page ambient rotation -------------------------------------------
# Home / Conflicts / News / Markets / Internals / Today / Household /
# Weather / Hourly / Sports / Scores / Portfolio / Predictions cycle the
# same way US/CA already does: a time.time()-based index, no Streamlit
# multipage chrome, no scrolling.
#
# "radar" was replaced with "hourly" ("get rid of radar and replace it
# with hourly weather data" — see pages_hourly.py) and later reinstated
# alongside it once RainViewer gave a genuinely better-animated source
# to build it from (see radar_client.py) — this time an addition, not
# another swap.
PAGES = [
    "home", "conflicts", "news", "email", "markets", "internals", "today", "household",
    "weather", "hourly", "radar", "sports", "scores", "portfolio", "predictions",
]
PAGE_ROTATION_SECONDS = 5 * 60

# PAGE_DURATION_OVERRIDES lets a specific page hold the screen longer
# than PAGE_ROTATION_SECONDS (see app.py's _scheduled_page) — empty for
# now, but the mechanism stays since it's a one-line reintroduction if a
# future page needs it again.
PAGE_DURATION_OVERRIDES = {}

# Commute origin coordinate is the exact one embedded in the calendar
# feed's own Apple-geocoded location for 281 Ouellette Rd (Nominatim's
# free geocoder has no house-number-level data for this rural road —
# only resolves to the street's rough centroid, off by ~2km). The
# destination came from Nominatim directly since that one resolved fine.
COMMUTE_ORIGIN = {"label": "Home", "lat": 46.228058, "lon": -79.245407}
COMMUTE_DESTINATION = {"label": "Work", "lat": 46.3185464, "lon": -79.4386137}

# Markets page refresh — yfinance has no key/rate-limit tier to work
# around, so this can just be "how fresh do we want it," not "how rarely
# can we afford to ask."
MARKET_DATA_TTL_SECONDS = 5 * 60
MARKET_SPARKLINE_PERIOD = "1y"

# Conflicts page is fully dynamic — no fixed list. Used to keyword-match
# headlines against a hand-maintained country-name/conflict-term list
# (CONFLICT_COUNTRIES/CONFLICT_TERMS); session request: "make conflicts
# feed directly from gemini instead of looking for headlines with
# specific names... remove the RSS keyword searching for different
# countries." pages_conflicts._ai_overview now does that identification
# itself from the raw headline pool, so there's no country/term list to
# maintain here anymore — see that module's own docstring.
MAX_CONFLICTS_SHOWN = 6

# Passed straight through as Google News' own `when:Xd` search operator —
# it returns this many days of real history directly, so a quiet news day
# doesn't make an ongoing conflict vanish (no local day-by-day
# accumulation needed; each fetch is already a complete rolling window).
CONFLICT_WINDOW_DAYS = 7

# Markets page: yfinance gives real index symbols directly, unlike Twelve
# Data's free tier (which needed ETF proxies — SPY/DIA/QQQ/EWC — as a
# workaround). Which 4 "index" slots show swaps by market status: the
# real index during NYSE/TSX hours (live), futures outside those hours
# (still live — futures trade nearly 24/5), crypto on weekends (the only
# thing actually moving when nothing else is open). No TSX futures
# symbol exists on yfinance, so Canada just stays on its index in every
# non-open state — same as any other closed-market quote, it shows the
# last close rather than nothing.
MARKET_INSTRUMENTS_OPEN = [
    {"key": "sp500", "label": "S&P 500", "symbol": "^GSPC"},
    {"key": "dow", "label": "Dow Jones", "symbol": "^DJI"},
    {"key": "nasdaq", "label": "Nasdaq", "symbol": "^IXIC"},
    {"key": "tsx", "label": "Canada", "symbol": "^GSPTSE"},
]
MARKET_INSTRUMENTS_CLOSED = [
    {"key": "sp500", "label": "S&P 500 Futures", "symbol": "ES=F"},
    {"key": "dow", "label": "Dow Futures", "symbol": "YM=F"},
    {"key": "nasdaq", "label": "Nasdaq Futures", "symbol": "NQ=F"},
    {"key": "tsx", "label": "Canada", "symbol": "^GSPTSE"},
]
# A Polymarket-derived weekend forecast (a synthetic S&P 500 tile that
# briefly displaced Bitcoin/Dogecoin from this list) came and went —
# session request: "get rid of the market implied weekend moves and
# just resort to Bitcoin, Ethereum, whatever, the main cryptos." Back
# to a plain crypto lineup, the four main ones.
MARKET_INSTRUMENTS_WEEKEND = [
    {"key": "btc", "label": "Bitcoin", "symbol": "BTC-USD"},
    {"key": "eth", "label": "Ethereum", "symbol": "ETH-USD"},
    {"key": "sol", "label": "Solana", "symbol": "SOL-USD"},
    {"key": "doge", "label": "Dogecoin", "symbol": "DOGE-USD"},
]
# Commodities always quote via futures (how gold/oil actually trade
# nearly around the clock anyway) and FX always via spot — neither needs
# the open/closed/weekend swap the equity indices get.
MARKET_INSTRUMENTS_ALWAYS = [
    {"key": "usdcad", "label": "USD/CAD", "symbol": "USDCAD=X"},
    {"key": "gold", "label": "Gold", "symbol": "GC=F"},
    {"key": "oil", "label": "Crude Oil", "symbol": "CL=F"},
]

# Govee smart-home devices (bedroom light + plug). Identifiers only — not
# secret on their own, control still requires GOVEE_API_KEY in
# .streamlit/secrets.toml. Pulled from the account's own device list via
# the Govee API, which uses a different (longer) device-id format than
# the MAC address printed on the device itself.
GOVEE_LIGHT = {"sku": "H6167", "device": "0C:1A:D4:39:C1:86:02:47"}
GOVEE_PLUG = {"sku": "H5080", "device": "1A:82:5C:E7:53:93:A5:56"}
