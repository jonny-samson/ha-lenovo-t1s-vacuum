"""Vacuum entity."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.components.vacuum import StateVacuumEntity, VacuumActivity, VacuumEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import T1ConfigEntry
from .const import (
    ATTR_DIRECTION,
    ATTR_DURATION,
    ATTR_MODE,
    ATTR_ROOMS,
    CLEAN_MODES,
    DOMAIN,
    SERVICE_CLEAN,
    SERVICE_CLEAN_ROOMS,
    SERVICE_CLEAN_ZONE,
    SERVICE_DRIVE,
    SERVICE_GO_TO_POINT,
)
from .entity import T1Entity
from .rooms import resolve_rooms
from .t1api import DRIVE_CODES, FAN_MODES

_ACTIVITY = {
    "cleaning": VacuumActivity.CLEANING,
    "paused": VacuumActivity.PAUSED,
    "returning": VacuumActivity.RETURNING,
    "docked": VacuumActivity.DOCKED,
    "idle": VacuumActivity.IDLE,
    "error": VacuumActivity.ERROR,
}


async def async_setup_entry(hass: HomeAssistant, entry: T1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([T1Vacuum(entry)])
    entity_platform.async_get_current_platform().async_register_entity_service(
        SERVICE_CLEAN_ROOMS,
        {vol.Required(ATTR_ROOMS): vol.All(cv.ensure_list, [vol.Any(vol.Coerce(int), cv.string)])},
        "async_clean_rooms",
    )
    entity_platform.async_get_current_platform().async_register_entity_service(
        SERVICE_DRIVE,
        {
            vol.Required(ATTR_DIRECTION): vol.In(list(DRIVE_CODES)),
            vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(float), vol.Range(min=0.25, max=10)),
        },
        "async_drive",
    )
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_CLEAN, {vol.Optional(ATTR_MODE, default="total"): vol.In(CLEAN_MODES)}, "async_clean")
    coords = {vol.Required(k): vol.Coerce(float) for k in ("x1", "y1", "x2", "y2")}
    platform.async_register_entity_service(SERVICE_CLEAN_ZONE, coords, "async_clean_zone")
    platform.async_register_entity_service(
        SERVICE_GO_TO_POINT, {vol.Required("x"): vol.Coerce(float), vol.Required("y"): vol.Coerce(float)},
        "async_go_to_point")


class T1Vacuum(T1Entity, StateVacuumEntity):
    _attr_name = None
    _attr_supported_features = (
        VacuumEntityFeature.START | VacuumEntityFeature.PAUSE | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.FAN_SPEED | VacuumEntityFeature.LOCATE
        | getattr(VacuumEntityFeature, "STATE", 0))
    _attr_fan_speed_list = list(FAN_MODES)

    def __init__(self, entry: T1ConfigEntry) -> None:
        super().__init__(entry, "vacuum")

    @property
    def activity(self) -> VacuumActivity:
        return _ACTIVITY[self.client.activity]

    @property
    def fan_speed(self) -> str | None:
        return self.client.fan_speed

    @property
    def extra_state_attributes(self) -> dict:
        return {
            **self.mode_attributes,
            "mode": self.client.mode,
            "fault_code": self.client.fault,
            "fault": self.client.fault_text,
            "map_saved": self.client.has_map,
        }

    async def async_start(self) -> None:
        if self.client.mode in ("pause", "findchargerpause"):
            await self.hass.async_add_executor_job(self.client.resume)
        else:
            await self._call(self.client.start_clean)

    async def async_pause(self) -> None:
        await self.hass.async_add_executor_job(self.client.pause)

    async def async_stop(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.client.stop_clean)

    async def async_return_to_base(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.client.dock)

    async def async_locate(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.client.locate)

    async def async_set_fan_speed(self, fan_speed: str, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.client.set_suction, FAN_MODES[fan_speed])

    async def async_clean_rooms(self, rooms: list) -> None:
        """Clean the given rooms in order. Items are room numbers or names."""
        ids = resolve_rooms(self.hass, self._entry, rooms)
        await self._call(self.client.clean_rooms, ids)

    async def async_clean(self, mode: str = "total") -> None:
        """Whole-home clean: total, deep (two passes) or along the walls. Deep and along_wall are untested."""
        if mode == "along_wall":
            await self._call(self.client.along_wall)
        else:
            await self._call(self.client.start_clean, mode == "deep")

    async def async_clean_zone(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Clean a rectangle in map coordinates. Untested."""
        await self._call(self.client.clean_zone, x1, y1, x2, y2)

    async def async_go_to_point(self, x: float, y: float) -> None:
        """Drive to a map coordinate. Untested."""
        await self._call(self.client.go_to_point, x, y)

    async def async_drive(self, direction: str, duration: float | None = None) -> None:
        """Manual control: move or turn for roughly `duration` seconds (default 1.5)."""
        await self.hass.async_add_executor_job(self.client.drive, direction, duration)

    async def _call(self, func, *args) -> None:
        try:
            await self.hass.async_add_executor_job(func, *args)
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="cannot_clean",
                translation_placeholders={"reason": str(err)}) from err
