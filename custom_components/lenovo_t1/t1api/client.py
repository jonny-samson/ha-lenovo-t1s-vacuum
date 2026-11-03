"""Persistent local Tuya connection to the Lenovo T1 Pro. No Home Assistant imports,
so the standalone test tools use the same code as the integration.

All traffic rides on DP 102 as base64 JSON; see docs/PROTOCOL.md.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable

import tinytuya

from . import protocol
from .commands import FAN_MODES_REV, Commands
from .const import (
    CONSUMABLE_KEYS,
    CONSUMABLE_LIFE_SECONDS,
    FAULT_CODES,
    INFOTYPE_DEVICE_STATUS,
    INFOTYPE_GET_AREA,
    INFOTYPE_GET_CONSUMABLE,
    INFOTYPE_NOTIFICATION,
    MAP_ID_NONE,
)

_LOGGER = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 8
MIN_BACKOFF = 5
MAX_BACKOFF = 60
RECV_TIMEOUT = 2  # seconds receive() blocks when idle
STATE_POLL = 30  # bare 20001 when nothing has been reported for this long
ROOMS_POLL = 300
CONSUMABLES_POLL = 600
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


class T1Client:
    def __init__(self, host: str, device_id: str, local_key: str, serial: str,
                 user_id: str, version: float = 3.3) -> None:
        self._host, self._dev_id, self._key = host, device_id, local_key
        self._version = float(version)
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
        self.fault: int = 0
        self.last_message: int | None = None  # last 20003 type=message code
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
        self.send(self.commands.query_state())
        self.send(self.commands.query_rooms())
        self.send(self.commands.query_consumables())

    def start_clean(self) -> None:
        self.send(self.commands.start_clean(self._require_map()))

    def clean_rooms(self, room_ids: list[int]) -> None:
        unknown = [r for r in room_ids if r not in self.room_ids()]
        if unknown:
            raise ValueError(f"rooms not on the saved map: {unknown}")
        self.send(self.commands.clean_rooms(room_ids, self._require_map()))

    def _require_map(self) -> int:
        if not self.has_map:
            raise ValueError("no saved map known yet; save the map in the app first")
        return self.map_id

    def pause(self) -> None:
        self.send(self.commands.pause())

    def resume(self) -> None:
        self.send(self.commands.resume())

    def dock(self) -> None:
        self.send(self.commands.dock())

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
                    raise ConnectionError(status.get("Error"))
                self.connected = True
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
        hb = rooms_at = cons_at = state_at = time.time()
        while not self._stop.is_set():
            try:
                msg = self._cmds.get(timeout=0.2)
                d.set_value(protocol.DP_RAW, protocol.encode(msg), nowait=True)
            except queue.Empty:
                pass
            now = time.time()
            if now - hb > HEARTBEAT_INTERVAL:
                d.heartbeat(nowait=True)
                hb = now
            if now - max(self.last_report, state_at) > STATE_POLL:
                self.send(self.commands.query_state())
                state_at = now
            if now - rooms_at > ROOMS_POLL:
                self.send(self.commands.query_rooms())
                rooms_at = now
            if now - cons_at > CONSUMABLES_POLL:
                self.send(self.commands.query_consumables())
                cons_at = now
            resp = d.receive()
            if resp and resp.get("Err") in ("901", "904", "905", "914"):
                raise ConnectionError(resp.get("Error"))
            if resp:
                self._handle(resp)

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
        if info_type == INFOTYPE_DEVICE_STATUS:
            self.last_report = time.time()
            new = {k: v for k, v in data.items() if k not in _NOISY_KEYS and k not in ("sn", "userId")}
            before = dict(self.state)
            self.state.update(new)
            changed = self.state != before or not self._seen_state
            self._seen_state = True
            if isinstance(data.get("mapId"), int):
                self.map_id = data["mapId"]
        elif info_type == INFOTYPE_GET_AREA:
            self.last_report = time.time()
            rooms = [r for r in data.get("autoAreaValue") or [] if isinstance(r, dict)]
            map_id = data.get("mapId", self.map_id)
            changed = rooms != self.rooms or map_id != self.map_id
            self.rooms, self.map_id = rooms, map_id
        elif info_type == INFOTYPE_GET_CONSUMABLE:
            self.last_report = time.time()
            new = {k: data[k] for k in CONSUMABLE_KEYS if isinstance(data.get(k), int)}
            changed = new != {k: self.consumables.get(k) for k in new}
            self.consumables.update(new)
        elif info_type == INFOTYPE_NOTIFICATION:
            code = (data.get("msg") or {}).get("code", 0)
            if data.get("type") == "error":
                changed = code != self.fault
                self.fault = code if isinstance(code, int) else 0
            elif data.get("type") == "message":
                self.last_message = code
                changed = True
        if changed:
            self._notify()
