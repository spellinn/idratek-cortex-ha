"""Binary sensors: Room occupancy, Motion and Door objects."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import CortexObject
from .const import TYPE_DOOR, TYPE_MOTION, TYPE_ROOM
from .coordinator import CortexConfigEntry, CortexCoordinator
from .entity import CortexEntity

PARALLEL_UPDATES = 0  # read only


@dataclass(frozen=True, kw_only=True)
class CortexBinarySensorDescription(BinarySensorEntityDescription):
    """Describes which Cortex port feeds a binary sensor."""

    port: int


DESCRIPTIONS: dict[str, tuple[CortexBinarySensorDescription, ...]] = {
    TYPE_ROOM: (
        CortexBinarySensorDescription(
            key="occupied",
            name=None,  # the main feature takes the device name
            port=2,
            device_class=BinarySensorDeviceClass.OCCUPANCY,
        ),
        CortexBinarySensorDescription(
            key="occupied_delayed",
            translation_key="occupied_delayed",
            port=8,
            device_class=BinarySensorDeviceClass.OCCUPANCY,
        ),
    ),
    TYPE_MOTION: (
        CortexBinarySensorDescription(
            key="motion",
            name=None,
            port=0,
            device_class=BinarySensorDeviceClass.MOTION,
        ),
    ),
    # Door output state: true means open, which matches the door device class.
    TYPE_DOOR: (
        CortexBinarySensorDescription(
            key="door",
            name=None,
            port=2,
            device_class=BinarySensorDeviceClass.DOOR,
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CortexConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create binary sensors for rooms, motion sensors and doors."""
    coordinator = entry.runtime_data
    async_add_entities(
        CortexBinarySensor(coordinator, obj, description)
        for obj in coordinator.objects.values()
        for description in DESCRIPTIONS.get(obj.type, ())
    )


class CortexBinarySensor(CortexEntity, BinarySensorEntity):
    """A binary sensor backed by one Cortex output port."""

    entity_description: CortexBinarySensorDescription

    def __init__(
        self,
        coordinator: CortexCoordinator,
        obj: CortexObject,
        description: CortexBinarySensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, obj, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the port State."""
        reading = self.port(self.entity_description.port)
        return reading.state if reading else None
