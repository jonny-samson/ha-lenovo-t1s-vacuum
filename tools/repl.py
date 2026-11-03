#!/usr/bin/env python3
"""Interactive test REPL for the T1 Pro, using the same client as the HA integration.
Disable the HA integration first so only one local connection is open.

Commands:
  state | rooms | consumables      show what the vacuum last reported
  locate                           find-robot chirp (auto-stops after 3 s)
  start                            total clean
  clean <id,id,...>                clean rooms in the given order (see 'rooms')
  pause | resume | dock
  stop                             cancel a dock trip
  vol <0-10>
  led on|off
  fan Low|Medium|High|Off
  reset filter|sideBrush|mainBrush
  raw <json>                       send an arbitrary message envelope
  quit
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "lenovo_t1"))

from config import DEVICE_ID, HOST, LOCAL_KEY, SERIAL, USER_ID, VERSION  # noqa: E402
from t1api import FAN_MODES, T1Client  # noqa: E402


def main() -> int:
    client = T1Client(HOST, DEVICE_ID, LOCAL_KEY, SERIAL, USER_ID, VERSION)
    client.start()
    print("Connecting...")
    for _ in range(40):
        if client.last_report:
            break
        time.sleep(0.25)
    print("connected" if client.connected else "not connected yet")
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
            cmd, _, arg = line.partition(" ")
            try:
                if cmd == "state":
                    print(client.activity, client.state)
                elif cmd == "rooms":
                    print("map saved:", client.has_map)
                    for r in client.rooms:
                        print(f"  {r.get('id')}: {r.get('tag') or '(unnamed)'} ({r.get('active')})")
                elif cmd == "consumables":
                    print({k: f"{client.consumable_hours(k)} h left" for k in client.consumables})
                elif cmd == "locate":
                    client.locate()
                elif cmd == "start":
                    client.start_clean()
                elif cmd == "clean" and arg:
                    client.clean_rooms([int(x) for x in arg.split(",")])
                elif cmd == "pause":
                    client.pause()
                elif cmd == "resume":
                    client.resume()
                elif cmd == "dock":
                    client.dock()
                elif cmd == "stop":
                    client.send(client.commands.dock_cancel())
                elif cmd == "vol" and arg:
                    client.set_volume(int(arg))
                elif cmd == "led" and arg:
                    client.set_light(arg == "on")
                elif cmd == "fan" and arg in FAN_MODES:
                    client.set_suction(FAN_MODES[arg])
                elif cmd == "reset" and arg:
                    client.reset_consumable(arg)
                elif cmd == "raw" and arg:
                    client.send(json.loads(arg))
                else:
                    print(f"unknown command or missing argument: {line!r}")
            except Exception as err:  # noqa: BLE001
                print(f"error: {err}")
    finally:
        client.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
