"""Static configuration for the command center dashboard."""
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
STATE_PATH = DATA_DIR / "state.json"
TASKS_PATH = DATA_DIR / "tasks.json"

LOCATION_NAME = "Corbeil, Ontario"
WEATHER_LAT = 46.3667
WEATHER_LON = -79.1667
TIMEZONE = "America/Toronto"

SYNC_INTERVAL_MINUTES = 30
DASHBOARD_REFRESH_SECONDS = 60
