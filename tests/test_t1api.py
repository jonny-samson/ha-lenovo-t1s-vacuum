"""Tests for the HA-free library: message formats and state handling."""
import pytest
from t1api import FAN_MODES, T1Client
from t1api.client import DriveBurst
from t1api.commands import Commands
from t1api.protocol import Envelope, decode, encode

CONSUMABLES = {"filter": 100000, "sideBrush": 200000, "mainBrush": 300000, "sensors": 0}


@pytest.fixture
def cmds():
    return Commands(Envelope("SN", "UID"))


@pytest.fixture
def client():
    return T1Client("192.0.2.1", "dev", "k" * 16, "SN", "UID")


def test_roundtrip_is_base64_json(cmds):
    msg = cmds.pause()
    assert decode(encode(msg)) == msg
    assert encode(msg).isascii() and "{" not in encode(msg)


def test_envelope_shape(cmds):
    msg = cmds.locate_start()
    assert msg["infoType"] == 21020 and msg["data"]["ctrlCode"] == 3010
    assert msg["data"]["sn"] == "SN" and msg["data"]["userId"] == "UID"
    assert msg["connectionType"] == 0 and msg["isShowTip"] is False


def test_room_clean_batch_order_and_shape(cmds):
    msg = cmds.clean_rooms([3, 1], 42)
    assert msg["infoType"] == 30000
    activate, sweep = msg["data"]["cmds"]
    assert activate["infoType"] == 21023
    assert activate["data"]["segmentId"] == [3, 1] and activate["data"]["cleanId"] == [-3]
    assert activate["data"]["mapId"] == 42 and activate["data"]["extraAreas"] == []
    assert sweep["infoType"] == 21005
    assert sweep["data"]["mode"] == "reAppointClean" and sweep["data"]["cleanMode"] == "sweepOnly"


def test_total_clean_has_no_setpathtype(cmds):
    msg = cmds.start_clean(42)
    assert [c["infoType"] for c in msg["data"]["cmds"]] == [21023, 21005]
    assert msg["data"]["cmds"][0]["data"]["cleanId"] == [-1, -3]


def test_no_rooms_rejected(cmds):
    with pytest.raises(ValueError):
        cmds.clean_rooms([], 42)


def test_fan_modes(cmds):
    assert FAN_MODES == {"Low": "quiet", "Medium": "auto", "High": "strong", "Off": "mop"}
    assert cmds.set_suction("strong")["infoType"] == 21022
    with pytest.raises(ValueError):
        cmds.set_suction("turbo")


def test_volume_clamped(cmds):
    assert cmds.set_volume(99)["data"]["value"] == 10
    assert cmds.set_volume(-3)["data"]["value"] == 0


def test_reset_consumable_keeps_others(cmds):
    msg = cmds.reset_consumable("filter", CONSUMABLES)
    assert msg["infoType"] == 21016
    d = msg["data"]
    assert d["filter"] == 0 and d["sideBrush"] == 200000 and d["mainBrush"] == 300000


def test_reset_requires_fresh_read(cmds):
    with pytest.raises(ValueError):
        cmds.reset_consumable("filter", {})
    with pytest.raises(ValueError):
        cmds.reset_consumable("bogus", CONSUMABLES)


def test_state_and_activity(client):
    client.handle_payload({"infoType": 20001, "data": {"mode": "sweep", "elec": 70, "vol": 4,
                                                       "led": 0, "workNoisy": "strong"}})
    assert client.activity == "cleaning" and client.battery == 70
    assert client.volume == 4 and client.light is False and client.fan_speed == "High"
    for mode, act in [("pause", "paused"), ("findchargerpause", "paused"), ("backcharge", "returning"),
                      ("charge", "docked"), ("fullcharge", "docked"), ("idle", "idle"), ("fault", "error"),
                      ("rfctrl", "cleaning")]:
        client.handle_payload({"infoType": 20001, "data": {"mode": mode}})
        assert client.activity == act


def test_noisy_keys_do_not_notify(client):
    seen = []
    client.add_listener(lambda: seen.append(1))
    client.handle_payload({"infoType": 20001, "data": {"mode": "sweep", "pos": [1, 2]}})
    n = len(seen)
    client.handle_payload({"infoType": 20001, "data": {"mode": "sweep", "pos": [3, 4], "phi": 9}})
    assert len(seen) == n


