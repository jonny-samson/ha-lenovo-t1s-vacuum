"""Persistent local Tuya connection to the Lenovo T1 Pro. No Home Assistant imports,
so the standalone test tools use the same code as the integration.

All traffic rides on DP 102 as base64 JSON; see docs/PROTOCOL.md.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import NamedTuple

import tinytuya

from . import protocol
from .commands import FAN_MODES_REV, Commands
from .const import (
    CONSUMABLE_KEYS,
    CONSUMABLE_LIFE_SECONDS,
    DRIVE_CODES,
    FAULT_CODES,
    INFOTYPE_DEVICE_STATUS,
    INFOTYPE_GET_AREA,
    INFOTYPE_GET_CONSUMABLE,
    INFOTYPE_GET_VERSION,
    INFOTYPE_GET_WIFI,
    INFOTYPE_NOTIFICATION,
    MAP_ID_NONE,
)

_LOGGER = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 8
MIN_BACKOFF = 5
MAX_BACKOFF = 60
RECV_TIMEOUT = 2  # seconds receive() blocks when idle
STATE_POLL = 30  # bare 20001 when nothing has been reported for this long
ROOMS_POLL = 300  # also used for the Wi-Fi and firmware queries
CONSUMABLES_POLL = 600  # default for slow_poll=300 (twice the slow poll)
# After connecting, the slow queries are spread out instead of fired back to back
# (a burst of 21015 with 20001/21020 once made the device drop the connection).
STARTUP_STAGGER = {"rooms": 2, "consumables": 4, "wifi": 6, "version": 8}
DRIVE_INTERVAL = 0.25  # seconds between remote-control messages
DRIVE_DEFAULT_COUNT = 6  # ~3 are needed before the vacuum moves
DRIVE_MAX_SECONDS = 10
STALE_AFTER = 120  # no report at all for this long => treat as unavailable

# 20001 keys that change constantly while moving and are not worth a state write.
_NOISY_KEYS = ("pos", "phi", "timeStamp")

# mode -> HA-style activity
ACTIVITY = {
    "sweep": "cleaning",
    "rfctrl": "cleaning",
    "pause": "paused",
    "findchargerpause": "paused",
    "backcharge": "returning",
    "charge": "docked",
    "fullcharge": "docked",  # on the dock at 100%
    "idle": "idle",
    "fault": "error",
}

WIFI_KEYS = ("staId", "staSignal", "staIp", "staMac")
FIRMWARE_KEYS = ("version", "fullversion", "mcu")


class DriveBurst(NamedTuple):
    """Queue item: repeat one remote-control code `count` times, DRIVE_INTERVAL apart."""
    ctrl_code: int
    count: int


class T1Client:
    def __init__(self, host: str, device_id: str, local_key: str, serial: str,
                 user_id: str, version: float = 3.3, state_poll: float = STATE_POLL,
                 slow_poll: float = ROOMS_POLL) -> None:
        self._host, self._dev_id, self._key = host, device_id, local_key
        self._version = float(version)
        self._state_poll = state_poll
        self._slow_poll = slow_poll  # rooms, Wi-Fi and firmware; consumables use twice this
        self.commands = Commands(protocol.Envelope(serial, user_id))
        self._cmds: queue.Queue = queue.Queue()
        self._listeners: list[Callable[[], None]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="lenovo_t1", daemon=True)
        self.connected = False
        self.last_report = 0.0
        self.state: dict = {}
        self.rooms: list[dict] = []
        self.map_id: int = MAP_ID_NONE
        self.consumables: dict = {}
        self.wifi: dict = {}
        self.firmware: dict = {}
        self._last_area: int | float | None = None
        self._last_time: int | float | None = None
        self.fault: int = 0
        self.last_message: int | None = None  # last 20003 type=message code
        self.connect_count = 0  # successful connections since start; first one is not a reconnect
        self.rooms_known = False  # a 21004 reply has arrived
        self.position = None  # last "pos" from the status report, as sent (format not documented)
        self.events: deque[tuple[str, int]] = deque(maxlen=50)  # ("message"|"fault"|"fault_cleared", code)
        self.event_count = 0  # events ever appended; lets a reader find the ones it has not seen
        self.auth_errors = 0  # consecutive "check device key or version" replies
        self.finished_cleans = 0  # cleans that ended on the dock since start
        self.finished_area: float = 0
        self.finished_seconds: float = 0
        self._in_clean = False
        self._seen_state = False

    # ---- lifecycle ----
    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        """cb() is called from the connection thread; returns a remover."""
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb) if cb in self._listeners else None

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("listener failed")

    # ---- derived state ----
    @property
    def available(self) -> bool:
        return self.connected and (time.time() - self.last_report) < STALE_AFTER

    @property
    def mode(self) -> str | None:
        return self.state.get("mode")

    @property
    def activity(self) -> str:
        return ACTIVITY.get(self.mode, "idle")

    @property
    def clean_area(self) -> int | float | None:
        """Area of the current clean, or of the last one while the vacuum is idle
        (the device reports 0 between cleans)."""
        return self._last_area if self._last_area is not None else self.state.get("cleanArea")

    @property
    def clean_time(self) -> int | float | None:
        """Seconds of the current or last clean, see clean_area."""
        return self._last_time if self._last_time is not None else self.state.get("cleanTime")

    @property
    def battery(self) -> int | None:
        return self.state.get("elec")

    @property
    def fan_speed(self) -> str | None:
        return FAN_MODES_REV.get(self.state.get("workNoisy"))

    @property
    def volume(self) -> int | None:
        return self.state.get("vol")

    @property
    def light(self) -> bool | None:
        led = self.state.get("led")
        return None if led is None else bool(led)

    @property
    def fault_text(self) -> str:
        return FAULT_CODES.get(self.fault, f"unknown ({self.fault})") if self.fault else "ok"

    @property
    def auth_failed(self) -> bool:
        """Three connection attempts in a row were refused for a bad key or protocol version."""
        return self.auth_errors >= 3

    @property
    def last_message_text(self) -> str | None:
        if self.last_message is None:
            return None
        return FAULT_CODES.get(self.last_message, f"unknown ({self.last_message})")

    @property
    def reconnects(self) -> int:
        return max(0, self.connect_count - 1)

    @property
    def has_map(self) -> bool:
        return self.map_id not in (None, MAP_ID_NONE, 0) and bool(self.rooms)

    def room_ids(self) -> list[int]:
        return [r["id"] for r in self.rooms if "id" in r]

    def room(self, room_id: int) -> dict | None:
        return next((r for r in self.rooms if r.get("id") == room_id), None)

    def consumable_hours(self, field: str) -> float | None:
        if field not in self.consumables:
            return None
        return round(max(0, CONSUMABLE_LIFE_SECONDS - self.consumables[field]) / 3600, 1)

    # ---- commands (queued, written by the connection thread) ----
    def send(self, msg: dict) -> None:
        self._cmds.put(msg)

    def refresh(self) -> None:
        """Ask for the state; the loop follows up with the slower queries."""
        self.send(self.commands.query_state())

    def start_clean(self, deep: bool = False) -> None:
        self.send(self.commands.start_clean(self._require_map(), deep))

    def clean_rooms(self, room_ids: list[int]) -> None:
        unknown = [r for r in room_ids if r not in self.room_ids()]
        if unknown:
            raise ValueError(f"rooms not on the saved map: {unknown}")
        self.send(self.commands.clean_rooms(room_ids, self._require_map()))

    def spot_clean(self) -> None:
        self.send(self.commands.spot_clean())

    def along_wall(self) -> None:
        self.send(self.commands.along_wall(self._require_map()))

    def clean_zone(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.send(self.commands.clean_zone(x1, y1, x2, y2, self._require_map()))

    def go_to_point(self, x: float, y: float) -> None:
        self.send(self.commands.go_to_point(x, y, self._require_map()))

    def set_room_passes(self, room_id: int, double: bool) -> None:
        """Change one room's pass count. Needs the room list as last read from the vacuum."""
        if not self.rooms_known:
            raise ValueError("the room list has not been read yet")
        self.send(self.commands.set_room_passes(self.rooms, room_id, double, self._require_map()))
        self.send(self.commands.query_rooms())

    def _require_map(self) -> int:
        if not self.has_map:
            raise ValueError("no saved map known yet; save the map in the app first")
        return self.map_id

    def pause(self) -> None:
        self.send(self.commands.pause())

    def resume(self) -> None:
        self.send(self.commands.resume())

    def stop_clean(self) -> None:
        self.send(self.commands.stop_clean())

    def dock(self) -> None:
        self.send(self.commands.dock())

    def cancel_dock(self) -> None:
        self.send(self.commands.dock_cancel())

    def drive(self, direction: str, duration: float | None = None) -> None:
        """Move in short steps: ~7.5 cm forward or ~11 degrees per message after start-up.
        `duration` (seconds, default about 1.5) sets how many messages are sent."""
        if direction not in DRIVE_CODES:
            raise ValueError(f"unknown direction: {direction}")
        count = DRIVE_DEFAULT_COUNT if duration is None else round(float(duration) / DRIVE_INTERVAL)
        count = max(1, min(count, int(DRIVE_MAX_SECONDS / DRIVE_INTERVAL)))
        self.send(DriveBurst(DRIVE_CODES[direction], count))

    def locate(self) -> None:
        self.send(self.commands.locate_start())
        threading.Timer(3.0, lambda: self.send(self.commands.locate_stop())).start()

    def set_suction(self, cmd: str) -> None:
        self.send(self.commands.set_suction(cmd))
        self.send(self.commands.query_state())

    def set_volume(self, value: int) -> None:
        self.send(self.commands.set_volume(value))
        self.send(self.commands.query_state())

    def set_light(self, on: bool) -> None:
        self.send(self.commands.set_light(on))
        self.send(self.commands.query_state())

    def reset_consumable(self, field: str) -> None:
        self.send(self.commands.reset_consumable(field, self.consumables))
        self.send(self.commands.query_consumables())

    # ---- connection thread ----
    def _run(self) -> None:
        backoff = MIN_BACKOFF
        while not self._stop.is_set():
            d = None
            try:
                d = tinytuya.Device(self._dev_id, self._host, self._key, version=self._version)
                d.set_socketPersistent(True)
                d.set_socketTimeout(RECV_TIMEOUT)
                d.set_socketRetryLimit(1)
                status = d.status()
                if isinstance(status, dict) and status.get("Error"):
                    if status.get("Err") == "914":
                        self._count_auth_error()
                    raise ConnectionError(status.get("Error"))
                self.connected = True
                self.connect_count += 1
                backoff = MIN_BACKOFF
                self.refresh()
                self._notify()
                self._loop(d)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("connection error: %s", err)
            finally:
                if d is not None:
                    try:
                        d.set_socketPersistent(False)
                        d.close()
                    except Exception:  # noqa: BLE001
                        pass
                if self.connected:
                    self.connected = False
                    self._notify()
            self._stop.wait(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)

    def _loop(self, d: tinytuya.Device) -> None:
        now = time.time()
        hb = state_at = now
        slow, cons_poll = self._slow_poll, self._slow_poll * 2
        rooms_at = now - slow + STARTUP_STAGGER["rooms"]
        cons_at = now - cons_poll + STARTUP_STAGGER["consumables"]
        wifi_at = now - slow + STARTUP_STAGGER["wifi"]
        version_at = now - slow + STARTUP_STAGGER["version"]
        while not self._stop.is_set():
            try:
                item = self._cmds.get(timeout=0.2)
                if isinstance(item, DriveBurst):
                    self._drive(d, item)
                else:
                    d.set_value(protocol.DP_RAW, protocol.encode(item), nowait=True)
            except queue.Empty:
                pass
            now = time.time()
            if now - hb > HEARTBEAT_INTERVAL:
                d.heartbeat(nowait=True)
                hb = now
            if now - max(self.last_report, state_at) > self._state_poll:
                self.send(self.commands.query_state())
                state_at = now
            if now - rooms_at > slow:
                self.send(self.commands.query_rooms())
                rooms_at = now
            if now - cons_at > cons_poll:
                self.send(self.commands.query_consumables())
                cons_at = now
            if now - wifi_at > slow:
                self.send(self.commands.query_wifi())
                wifi_at = now
            if now - version_at > slow:
                self.send(self.commands.query_version())
                version_at = now
            resp = d.receive()
            if resp and resp.get("Err") in ("901", "904", "905", "914"):
                if resp.get("Err") == "914":
                    self._count_auth_error()
                raise ConnectionError(resp.get("Error"))
            if resp:
                self._handle(resp)

    def _add_event(self, kind: str, code: int) -> None:
        self.events.append((kind, code))
        self.event_count += 1

    def new_events(self, seen: int) -> list[tuple[str, int]]:
        """Events added since the reader last looked (`seen` = the event_count it saw then)."""
        fresh = min(self.event_count - seen, len(self.events))
        return list(self.events)[len(self.events) - fresh:] if fresh > 0 else []

    def _count_auth_error(self) -> None:
        self.auth_errors += 1
        if self.auth_failed:
            self._notify()

    def _drive(self, d: tinytuya.Device, burst: DriveBurst) -> None:
        for _ in range(burst.count):
            if self._stop.is_set():
                return
            msg = self.commands.drive(burst.ctrl_code)
            d.set_value(protocol.DP_RAW, protocol.encode(msg), nowait=True)
            self._stop.wait(DRIVE_INTERVAL)

    # ---- incoming ----
    def _handle(self, resp: dict) -> None:
        for dp, val in (resp.get("dps") or {}).items():
            if dp != protocol.DP_RAW:
                continue
            try:
                payload = protocol.decode(val)
            except Exception:  # noqa: BLE001
                continue
            self.handle_payload(payload)

    def handle_payload(self, payload: dict) -> None:
        """Apply one decoded DP-102 payload (public so tests can feed it)."""
        info_type = payload.get("infoType")
        data = payload.get("data")
        if not isinstance(data, dict):
            return
        changed = False
        if info_type in (INFOTYPE_DEVICE_STATUS, INFOTYPE_GET_AREA, INFOTYPE_GET_CONSUMABLE,
                         INFOTYPE_GET_WIFI, INFOTYPE_GET_VERSION):
            self.auth_errors = 0
        if info_type == INFOTYPE_DEVICE_STATUS:
            self.last_report = time.time()
            if "pos" in data:
                self.position = data["pos"]
            new = {k: v for k, v in data.items() if k not in _NOISY_KEYS and k not in ("sn", "userId")}
            before = dict(self.state)
            self.state.update(new)
            self._remember_clean(new)
            changed = self.state != before or not self._seen_state
            self._seen_state = True
            if isinstance(data.get("mapId"), int):
                self.map_id = data["mapId"]
        elif info_type == INFOTYPE_GET_AREA:
            self.last_report = time.time()
            rooms = [r for r in data.get("autoAreaValue") or [] if isinstance(r, dict)]
            map_id = data.get("mapId", self.map_id)
            changed = rooms != self.rooms or map_id != self.map_id
            changed = changed or not self.rooms_known
            self.rooms, self.map_id, self.rooms_known = rooms, map_id, True
        elif info_type == INFOTYPE_GET_CONSUMABLE:
            self.last_report = time.time()
            new = {k: data[k] for k in CONSUMABLE_KEYS if isinstance(data.get(k), int)}
            changed = new != {k: self.consumables.get(k) for k in new}
            self.consumables.update(new)
        elif info_type == INFOTYPE_GET_WIFI:
            self.last_report = time.time()
            new = {k: data[k] for k in WIFI_KEYS if k in data}
            changed = new != {k: self.wifi.get(k) for k in new}
            self.wifi.update(new)
        elif info_type == INFOTYPE_GET_VERSION:
            self.last_report = time.time()
            new = {k: data[k] for k in FIRMWARE_KEYS if k in data}
            changed = new != {k: self.firmware.get(k) for k in new}
            self.firmware.update(new)
        elif info_type == INFOTYPE_NOTIFICATION:
            code = (data.get("msg") or {}).get("code", 0)
            if data.get("type") == "error":
                changed = code != self.fault
                if changed:
                    self._add_event("fault" if code else "fault_cleared", code or self.fault)
                self.fault = code if isinstance(code, int) else 0
            elif data.get("type") == "message":
                self.last_message = code
                self._add_event("message", code)
                changed = True
        if changed:
            self._notify()

    def _remember_clean(self, new: dict) -> None:
        """Keep the last non-zero area/time; a fresh clean (mode sweep) may start from 0.
        A clean that ends on the dock (or idle) is added to the finished totals once."""
        mode = self.state.get("mode")
        starting = mode == "sweep"
        for key, attr in (("cleanArea", "_last_area"), ("cleanTime", "_last_time")):
            value = new.get(key)
            if isinstance(value, (int, float)) and (value > 0 or starting):
                setattr(self, attr, value)
        if starting:
            self._in_clean = True
        elif self._in_clean and mode in ("charge", "fullcharge", "idle"):
            self._in_clean = False
            area, seconds = self._last_area or 0, self._last_time or 0
            if area > 0 or seconds > 0:
                self.finished_cleans += 1
                self.finished_area += area
                self.finished_seconds += seconds
