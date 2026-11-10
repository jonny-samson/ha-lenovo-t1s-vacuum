"""Event entity for the vacuum's own messages and fault changes."""
from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import T1ConfigEntry
from .const import EVENT_TYPES, MESSAGE_EVENT_TYPES
from .entity import T1Entity
from .t1api.const import FAULT_CODES


async def async_setup_entry(hass: HomeAssistant, entry: T1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([T1Messages(entry)])


class T1Messages(T1Entity, EventEntity):
    """Fires for each message the vacuum sends ("cleaning completed", ...) and when a fault
    appears or clears. Use it as an automation trigger."""

    _attr_name = "Vacuum message"
    _attr_translation_key = "vacuum_message"
    _attr_event_types = EVENT_TYPES

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "messages")
        self._seen = self.client.event_count

    @callback
    def _refresh(self) -> None:
        for kind, code in self.client.new_events(self._seen):
            if kind == "message":
                event_type = MESSAGE_EVENT_TYPES.get(code, "unknown_message")
            else:
                event_type = kind
            self._trigger_event(event_type, {"code": code, "message": FAULT_CODES.get(code, f"unknown ({code})")})
        self._seen = self.client.event_count
        self.async_write_ha_state()
