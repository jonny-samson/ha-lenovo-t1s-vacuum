"""Persistent local Tuya connection for the Lenovo T1 Pro (DP 102 rawdata protocol)."""
import base64
import json
import logging
import queue
import threading
import time

import tinytuya

_LOGGER = logging.getLogger(__name__)

DP_RAW = "102"
SILENCE_DOCKED_AFTER = 45  # seconds of silence after "backcharge" => assume docked


class T1Client:
    def __init__(self, host, dev_id, local_key, version, sn, user_id):
        self._host, self._dev_id, self._key = host, dev_id, local_key
        self._version = float(version)
        self._sn, self._uid = sn, user_id
        self._cmds: queue.Queue = queue.Queue()
        self._listeners = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="lenovo_t1", daemon=True)
        self.state = {}  # last 20001 data
        self.last_report = 0.0
        self.last_back = 0.0
        self.connected = False
        self.fan_speed = "auto"
        self.volume = None
        self.light = None
        self.fault = 0

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def add_listener(self, cb):
        self._listeners.append(cb)

    # ---- state ----
    @property
    def mode(self):
        return self.state.get("mode")

    @property
    def battery(self):
        return self.state.get("elec")

    @property
    def activity(self):
        mode = self.mode
        silent = time.time() - self.last_report
        if mode == "sweep":
            return "cleaning" if silent < 30 else "docked"
        if mode == "pause":
            return "paused" if silent < 300 else "docked"
        if mode == "backcharge":
            return "returning" if silent < SILENCE_DOCKED_AFTER else "docked"
        return "docked"

    # ---- commands ----
    def _msg(self, info_type, **data):
        data.update(sn=self._sn, userId=self._uid)
        return {
            "connectionType": 1,
            "dInfo": {"ts": str(int(time.time() * 1000)), "userId": self._uid},
            "data": data,
            "infoType": info_type,
            "isShowTip": False,
        }

    def send(self, msg):
        self._cmds.put(msg)

    def start_clean(self):
        # Mirrors the app's "total clean" batch (infoType 30000).
        now = str(int(time.time() * 1000))
        di = {"ts": now, "userId": self._uid}
        cmds = [
            self._msg(21024, cmd="setPathType", value=0),
            {"connectionType": 0, "dInfo": di, "infoType": 21023, "isShowTip": False,
             "data": {"cleanId": [-1, -3], "mapId": self.state.get("mapId", 0), "sn": self._sn,
                      "userId": self._uid, "extraAreas": []}},
            {"connectionType": 0, "dInfo": di, "infoType": 21005, "isShowTip": False,
             "data": {"mode": "reAppointClean", "cleanMode": "sweepOnly", "sn": self._sn,
                      "userId": self._uid}},
        ]
        self.send(self._msg(30000, cmds=cmds))

    def pause(self):
        self.send(self._msg(21017, cmd="pause"))

    def resume(self):
        self.send(self._msg(21017, cmd="continue"))

    def dock(self):
        self.send(self._msg(21012, cmd="start"))

    def locate(self):
        self.send(self._msg(21020, ctrlCode=3010))

    def set_suction(self, cmd):
        self.fan_speed = cmd
        self.send(self._msg(21022, cmd=cmd))
        self._notify()

    def set_volume(self, value):
        self.volume = int(value)
        self.send(self._msg(21024, cmd="setVolume", value=int(value)))
        self._notify()

    def set_light(self, on):
        self.light = bool(on)
        self.send(self._msg(21024, cmd="setledswitch", value=1 if on else 0))
        self._notify()

    def query_state(self):
        self.send(self._msg(20001))

    # ---- worker ----
    def _notify(self):
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("listener failed")

    def _handle(self, resp):
        for dp, val in (resp.get("dps") or {}).items():
            if dp != DP_RAW:
                continue
            try:
                p = json.loads(base64.b64decode(val))
            except Exception:  # noqa: BLE001
                continue
            it = p.get("infoType")
            if it == 20001 and isinstance(p.get("data"), dict):
                self.state.update({k: v for k, v in p["data"].items() if k not in ("pos", "phi")})
                self.last_report = time.time()
                self._notify()
            elif it == 20003:
                self.fault = (p.get("data", {}).get("msg", {}) or {}).get("code", 0)
                self._notify()

    def _run(self):
        while not self._stop.is_set():
            try:
                d = tinytuya.Device(self._dev_id, self._host, self._key, version=self._version)
                d.set_socketPersistent(True)
                d.set_socketTimeout(2)
                d.set_socketRetryLimit(1)
                d.status()
                self.connected = True
                self._notify()
                hb = 0.0
                while not self._stop.is_set():
                    try:
                        msg = self._cmds.get_nowait()
                        d.set_value(102, base64.b64encode(json.dumps(msg, separators=(",", ":")).encode()).decode(), nowait=True)
                    except queue.Empty:
                        pass
                    if time.time() - hb > 8:
                        d.heartbeat(nowait=True)
                        hb = time.time()
                    resp = d.receive()
                    if resp and resp.get("Err") in ("901", "904", "905", "914"):
                        raise ConnectionError(resp.get("Error"))
                    if resp:
                        self._handle(resp)
                    self._notify_if_silence_changed()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("T1 connection error: %s", err)
            self.connected = False
            self._notify()
            self._stop.wait(5)

    _last_act = None

    def _notify_if_silence_changed(self):
        act = self.activity
        if act != self._last_act:
            self._last_act = act
            self._notify()
