"""Sensors: Cortex Temperature objects."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import CortexObject
from .const import TYPE_TEMPERATURE
from .coordinator import CortexConfigEntry, CortexCoordinator
from .entity import CortexEntity

PARALLEL_UPDATES = 0  # read only

TEMPERATURE_PORT = 0  # "Temperature Output", plain degrees Celsius
# Cortex reports -1000 when a temperature source is missing (as for HVAC setpoints).
INVALID_BELOW = -999.0

TEMPERATURE = SensorEntityDescription(
    key="temperature",
    name=None,  # the main feature takes the device name
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=1,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CortexConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a temperature sensor for each Cortex Temperature object."""
    coordinator = entry.runtime_data
    async_add_entities(
        CortexTemperatureSensor(coordinator, obj)
        for obj in coordinator.objects.values()
        if obj.type == TYPE_TEMPERATURE
    )


class CortexTemperatureSensor(CortexEntity, SensorEntity):
    """Room temperature from a Cortex Temperature object."""

    entity_description = TEMPERATURE

    def __init__(self, coordinator: CortexCoordinator, obj: CortexObject) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, obj, TEMPERATURE.key)

    @property
    def native_value(self) -> float | None:
        """Return the temperature, or None when the source is missing."""
        reading = self.port(TEMPERATURE_PORT)
        if reading is None or reading.value is None or reading.value < INVALID_BELOW:
            return None
        return reading.value
