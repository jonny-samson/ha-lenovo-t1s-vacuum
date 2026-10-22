"""DP-102 message envelope + encode/decode helpers.

Wire shape (CONFIRMED from decompiled app source):
    {"connectionType":0|1,"dInfo":{"ts":...,"userId":...},
     "data":{...,"sn":...,"userId":...},"infoType":N,"isShowTip":false}

Outgoing writes and incoming reads both carry this JSON base64-encoded in
Tuya DP 102 — the HA integration previously hex-encoded outgoing writes
while decoding incoming ones as base64, a mismatch suspected of causing
every outgoing command to transmit cleanly but have no effect. This module
is base64 both ways, matching the decompiled app.
"""
from __future__ import annotations

import base64
import json
import time

from config import SERIAL, USER_ID

DP_RAW = "102"


def build(info_type: int, connection_type: int = 1, **data) -> dict:
    data.update(sn=SERIAL, userId=USER_ID)
    return {
        "connectionType": connection_type,
        "dInfo": {"ts": str(int(time.time() * 1000)), "userId": USER_ID},
        "data": data,
        "infoType": info_type,
        "isShowTip": False,
    }


def encode(msg: dict) -> str:
    return base64.b64encode(json.dumps(msg, separators=(",", ":")).encode()).decode()


def decode(value: str) -> dict:
    return json.loads(base64.b64decode(value))
