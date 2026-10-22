from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE

from .entity import T1Entity


async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    add_entities([T1Battery(hass)])


class T1Battery(T1Entity, SensorEntity):
    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass):
        super().__init__(hass, "battery")

    @property
    def native_value(self):
        return self.client.battery
