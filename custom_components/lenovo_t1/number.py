"""Volume."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import T1ConfigEntry
from .entity import T1Entity


async def async_setup_entry(hass: HomeAssistant, entry: T1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([T1Volume(entry)])


class T1Volume(T1Entity, NumberEntity):
    _attr_name = "Volume"
    _attr_native_min_value = 0
    _attr_native_max_value = 10
    _attr_native_step = 1

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "volume")

    @property
    def native_value(self) -> int | None:
        return self.client.volume

    async def async_set_native_value(self, value: float) -> None:
        await self.hass.async_add_executor_job(self.client.set_volume, int(value))
