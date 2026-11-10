"""Lenovo T1 Pro robot vacuum over the local Tuya protocol."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send

from .const import (
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_ROOM_SLOTS,
    CONF_SERIAL,
    CONF_SLOW_POLL,
    CONF_STATE_POLL,
    CONF_USER_ID,
    CONF_VERSION,
    DEFAULT_SLOW_POLL,
    DEFAULT_STATE_POLL,
    DEFAULT_VERSION,
    DOMAIN,
    ROOM_SLOTS,
)
from .rooms import RoomQueue
from .t1api import T1Client

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.VACUUM, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.BUTTON,
             Platform.NUMBER, Platform.EVENT]
FIRST_DATA_TIMEOUT = 10


@dataclass
class T1Data:
    client: T1Client
    queue: RoomQueue
    signal: str


type T1ConfigEntry = ConfigEntry[T1Data]


async def async_setup_entry(hass: HomeAssistant, entry: T1ConfigEntry) -> bool:
    d = entry.data
    client = T1Client(d[CONF_HOST], d[CONF_DEVICE_ID], d[CONF_LOCAL_KEY], d[CONF_SERIAL],
                      d[CONF_USER_ID], float(d.get(CONF_VERSION, DEFAULT_VERSION)),
                      state_poll=entry.options.get(CONF_STATE_POLL, DEFAULT_STATE_POLL),
                      slow_poll=entry.options.get(CONF_SLOW_POLL, DEFAULT_SLOW_POLL))
    signal = f"{DOMAIN}_{entry.entry_id}_update"
    entry.runtime_data = T1Data(client, RoomQueue(), signal)

    def _push() -> None:  # called from the connection thread
        hass.loop.call_soon_threadsafe(async_dispatcher_send, hass, signal)

    client.add_listener(_push)

    first = asyncio.Event()
    client.add_listener(lambda: hass.loop.call_soon_threadsafe(first.set) if client.rooms else None)
    await hass.async_add_executor_job(client.start)
    try:  # entity defaults depend on the rooms, so give the first reply a moment
        await asyncio.wait_for(first.wait(), FIRST_DATA_TIMEOUT)
    except TimeoutError:
        _LOGGER.debug("no room list yet; creating entities anyway")
    slots = room_slots(entry)
    if any(rid > slots for rid in client.room_ids()):
        _LOGGER.warning("The map has rooms with an id above %s; those rooms cannot be selected "
                        "from the room switches (raise the room slots in the integration options)", slots)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def _on_update() -> None:
        _sync(hass, entry)

    entry.async_on_unload(async_dispatcher_connect(hass, signal, _on_update))
    _sync(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


def room_slots(entry: T1ConfigEntry) -> int:
    return entry.options.get(CONF_ROOM_SLOTS, ROOM_SLOTS)


def _sync(hass: HomeAssistant, entry: T1ConfigEntry) -> None:
    """Things that follow the vacuum's state but are not entity state: the device's firmware
    version, the "no saved map" repair, and re-authentication."""
    client = entry.runtime_data.client
    version = client.firmware.get("fullversion") or client.firmware.get("version")
    if version:
        device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.unique_id)})
        if device and device.sw_version != version:
            dr.async_get(hass).async_update_device(device.id, sw_version=version)

    issue_id = f"no_map_{entry.entry_id}"
    if client.connected and client.rooms_known and not client.has_map:
        ir.async_create_issue(hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING,
                              translation_key="no_map")
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)

    if client.auth_failed:
        entry.async_start_reauth(hass)


async def _reload(hass: HomeAssistant, entry: T1ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: T1ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await hass.async_add_executor_job(entry.runtime_data.client.stop)
    return ok
