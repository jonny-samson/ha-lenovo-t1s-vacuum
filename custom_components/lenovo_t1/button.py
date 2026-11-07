"""Buttons: find robot, room queue actions, consumable resets."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import T1ConfigEntry
from .const import DOMAIN
from .entity import T1Entity

CONSUMABLES = {"filter": "Filter", "sideBrush": "Side brush", "mainBrush": "Main brush", "sensors": "Sensors"}

# key, name, direction, icon
DRIVE_BUTTONS = (
    ("drive_forward", "Drive forward", "forward", "mdi:arrow-up-bold"),
    ("drive_back", "Drive back", "back", "mdi:arrow-down-bold"),
    ("turn_left", "Turn left", "left", "mdi:arrow-top-left-bold-outline"),
    ("turn_right", "Turn right", "right", "mdi:arrow-top-right-bold-outline"),
)


async def async_setup_entry(hass: HomeAssistant, entry: T1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([
        T1Locate(entry), T1CancelDock(entry), T1CleanQueue(entry), T1ClearQueue(entry),
        *[T1Drive(entry, *b) for b in DRIVE_BUTTONS],
        *[T1ResetConsumable(entry, k, v) for k, v in CONSUMABLES.items()],
    ])


class T1Locate(T1Entity, ButtonEntity):
    _attr_name = "Find robot"

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "locate")

    async def async_press(self) -> None:
        await self.hass.async_add_executor_job(self.client.locate)


class T1CancelDock(T1Entity, ButtonEntity):
    _attr_name = "Cancel dock"
    _attr_icon = "mdi:home-remove"

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "cancel_dock")

    async def async_press(self) -> None:
        await self.hass.async_add_executor_job(self.client.cancel_dock)


class T1Drive(T1Entity, ButtonEntity):
    """One manual-control burst (about 1.5 s of driving or turning)."""

    def __init__(self, entry: T1ConfigEntry, key: str, name: str, direction: str, icon: str) -> None:
        super().__init__(entry, key)
        self._direction = direction
        self._attr_name = name
        self._attr_icon = icon

    async def async_press(self) -> None:
        await self.hass.async_add_executor_job(self.client.drive, self._direction)


class T1CleanQueue(T1Entity, ButtonEntity):
    _attr_name = "Clean queued rooms"
    _attr_icon = "mdi:play-box-multiple"

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "clean_queue")

    async def async_press(self) -> None:
        ids = self.queue.ids
        if not ids:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="queue_empty")
        try:
            await self.hass.async_add_executor_job(self.client.clean_rooms, ids)
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="cannot_clean",
                translation_placeholders={"reason": str(err)}) from err
        self.queue.clear()
        async_dispatcher_send(self.hass, self._entry.runtime_data.signal)


class T1ClearQueue(T1Entity, ButtonEntity):
    _attr_name = "Clear room queue"
    _attr_icon = "mdi:playlist-remove"

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "clear_queue")

    async def async_press(self) -> None:
        self.queue.clear()
        async_dispatcher_send(self.hass, self._entry.runtime_data.signal)


class T1ResetConsumable(T1Entity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: T1ConfigEntry, field: str, label: str) -> None:
        super().__init__(entry, f"reset_{field}")
        self._field = field
        self._attr_name = f"Reset {label.lower()} life"

    async def async_press(self) -> None:
        try:
            await self.hass.async_add_executor_job(self.client.reset_consumable, self._field)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
