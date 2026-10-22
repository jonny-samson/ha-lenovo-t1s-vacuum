from homeassistant.components.number import NumberEntity

from .entity import T1Entity


async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    add_entities([T1Volume(hass)])


class T1Volume(T1Entity, NumberEntity):
    _attr_name = "Volume"
    _attr_native_min_value = 0
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_assumed_state = True

    def __init__(self, hass):
        super().__init__(hass, "volume")

    @property
    def native_value(self):
        return self.client.volume

    async def async_set_native_value(self, value):
        await self.hass.async_add_executor_job(self.client.set_volume, value)
