"""Setup, entity state and command tests."""

from __future__ import annotations


from custom_components.idratek_cortex.api import CortexAuthError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities_and_state(hass, mock_client, mock_config_entry) -> None:
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    dimmer = hass.states.get("light.lounge_lights")
    assert dimmer.state == "on"
    assert dimmer.attributes["brightness"] == 204  # 80% of 255
    assert hass.states.get("light.outside_light").state == "off"
    assert hass.states.get("switch.extractor_fan").state == "on"

    climate = hass.states.get("climate.front_bedroom_radiator")
    assert climate.state == "heat"
    assert climate.attributes["current_temperature"] == 22.8
    assert climate.attributes["temperature"] == 22.0
    assert climate.attributes["hvac_action"] == "idle"
    assert climate.attributes["hvac_modes"] == ["off", "heat"]


async def test_light_commands(hass, mock_client, mock_config_entry) -> None:
    await _setup(hass, mock_config_entry)
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.lounge_lights", "brightness": 255}, blocking=True
    )
    mock_client.write_port_value.assert_awaited_with("178", 5, 100)
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.outside_light"}, blocking=True
    )
    mock_client.trigger.assert_awaited_with("Outside light", "130", "Turn On", 5)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.extractor_fan"}, blocking=True
    )
    mock_client.trigger.assert_awaited_with("Extractor fan", "257", "Turn off", 2)


async def test_climate_commands(hass, mock_client, mock_config_entry) -> None:
    await _setup(hass, mock_config_entry)
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.front_bedroom_radiator", "temperature": 21.5},
        blocking=True,
    )
    mock_client.write_port_value.assert_awaited_with("42", 31, 21.5)
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.front_bedroom_radiator", "hvac_mode": "off"},
        blocking=True,
    )
    mock_client.trigger.assert_awaited_with("Front Bedroom Radiator", "42", "Mode Off", 6)


async def test_auth_failure_starts_reauth(hass, mock_client, mock_config_entry) -> None:
    mock_client.get_objects.side_effect = CortexAuthError("401")
    await _setup_expect_fail(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    assert any(mock_config_entry.async_get_active_flows(hass, {"reauth"}))


async def _setup_expect_fail(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_webhook_refreshes(hass, hass_client_no_auth, mock_client, mock_config_entry) -> None:
    await _setup(hass, mock_config_entry)
    calls = mock_client.read_port.await_count
    client = await hass_client_no_auth()
    resp = await client.post(f"/api/webhook/idratek_cortex_{mock_config_entry.entry_id}", json={})
    assert resp.status == 200
    await hass.async_block_till_done()
    assert mock_client.read_port.await_count > calls
