"""Room queue and room name resolution."""
from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, ROOM_SLOTS

if TYPE_CHECKING:
    from . import T1ConfigEntry


class RoomQueue:
    """Ordered list of room ids waiting to be cleaned. Order = cleaning order."""

    def __init__(self) -> None:
        self._ids: list[int] = []

    @property
    def ids(self) -> list[int]:
        return list(self._ids)

    def add(self, room_id: int) -> None:
        if room_id not in self._ids:
            self._ids.append(room_id)

    def remove(self, room_id: int) -> None:
        if room_id in self._ids:
            self._ids.remove(room_id)

    def clear(self) -> None:
        self._ids.clear()

    def position(self, room_id: int) -> int | None:
        return self._ids.index(room_id) + 1 if room_id in self._ids else None


def room_label(room: dict | None, slot: int) -> str:
    tag = (room or {}).get("tag") or (room or {}).get("name")
    return tag or f"Room {slot}"


def resolve_rooms(hass: HomeAssistant, entry: T1ConfigEntry, items: list) -> list[int]:
    """Turn a mixed list of room numbers and names into ordered room ids.

    A name matches either the room's name on the vacuum's map or the name the
    user gave the room's switch in Home Assistant.
    """
    client = entry.runtime_data.client
    by_name: dict[str, int] = {}
    for room in client.rooms:
        rid = room.get("id")
        if isinstance(rid, int):
            by_name[room_label(room, rid).casefold()] = rid
    registry = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        if ent.domain == "switch" and "_room_" in ent.unique_id:
            slot = int(ent.unique_id.rsplit("_", 1)[1])
            for label in (ent.name, ent.original_name):
                if label:
                    by_name.setdefault(label.casefold(), slot)

    ids: list[int] = []
    for item in items:
        if isinstance(item, int) or (isinstance(item, str) and item.strip().isdigit()):
            rid = int(item)
        else:
            rid = by_name.get(str(item).strip().casefold())
        if rid is None or rid not in client.room_ids():
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_room",
                translation_placeholders={"room": str(item)},
            )
        if rid not in ids:
            ids.append(rid)
    return ids


def enabled_by_default(known_ids: list[int], slot: int, slots: int = ROOM_SLOTS) -> bool:
    """Slots that exist on the map are enabled; the rest start disabled."""
    return slot in known_ids if known_ids else slot <= slots
