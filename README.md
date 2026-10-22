# Lenovo T1 Pro (Proscenic M7 Pro, Tuya OEM `com.ldrobot.tys1`) — local control

Local (LAN) control of the Lenovo Cleaner T1 / T1 Pro robot vacuum over the Tuya 3.3 protocol, for Home Assistant.
Maps stay in the vendor app; everything else is controllable locally. Reverse-engineered from the app and
verified live on the device (October 2026, firmware 0.3.6 / build 1900).

## How the device talks
- Tuya local protocol **v3.3**, TCP 6668, one logical DP: **DP 102 (raw)**. No standard Tuya DPs are used.
- Payload is JSON, **base64-encoded in both directions**. (The app SDK takes hex and converts; tinytuya does
  not, so sending hex does nothing.)
- Envelope: `{"connectionType":0|1,"dInfo":{"ts":..,"userId":..},"data":{..,"sn":..,"userId":..},"infoType":N,"isShowTip":false}`
- The vacuum is silent while docked until asked; a bare `20001` query returns the full state. Once moving it
  reports about twice a second. Local and app connections can coexist when the app is idle.
- Needs: device ID, local key, IP, plus `sn` and `userId` (copy both from any app command or state reply).
  Keep these in secrets, never in the repo. **Never re-pair or reset the vacuum: that changes the local key.**

## What works (all tested live)
Find robot, LED, volume, fan (Low/Medium/High/Off), pause/resume, dock (and cancel), total clean, single and
multi-room clean (cleaned in the order given), room rename and per-room double pass, split/merge rooms,
remote control, state/battery/area/time, consumable counters and reset, 7 fault codes (+ relocate messages),
firmware/Wi-Fi/fault-detection reads. Details and exact messages: `docs/PROTOCOL.md`.

## Not applicable to this model
Mop/water level, dust-station emptying, schedules (HA owns scheduling; the two on-device schedules are disabled).

## Not done / open
- Side brush fault (`-2402`) and the other fault codes in the app's table are untested; only decoded from the app.
- Double pass is stored (`active: depth`) but whether it re-cleans each room twice was not observed.
- `deepClean`/`alongWall` state fields exist, but no command was found/tested to set them; `autoBoost`/`mute` likewise.
- Statistics (`21009`), path (`21011`), map image (`21014`/`20002`) get no reply locally; map geometry is app-only.
- `sensors` consumable life limit unknown (filter/brushes: 200 h).

## Contents
- `docs/PROTOCOL.md` — message reference, modes, fault codes, calibration, what was verified
- `tools/` — standalone Python test harness (`repl.py`) + command builders. `pip install -r requirements.txt`,
  copy `config.example.py` to `config.py` (mode 600), then `python repl.py`. Disable the HA integration first.
- `ha-component/` — custom component `lenovo_t1` (YAML config, tinytuya). **Out of date, see `PORTING.md`.**
