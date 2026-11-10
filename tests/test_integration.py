import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lenovo_t1.const import DOMAIN

from .conftest import ENTRY_DATA


async def _setup(hass: HomeAssistant, fake_client):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="dev123", title="Lenovo T1 Pro")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, fake_client["client"]


def _eid(hass, domain, unique_suffix):
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"dev123_{unique_suffix}")


async def test_entities_created(hass, fake_client):
    await _setup(hass, fake_client)
    assert hass.states.get("vacuum.lenovo_t1_pro").state == "docked"
    assert hass.states.get("sensor.lenovo_t1_pro_battery").state == "88"
    assert hass.states.get("number.lenovo_t1_pro_volume").state == "6"
    assert hass.states.get("switch.lenovo_t1_pro_indicator_light").state == "on"
    assert hass.states.get("vacuum.lenovo_t1_pro").attributes["fan_speed"] == "Medium"


async def test_room_slots_enabled_only_for_existing_rooms(hass, fake_client):
    await _setup(hass, fake_client)
    reg = er.async_get(hass)
    for slot in range(1, 11):
        ent = reg.async_get(_eid(hass, "switch", f"room_{slot}"))
        assert ent is not None
        assert (ent.disabled_by is None) == (slot <= 3), slot
    assert hass.states.get("switch.lenovo_t1_pro_kitchen").attributes["passes"] == "double"
    assert hass.states.get("switch.lenovo_t1_pro_living_room").attributes["passes"] == "single"


async def test_queue_order_is_toggle_order_and_button_cleans(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    client.sent()
    for name in ("living_room", "front_hall"):
        await hass.services.async_call("switch", "turn_on",
                                       {"entity_id": f"switch.lenovo_t1_pro_{name}"}, blocking=True)
    assert hass.states.get("sensor.lenovo_t1_pro_room_queue").state == "Living Room, Front Hall"
    assert hass.states.get("switch.lenovo_t1_pro_living_room").attributes["queue_position"] == 1

    await hass.services.async_call("button", "press",
                                   {"entity_id": "button.lenovo_t1_pro_clean_queued_rooms"}, blocking=True)
    sent = client.sent()
    batch = [m for m in sent if m["infoType"] == 30000][0]
    assert batch["data"]["cmds"][0]["data"]["segmentId"] == [3, 1]
    assert batch["data"]["cmds"][0]["data"]["mapId"] == 5
    assert hass.states.get("sensor.lenovo_t1_pro_room_queue").state == "empty"
    assert hass.states.get("switch.lenovo_t1_pro_living_room").state == "off"


async def test_empty_queue_is_an_error(hass, fake_client):
    await _setup(hass, fake_client)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("button", "press",
                                       {"entity_id": "button.lenovo_t1_pro_clean_queued_rooms"}, blocking=True)


async def test_clear_queue(hass, fake_client):
    await _setup(hass, fake_client)
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.lenovo_t1_pro_kitchen"}, blocking=True)
    await hass.services.async_call("button", "press",
                                   {"entity_id": "button.lenovo_t1_pro_clear_room_queue"}, blocking=True)
    assert hass.states.get("switch.lenovo_t1_pro_kitchen").state == "off"


async def test_clean_rooms_service_by_name_number_and_renamed_entity(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    client.sent()
    reg = er.async_get(hass)
    reg.async_update_entity(_eid(hass, "switch", "room_1"), name="Hallway")
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "clean_rooms",
                                   {"entity_id": "vacuum.lenovo_t1_pro", "rooms": ["kitchen", 3, "Hallway"]},
                                   blocking=True)
    batch = [m for m in client.sent() if m["infoType"] == 30000][0]
    assert batch["data"]["cmds"][0]["data"]["segmentId"] == [2, 3, 1]


async def test_clean_rooms_unknown_room(hass, fake_client):
    await _setup(hass, fake_client)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "clean_rooms",
                                       {"entity_id": "vacuum.lenovo_t1_pro", "rooms": ["Garage"]}, blocking=True)


