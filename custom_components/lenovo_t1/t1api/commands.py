"""Command builders. Every format here was verified live (see docs/PROTOCOL.md)."""
from __future__ import annotations

from .const import (
    CLEAN_MODE_RE_APPOINT,
    CONSUMABLE_KEYS,
    CONSUMABLE_RESET_VALUE,
    CTRL_FIND_ROBOT_START,
    CTRL_FIND_ROBOT_STOP,
    INFOTYPE_ACTIVATE_AREA,
    INFOTYPE_COMPOUND,
    INFOTYPE_CONTROL,
    INFOTYPE_DEVICE_STATUS,
    INFOTYPE_GET_AREA,
    INFOTYPE_GET_CONSUMABLE,
    INFOTYPE_GET_VERSION,
    INFOTYPE_GET_WIFI,
    INFOTYPE_SET_AREA_SWEEP,
    INFOTYPE_SET_CONSUMABLE,
    INFOTYPE_SET_PAUSE,
    INFOTYPE_SET_ROBOT,
    INFOTYPE_SET_ROBOT_TO_CHARGE,
    INFOTYPE_SET_WIND_POWER,
    SWEEP_MODE_SWEEP_ONLY,
)
from .protocol import Envelope

# Suction levels exposed to users -> wire values. This model has no mop:
# "Off" (wire value "mop") is the app's fourth setting.
FAN_MODES = {"Low": "quiet", "Medium": "auto", "High": "strong", "Off": "mop"}
FAN_MODES_REV = {v: k for k, v in FAN_MODES.items()}


class Commands:
    def __init__(self, envelope: Envelope) -> None:
        self._e = envelope

    # ---- queries ----
    def query_state(self) -> dict:
        return self._e.build(INFOTYPE_DEVICE_STATUS)

    def query_consumables(self) -> dict:
        return self._e.build(INFOTYPE_GET_CONSUMABLE)

    def query_rooms(self) -> dict:
        return self._e.build(INFOTYPE_GET_AREA)

    def query_wifi(self) -> dict:
        return self._e.build(INFOTYPE_GET_WIFI)

    def query_version(self) -> dict:
        return self._e.build(INFOTYPE_GET_VERSION)

    # ---- simple controls ----
    def locate_start(self) -> dict:
        return self._e.build(INFOTYPE_CONTROL, connection_type=0, ctrlCode=CTRL_FIND_ROBOT_START)

    def locate_stop(self) -> dict:
        return self._e.build(INFOTYPE_CONTROL, connection_type=0, ctrlCode=CTRL_FIND_ROBOT_STOP)

    def drive(self, ctrl_code: int) -> dict:
        """One remote-control step (3005 fwd, 3006 back, 3007 left, 3008 right).
        Send every ~0.25 s; the vacuum needs ~3 messages before it moves."""
        return self._e.build(INFOTYPE_CONTROL, connection_type=0, ctrlCode=ctrl_code)

    def pause(self) -> dict:
        return self._e.build(INFOTYPE_SET_PAUSE, cmd="pause")

    def resume(self) -> dict:
        return self._e.build(INFOTYPE_SET_PAUSE, cmd="continue")

    def stop_clean(self) -> dict:
        return self._e.build(INFOTYPE_SET_PAUSE, cmd="stop")

    def dock(self) -> dict:
        return self._e.build(INFOTYPE_SET_ROBOT_TO_CHARGE, cmd="start")

    def dock_cancel(self) -> dict:
        return self._e.build(INFOTYPE_SET_ROBOT_TO_CHARGE, cmd="stop")

    def set_suction(self, cmd: str) -> dict:
        if cmd not in FAN_MODES_REV:
            raise ValueError(f"unknown suction value: {cmd}")
        return self._e.build(INFOTYPE_SET_WIND_POWER, cmd=cmd)

    def set_volume(self, value: int) -> dict:
        return self._e.build(INFOTYPE_SET_ROBOT, cmd="setVolume", value=max(0, min(10, int(value))))

    def set_light(self, on: bool) -> dict:
        return self._e.build(INFOTYPE_SET_ROBOT, cmd="setledswitch", value=1 if on else 0)

    def reset_consumable(self, field: str, current: dict) -> dict:
        """Zero one counter, keeping the other three at their current values.
        `current` must be a fresh 21015 reply, otherwise the others are overwritten."""
        if field not in CONSUMABLE_KEYS:
            raise ValueError(f"unknown consumable field: {field}")
        missing = [k for k in CONSUMABLE_KEYS if k not in current]
        if missing:
            raise ValueError(f"consumables not read yet, missing {missing}")
        payload = {k: current[k] for k in CONSUMABLE_KEYS}
        payload[field] = CONSUMABLE_RESET_VALUE
        return self._e.build(INFOTYPE_SET_CONSUMABLE, **payload)

    # ---- cleaning ----
    def start_clean(self, map_id: int) -> dict:
        """Total clean. `map_id` comes from the 21004 reply (needs a saved map)."""
        return self._clean_batch(map_id, cleanId=[-1, -3])

    def clean_rooms(self, room_ids: list[int], map_id: int) -> dict:
        """Clean the given room ids; order given = order cleaned."""
        if not room_ids:
            raise ValueError("no rooms given")
        return self._clean_batch(map_id, segmentId=[int(r) for r in room_ids], cleanId=[-3])

    def _clean_batch(self, map_id: int, **activate_data) -> dict:
        activate = self._e.build(INFOTYPE_ACTIVATE_AREA, connection_type=0,
                                 mapId=map_id, extraAreas=[], **activate_data)
        sweep = self._e.build(INFOTYPE_SET_AREA_SWEEP, connection_type=0,
                              mode=CLEAN_MODE_RE_APPOINT, cleanMode=SWEEP_MODE_SWEEP_ONLY)
        return self._e.build(INFOTYPE_COMPOUND, cmds=[activate, sweep])