def test_rooms_and_map(client):
    assert not client.has_map
    client.handle_payload({"infoType": 21004, "data": {"mapId": 5, "autoAreaValue": [
        {"id": 1, "tag": "Hall", "active": "depth"}, {"id": 2, "tag": "Kitchen", "active": "normal"}]}})
    assert client.has_map and client.room_ids() == [1, 2] and client.room(2)["tag"] == "Kitchen"
    client.clean_rooms([2, 1])
    sent = client._cmds.get_nowait()
    assert sent["data"]["cmds"][0]["data"]["segmentId"] == [2, 1]
    with pytest.raises(ValueError):
        client.clean_rooms([9])


def test_no_map_blocks_clean(client):
    with pytest.raises(ValueError):
        client.start_clean()


def test_map_id_none_is_not_a_map(client):
    client.handle_payload({"infoType": 21004, "data": {"mapId": -1, "autoAreaValue": []}})
    assert not client.has_map


def test_faults(client):
    client.handle_payload({"infoType": 20003, "data": {"msg": {"code": -2601}, "type": "error"}})
    assert client.fault == -2601 and client.fault_text == "start on the ground"
    client.handle_payload({"infoType": 20003, "data": {"msg": {"code": 6023}, "type": "message"}})
    assert client.fault == -2601 and client.last_message == 6023
    client.handle_payload({"infoType": 20003, "data": {"msg": {"code": 0}, "type": "error"}})
    assert client.fault == 0 and client.fault_text == "ok"


def test_consumable_hours(client):
    client.handle_payload({"infoType": 21015, "data": {**CONSUMABLES, "battery": 1}})
    assert client.consumable_hours("filter") == round((720000 - 100000) / 3600, 1)
    assert client.consumable_hours("nope") is None


def test_drive_commands(cmds):
    from t1api import DRIVE_CODES
    assert DRIVE_CODES == {"forward": 3005, "back": 3006, "left": 3007, "right": 3008}
    msg = cmds.drive(3007)
    assert msg["infoType"] == 21020 and msg["data"]["ctrlCode"] == 3007 and msg["connectionType"] == 0


def test_drive_burst_queued_and_clamped(client):
    client.drive("forward")
    assert client._cmds.get_nowait() == DriveBurst(3005, 6)
    client.drive("left", 2)
    assert client._cmds.get_nowait() == DriveBurst(3007, 8)
    client.drive("right", 0.01)
    assert client._cmds.get_nowait().count == 1
    client.drive("back", 999)
    assert client._cmds.get_nowait().count == 40
    with pytest.raises(ValueError):
        client.drive("up")


def test_cancel_dock_and_stop_commands(cmds):
    assert cmds.dock_cancel()["data"]["cmd"] == "stop" and cmds.dock_cancel()["infoType"] == 21012
    assert cmds.stop_clean()["data"]["cmd"] == "stop" and cmds.stop_clean()["infoType"] == 21017


def test_wifi_and_firmware_replies(client):
    client.handle_payload({"infoType": 21019, "data": {"staId": "Net", "staSignal": 55, "staIp": "1.2.3.4",
                                                       "staMac": "aa", "other": 1}})
    assert client.wifi == {"staId": "Net", "staSignal": 55, "staIp": "1.2.3.4", "staMac": "aa"}
    client.handle_payload({"infoType": 21018, "data": {"version": "0.3.6", "fullversion": "0.3.6.1", "mcu": "2"}})
    assert client.firmware["version"] == "0.3.6" and client.firmware["mcu"] == "2"


def test_queries_for_wifi_and_version(cmds):
    assert cmds.query_wifi()["infoType"] == 21019
    assert cmds.query_version()["infoType"] == 21018


def test_connect_sends_only_the_state_query(client):
    client.refresh()
    assert [m["infoType"] for m in iter(lambda: client._cmds.get_nowait() if not client._cmds.empty() else None,
                                        None)] == [20001]


def test_last_clean_values_are_kept_between_cleans(client):
    def report(**data):
        client.handle_payload({"infoType": 20001, "data": data})
    report(mode="charge", cleanArea=0, cleanTime=0)
    assert client.clean_area == 0
    report(mode="sweep", cleanArea=12, cleanTime=1785)
    report(mode="backcharge", cleanArea=14, cleanTime=1900)
    report(mode="charge", cleanArea=0, cleanTime=0)
    assert client.clean_area == 14 and client.clean_time == 1900
    report(mode="sweep", cleanArea=0, cleanTime=0)
    assert client.clean_area == 0 and client.clean_time == 0
