"""Constants for the Lenovo T1 Pro integration."""
DOMAIN = "lenovo_t1"

CONF_DEVICE_ID = "device_id"
CONF_LOCAL_KEY = "local_key"
CONF_SERIAL = "serial"
CONF_USER_ID = "user_id"
CONF_VERSION = "version"

DEFAULT_NAME = "Lenovo T1 Pro"
DEFAULT_VERSION = "3.3"
PROTOCOL_VERSIONS = ["3.3", "3.4", "3.5"]

# Number of room slots created. Slot N is the vacuum's room id N.
ROOM_SLOTS = 10

SERVICE_CLEAN_ROOMS = "clean_rooms"
ATTR_ROOMS = "rooms"

SERVICE_DRIVE = "drive"
ATTR_DIRECTION = "direction"
ATTR_DURATION = "duration"
