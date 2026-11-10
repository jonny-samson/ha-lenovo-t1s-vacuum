"""Indicator light and the room-queue switches."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import T1ConfigEntry, room_slots
from .entity import T1Entity
from .rooms import enabled_by_default, room_label


async def async_setup_entry(hass: HomeAssistant, entry: T1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    known = entry.runtime_data.client.room_ids()
    slots = room_slots(entry)
    async_add_entities(
        [T1Light(entry)]
        + [T1RoomSwitch(entry, slot, enabled_by_default(known, slot, slots)) for slot in range(1, slots + 1)]
        + [T1RoomPasses(entry, slot) for slot in range(1, slots + 1)])


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


class T1RoomPasses(T1Entity, SwitchEntity):
    """Double pass for one room, saved on the vacuum's map. Off by default: turning it on or off
    rewrites the saved room list (the same save the vendor app does), so enable it deliberately."""

    _attr_icon = "mdi:layers-double"
    _attr_entity_registry_enabled_default = False

    def __init__(self, entry: T1ConfigEntry, slot: int) -> None:
        super().__init__(entry, f"passes_{slot}")
        self._slot = slot

    @property
    def name(self) -> str:
        return f"{room_label(self.client.room(self._slot), self._slot)} double pass"

    @property
    def available(self) -> bool:
        return self.client.available and self.client.room(self._slot) is not None

    @property
    def is_on(self) -> bool:
        return (self.client.room(self._slot) or {}).get("active") == "depth"

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)

    async def _set(self, double: bool) -> None:
        try:
            await self.hass.async_add_executor_job(self.client.set_room_passes, self._slot, double)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
