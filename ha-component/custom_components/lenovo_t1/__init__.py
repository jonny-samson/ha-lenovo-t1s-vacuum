"""Lenovo T1 Pro vacuum over local Tuya (YAML configured)."""
import voluptuous as vol

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform

from .client import T1Client

DOMAIN = "lenovo_t1"
PLATFORMS = ["vacuum", "sensor", "number", "switch", "button"]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required("device_id"): cv.string,
                vol.Required("local_key"): cv.string,
                vol.Required("serial"): cv.string,
                vol.Required("user_id"): cv.string,
                vol.Optional("version", default=3.3): vol.Coerce(float),
                vol.Optional("name", default="Lenovo T1 Pro"): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config) -> bool:
    conf = config[DOMAIN]
    client = T1Client(conf[CONF_HOST], conf["device_id"], conf["local_key"], conf["version"],
                      conf["serial"], conf["user_id"])
    hass.data[DOMAIN] = {"client": client, "name": conf["name"], "id": conf["device_id"]}
    await hass.async_add_executor_job(client.start)
    hass.bus.async_listen_once("homeassistant_stop", lambda _e: client.stop())
    for platform in PLATFORMS:
        hass.async_create_task(async_load_platform(hass, platform, DOMAIN, {}, config))
    return True
