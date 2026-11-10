"""Problem indicator."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import T1ConfigEntry
from .entity import T1Entity


async def async_setup_entry(hass: HomeAssistant, entry: T1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([T1Problem(entry), T1Connection(entry), T1MapSaved(entry)])


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


class T1Connection(T1Entity, BinarySensorEntity):
    """Whether the vacuum is answering. Stays available when it is not, unlike the other entities."""

    _attr_name = "Connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "connection")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.client.available


class T1MapSaved(T1Entity, BinarySensorEntity):
    """On when the vacuum has a saved map. Room and total cleaning are ignored without one."""

    _attr_name = "Map saved"
    _attr_icon = "mdi:map-check"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "map_saved")

    @property
    def is_on(self) -> bool:
        return self.client.has_map
