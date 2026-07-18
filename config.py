"""Static configuration: FRED series, weather location, thresholds."""

# Corbeil, Ontario
WEATHER_LAT = 46.2616
WEATHER_LON = -79.2920
TIMEZONE = "America/Toronto"

# Reference towns shown as neutral markers on the radar map (see
# ec_radar.nearby_city_markers) — so it's obvious where rain actually is
# relative to real places, not just relative to Corbeil's own marker.
# Geocoded once via commute_client.geocode() (the same TomTom API the
# commute feature uses) and hardcoded here since these are fixed
# locations — no reason to spend a live geocoding call rendering the
# radar page every few minutes for coordinates that never change.
# Sudbury was excluded at first for falling outside the radar image's
# old square ~115km longitudinal half-span — the frame is wider now
# (see ec_radar.IMAGE_ASPECT_RATIO), and Sudbury genuinely fits inside
# it (confirmed live, pixel (438, 271) well within the new 1600x640
# frame), so it's back in.
# Callander was checked too but sits only ~7km from North Bay — close
# enough that their labels overlapped illegibly on a narrow (mobile)
# frame, so it's left out as redundant with North Bay at this zoom.
RADAR_NEARBY_CITIES = [
    {"label": "North Bay", "lat": 46.309464, "lon": -79.46163},
    {"label": "Powassan", "lat": 46.082132, "lon": -79.359081},
    {"label": "Sturgeon Falls", "lat": 46.3660968, "lon": -79.9309088},
    {"label": "Mattawa", "lat": 46.3132636, "lon": -78.709835},
    {"label": "Sudbury", "lat": 46.489459, "lon": -80.989206},
    # Added once the radar frame widened to a 2.5:1 image (see
    # ec_radar.py) — these sit well outside the old square bbox but
    # comfortably inside the new one, confirmed via ec_radar's own
    # _latlon_to_pixel/nearby_city_markers (which already silently drops
    # anything landing outside the frame, so there's no risk in listing
    # a town that turns out to be just out of range).
    {"label": "Parry Sound", "lat": 45.3502, "lon": -80.0329},
    {"label": "Huntsville", "lat": 45.3238, "lon": -79.2177},
    {"label": "Pembroke", "lat": 45.8168, "lon": -77.1141},
    {"label": "Temiskaming Shores", "lat": 47.5169, "lon": -79.6810},
    {"label": "Deep River", "lat": 46.1001, "lon": -77.4931},
]

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
# How often the Scores page flips to the next active league (MLB/NBA/
# NHL/NFL) — deliberately much shorter than PAGE_ROTATION_SECONDS
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

# Release is treated as "imminent" (countdown shown) inside this window
COUNTDOWN_WINDOW_HOURS = 24

# Earnings dates folded into the same bottom ticker as the macro release
# calendar (see ticker.build_earnings_schedule) — deliberately just the
# "mega-cap tech" names, not news.py's full ~90-ticker EARNINGS_COMPANIES
# map (built for headline text-matching, not for populating a scrolling
# ticker with 90 items nobody asked to track).
EARNINGS_TICKER_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "NFLX", "AVGO", "BRK-B",
]

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
# Weather / Radar / Sports / Scores cycle the same way US/CA already does: a
# time.time()-based index, no Streamlit multipage chrome, no scrolling.
PAGES = [
    "home", "conflicts", "news", "markets", "internals", "today", "household",
    "weather", "radar", "sports", "scores", "recovery",
]
PAGE_ROTATION_SECONDS = 5 * 60

# Temporary: added while recovering from wisdom teeth surgery (see
# pages_recovery.py) — worth more than one uniform rotation slot so it's
# actually on screen long enough to read, not just flash past for the
# same 5 minutes as every other ambient page. Any page not listed here
# just falls back to PAGE_ROTATION_SECONDS above.
# Remove this override, the "recovery" entry above, pages_recovery.py,
# and recovery_timer.html once recovery's done.
PAGE_DURATION_OVERRIDES = {"recovery": 10 * 60}

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

