"""Base entity for Idratek Cortex."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CortexObject, PortReading
from .const import DOMAIN, MANUFACTURER
from .coordinator import CortexCoordinator, CortexObjectState


class CortexEntity(CoordinatorEntity[CortexCoordinator]):
    """Entity bound to one port group of one Cortex object."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: CortexCoordinator, obj: CortexObject, key: str = "main"
    ) -> None:
        """Initialise with a stable unique ID: <entry>_<object id>_<key>."""
        super().__init__(coordinator)
        self._object = obj
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{obj.object_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{obj.object_id}")},
            manufacturer=MANUFACTURER,
            model=obj.type,
            name=obj.name,
            via_device=(DOMAIN, entry_id),
            serial_number=obj.object_id,
        )

    @property
    def object_state(self) -> CortexObjectState | None:
        """Latest readings for this object."""
        return self.coordinator.data.get(self._object.object_id)

    def port(self, number: int) -> PortReading | None:
        """Return the reading for a port, if polled."""
        state = self.object_state
        return state.ports.get(number) if state else None

    @property
    def available(self) -> bool:
        """Entity is available while the object is present in the last update."""
        return super().available and self.object_state is not None
