"""Static configuration for the command center dashboard."""
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
STATE_PATH = DATA_DIR / "state.json"
TASKS_PATH = DATA_DIR / "tasks.json"

LOCATION_NAME = "Corbeil, Ontario"
# Ouellette Road, East Ferris Township (Corbeil) — precise home location, used for
# both the weather grid point and as the commute origin.
WEATHER_LAT = 46.2423683
WEATHER_LON = -79.2526926
TIMEZONE = "America/Toronto"

SYNC_INTERVAL_MINUTES = 20
DASHBOARD_REFRESH_SECONDS = 15

LEAVE_SOON_MINUTES = 15  # show the "leave now" banner once a leave_by is this close
ROTATION_CYCLE_SECONDS = 60  # main view + extras view repeating cycle
ROTATION_EXTRAS_SECONDS = 15  # how much of each cycle shows the extras view

# Commute monitoring: Corbeil (home) -> 103 Laurentian Ave, North Bay
HOME_LAT = 46.2423683
HOME_LON = -79.2526926
COMMUTE_DEST_LABEL = "103 Laurentian Ave, North Bay"
COMMUTE_DEST_LAT = 46.3204083
COMMUTE_DEST_LON = -79.4397409
COMMUTE_ALERT_THRESHOLD_MINUTES = 25
