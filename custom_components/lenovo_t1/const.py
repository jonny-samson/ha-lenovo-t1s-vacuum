"""Constants for the Lenovo T1 Pro integration."""
import re

from .t1api.const import FAULT_CODES

DOMAIN = "lenovo_t1"

CONF_DEVICE_ID = "device_id"
CONF_LOCAL_KEY = "local_key"
CONF_SERIAL = "serial"
CONF_USER_ID = "user_id"
CONF_VERSION = "version"

DEFAULT_NAME = "Lenovo T1 Pro"
DEFAULT_VERSION = "3.3"
PROTOCOL_VERSIONS = ["3.3", "3.4", "3.5"]

CONF_ROOM_SLOTS = "room_slots"
CONF_STATE_POLL = "state_poll"
CONF_SLOW_POLL = "slow_poll"
DEFAULT_STATE_POLL = 30
DEFAULT_SLOW_POLL = 300

# Number of room slots created. Slot N is the vacuum's room id N.
ROOM_SLOTS = 10

SERVICE_CLEAN_ROOMS = "clean_rooms"
ATTR_ROOMS = "rooms"

SERVICE_DRIVE = "drive"
ATTR_DIRECTION = "direction"
ATTR_DURATION = "duration"

# Readable text for the vacuum's own mode values. Keep in step with entity.sensor.mode.state in strings.json.
MODE_NAMES = {
    "idle": "Idle",
    "charge": "Charging",
    "fullcharge": "Fully charged",
    "sweep": "Cleaning",
    "rfctrl": "Remote control",
    "pause": "Paused",
    "findchargerpause": "Paused, finding dock",
    "backcharge": "Returning to dock",
    "fault": "Fault",
}
SERVICE_CLEAN = "clean"
SERVICE_CLEAN_ZONE = "clean_zone"
SERVICE_GO_TO_POINT = "go_to_point"
ATTR_MODE = "mode"
CLEAN_MODES = ["total", "deep", "along_wall"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# Informational vacuum messages (positive 20003 codes) -> event type for the event entity.
MESSAGE_EVENT_TYPES = {code: _slug(text) for code, text in FAULT_CODES.items() if code > 0}
EVENT_TYPES = [*MESSAGE_EVENT_TYPES.values(), "unknown_message", "fault", "fault_cleared"]
