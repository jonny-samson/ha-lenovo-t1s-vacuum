from homeassistant.components.button import ButtonEntity

from .entity import T1Entity


async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    add_entities([T1Locate(hass)])


class T1Locate(T1Entity, ButtonEntity):
    _attr_name = "Find robot"

    def __init__(self, hass):
        super().__init__(hass, "locate")

    async def async_press(self):
        await self.hass.async_add_executor_job(self.client.locate)
