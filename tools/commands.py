"""High-level command builders — each returns a message envelope ready for
device.T1Device.send(). All formats below were verified live against the
device (see PROTOCOL.md).
"""
from __future__ import annotations

from protocol import build
from const import (
    CLEAN_MODE_RE_APPOINT,
    CONSUMABLE_KEYS,
    CONSUMABLE_RESET_VALUE,
    INFOTYPE_ACTIVATE_AREA,
    INFOTYPE_COMPOUND,
    INFOTYPE_CONTROL,
    INFOTYPE_DEVICE_STATUS,
    INFOTYPE_GET_AREA,
    INFOTYPE_GET_CONSUMABLE,
    INFOTYPE_SET_AREA_SWEEP,
    INFOTYPE_SET_CONSUMABLE,
    INFOTYPE_SET_PAUSE,
    INFOTYPE_SET_ROBOT,
    INFOTYPE_SET_ROBOT_TO_CHARGE,
    INFOTYPE_SET_WIND_POWER,
    CTRL_FIND_ROBOT_START,
    CTRL_FIND_ROBOT_STOP,
    SWEEP_MODE_SWEEP_ONLY,
)

# fan: Low / Medium / High / Off  (this model has no mop; "mop" = suction off)
FAN_MODES = {"low": "quiet", "medium": "auto", "high": "strong", "off": "mop"}


def query_state():
    return build(INFOTYPE_DEVICE_STATUS)


def query_consumables():
    return build(INFOTYPE_GET_CONSUMABLE)


def query_rooms():
    return build(INFOTYPE_GET_AREA)


def locate_start():
    return build(INFOTYPE_CONTROL, connection_type=0, ctrlCode=CTRL_FIND_ROBOT_START)


def locate_stop():
    return build(INFOTYPE_CONTROL, connection_type=0, ctrlCode=CTRL_FIND_ROBOT_STOP)


def drive(ctrl_code: int):
    """One remote-control step (3005 fwd, 3006 back, 3007 left, 3008 right).
    Send repeatedly every ~0.25 s; the vacuum needs ~3 messages to start moving."""
    return build(INFOTYPE_CONTROL, connection_type=0, ctrlCode=ctrl_code)


def pause():
    return build(INFOTYPE_SET_PAUSE, cmd="pause")


def resume():
    return build(INFOTYPE_SET_PAUSE, cmd="continue")


def dock():
    return build(INFOTYPE_SET_ROBOT_TO_CHARGE, cmd="start")


def dock_cancel():
    return build(INFOTYPE_SET_ROBOT_TO_CHARGE, cmd="stop")


def set_suction(cmd):
    return build(INFOTYPE_SET_WIND_POWER, cmd=cmd)


def set_volume(value):
    return build(INFOTYPE_SET_ROBOT, cmd="setVolume", value=int(value))


def set_light(on: bool):
    return build(INFOTYPE_SET_ROBOT, cmd="setledswitch", value=1 if on else 0)


def reset_consumable(field: str, current: dict):
    """Zero one counter, keeping the other three at their current values.
    `current` must be a fresh 21015 reply or the others get overwritten."""
    if field not in CONSUMABLE_KEYS:
        raise ValueError(f"unknown consumable field: {field}")
    missing = [k for k in CONSUMABLE_KEYS if k not in current]
    if missing:
        raise ValueError(f"run 'consumables' first, missing {missing}")
    payload = {k: current[k] for k in CONSUMABLE_KEYS}
    payload[field] = CONSUMABLE_RESET_VALUE
    return build(INFOTYPE_SET_CONSUMABLE, **payload)


def start_clean(map_id: int):
    """Total clean. map_id comes from the 21004 reply (rooms must be saved)."""
    return _clean_batch(map_id, cleanId=[-1, -3])


def clean_rooms(room_ids: list[int], map_id: int):
    """Clean the given room ids, in the order given (order = cleaning order)."""
    return _clean_batch(map_id, segmentId=list(room_ids), cleanId=[-3])


def _clean_batch(map_id, **activate_data):
    activate = build(INFOTYPE_ACTIVATE_AREA, connection_type=0,
                     mapId=map_id, extraAreas=[], **activate_data)
    sweep = build(INFOTYPE_SET_AREA_SWEEP, connection_type=0,
                  mode=CLEAN_MODE_RE_APPOINT, cleanMode=SWEEP_MODE_SWEEP_ONLY)
    return build(INFOTYPE_COMPOUND, cmds=[activate, sweep])
