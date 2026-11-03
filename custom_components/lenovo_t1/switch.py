"""Indicator light and the room-queue switches."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import T1ConfigEntry
from .const import ROOM_SLOTS
from .entity import T1Entity
from .rooms import enabled_by_default, room_label


async def async_setup_entry(hass: HomeAssistant, entry: T1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    known = entry.runtime_data.client.room_ids()
    async_add_entities(
        [T1Light(entry)] + [T1RoomSwitch(entry, slot, enabled_by_default(known, slot))
                            for slot in range(1, ROOM_SLOTS + 1)])


class T1Light(T1Entity, SwitchEntity):
    _attr_name = "Indicator light"

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "light")

    @property
    def is_on(self) -> bool | None:
        return self.client.light

    async def async_turn_on(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.client.set_light, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.client.set_light, False)


class T1RoomSwitch(T1Entity, SwitchEntity):
    """Adds the room to the cleaning queue. The order the switches are turned on
    is the order the rooms are cleaned. Rename or disable it like any entity."""

    _attr_icon = "mdi:floor-plan"

    def __init__(self, entry: T1ConfigEntry, slot: int, enabled: bool) -> None:
        super().__init__(entry, f"room_{slot}")
        self._slot = slot
        self._attr_entity_registry_enabled_default = enabled

    @property
    def name(self) -> str:
        return room_label(self.client.room(self._slot), self._slot)

    @property
    def available(self) -> bool:
        return self.client.available and self.client.room(self._slot) is not None

    @property
    def is_on(self) -> bool:
        return self._slot in self.queue.ids

    @property
    def extra_state_attributes(self) -> dict:
        room = self.client.room(self._slot) or {}
        return {
            "room_id": self._slot,
            "passes": "double" if room.get("active") == "depth" else "single",
            "queue_position": self.queue.position(self._slot),
        }

    async def async_turn_on(self, **kwargs) -> None:
        self.queue.add(self._slot)
        async_dispatcher_send(self.hass, self._entry.runtime_data.signal)

    async def async_turn_off(self, **kwargs) -> None:
        self.queue.remove(self._slot)
        async_dispatcher_send(self.hass, self._entry.runtime_data.signal)
