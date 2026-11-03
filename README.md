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

**Vacuum:** start (total clean; resumes if paused), pause, return to dock, locate, fan speed
(Low / Medium / High / Off). State, battery, fault and map status are attributes.

**Room queue (10 slots).** Each room on the vacuum's saved map gets a switch named after the room
(`switch.<name>_kitchen`). Slots beyond the rooms you have start **disabled**: enable one in
Settings > Entities when you add a room in the app. Rename any of them in HA like a normal entity.

- Turn rooms **on** to queue them. **The order you switch them on is the order they are cleaned.**
- Press **Clean queued rooms** to start; the queue clears itself. **Clear room queue** empties it.
- **Room queue** sensor shows the order, e.g. `Living Room, Front Hall`.
- Each room switch has attributes `room_id`, `passes` (single/double) and `queue_position`.

**Sensors:** battery, cleaned area (m²), cleaning time, fault (text, code in attributes), filter / side
brush / main brush life remaining (hours), and a disabled-by-default raw mode sensor.
**Controls:** volume (0-10), indicator light, find robot, reset filter / side brush / main brush life.

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

## Needs a saved map

Room and total cleaning need a map saved in the vendor app (the vacuum ignores them without one).
Map editing, room names and per-room double pass are still done in the app; HA reads them back. The
integration re-reads the room list every five minutes.

## Not applicable / not done

- This model has no mop, water tank or emptiable dock, so none of those entities exist.
- Schedules are left to Home Assistant; the two on-device schedules are not used.
- Not done: side-brush fault (`-2402`) is decoded but untested; per-room passes are read-only; the
  map image and statistics get no local reply.

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
