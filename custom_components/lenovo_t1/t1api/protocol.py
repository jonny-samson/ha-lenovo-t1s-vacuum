"""DP-102 message envelope and base64 encode/decode.

Wire shape (verified live):
    {"connectionType":0|1,"dInfo":{"ts":...,"userId":...},
     "data":{...,"sn":...,"userId":...},"infoType":N,"isShowTip":false}

The JSON is base64-encoded in both directions on Tuya DP 102.
"""
from __future__ import annotations

import base64
import json
import time

DP_RAW = "102"


class Envelope:
    """Builds message envelopes for one device (serial + user id)."""

    def __init__(self, serial: str, user_id: str) -> None:
        self._serial = serial
        self._user_id = user_id

    def build(self, info_type: int, connection_type: int = 1, **data) -> dict:
        data.update(sn=self._serial, userId=self._user_id)
        return {
            "connectionType": connection_type,
            "dInfo": {"ts": str(int(time.time() * 1000)), "userId": self._user_id},
            "data": data,
            "infoType": info_type,
            "isShowTip": False,
        }


def encode(msg: dict) -> str:
    return base64.b64encode(json.dumps(msg, separators=(",", ":")).encode()).decode()


def decode(value: str) -> dict:
    return json.loads(base64.b64decode(value))
