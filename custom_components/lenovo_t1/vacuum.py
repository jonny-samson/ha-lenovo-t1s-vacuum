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
from .const import ATTR_ROOMS, DOMAIN, SERVICE_CLEAN_ROOMS
from .entity import T1Entity
from .rooms import resolve_rooms
from .t1api import FAN_MODES

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


class T1Vacuum(T1Entity, StateVacuumEntity):
    _attr_name = None
    _attr_supported_features = (
        VacuumEntityFeature.START | VacuumEntityFeature.PAUSE | VacuumEntityFeature.RETURN_HOME
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

    async def _call(self, func, *args) -> None:
        try:
            await self.hass.async_add_executor_job(func, *args)
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="cannot_clean",
                translation_placeholders={"reason": str(err)}) from err
