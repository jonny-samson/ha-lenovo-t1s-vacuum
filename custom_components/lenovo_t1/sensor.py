"""Sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfArea, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import T1ConfigEntry
from .entity import T1Entity
from .rooms import room_label
from .t1api.client import ACTIVITY

MODES = list(ACTIVITY)
CONSUMABLES = {"filter": "Filter", "sideBrush": "Side brush", "mainBrush": "Main brush", "sensors": "Sensors"}


async def async_setup_entry(hass: HomeAssistant, entry: T1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([
        T1Battery(entry), T1CleanArea(entry), T1CleanTime(entry), T1Fault(entry),
        T1Mode(entry), T1RoomQueue(entry), T1Firmware(entry),
        T1MapId(entry), T1RoomCount(entry), T1CleanType(entry), T1LastEvent(entry), T1Reconnects(entry),
        T1Info(entry, "wifi_ssid", "Wi-Fi network", "wifi", "staId", "mdi:wifi"),
        T1WifiSignal(entry),
        T1Info(entry, "wifi_ip", "IP address", "wifi", "staIp", "mdi:ip-network", enabled=False),
        T1Info(entry, "wifi_mac", "MAC address", "wifi", "staMac", "mdi:network", enabled=False),
        *[T1ConsumableLife(entry, k, v) for k, v in CONSUMABLES.items()],
    ])


class T1Battery(T1Entity, SensorEntity):
    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "battery")

    @property
    def native_value(self) -> int | None:
        return self.client.battery


class T1CleanArea(T1Entity, SensorEntity):
    _attr_name = "Cleaned area"
    _attr_device_class = SensorDeviceClass.AREA
    _attr_native_unit_of_measurement = UnitOfArea.SQUARE_METERS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "clean_area")

    @property
    def native_value(self) -> int | float | None:
        return self.client.clean_area


class T1CleanTime(T1Entity, SensorEntity):
    _attr_name = "Cleaning time"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "clean_time")

    @property
    def native_value(self) -> int | None:
        seconds = self.client.clean_time
        return None if seconds is None else round(seconds / 60)


class T1Fault(T1Entity, SensorEntity):
    _attr_name = "Fault"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "fault")

    @property
    def native_value(self) -> str:
        return self.client.fault_text

    @property
    def extra_state_attributes(self) -> dict:
        return {"code": self.client.fault, "last_message_code": self.client.last_message}


class T1Mode(T1Entity, SensorEntity):
    """The vacuum's own mode. The state keeps the raw value (so automations that match it keep
    working); the translations give the display text, e.g. rfctrl -> "Remote control"."""

    _attr_name = "Mode"
    _attr_translation_key = "mode"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = MODES
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "mode")

    @property
    def native_value(self) -> str | None:
        # An enum sensor cannot hold a value outside its options; unknown modes show in the attribute.
        return self.client.mode if self.client.mode in MODES else None

    @property
    def extra_state_attributes(self) -> dict:
        # The whole last status report (position and timestamps are left out), handy for spotting new fields.
        return {**self.mode_attributes, "report": dict(self.client.state)}


class T1MapId(T1Entity, SensorEntity):
    _attr_name = "Map ID"
    _attr_icon = "mdi:map-marker-path"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "map_id")

    @property
    def native_value(self) -> int | None:
        return self.client.map_id if self.client.has_map else None

    @property
    def extra_state_attributes(self) -> dict:
        return {"map_saved": self.client.has_map}


class T1RoomCount(T1Entity, SensorEntity):
    _attr_name = "Rooms"
    _attr_icon = "mdi:floor-plan"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "room_count")

    @property
    def native_value(self) -> int:
        return len(self.client.rooms)

    @property
    def extra_state_attributes(self) -> dict:
        return {"rooms": [
            {"id": r.get("id"), "name": room_label(r, r.get("id")),
             "passes": "double" if r.get("active") == "depth" else "single"}
            for r in self.client.rooms]}


class T1CleanType(T1Entity, SensorEntity):
    """How the current clean was started (subMode in the status report), when the vacuum says."""

    _attr_name = "Clean type"
    _attr_icon = "mdi:broom"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "clean_type")

    @property
    def native_value(self) -> str | None:
        value = self.client.state.get("subMode")
        return None if value in (None, "", "null") else str(value)


class T1LastEvent(T1Entity, SensorEntity):
    """The latest informational message from the vacuum, e.g. "cleaning completed"."""

    _attr_name = "Last event"
    _attr_icon = "mdi:message-text-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "last_event")

    @property
    def native_value(self) -> str | None:
        return self.client.last_message_text

    @property
    def extra_state_attributes(self) -> dict:
        return {"code": self.client.last_message}


class T1Reconnects(T1Entity, SensorEntity):
    """Times the connection to the vacuum was re-established since Home Assistant started."""

    _attr_name = "Reconnects"
    _attr_icon = "mdi:lan-connect"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "reconnects")

    @property
    def native_value(self) -> int:
        return self.client.reconnects


class T1Info(T1Entity, SensorEntity):
    """A text field from the Wi-Fi reply (21019)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: T1ConfigEntry, key: str, name: str, source: str, field: str,
                 icon: str, enabled: bool = True) -> None:
        super().__init__(entry, key)
        self._source, self._field = source, field
        self._attr_name = name
        self._attr_icon = icon
        self._attr_entity_registry_enabled_default = enabled

    @property
    def native_value(self) -> str | None:
        value = getattr(self.client, self._source).get(self._field)
        return None if value in (None, "") else str(value)


class T1WifiSignal(T1Entity, SensorEntity):
    """Signal quality 0-100 as reported by the vacuum; it is not dBm."""

    _attr_name = "Wi-Fi signal"
    _attr_icon = "mdi:wifi-strength-3"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "wifi_signal")

    @property
    def native_value(self) -> int | None:
        try:
            return int(self.client.wifi["staSignal"])
        except (KeyError, TypeError, ValueError):
            return None


class T1Firmware(T1Entity, SensorEntity):
    _attr_name = "Firmware version"
    _attr_icon = "mdi:chip"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "firmware")

    @property
    def native_value(self) -> str | None:
        version = self.client.firmware.get("version")
        return None if version in (None, "") else str(version)

    @property
    def extra_state_attributes(self) -> dict:
        return {k: self.client.firmware.get(k) for k in ("fullversion", "mcu")}


class T1ConsumableLife(T1Entity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: T1ConfigEntry, field: str, label: str) -> None:
        super().__init__(entry, f"life_{field}")
        self._field = field
        self._attr_name = f"{label} life remaining"

    @property
    def native_value(self) -> float | None:
        return self.client.consumable_hours(self._field)


class T1RoomQueue(T1Entity, SensorEntity):
    _attr_name = "Room queue"
    _attr_icon = "mdi:format-list-numbered"

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "room_queue")

    @property
    def native_value(self) -> str:
        ids = self.queue.ids
        if not ids:
            return "empty"
        return ", ".join(room_label(self.client.room(i), i) for i in ids)

    @property
    def extra_state_attributes(self) -> dict:
        return {"room_ids": self.queue.ids}
