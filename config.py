"""Static configuration: FRED series, weather location, thresholds."""

# North Bay, Ontario
WEATHER_LAT = 46.31
WEATHER_LON = -79.46
TIMEZONE = "America/Toronto"

UV_HIGH_THRESHOLD = 5
RAIN_PROBABILITY_THRESHOLD = 50  # percent, for the "Rain in Xh" nowcast label
RAIN_LOOKAHEAD_HOURS = 12

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

ROTATION_SECONDS = 120

# Standard-deviation band used to classify a reading vs its trailing trend
HOT_COOL_THRESHOLD = 0.75

# A reading this many standard deviations from trend gets a "significant move" flash
SIGNIFICANT_Z = 2.5

# Release is treated as "imminent" (countdown shown) inside this window
COUNTDOWN_WINDOW_HOURS = 24

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
# Home / Conflicts / News / Markets / Watchlist cycle the same way US/CA
# already does: a time.time()-based index, no Streamlit multipage chrome,
# no scrolling.
PAGES = ["home", "conflicts", "news", "markets", "watchlist"]
PAGE_ROTATION_SECONDS = 90

# Watchlist tiles are wider (more metric rows than Markets' tiles) — cap
# and row-wrap at a narrower count than Markets' 7 so they stay readable.
MAX_WATCHLIST_SHOWN = 12
WATCHLIST_ROW_SIZE = 6

# Twelve Data free tier caps at 8 credits/minute — a single batched request
# every 20 minutes stays far under that regardless of per-call cost.
TWELVEDATA_TTL_SECONDS = 20 * 60

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

# Twelve Data's free tier doesn't include raw index symbols (SPX/DJI/IXIC),
# so major ETFs stand in as proxies for the indices/oil — same spirit as the
# FRED/StatCan proxies used elsewhere, just not called out in the label.
MARKET_INSTRUMENTS = [
    {"key": "sp500", "label": "S&P 500", "symbol": "SPY"},
    {"key": "dow", "label": "Dow Jones", "symbol": "DIA"},
    {"key": "nasdaq", "label": "Nasdaq", "symbol": "QQQ"},
    {"key": "tsx", "label": "Canada", "symbol": "EWC"},
    {"key": "usdcad", "label": "USD/CAD", "symbol": "USD/CAD"},
    {"key": "gold", "label": "Gold", "symbol": "XAU/USD"},
    {"key": "oil", "label": "Crude Oil", "symbol": "USO"},
]
