"""Standalone persistent connection to the T1 Pro, for interactive protocol
testing outside Home Assistant. Mirrors the proven-working tinytuya
connection parameters from custom_components/lenovo_t1/client.py
(persistent=True, timeout=2, retry=1) — a config-flow probe once used
different parameters and silently failed where this combination worked.
"""
from __future__ import annotations

import logging
import queue
import threading
import time

import tinytuya

import protocol
from config import DEVICE_ID, HOST, LOCAL_KEY, VERSION

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
_LOGGER = logging.getLogger("t1")

HEARTBEAT_INTERVAL = 8
MIN_BACKOFF = 5
MAX_BACKOFF = 60
RECV_TIMEOUT = 2  # lower (e.g. 0.15) for tight command pacing; receive() blocks this long when idle


class T1Device:
    def __init__(self, on_message=None):
        """on_message(dict): called for every decoded DP-102 payload received."""
        self._cmds: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._on_message = on_message or (lambda p: None)
        self.connected = False
        self._thread = threading.Thread(target=self._run, name="t1-device", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)

    def send(self, msg: dict):
        """Queue a pre-built message envelope (see protocol.build) for the
        connection thread to write out."""
        _LOGGER.debug("queueing: %s", msg)
        self._cmds.put(msg)

    def _run(self):
        backoff = MIN_BACKOFF
        while not self._stop.is_set():
            d = None
            try:
                d = tinytuya.Device(DEVICE_ID, HOST, LOCAL_KEY, version=VERSION)
                d.set_socketPersistent(True)
                d.set_socketTimeout(RECV_TIMEOUT)
                d.set_socketRetryLimit(1)
                d.status()
                self.connected = True
                backoff = MIN_BACKOFF
                _LOGGER.info("connected to %s", HOST)

                hb = 0.0
                while not self._stop.is_set():
                    try:
                        msg = self._cmds.get(timeout=0.2)
                        d.set_value(protocol.DP_RAW, protocol.encode(msg), nowait=True)
                        _LOGGER.info("sent: %s", msg)
                    except queue.Empty:
                        pass
                    now = time.time()
                    if now - hb > HEARTBEAT_INTERVAL:
                        d.heartbeat(nowait=True)
                        hb = now
                    resp = d.receive()
                    if resp and resp.get("Err") in ("901", "904", "905", "914"):
                        raise ConnectionError(resp.get("Error"))
                    if resp:
                        self._handle(resp)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("connection error: %s", err)
            finally:
                if d is not None:
                    try:
                        d.set_socketPersistent(False)
                        d.close()
                    except Exception:  # noqa: BLE001
                        pass
                self.connected = False
            self._stop.wait(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)

    def _handle(self, resp):
        for dp, val in (resp.get("dps") or {}).items():
            if dp != protocol.DP_RAW:
                _LOGGER.info("other dp %s len=%s", dp, len(str(val)))
                continue
            try:
                payload = protocol.decode(val)
            except Exception:  # noqa: BLE001
                _LOGGER.info("undecodable DP %s len=%s head=%r", dp, len(str(val)), str(val)[:60])
                continue
            _LOGGER.info("recv infoType=%s data=%s", payload.get("infoType"), payload.get("data"))
            self._on_message(payload)
