from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lenovo_t1.const import DOMAIN

from .conftest import ENTRY_DATA

USER = {"name": "Lenovo T1 Pro", **ENTRY_DATA}


async def test_user_flow_success(hass):
    with patch("custom_components.lenovo_t1.config_flow._probe", return_value=None), \
         patch("custom_components.lenovo_t1.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Lenovo T1 Pro"
    assert result["data"]["device_id"] == "dev123" and "name" not in result["data"]


async def test_user_flow_errors_then_recovers(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    for err in ("cannot_connect", "no_response"):
        with patch("custom_components.lenovo_t1.config_flow._probe", return_value=err):
            result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
        assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": err}
    with patch("custom_components.lenovo_t1.config_flow._probe", return_value=None), \
         patch("custom_components.lenovo_t1.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_aborts(hass):
    MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="dev123").add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"


async def test_reconfigure(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="dev123", title="x")
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    new = {k: v for k, v in ENTRY_DATA.items() if k != "device_id"} | {"host": "192.0.2.99"}
    with patch("custom_components.lenovo_t1.config_flow._probe", return_value=None), \
         patch("custom_components.lenovo_t1.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], new)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "192.0.2.99"


async def test_reauth_flow_updates_key(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id="dev123", title="x")
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "reauth_confirm"
    with patch("custom_components.lenovo_t1.config_flow._probe", return_value="invalid_auth"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"local_key": "z" * 16, "version": "3.4"})
    assert result["errors"] == {"base": "invalid_auth"}
    with patch("custom_components.lenovo_t1.config_flow._probe", return_value=None), \
         patch("custom_components.lenovo_t1.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"local_key": "z" * 16, "version": "3.4"})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reauth_successful"
    assert entry.data["local_key"] == "z" * 16 and entry.data["version"] == "3.4"


def test_probe_reports_invalid_auth():
    from custom_components.lenovo_t1 import config_flow
    from custom_components.lenovo_t1.t1api import T1Client

    class Refused(T1Client):
        def start(self):
            self.auth_errors = 1

        def stop(self):
            pass

    with patch.object(config_flow, "T1Client", Refused):
        assert config_flow._probe({**ENTRY_DATA}) == "invalid_auth"
