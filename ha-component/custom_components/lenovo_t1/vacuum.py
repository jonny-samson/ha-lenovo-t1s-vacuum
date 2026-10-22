from homeassistant.components.vacuum import StateVacuumEntity, VacuumEntityFeature

try:  # HA >= 2025.1
    from homeassistant.components.vacuum import VacuumActivity
    _ACT = {"cleaning": VacuumActivity.CLEANING, "paused": VacuumActivity.PAUSED,
            "returning": VacuumActivity.RETURNING, "docked": VacuumActivity.DOCKED}
except ImportError:  # older HA
    VacuumActivity = None
    _ACT = {"cleaning": "cleaning", "paused": "paused", "returning": "returning", "docked": "docked"}

from .entity import T1Entity

SPEEDS = {"Low": "quiet", "Medium": "auto", "High": "strong", "Off": "mop"}
REV = {v: k for k, v in SPEEDS.items()}


async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    add_entities([T1Vacuum(hass)])


class T1Vacuum(T1Entity, StateVacuumEntity):
    _attr_name = None
    _attr_supported_features = (
        VacuumEntityFeature.START | VacuumEntityFeature.PAUSE | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.FAN_SPEED | VacuumEntityFeature.LOCATE | VacuumEntityFeature.STATE)
    _attr_fan_speed_list = list(SPEEDS)

    def __init__(self, hass):
        super().__init__(hass, "vacuum")

    @property
    def activity(self):
        return _ACT[self.client.activity]

    @property
    def state(self):  # for HA versions without VacuumActivity
        return self.client.activity

    @property
    def fan_speed(self):
        return REV.get(self.client.fan_speed)

    @property
    def extra_state_attributes(self):
        s = self.client.state
        return {"mode": s.get("mode"), "clean_area": s.get("cleanArea"),
                "clean_time": s.get("cleanTime"), "fault_code": self.client.fault}

    async def async_start(self):
        if self.client.mode == "pause":
            await self.hass.async_add_executor_job(self.client.resume)
        else:
            await self.hass.async_add_executor_job(self.client.start_clean)

    async def async_pause(self):
        await self.hass.async_add_executor_job(self.client.pause)

    async def async_return_to_base(self, **kwargs):
        await self.hass.async_add_executor_job(self.client.dock)

    async def async_locate(self, **kwargs):
        await self.hass.async_add_executor_job(self.client.locate)

    async def async_set_fan_speed(self, fan_speed, **kwargs):
        await self.hass.async_add_executor_job(self.client.set_suction, SPEEDS[fan_speed])
