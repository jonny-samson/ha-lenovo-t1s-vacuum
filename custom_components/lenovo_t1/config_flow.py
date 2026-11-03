"""Config flow: set up the vacuum from the UI, no YAML or secrets.yaml needed."""
from __future__ import annotations

import logging
import time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_SERIAL,
    CONF_USER_ID,
    CONF_VERSION,
    DEFAULT_NAME,
    DEFAULT_VERSION,
    DOMAIN,
    PROTOCOL_VERSIONS,
)
from .t1api import T1Client

_LOGGER = logging.getLogger(__name__)
PROBE_TIMEOUT = 10


def _probe(data: dict) -> str | None:
    """Connect and wait for an answer. Returns an error key, or None on success."""
    client = T1Client(data[CONF_HOST], data[CONF_DEVICE_ID], data[CONF_LOCAL_KEY],
                      data[CONF_SERIAL], data[CONF_USER_ID], float(data[CONF_VERSION]))
    client.start()
    try:
        deadline = time.time() + PROBE_TIMEOUT
        while time.time() < deadline:
            if client.last_report:
                return None
            time.sleep(0.25)
        return "no_response" if client.connected else "cannot_connect"
    finally:
        client.stop()


def _schema(defaults: dict | None = None, *, full: bool = True) -> vol.Schema:
    d = defaults or {}
    secret = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
    fields: dict = {vol.Required(CONF_HOST, default=d.get(CONF_HOST, "")): str}
    if full:
        fields[vol.Required(CONF_NAME, default=d.get(CONF_NAME, DEFAULT_NAME))] = str
        fields[vol.Required(CONF_DEVICE_ID, default=d.get(CONF_DEVICE_ID, ""))] = str
    fields[vol.Required(CONF_LOCAL_KEY, default=d.get(CONF_LOCAL_KEY, ""))] = secret
    fields[vol.Required(CONF_SERIAL, default=d.get(CONF_SERIAL, ""))] = str
    fields[vol.Required(CONF_USER_ID, default=d.get(CONF_USER_ID, ""))] = str
    fields[vol.Required(CONF_VERSION, default=d.get(CONF_VERSION, DEFAULT_VERSION))] = SelectSelector(
        SelectSelectorConfig(options=PROTOCOL_VERSIONS))
    return vol.Schema(fields)


class LenovoT1ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = {k: v.strip() if isinstance(v, str) else v for k, v in user_input.items()}
            await self.async_set_unique_id(user_input[CONF_DEVICE_ID])
            self._abort_if_unique_id_configured()
            error = await self.hass.async_add_executor_job(_probe, user_input)
            if error is None:
                name = user_input.pop(CONF_NAME)
                return self.async_create_entry(title=name, data=user_input)
            errors["base"] = error
        return self.async_show_form(step_id="user", data_schema=_schema(user_input), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the IP, key or protocol version of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = {k: v.strip() if isinstance(v, str) else v for k, v in user_input.items()}
            merged = {**entry.data, **user_input}
            error = await self.hass.async_add_executor_job(_probe, merged)
            if error is None:
                return self.async_update_reload_and_abort(entry, data=merged)
            errors["base"] = error
        return self.async_show_form(
            step_id="reconfigure", data_schema=_schema(user_input or dict(entry.data), full=False),
            errors=errors)
