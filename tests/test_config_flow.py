"""Config flow tests."""

from __future__ import annotations

from custom_components.idratek_cortex.api import CortexAuthError, CortexConnectionError
from custom_components.idratek_cortex.const import DOMAIN
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

USER_INPUT = {"host": "192.168.50.61", "port": 80, "username": "ha", "password": "pw"}


async def test_user_flow(hass, mock_client) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Cortex: 45HVC"
    assert result["result"].unique_id == "house-18"


async def test_errors_then_recover(hass, mock_client) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    mock_client.get_objects.side_effect = CortexAuthError("401")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "invalid_auth"}
    mock_client.get_objects.side_effect = CortexConnectionError("down")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}
    mock_client.get_objects.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_aborts(hass, mock_client, mock_config_entry) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass, mock_client, mock_config_entry) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "ha", "password": "new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data["password"] == "new"