# Conflicts page is fully dynamic — no fixed list. GDELT turned out
# unreliable (persistent rate-limiting), so this scans the same free RSS
# pool that powers the news alerts: any headline mentioning one of these
# countries/regions alongside a conflict-indicator term counts as a hit,
# grouped by which countries co-occur (so e.g. "Ukraine"+"Russia" in the
# same headline forms one two-flag group), then ranked by hit count —
# whatever's most documented right now surfaces automatically, and a
# conflict that goes quiet naturally drops off.
#
# Name variants map to the same flag code so "Congo"/"DRC" etc. all match.
CONFLICT_COUNTRIES = {
    "ukraine": "ua", "russia": "ru", "russian": "ru",
    "israel": "il", "gaza": "ps", "palestinian": "ps", "palestine": "ps",
    "sudan": "sd", "south sudan": "ss",
    "myanmar": "mm", "burma": "mm",
    "syria": "sy", "syrian": "sy",
    "iraq": "iq", "iraqi": "iq",
    "iran": "ir", "iranian": "ir",
    "yemen": "ye", "yemeni": "ye",
    "lebanon": "lb", "lebanese": "lb", "hezbollah": "lb",
    "saudi arabia": "sa", "saudi": "sa",
    "turkey": "tr", "turkish": "tr",
    "ethiopia": "et", "ethiopian": "et",
    "somalia": "so", "somali": "so",
    "congo": "cd", "drc": "cd",
    "mali": "ml",
    "niger": "ne",
    "nigeria": "ng", "nigerian": "ng",
    "libya": "ly", "libyan": "ly",
    "chad": "td",
    "central african republic": "cf",
    "mozambique": "mz",
    "cameroon": "cm",
    "afghanistan": "af", "afghan": "af", "taliban": "af",
    "pakistan": "pk", "pakistani": "pk",
    "north korea": "kp",
    "south korea": "kr",
    "taiwan": "tw", "taiwanese": "tw",
    "china": "cn", "chinese": "cn",
    "philippines": "ph", "filipino": "ph",
    "georgia": "ge", "georgian": "ge",
    "armenia": "am", "armenian": "am",
    "azerbaijan": "az",
    "serbia": "rs", "serbian": "rs",
    "kosovo": "xk",
    "venezuela": "ve", "venezuelan": "ve",
    "colombia": "co", "colombian": "co",
    "mexico": "mx", "mexican": "mx",
    "haiti": "ht", "haitian": "ht",
    "ecuador": "ec", "ecuadorian": "ec",
    "india": "in", "indian": "in",
    "japan": "jp", "japanese": "jp",
}

# One canonical display name per flag code, for labeling groups (several
# keyword variants above map to the same code, e.g. "russia"/"russian").
FLAG_CODE_NAME = {
    "ua": "Ukraine", "ru": "Russia", "il": "Israel", "ps": "Gaza/Palestine",
    "sd": "Sudan", "ss": "South Sudan", "mm": "Myanmar", "sy": "Syria",
    "iq": "Iraq", "ir": "Iran", "ye": "Yemen", "lb": "Lebanon",
    "sa": "Saudi Arabia", "tr": "Turkey", "et": "Ethiopia", "so": "Somalia",
    "cd": "DR Congo", "ml": "Mali", "ne": "Niger", "ng": "Nigeria",
    "ly": "Libya", "td": "Chad", "cf": "Central African Republic",
    "mz": "Mozambique", "cm": "Cameroon", "af": "Afghanistan", "pk": "Pakistan",
    "kp": "North Korea", "kr": "South Korea", "tw": "Taiwan", "cn": "China",
    "ph": "Philippines", "ge": "Georgia", "am": "Armenia", "az": "Azerbaijan",
    "rs": "Serbia", "xk": "Kosovo", "ve": "Venezuela", "co": "Colombia",
    "mx": "Mexico", "ht": "Haiti", "ec": "Ecuador", "in": "India", "jp": "Japan",
}

CONFLICT_TERMS = [
    "war", "conflict", "clashes", "clash", "airstrike", "air strike",
    "rebels", "rebel", "insurgency", "insurgent", "ceasefire", "invasion",
    "civil war", "militant", "offensive", "shelling", "missile strike",
    "drone strike", "junta", "coup", "troops", "strikes kill", "attack",
]

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
