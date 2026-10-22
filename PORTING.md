# Porting the verified protocol back into the HA component

`ha-component/custom_components/lenovo_t1` (v0.1.0) predates the live testing. `tools/commands.py` is the
reference implementation: it holds the verified message formats. Changes needed:

## Must fix
1. **Encoding**: send `base64(json)` on DP 102, not hex. (`client.py` already patched; confirm.)
2. **Start / rooms**: replace the old batch with the verified one in `tools/commands.py`
   (`start_clean`, `clean_rooms`): `30000` = [`21023` activate, `21005` `reAppointClean`/`sweepOnly`].
   Drop `setPathType` (the vacuum rejects it). Needs the real `mapId` from a `21004` reply; with `mapId -1`
   the activation is ignored.
3. **Fan names**: Low / Medium / High / Off = `quiet` / `auto` / `strong` / `mop` (patched in `vacuum.py`).
4. **State mapping**: `mode` → activity: `sweep` cleaning, `pause`/`findchargerpause` paused, `backcharge`
   returning, `charge`/`idle` docked, `fault` error, `rfctrl` manual driving. Do not rely on `subMode`
   (`total`, `smart`, `smartArea`, `null` vary by who started the clean).
5. **Faults**: `20003` with `type: error` and a negative `code` is a fault (0 = cleared); `type: message`
   (e.g. 6023 done, 6052/6136 relocating) is informational. Lookup table is in `docs/PROTOCOL.md`.
6. Remove mop/water/dust-station entities if any; they do not apply to this model.

## Add
- Room clean service: `lenovo_t1.clean_rooms` with an ordered list of room ids/names (from `21004`
  `autoAreaValue`: `id` and `tag`). Order sent = order cleaned.
- Consumable sensors (remaining h = (720000 − counter)/3600) and reset buttons (`21016`, zero one field, keep
  the other three from a fresh `21015`).
- Diagnostics: firmware (`21018`), Wi-Fi signal (`21019`), fault lists (`21010`).
- Poll `20001` (bare) when idle; no need to poll while moving.
- Optional: remote-control service (`3005`–`3008`, one message per 0.25 s, ~3 messages start-up).

## Rules
- One connection at a time is safest; disable the old integration before running `tools/repl.py`.
- Secrets in `secrets.yaml` only. Device ID, local key, `sn`, `userId`.
- Do not re-pair or reset the vacuum.
