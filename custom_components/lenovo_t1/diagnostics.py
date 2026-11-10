"""Diagnostics with identifiers redacted."""
from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import T1ConfigEntry
from .const import CONF_DEVICE_ID, CONF_LOCAL_KEY, CONF_SERIAL, CONF_USER_ID

TO_REDACT = {CONF_HOST, CONF_DEVICE_ID, CONF_LOCAL_KEY, CONF_SERIAL, CONF_USER_ID,
             "mapId", "map_id", "sn", "userId", "unique_id", "staId", "staIp", "staMac"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: T1ConfigEntry) -> dict:
    client = entry.runtime_data.client
    return async_redact_data({
        "entry": dict(entry.data),
        "connected": client.connected,
        "state": client.state,
        "map_id": client.map_id,
        "rooms": client.rooms,
        "consumables": client.consumables,
        "wifi": client.wifi,
        "firmware": client.firmware,
        "fault": client.fault,
        "position": client.position,
        "rooms_known": client.rooms_known,
        "auth_errors": client.auth_errors,
        "reconnects": client.reconnects,
        "finished": {"cleans": client.finished_cleans, "area": client.finished_area,
                     "seconds": client.finished_seconds},
        "options": dict(entry.options),
        "queue": entry.runtime_data.queue.ids,
    }, TO_REDACT)
