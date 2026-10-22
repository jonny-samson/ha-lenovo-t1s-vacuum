#!/usr/bin/env python3
"""Interactive REPL for testing the T1 Pro protocol directly, without going
through Home Assistant's restart cycle. The HA integration (lenovo_t1
config entry) must be disabled first — the device only accepts one local
connection at a time.

Commands:
  state                   query full status
  consumables             query filter/brush/sensor life
  area                    query map id + room list
  locate                  find-robot chirp (auto-stops after 3s)
  stop                    cancel a dock trip
  start                   start total clean
  pause / resume / dock
  vol <0-10>
  led on|off
  fan quiet|auto|strong|mop   (Low / Medium / High / Off)
  reset filter|sideBrush|mainBrush|sensors
  rooms <id,id,...>       clean rooms in the given order (run 'area' first for ids + map id)
  raw <json>              send an arbitrary message envelope
  quit
"""
from __future__ import annotations

import json
import sys
import threading
import time

import commands
from const import INFOTYPE_DEVICE_STATUS, INFOTYPE_GET_AREA, INFOTYPE_GET_CONSUMABLE
from device import T1Device

state: dict = {}
consumables: dict = {}
rooms = None
map_id = -1


def on_message(payload: dict):
    global rooms, map_id
    info_type = payload.get("infoType")
    data = payload.get("data") or {}
    if info_type == INFOTYPE_DEVICE_STATUS and isinstance(data, dict):
        state.update(data)
        if "mapId" in data:
            map_id = data["mapId"]
    elif info_type == INFOTYPE_GET_CONSUMABLE and isinstance(data, dict):
        consumables.update(data)
    elif info_type == INFOTYPE_GET_AREA and isinstance(data, dict):
        rooms = data.get("rooms") or data.get("areaList") or data
        if "mapId" in data:
            map_id = data["mapId"]


def main():
    dev = T1Device(on_message=on_message)
    dev.start()
    print("Connecting... (ctrl-C or 'quit' to exit)")
    time.sleep(2)
    print(__doc__)

    try:
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line in ("quit", "exit"):
                break

            parts = line.split(maxsplit=1)
            cmd, arg = parts[0], (parts[1] if len(parts) > 1 else None)

            try:
                if cmd == "state":
                    dev.send(commands.query_state())
                elif cmd == "consumables":
                    dev.send(commands.query_consumables())
                elif cmd == "area":
                    dev.send(commands.query_rooms())
                elif cmd == "locate":
                    dev.send(commands.locate_start())
                    t = threading.Timer(3.0, lambda: dev.send(commands.locate_stop()))
                    t.daemon = True
                    t.start()
                elif cmd == "start":
                    dev.send(commands.start_clean(map_id=map_id))
                elif cmd == "pause":
                    dev.send(commands.pause())
                elif cmd == "resume":
                    dev.send(commands.resume())
                elif cmd == "dock":
                    dev.send(commands.dock())
                elif cmd == "stop":
                    dev.send(commands.dock_cancel())
                elif cmd == "vol" and arg:
                    dev.send(commands.set_volume(int(arg)))
                elif cmd == "led" and arg:
                    dev.send(commands.set_light(arg == "on"))
                elif cmd == "fan" and arg:
                    dev.send(commands.set_suction(arg))
                elif cmd == "reset" and arg:
                    dev.send(commands.reset_consumable(arg, consumables))
                elif cmd == "rooms" and arg:
                    dev.send(commands.clean_rooms([int(x) for x in arg.split(",")], map_id=map_id))
                elif cmd == "raw" and arg:
                    dev.send(json.loads(arg))
                else:
                    print(f"unknown command or missing argument: {line!r}")
            except Exception as err:  # noqa: BLE001
                print(f"error: {err}")
    finally:
        dev.stop()


if __name__ == "__main__":
    sys.exit(main())
