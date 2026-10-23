"""Sensors: Cortex Temperature, Humidity and LightLevel objects."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import CortexObject
from .const import TYPE_HUMIDITY, TYPE_LIGHTLEVEL, TYPE_TEMPERATURE
from .coordinator import CortexConfigEntry, CortexCoordinator
from .entity import CortexEntity

PARALLEL_UPDATES = 0  # read only

# Cortex reports -1000 when a source is missing (as for HVAC setpoints).
INVALID_BELOW = -999.0


@dataclass(frozen=True, kw_only=True)
class CortexSensorDescription(SensorEntityDescription):
    """Describes which Cortex port feeds a sensor."""

    port: int


DESCRIPTIONS: dict[str, tuple[CortexSensorDescription, ...]] = {
    TYPE_TEMPERATURE: (
        CortexSensorDescription(
            key="temperature",
            name=None,  # the main feature takes the device name
            port=0,  # Temperature Output, plain degrees Celsius
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
    ),
    TYPE_HUMIDITY: (
        CortexSensorDescription(
            key="humidity",
            name=None,
            port=0,  # Humidity Output
            device_class=SensorDeviceClass.HUMIDITY,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
        CortexSensorDescription(
            key="dewpoint",
            translation_key="dewpoint",
            port=5,  # Dewpoint Output
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
    ),
    # The Light Level Output scale is not documented (lux or an index), so no unit
    # or illuminance device class is claimed.
    TYPE_LIGHTLEVEL: (
        CortexSensorDescription(
            key="light_level",
            name=None,
            port=0,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CortexConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors for Temperature, Humidity and LightLevel objects."""
    coordinator = entry.runtime_data
    async_add_entities(
        CortexSensor(coordinator, obj, description)
        for obj in coordinator.objects.values()
        for description in DESCRIPTIONS.get(obj.type, ())
    )


class CortexSensor(CortexEntity, SensorEntity):
    """A sensor backed by one Cortex output port."""

    entity_description: CortexSensorDescription

    def __init__(
        self,
        coordinator: CortexCoordinator,
        obj: CortexObject,
        description: CortexSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, obj, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the port value, or None when the source is missing."""
        reading = self.port(self.entity_description.port)
        if reading is None or reading.value is None or reading.value < INVALID_BELOW:
            return None
        return reading.value
