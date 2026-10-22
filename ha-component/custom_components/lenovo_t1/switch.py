from homeassistant.components.switch import SwitchEntity

from .entity import T1Entity


async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    add_entities([T1Light(hass)])


class T1Light(T1Entity, SwitchEntity):
    _attr_name = "Indicator light"
    _attr_assumed_state = True

    def __init__(self, hass):
        super().__init__(hass, "light")

    @property
    def is_on(self):
        return self.client.light

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_executor_job(self.client.set_light, True)

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(self.client.set_light, False)
