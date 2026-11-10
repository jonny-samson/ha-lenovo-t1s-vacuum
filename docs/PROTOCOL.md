# Lenovo T1 Pro (com.ldrobot.tys1 v1.9.20) — protocol findings

Sections marked VERIFIED were tested live; the rest comes from the decompiled app only. See the final
'Verified live' table for the working commands.

Source: real (unpacked) dex dumped from the running app via frida-dexdump, decompiled with jadx.
The APK itself is packed (Tencent Legu: libshell-super / libshella); a static decompile of the
file only yields the unpacker stub. All command builders live in
`com.aliyun.iot.ilop.demo.network.socketconnect.SocketPackageManager` (+ `SocketUrl`).
Message envelope (hex-encoded JSON on Tuya DP 102):
`{"connectionType":1,"dInfo":{...},"data":{"sn":..,"userId":..,...},"infoType":N,"isShowTip":false}`

## infoType table (SocketUrl)
| infoType | name | notes |
|---|---|---|
| 20001 | DEVICE_STATUS | state snapshot (mode, subMode, elec, cleanArea, cleanTime) |
| 20002 | MAP | |
| 20003 | NOTIFICATION | fault/info code in data.msg.code |
| 20004 | HISTORY_MAP | |
| 21001 / 21002 | SET / GET_SWEEP_APPOINTMENT | schedules |
| 21003 | SET_AREA | |
| 21004 | GET_AREA | reply carries mapId + room/area list (ids) |
| 21005 | SET_AREA_SWEEP | start clean; data.mode (see below), cleanMode, pathType, areaId[] |
| 21006 | GET_ONLINE_STATE | |
| 21007 / 21008 | SET / GET_CHARGE | |
| 21009 | GET_STATISTICAL_INFORMATION | |
| 21010 | GET_FAULT_DETECTION | |
| 21011 | GET_SWEEP_PATH | |
| 21012 | SET_ROBOT_TO_CHARGE | dock: cmd "start" (also "stop") |
| 21014 | GET_MAP | |
| 21015 | GET_CONSUMABLE | |
| 21016 | SET_CONSUMABLE | data: filter, sideBrush, mainBrush, sensors (ints) |
| 21017 | SET_PAUSE | cmd "pause" / "continue" / "stop" |
| 21018 / 21019 | GET_VERSION / GET_WIFI_INFORMATION | replies: version, fullversion, mcu / staId (SSID), staSignal (0-100, not dBm), staIp, staMac |
| 21020 | CONTROL | data.ctrlCode (see below) |
| 21021 | UPDATA | |
| 21022 | SET_WIND_POWER | cmd quiet / auto / strong / mop |
| 21023 | ACTIVATE_AREA | room/zone selection: mapId, cleanId[], extraAreas[], segmentId[] |
| 21024 | SET_ROBOT | cmd setVolume / setledswitch / setPathType / setWaterPump / ... + value |
| 21025 | BACKUP_MAP | |
| 21027 | SWITCH_VOICE | cmd getVoicePackageInfo / downloadAndApply |
| 21030 | AUTO_AREA | |
| 21031 | MULT_MAPS_CTRL | |
| 21032 | GET_LOCAL_MAPS_DATA | |
| 22001 | SET_CONTROL | |
| 30000 | COMPOUND | data.cmds[] = batch of the above |

## ctrlCode values for infoType 21020 (SocketPackageManager)
CHARGE 3000, SPOT 3001, START_OR_PAUSE 3002, CHANGE_WIND 3003, FORWARD 3005, BACK 3006,
TURN_LEFT 3007, TURN_RIGHT 3008, CHECK_WIFI_STATUS 3009, **FIND_ROBOT_START 3010**,
**FIND_ROBOT_STOP 3011**, CLEAR_DATA 3012, SIG_SET_SPEED 3013 (extra data.params {speed_v, speed_w}).
(3004 is unused in the constants.) Hold-to-drive repeats the code (~16 msgs per hold, 3006 verified live).
So the guessed locate command (21020 / 3010) is CORRECT; the app also sends 3011 to stop it.

## Cleaning modes (21005 data.mode / cleanMode / pathType)
mode: smartClean, depthTotalClean, alongWallClean, appointClean, smartAreaClean, reAppointClean,
areaClean (uses data.areaId[] of selected room ids), givenPoint (data.point [x,y]), totalClean.
cleanMode: sweepOnly | mopOnly | sweepMop. pathType: normal (code 0) | y_word (code 1) | repeat.
cleanTimes: normal | depth.

## Room / area clean (21023 ACTIVATE_AREA, then 21005) — VERIFIED, see 'Verified live' for the working batch
- mapId = current map id (from the 21004 reply `mapId`; -1 means no saved map -> room clean impossible).
- Selected rooms: `cleanId: [<room ids...>, -3]`, `extraAreas: []` (-3 is the terminator/"activate" sentinel).
  "Total clean" = `cleanId: [-1, -3]`.
- Auto-segmented rooms: `segmentId: [..]`, `cleanId: [-3]`, `extraAreas: []`.
- Custom zone: `cleanId: [-3]`, `extraAreas: [{name, id, tag, vertexs, active:"depth", mode:"point"}]`.
- Room ids come from the 21004 (GET_AREA) reply, so a map must exist first.