async def test_vacuum_controls(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    client.sent()
    await hass.services.async_call("vacuum", "start", {"entity_id": "vacuum.lenovo_t1_pro"}, blocking=True)
    assert [m["infoType"] for m in client.sent()] == [30000]
    await hass.services.async_call("vacuum", "set_fan_speed",
                                   {"entity_id": "vacuum.lenovo_t1_pro", "fan_speed": "High"}, blocking=True)
    assert client.sent()[0]["data"]["cmd"] == "strong"
    client.handle_payload({"infoType": 20001, "data": {"mode": "pause"}})
    await hass.services.async_call("vacuum", "start", {"entity_id": "vacuum.lenovo_t1_pro"}, blocking=True)
    assert client.sent()[0]["data"]["cmd"] == "continue"


async def test_fault_sensor(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    client.handle_payload({"infoType": 20003, "data": {"msg": {"code": -2406}, "type": "error"}})
    await hass.async_block_till_done()
    s = hass.states.get("sensor.lenovo_t1_pro_fault")
    assert s.state == "dust box missing" and s.attributes["code"] == -2406


async def test_consumables(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    assert float(hass.states.get("sensor.lenovo_t1_pro_filter_life_remaining").state) == 160.0
    client.sent()
    await hass.services.async_call("button", "press",
                                   {"entity_id": "button.lenovo_t1_pro_reset_filter_life"}, blocking=True)
    msg = [m for m in client.sent() if m["infoType"] == 21016][0]
    assert msg["data"]["filter"] == 0 and msg["data"]["mainBrush"] == 144000


async def test_unavailable_when_disconnected(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    client.connected = False
    client._notify()
    await hass.async_block_till_done()
    assert hass.states.get("vacuum.lenovo_t1_pro").state == "unavailable"


async def test_unload(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert client.connected is False


async def test_diagnostics_redacts(hass, hass_client, fake_client):
    from custom_components.lenovo_t1.diagnostics import async_get_config_entry_diagnostics
    entry, client = await _setup(hass, fake_client)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    blob = str(diag)
    for secret in ("192.0.2.10", "dev123", "kkkkkkkkkkkkkkkk", "SN1", "UID1", "HomeNet", "aa:bb:cc:dd:ee:ff"):
        assert secret not in blob


async def test_manual_control_buttons(hass, fake_client):
    from custom_components.lenovo_t1.t1api.client import DriveBurst
    entry, client = await _setup(hass, fake_client)
    client.sent()
    for name, code in (("drive_forward", 3005), ("drive_back", 3006), ("turn_left", 3007), ("turn_right", 3008)):
        await hass.services.async_call("button", "press",
                                       {"entity_id": f"button.lenovo_t1_pro_{name}"}, blocking=True)
        assert client._cmds.get_nowait() == DriveBurst(code, 6)


async def test_drive_service(hass, fake_client):
    from custom_components.lenovo_t1.t1api.client import DriveBurst
    entry, client = await _setup(hass, fake_client)
    client.sent()
    await hass.services.async_call(DOMAIN, "drive", {"entity_id": "vacuum.lenovo_t1_pro",
                                                     "direction": "left", "duration": 2}, blocking=True)
    assert client._cmds.get_nowait() == DriveBurst(3007, 8)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "drive", {"entity_id": "vacuum.lenovo_t1_pro",
                                                         "direction": "sideways"}, blocking=True)


async def test_cancel_dock_button_and_vacuum_stop(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    client.sent()
    await hass.services.async_call("button", "press",
                                   {"entity_id": "button.lenovo_t1_pro_cancel_dock"}, blocking=True)
    m = client.sent()[0]
    assert m["infoType"] == 21012 and m["data"]["cmd"] == "stop"
    await hass.services.async_call("vacuum", "stop", {"entity_id": "vacuum.lenovo_t1_pro"}, blocking=True)
    m = client.sent()[0]
    assert m["infoType"] == 21017 and m["data"]["cmd"] == "stop"


async def test_wifi_and_firmware_sensors(hass, fake_client):
    await _setup(hass, fake_client)
    assert hass.states.get("sensor.lenovo_t1_pro_wi_fi_network").state == "HomeNet"
    sig = hass.states.get("sensor.lenovo_t1_pro_wi_fi_signal")
    assert sig.state == "72" and "device_class" not in sig.attributes
    fw = hass.states.get("sensor.lenovo_t1_pro_firmware_version")
    assert fw.state == "0.3.6" and fw.attributes["mcu"] == "1.2"
    reg = er.async_get(hass)
    for key in ("wifi_ip", "wifi_mac"):  # identifiers stay off unless wanted
        assert reg.async_get(_eid(hass, "sensor", key)).disabled_by is not None


async def test_sensors_consumable_and_reset(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    assert float(hass.states.get("sensor.lenovo_t1_pro_sensors_life_remaining").state) == 200.0
    client.sent()
    await hass.services.async_call("button", "press",
                                   {"entity_id": "button.lenovo_t1_pro_reset_sensors_life"}, blocking=True)
    msg = [m for m in client.sent() if m["infoType"] == 21016][0]
    assert msg["data"]["sensors"] == 0 and msg["data"]["filter"] == 144000


async def test_problem_sensor(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    assert hass.states.get("binary_sensor.lenovo_t1_pro_problem").state == "off"
    client.handle_payload({"infoType": 20003, "data": {"msg": {"code": -2406}, "type": "error"}})
    await hass.async_block_till_done()
    s = hass.states.get("binary_sensor.lenovo_t1_pro_problem")
    assert s.state == "on" and s.attributes["fault"] == "dust box missing"
    assert s.attributes["device_class"] == "problem"


async def test_mode_sensor_disabled_by_default(hass, fake_client):
    await _setup(hass, fake_client)
    assert er.async_get(hass).async_get(_eid(hass, "sensor", "mode")).disabled_by is not None


async def test_area_and_time_round_and_hold(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    client.handle_payload({"infoType": 20001, "data": {"mode": "sweep", "cleanArea": 11, "cleanTime": 1785}})
    client.handle_payload({"infoType": 20001, "data": {"mode": "charge", "cleanArea": 0, "cleanTime": 0}})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.lenovo_t1_pro_cleaned_area").state == "11"
    s = hass.states.get("sensor.lenovo_t1_pro_cleaning_time")
    assert s.state == "30" and s.attributes["unit_of_measurement"] == "min"


async def test_mode_sensor_keeps_raw_state_and_translates_remote_control(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    reg = er.async_get(hass)
    reg.async_update_entity(_eid(hass, "sensor", "mode"), disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    client = fake_client["client"]
    eid = _eid(hass, "sensor", "mode")
    client.handle_payload({"infoType": 20001, "data": {"mode": "rfctrl"}})
    await hass.async_block_till_done()
    s = hass.states.get(eid)
    assert s.state == "rfctrl" and s.attributes["device_class"] == "enum"
    assert s.attributes["raw_state"] == "rfctrl" and s.attributes["friendly_state"] == "Remote control"
    v = hass.states.get("vacuum.lenovo_t1_pro")
    assert v.attributes["raw_state"] == "rfctrl" and v.attributes["friendly_state"] == "Remote control"
    assert v.state == "cleaning"
    client.handle_payload({"infoType": 20001, "data": {"mode": "somethingnew"}})
    await hass.async_block_till_done()
    s = hass.states.get(eid)
    assert s.state == "unknown" and s.attributes["raw_state"] == "somethingnew"
    assert s.attributes["friendly_state"] == "somethingnew"


def test_mode_translation_text():
    import json
    from pathlib import Path
    base = Path(__file__).parent.parent / "custom_components" / "lenovo_t1"
    from custom_components.lenovo_t1.const import MODE_NAMES
    from custom_components.lenovo_t1.sensor import MODES
    for name in ("strings.json", "translations/en.json"):
        states = json.loads((base / name).read_text())["entity"]["sensor"]["mode"]["state"]
        assert states["rfctrl"] == "Remote control" and states["backcharge"] == "Returning to dock"
        assert all(v and v != k for k, v in states.items())
        assert set(states) == set(MODES)
        assert states == MODE_NAMES


async def test_overview_sensors(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    assert hass.states.get("sensor.lenovo_t1_pro_map_id").state == "5"
    rooms = hass.states.get("sensor.lenovo_t1_pro_rooms")
    assert rooms.state == "3"
    assert rooms.attributes["rooms"][1] == {"id": 2, "name": "Kitchen", "passes": "double"}
    assert hass.states.get("binary_sensor.lenovo_t1_pro_map_saved").state == "on"
    assert hass.states.get("binary_sensor.lenovo_t1_pro_connection").state == "on"
    assert hass.states.get("sensor.lenovo_t1_pro_reconnects").state == "0"
    assert hass.states.get("sensor.lenovo_t1_pro_last_event").state == "unknown"
    client.handle_payload({"infoType": 20003, "data": {"msg": {"code": 6023}, "type": "message"}})
    client.handle_payload({"infoType": 20001, "data": {"subMode": "smartArea"}})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.lenovo_t1_pro_last_event").state == "cleaning completed"
    assert hass.states.get("sensor.lenovo_t1_pro_clean_type").state == "smartArea"


async def test_connection_sensor_stays_available_when_offline(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    client.connected = False
    client._notify()
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.lenovo_t1_pro_connection").state == "off"
    assert hass.states.get("sensor.lenovo_t1_pro_battery").state == "unavailable"


async def test_no_map_shows_unknown_map_id(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    client.handle_payload({"infoType": 21004, "data": {"mapId": -1, "autoAreaValue": []}})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.lenovo_t1_pro_map_id").state == "unknown"
    assert hass.states.get("binary_sensor.lenovo_t1_pro_map_saved").state == "off"
    assert hass.states.get("sensor.lenovo_t1_pro_rooms").state == "0"


async def test_event_entity_fires_for_messages_and_faults(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    eid = _eid(hass, "event", "messages")
    state = hass.states.get(eid)
    assert state is not None and "cleaning_completed" in state.attributes["event_types"]
    client.handle_payload({"infoType": 20003, "data": {"msg": {"code": 6023}, "type": "message"}})
    await hass.async_block_till_done()
    s = hass.states.get(eid)
    assert s.attributes["event_type"] == "cleaning_completed" and s.attributes["code"] == 6023
    client.handle_payload({"infoType": 20003, "data": {"msg": {"code": -2406}, "type": "error"}})
    await hass.async_block_till_done()
    assert hass.states.get(eid).attributes["event_type"] == "fault"
    client.handle_payload({"infoType": 20003, "data": {"msg": {"code": 99999}, "type": "message"}})
    await hass.async_block_till_done()
    assert hass.states.get(eid).attributes["event_type"] == "unknown_message"


async def test_device_gets_firmware_version(hass, fake_client):
    from homeassistant.helpers import device_registry as dr
    await _setup(hass, fake_client)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "dev123")})
    assert device.sw_version == "0.3.6.1"


async def test_no_map_repair_issue_appears_and_clears(hass, fake_client):
    from homeassistant.helpers import issue_registry as ir
    entry, client = await _setup(hass, fake_client)
    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, f"no_map_{entry.entry_id}") is None
    client.handle_payload({"infoType": 21004, "data": {"mapId": -1, "autoAreaValue": []}})
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, f"no_map_{entry.entry_id}") is not None
    client.handle_payload({"infoType": 21004, "data": {"mapId": 5, "autoAreaValue": [{"id": 1, "tag": "A"}]}})
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, f"no_map_{entry.entry_id}") is None


async def test_double_pass_switch_is_off_by_default_and_saves_the_room_list(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    reg = er.async_get(hass)
    ent = reg.async_get(_eid(hass, "switch", "passes_3"))
    assert ent is not None and ent.disabled_by is not None
    reg.async_update_entity(ent.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    client = fake_client["client"]
    assert hass.states.get(ent.entity_id).state == "off"  # Living Room: single pass
    client.sent()
    await hass.services.async_call("switch", "turn_on", {"entity_id": ent.entity_id}, blocking=True)
    sent = client.sent()
    save = [m for m in sent if m["infoType"] == 21003][0]["data"]
    assert save["mapId"] == 5
    assert [r["active"] for r in save["autoAreaValue"]] == ["depth", "depth", "depth"]
    assert [r["tag"] for r in save["autoAreaValue"]] == ["Front Hall", "Kitchen", "Living Room"]
    assert sent[-1]["infoType"] == 21004


async def test_spot_clean_button_off_by_default(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    ent = er.async_get(hass).async_get(_eid(hass, "button", "spot_clean"))
    assert ent is not None and ent.disabled_by is not None


async def test_clean_services(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    client.sent()
    vac = {"entity_id": "vacuum.lenovo_t1_pro"}
    await hass.services.async_call(DOMAIN, "clean", {**vac, "mode": "deep"}, blocking=True)
    assert client.sent()[0]["data"]["cmds"][1]["data"]["cleanTimes"] == "depth"
    await hass.services.async_call(DOMAIN, "clean", {**vac, "mode": "along_wall"}, blocking=True)
    assert client.sent()[0]["data"]["mode"] == "alongWallClean"
    await hass.services.async_call(DOMAIN, "clean_zone", {**vac, "x1": 0, "y1": 0, "x2": 1, "y2": 2}, blocking=True)
    assert client.sent()[0]["data"]["cmds"][0]["data"]["extraAreas"][0]["vertexs"][2] == [1, 2]
    await hass.services.async_call(DOMAIN, "go_to_point", {**vac, "x": 1.5, "y": 2}, blocking=True)
    assert client.sent()[0]["data"]["point"] == [1.5, 2]
    client.handle_payload({"infoType": 21004, "data": {"mapId": -1, "autoAreaValue": []}})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "clean", vac, blocking=True)


async def test_totals_count_finished_cleans_and_restore(hass, fake_client):
    from homeassistant.core import State
    from pytest_homeassistant_custom_component.common import mock_restore_cache
    mock_restore_cache(hass, [State("sensor.lenovo_t1_pro_total_cleaned_area", "100.0"),
                              State("sensor.lenovo_t1_pro_cleans_completed", "7")])
    entry, client = await _setup(hass, fake_client)
    area = "sensor.lenovo_t1_pro_total_cleaned_area"
    assert hass.states.get(area).state == "100.0"
    for mode, a, t in (("sweep", 10, 600), ("backcharge", 12, 720), ("charge", 0, 0)):
        client.handle_payload({"infoType": 20001, "data": {"mode": mode, "cleanArea": a, "cleanTime": t}})
    await hass.async_block_till_done()
    assert hass.states.get(area).state == "112.0"
    assert hass.states.get("sensor.lenovo_t1_pro_cleans_completed").state == "8"
    assert hass.states.get("sensor.lenovo_t1_pro_total_cleaning_time").state == "12"


async def test_position_sensor_off_by_default(hass, fake_client):
    await _setup(hass, fake_client)
    ent = er.async_get(hass).async_get(_eid(hass, "sensor", "position"))
    assert ent is not None and ent.disabled_by is not None


async def test_room_slots_option_changes_switch_count(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"room_slots": 12, "state_poll": 20, "slow_poll": 120})
    await hass.async_block_till_done()
    assert entry.options == {"room_slots": 12, "state_poll": 20, "slow_poll": 120}
    assert _eid(hass, "switch", "room_12") is not None and _eid(hass, "switch", "room_13") is None


async def test_auth_failure_starts_reauth(hass, fake_client):
    entry, client = await _setup(hass, fake_client)
    client.auth_errors = 3
    client._notify()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"]["source"] == "reauth" for f in flows)
