"""Fixtures for Idratek Cortex tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.idratek_cortex.api import CortexObject, PortReading
from custom_components.idratek_cortex.const import DOMAIN
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

OBJECTS = {
    "18": CortexObject("18", "45HVC", "House", "World", {}),
    "178": CortexObject("178", "Lounge lights", "IdratekDimmer1", "Lounge", {}),
    "130": CortexObject("130", "Outside light", "Light", "Ground", {}),
    "257": CortexObject("257", "Extractor fan", "OnOffLoad", "Bathroom", {}),
    "42": CortexObject("42", "Front Bedroom Radiator", "HVAC", "Front bedroom", {}),
}
PORTS = {
    ("178", 0): PortReading(80.0, True),
    ("178", 1): PortReading(80.0, None),
    ("130", 15): PortReading(0.0, False),
    ("257", 16): PortReading(100.0, True),
    ("42", 0): PortReading(22.78, None),
    ("42", 17): PortReading(0.0, False),
    ("42", 18): PortReading(0.0, False),
    ("42", 46): PortReading(22.0, None),
    ("42", 47): PortReading(-1000.0, None),
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of custom integrations in tests."""


@pytest.fixture
def mock_client() -> Generator[AsyncMock]:
    """Patch the Cortex client used by the integration and the config flow."""
    with (
        patch("custom_components.idratek_cortex.CortexClient", autospec=True) as init_cls,
        patch("custom_components.idratek_cortex.config_flow.CortexClient", new=init_cls),
    ):
        client = init_cls.return_value
        client.get_objects.return_value = OBJECTS
        client.read_port.side_effect = lambda oid, port: PORTS[(oid, port)]
        client.get_object.return_value = CortexObject(
            "42", "Front Bedroom Radiator", "HVAC", None, {"PaintString": "H 22.00"}
        )
        yield client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A configured entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Cortex: 45HVC",
        unique_id="house-18",
        data={
            CONF_HOST: "192.168.50.61",
            CONF_PORT: 80,
            CONF_USERNAME: "ha",
            CONF_PASSWORD: "secret",
        },
    )