## Consumables (VERIFIED)
21015 reads {filter, sideBrush, mainBrush, sensors, battery}: run-time counters in SECONDS, life 200 h = 720000 s
(app: remaining = (720000 - counter) / 3600 h; 24% left at 151 h). Reset = 21016 with that one field set to 0 and the
other three left at their current values (read 21015 first). Tested on filter, then restored.

## Fault / notification codes (20003 data.msg.code)
Not in the code: the app downloads a table into SharedPreferences (`code.xml`, 48 entries). They are plain
decimal IDs, NOT a bitmask (0 = no fault). English text:
-2706 radar abnormal; -2705 fan abnormal; -2704 side brush abnormal; -2703 main wheel abnormal;
-2702 main brush abnormal; -2701 battery abnormal; -2607 check cliff sensor; -2606 move out of restricted zone;
-2605 cannot reach specified zone; -2604 firmware upgrade failed; -2603 water amount insufficient;
-2602 water tank missing; -2601 start on the ground; -2502/-2501 start at another location;
-2407 clean dust box and filter; -2406 dust box missing; -2405 dust box full; -2404 radar cover blocked;
-2403 fan problem; -2402 side brush stuck; -2401 main brush stuck; -2309 wall sensor abnormal;
-2308 collision sensor abnormal; -2306 radar stuck; -2305 radar blocked; -2304 place on level ground;
-2302 edge stuck; -2201 main wheel stuck; -2102 power off, low battery; -2101 low battery, going to charge;
5058 fail to recharge; 6023 cleaning completed; 6034 timed cleaning begins; 6052 re-locate;
6096 charged, cleaning continues; 6097 low battery, cannot start; 6105 fail to power off on charging pile;
6126 re-locate failed (restricted zone); 6127 re-locate failed (cannot find dock);
6128 cleaning in progress, timed clean skipped; 6129 battery low, please charge; 6130 partial cleaning ends;
6131 start dust collection; 6132 dust collection complete; 6133 dust bag seems full;
6134 dust bag not in place; 6135 dust collection fault.

## Verified live (local tests, 2026-10-22)
Transport: tinytuya v3.3, DP 102. **Outgoing = base64(JSON)** (not hex; the app SDK takes hex and converts, tinytuya sends as-is).
Replies/state arrive as base64 JSON on DP 102; vacuum answers a bare 20001 even when docked.

| Function | Message |
|---|---|
| Find robot | 21020 ctrlCode 3010 (stop 3011) |
| LED / volume | 21024 cmd setledswitch value 0/1; cmd setVolume value 0-10 |
| Fan | 21022 cmd quiet/auto/strong/mop = Low/Medium/High/Off |
| Pause / resume / dock | 21017 cmd pause/continue; 21012 cmd start (stop cancels dock trip) |
| Total clean | 30000 batch: [21023 cleanId [-1,-3] + mapId, 21005 mode reAppointClean cleanMode sweepOnly]. The app also sends 21024 setPathType 0 first, but the vacuum replies 'fail' to it and cleans fine without; omit it |
| Room clean | 30000 batch: [21023 segmentId [ids] cleanId [-3] mapId extraAreas [], 21005 reAppointClean sweepOnly]; ORDER of segmentId = cleaning order (verified) |
| Rooms / map | 21004 -> autoAreaValue [{id, tag(name), active normal|depth(=2 passes), ...}], mapId. Save = 21003 with mapId + autoAreaValue (rename -> tag; double pass -> active depth). Split/merge = 21030 operate split/merge |
| Remote control | 21020 ctrlCode 3005/3006/3007/3008 every 0.25 s; mode rfctrl; ~7.5 cm (fwd) / ~11 deg (turn) per msg after ~2.7 msg start-up; reverse slower (~3 cm) |
| Dust frequency | 21024 cmd dustCenterFreq value 0 never,1 after 1 sweep,2 after 2,3 after 3 (from app UI; not sent) |

Modes seen: idle, charge, sweep (subMode total|smart|smartArea|null), pause, backcharge, findchargerpause, fault, rfctrl.
20003 notifications: type error (code 0 = cleared) or type message (6023 done, 6052/6136 relocating).
Faults seen live: -2601 off ground, -2406 dust box missing, -2305 radar blocked, -2404 radar cover, -2607 cliff, -2201 main wheel stuck, -2401 main brush stuck.
Total clean via bare 21005 totalClean works only with ~1-2 min delay and no mapId; use the batch above with the real mapId.
This model: no mop, water, schedules (disabled; HA owns scheduling), or emptiable dock.

## Implemented from the app only (not verified live)
These are in the integration, flagged experimental. Formats come from the decompiled app:
- Spot clean: 21020 ctrlCode 3001.
- Deep total clean: the total-clean batch with `cleanTimes: "depth"` added to the 21005 message.
- Along the walls: bare 21005 `mode: alongWallClean, cleanMode: sweepOnly, mapId`.
- Zone clean: the room-clean batch with `extraAreas: [{name, id, tag, active, mode: "point", vertexs: [[x,y] x4]}]`, `cleanId: [-3]`.
- Go to point: bare 21005 `mode: givenPoint, point: [x, y], mapId`.
- Per-room passes: 21003 with the full `autoAreaValue` as last read, one room's `active` changed (`depth` = two passes).
  The 21003 save itself is in the verified table above; changing one room's pass count through it was not re-run.
