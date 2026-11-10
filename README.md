# Lenovo T1 Pro robot vacuum for Home Assistant

Local (LAN) control of the Lenovo Cleaner T1 / T1 Pro robot vacuum (Proscenic M7 Pro, Tuya OEM
`com.ldrobot.tys1`) over the Tuya 3.3 protocol. No cloud, no YAML. Install through HACS, set it up in the UI.

Tested on firmware 0.3.6 (build 1900) and Home Assistant 2026.2.

## Install (HACS custom repository)

1. HACS > three-dot menu > **Custom repositories** > add this repo's URL, category **Integration**.
2. Download **Lenovo T1 Pro Vacuum**, then restart Home Assistant.
3. **Settings > Devices & services > Add integration > Lenovo T1 Pro Vacuum**.

## What you need

| Field | Where it comes from |
|---|---|
| IP address | The vacuum's LAN address. Reserve it in your router. |
| Device ID, local key | Tuya IoT platform (the device's `local_key`). |
| Serial (`sn`) and user ID | Copy from any state report or app command (see `docs/PROTOCOL.md`). |

These are stored in Home Assistant's config entry (`.storage`), not in this repo. **Never re-pair or
factory-reset the vacuum:** that changes the local key. The Reconfigure option on the integration page
updates the IP, key or protocol version later.

## Entities

**Vacuum:** start (total clean; resumes if paused), pause, stop, return to dock, locate, fan speed
(Low / Medium / High / Off). State, battery, fault and map status are attributes, including `raw_state`
(the vacuum's own mode, e.g. `rfctrl`) and `friendly_state` (e.g. "Remote control"); the Mode sensor has the same two.
Stop is sent as `21017 stop` and has not been verified on the real device.

**Room queue (10 slots).** Each room on the vacuum's saved map gets a switch named after the room
(`switch.<name>_kitchen`). Slots beyond the rooms you have start **disabled**: enable one in
Settings > Entities when you add a room in the app. Rename any of them in HA like a normal entity.

- Turn rooms **on** to queue them. **The order you switch them on is the order they are cleaned.**
- Press **Clean queued rooms** to start; the queue clears itself. **Clear room queue** empties it.
- **Room queue** sensor shows the order, e.g. `Living Room, Front Hall`.
- Each room switch has attributes `room_id`, `passes` (single/double) and `queue_position`.

**Manual control.** Buttons **Drive forward**, **Drive back**, **Turn left**, **Turn right** each send a
short burst (about 1.5 s: roughly 7.5 cm forward or 11 degrees per step, after a moment to start). Press
again to continue. **Cancel dock** stops a return-to-dock trip. Stay nearby: the vacuum does not avoid
obstacles any differently than in the app. See `lenovo_t1.drive` for longer moves.

**Sensors:** battery, cleaned area (m²) and cleaning time (whole minutes; both keep the last clean's value
until the next one starts), **Fault** (text, code in attributes) and a **Problem** binary sensor that is on
whenever there is a fault, and filter / side brush / main brush / sensors life remaining (hours of 200).
**Diagnostics:** Wi-Fi network, Wi-Fi signal (0-100 quality as the vacuum reports it, not dBm), firmware
version (with the full version and MCU as attributes), and IP and MAC address (disabled by default). The
**Mode** sensor is disabled by default; it shows readable names (e.g. "Remote control"), and its state
keeps the raw value such as `rfctrl`.
**Controls:** volume (0-10), indicator light, find robot, and reset buttons for the filter, side brush, main
brush and sensors life.

**Events and totals.** The **Vacuum message** event entity fires for each message the vacuum sends ("cleaning
completed", re-locate, dust collection...) and when a fault appears or clears: use it as an automation trigger.
**Total cleaned area**, **Total cleaning time** and **Cleans completed** are counted in Home Assistant, because the
vacuum's own statistics do not answer locally. A clean counts when it ends on the dock, and the totals survive
restarts.

**Experimental (not tested on the real vacuum):** formats taken from the vendor app. The **Spot clean** button and
the per-room **double pass** switches are off by default; enable them in Settings > Entities. Turning a double pass
switch on or off saves the room list on the vacuum, the same save the app does. The services
`lenovo_t1.clean` (`mode`: total, deep, along_wall), `lenovo_t1.clean_zone` (`x1`, `y1`, `x2`, `y2` in map
coordinates) and `lenovo_t1.go_to_point` (`x`, `y`) may do nothing or the wrong thing on your vacuum. The
**Position** sensor (off by default) shows the coordinates the vacuum reports, to help pick values for them.

**Options** (Configure on the integration page): number of room slots (default 10) and the polling intervals. If the
vacuum keeps refusing the key, a repair notice and a re-authentication prompt appear. A repair notice also shows while the vacuum has no saved map.

**Overview / health (diagnostic):** Map ID, Rooms (count; the list with names and single/double pass is an
attribute), Map saved, Clean type, Last event (latest message from the vacuum), Reconnects, and a Connection
sensor that stays available while the vacuum is offline.

State, rooms, consumables, Wi-Fi and firmware refresh on their own (every 30 s, 5 min, 10 min, 5 min and
5 min), so there are no manual refresh buttons.

## Service: `lenovo_t1.clean_rooms`

For automations. Rooms are cleaned in the order listed; each item is a room number or a name (the name on
the map, or the name you gave the room's switch):

```yaml
action: lenovo_t1.clean_rooms
target:
  entity_id: vacuum.lenovo_t1_pro
data:
  rooms: ["Kitchen", "Living Room"]
```

## Service: `lenovo_t1.drive`

Manual control from an automation or dashboard. `direction` is `forward`, `back`, `left` or `right`;
`duration` is optional (seconds, default 1.5, maximum 10).

```yaml
action: lenovo_t1.drive
target:
  entity_id: vacuum.lenovo_t1_pro
data:
  direction: left
  duration: 3
```

## Needs a saved map

Room and total cleaning need a map saved in the vendor app (the vacuum ignores them without one).
Map editing, room names and per-room double pass are still done in the app; HA reads them back. The
integration re-reads the room list every five minutes.

## Not applicable / not done

- This model has no mop, water tank or emptiable dock, so none of those entities exist.
- Schedules are left to Home Assistant; the two on-device schedules are not used.
- Not done: side-brush fault (`-2402`) is decoded but untested; the map image and statistics get no local reply.

## Development

```
python3.13 -m venv .venv && . .venv/bin/activate
pip install pytest-homeassistant-custom-component tinytuya ruff
ruff check . && pytest
```

- `custom_components/lenovo_t1/t1api/` is the Home Assistant-free client library (messages, state handling).
  The integration and `tools/repl.py` both use it.
- `tools/` is an interactive REPL for testing against the real vacuum without restarting Home Assistant.
  Copy `tools/config.example.py` to `tools/config.py` (mode 600, git-ignored). Disable the HA integration
  first so only one local connection is open.
- `docs/PROTOCOL.md` documents every verified message, the fault codes and calibration data.
- CI (`.github/workflows/validate.yml`) runs hassfest, HACS validation, ruff and the tests.
