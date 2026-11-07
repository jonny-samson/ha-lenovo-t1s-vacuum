"""Protocol constants for the Lenovo T1 Pro (local Tuya).

Values come from the decompiled vendor app and were verified live on the device;
see docs/PROTOCOL.md for the full write-up.
"""

# ---- infoType values (CONFIRMED, SocketUrl) ----
INFOTYPE_DEVICE_STATUS = 20001  # state snapshot: mode, subMode, elec, cleanArea, cleanTime
INFOTYPE_NOTIFICATION = 20003  # fault/info code in data.msg.code
INFOTYPE_GET_AREA = 21004  # reply carries mapId + room/area ids
INFOTYPE_SET_AREA_SWEEP = 21005  # start clean: data.mode / cleanMode / pathType / areaId[]
INFOTYPE_SET_ROBOT_TO_CHARGE = 21012  # dock: cmd "start" / "stop"
INFOTYPE_GET_CONSUMABLE = 21015  # read filter/sideBrush/mainBrush/sensors
INFOTYPE_SET_CONSUMABLE = 21016  # write ints: filter, sideBrush, mainBrush, sensors
INFOTYPE_SET_PAUSE = 21017  # cmd "pause" / "continue" / "stop"
INFOTYPE_GET_VERSION = 21018  # reply: version, fullversion, mcu
INFOTYPE_GET_WIFI = 21019  # reply: staId (SSID), staSignal (0-100), staIp, staMac
INFOTYPE_CONTROL = 21020  # data.ctrlCode (see CTRL_* below)
INFOTYPE_SET_WIND_POWER = 21022  # cmd quiet / auto / strong / mop
INFOTYPE_ACTIVATE_AREA = 21023  # room/zone selection: mapId, cleanId[], extraAreas[]
INFOTYPE_SET_ROBOT = 21024  # cmd setVolume / setledswitch / setPathType / setWaterPump
INFOTYPE_COMPOUND = 30000  # data.cmds[] = batch of the above

# ---- ctrlCode values for INFOTYPE_CONTROL (CONFIRMED) ----
CTRL_CHARGE = 3000
CTRL_SPOT = 3001
CTRL_START_OR_PAUSE = 3002
CTRL_CHANGE_WIND = 3003
CTRL_FORWARD = 3005
CTRL_BACK = 3006
CTRL_TURN_LEFT = 3007
CTRL_TURN_RIGHT = 3008
CTRL_CHECK_WIFI_STATUS = 3009
CTRL_FIND_ROBOT_START = 3010
CTRL_FIND_ROBOT_STOP = 3011
CTRL_CLEAR_DATA = 3012
CTRL_SIG_SET_SPEED = 3013

# Remote-control directions -> ctrlCode (verified live, see docs/PROTOCOL.md).
DRIVE_CODES = {
    "forward": CTRL_FORWARD,
    "back": CTRL_BACK,
    "left": CTRL_TURN_LEFT,
    "right": CTRL_TURN_RIGHT,
}

# ---- cleaning modes for INFOTYPE_SET_AREA_SWEEP (CONFIRMED) ----
CLEAN_MODE_TOTAL = "totalClean"
CLEAN_MODE_AREA = "areaClean"  # takes data.areaId[] of selected room ids
CLEAN_MODE_RE_APPOINT = "reAppointClean"
SWEEP_MODE_SWEEP_ONLY = "sweepOnly"
PATH_TYPE_NORMAL = "normal"

# ---- state field keys (CONFIRMED from INFOTYPE_DEVICE_STATUS) ----
KEY_BATTERY = "elec"
KEY_MODE = "mode"
KEY_MAP_ID = "mapId"
KEY_CLEAN_AREA = "cleanArea"
KEY_CLEAN_TIME = "cleanTime"

# mapId value meaning "no saved map yet" — room/zone cleaning is impossible
# until the vacuum has built one.
MAP_ID_NONE = -1

# ---- consumable field keys (CONFIRMED from INFOTYPE_GET_CONSUMABLE / _SET_CONSUMABLE) ----
KEY_CONSUMABLE_FILTER = "filter"
KEY_CONSUMABLE_SIDE_BRUSH = "sideBrush"
KEY_CONSUMABLE_MAIN_BRUSH = "mainBrush"
KEY_CONSUMABLE_SENSORS = "sensors"
CONSUMABLE_KEYS = (
    KEY_CONSUMABLE_FILTER,
    KEY_CONSUMABLE_SIDE_BRUSH,
    KEY_CONSUMABLE_MAIN_BRUSH,
    KEY_CONSUMABLE_SENSORS,
)

# Counters are run-time seconds; SET_CONSUMABLE writes an absolute value per field,
# and the app "resets" by writing 0. Life is 200 h for filter and brushes.
CONSUMABLE_RESET_VALUE = 0
CONSUMABLE_LIFE_SECONDS = 720000

# Fault/notification code -> human description (20003 data.msg.code).
# CONFIRMED flat decimal ID table (48 entries), not a bitmask. 0 = no fault.
FAULT_CODES: dict[int, str] = {
    0: "ok",
    -2706: "radar abnormal",
    -2705: "fan abnormal",
    -2704: "side brush abnormal",
    -2703: "main wheel abnormal",
    -2702: "main brush abnormal",
    -2701: "battery abnormal",
    -2607: "check cliff sensor",
    -2606: "move out of restricted zone",
    -2605: "cannot reach specified zone",
    -2604: "firmware upgrade failed",
    -2603: "water amount insufficient",
    -2602: "water tank missing",
    -2601: "start on the ground",
    -2502: "start at another location",
    -2501: "start at another location",
    -2407: "clean dust box and filter",
    -2406: "dust box missing",
    -2405: "dust box full",
    -2404: "radar cover blocked",
    -2403: "fan problem",
    -2402: "side brush stuck",
    -2401: "main brush stuck",
    -2309: "wall sensor abnormal",
    -2308: "collision sensor abnormal",
    -2306: "radar stuck",
    -2305: "radar blocked",
    -2304: "place on level ground",
    -2302: "edge stuck",
    -2201: "main wheel stuck",
    -2102: "power off, low battery",
    -2101: "low battery, going to charge",
    5058: "fail to recharge",
    6023: "cleaning completed",
    6034: "timed cleaning begins",
    6052: "re-locate",
    6096: "charged, cleaning continues",
    6097: "low battery, cannot start",
    6105: "fail to power off on charging pile",
    6126: "re-locate failed (restricted zone)",
    6127: "re-locate failed (cannot find dock)",
    6128: "cleaning in progress, timed clean skipped",
    6129: "battery low, please charge",
    6130: "partial cleaning ends",
    6131: "start dust collection",
    6132: "dust collection complete",
    6133: "dust bag seems full",
    6134: "dust bag not in place",
    6135: "dust collection fault",
}
