from homeassistant.helpers.entity import DeviceInfo, Entity

from . import DOMAIN


class T1Entity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, hass, suffix):
        data = hass.data[DOMAIN]
        self.client = data["client"]
        self._attr_unique_id = f"{data['id']}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, data["id"])}, name=data["name"],
            manufacturer="Lenovo", model="T1 Pro")

    @property
    def available(self):
        return self.client.connected

    async def async_added_to_hass(self):
        loop = self.hass.loop

        def _cb():
            loop.call_soon_threadsafe(self.async_write_ha_state)

        self.client.add_listener(_cb)
