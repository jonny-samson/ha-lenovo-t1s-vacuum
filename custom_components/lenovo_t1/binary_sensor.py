"""Problem indicator."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import T1ConfigEntry
from .entity import T1Entity


async def async_setup_entry(hass: HomeAssistant, entry: T1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([T1Problem(entry)])


class T1Problem(T1Entity, BinarySensorEntity):
    _attr_name = "Problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "problem")

    @property
    def is_on(self) -> bool:
        return self.client.fault != 0

    @property
    def extra_state_attributes(self) -> dict:
        return {"fault": self.client.fault_text, "code": self.client.fault}
