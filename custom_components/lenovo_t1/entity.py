"""Base entity."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from . import T1ConfigEntry
from .const import DOMAIN, MODE_NAMES


class T1Entity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: T1ConfigEntry, key: str) -> None:
        self._entry = entry
        data = entry.runtime_data
        self.client = data.client
        self.queue = data.queue
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="Lenovo",
            model="T1 Pro",
        )

    @property
    def mode_attributes(self) -> dict:
        """`raw_state` is the vacuum's own mode value, `friendly_state` its readable form."""
        mode = self.client.mode
        return {"raw_state": mode, "friendly_state": MODE_NAMES.get(mode, mode)}

    @property
    def available(self) -> bool:
        return self.client.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._entry.runtime_data.signal, self._refresh))

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()
