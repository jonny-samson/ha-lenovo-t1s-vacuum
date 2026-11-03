import pytest
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
    for secret in ("192.0.2.10", "dev123", "kkkkkkkkkkkkkkkk", "SN1", "UID1"):
        assert secret not in blob
