"""Lenovo T1 Pro robot vacuum over the local Tuya protocol."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_SERIAL,
    CONF_USER_ID,
    CONF_VERSION,
    DEFAULT_VERSION,
    DOMAIN,
    ROOM_SLOTS,
)
from .rooms import RoomQueue
from .t1api import T1Client

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.VACUUM, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.BUTTON,
             Platform.NUMBER]
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
                      d[CONF_USER_ID], float(d.get(CONF_VERSION, DEFAULT_VERSION)))
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
    if any(rid > ROOM_SLOTS for rid in client.room_ids()):
        _LOGGER.warning("The map has rooms with an id above %s; those rooms cannot be selected "
                        "from the room switches", ROOM_SLOTS)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: T1ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: T1ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await hass.async_add_executor_job(entry.runtime_data.client.stop)
    return ok
