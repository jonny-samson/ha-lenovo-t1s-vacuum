from unittest.mock import patch

import pytest

from custom_components.lenovo_t1.t1api import T1Client

pytest_plugins = "pytest_homeassistant_custom_component"

ROOMS = {"infoType": 21004, "data": {"mapId": 5, "autoAreaValue": [
    {"id": 1, "tag": "Front Hall", "active": "depth"},
    {"id": 2, "tag": "Kitchen", "active": "depth"},
    {"id": 3, "tag": "Living Room", "active": "normal"}]}}
STATE = {"infoType": 20001, "data": {"mode": "charge", "elec": 88, "vol": 6, "led": 1,
                                      "workNoisy": "auto", "cleanArea": 4, "cleanTime": 300}}
CONSUMABLES = {"infoType": 21015, "data": {"filter": 144000, "sideBrush": 144000,
                                           "mainBrush": 144000, "sensors": 0}}
WIFI = {"infoType": 21019, "data": {"staId": "HomeNet", "staSignal": 72, "staIp": "192.0.2.10",
                                    "staMac": "aa:bb:cc:dd:ee:ff"}}
VERSION = {"infoType": 21018, "data": {"version": "0.3.6", "fullversion": "0.3.6.1", "mcu": "1.2"}}
ENTRY_DATA = {"host": "192.0.2.10", "device_id": "dev123", "local_key": "k" * 16,
              "serial": "SN1", "user_id": "UID1", "version": "3.3"}


class FakeClient(T1Client):
    """Real client logic, no socket: payloads are fed in by the test."""

    def start(self):
        self.connected = True
        for p in (STATE, ROOMS, CONSUMABLES, WIFI, VERSION):
            self.handle_payload(p)

    def stop(self):
        self.connected = False

    def sent(self):
        out = []
        while not self._cmds.empty():
            out.append(self._cmds.get_nowait())
        return out


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def fake_client():
    holder = {}

    def factory(*args, **kwargs):
        holder["client"] = FakeClient(*args, **kwargs)
        return holder["client"]

    with patch("custom_components.lenovo_t1.T1Client", side_effect=factory):
        yield holder
