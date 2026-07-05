"""Static configuration: FRED series, weather location, thresholds."""

# North Bay, Ontario
WEATHER_LAT = 46.31
WEATHER_LON = -79.46
TIMEZONE = "America/Toronto"

UV_HIGH_THRESHOLD = 5
RAIN_PROBABILITY_THRESHOLD = 50  # percent, for the "Rain in Xh" nowcast label
RAIN_LOOKAHEAD_HOURS = 12

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
