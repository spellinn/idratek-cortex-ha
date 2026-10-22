"""Switch platform: OnOffLoad objects (plugs, relays, fans)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import CortexError, CortexObject
from .const import SWITCH_TYPES, SwitchedPorts
from .coordinator import CortexConfigEntry, CortexCoordinator
from .entity import CortexEntity
from .light import _command_error

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CortexConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a switch for each OnOffLoad."""
    coordinator = entry.runtime_data
    async_add_entities(
        CortexSwitch(coordinator, obj, SWITCH_TYPES[obj.type])
        for obj in coordinator.objects.values()
        if obj.type in SWITCH_TYPES
    )


class CortexSwitch(CortexEntity, SwitchEntity):
    """A Cortex OnOffLoad."""

    _attr_name = None
    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(
        self, coordinator: CortexCoordinator, obj: CortexObject, ports: SwitchedPorts
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, obj)
        self._ports = ports

    @property
    def is_on(self) -> bool | None:
        """Return true when Set On (Output) is true."""
        reading = self.port(self._ports.state)
        return reading.state if reading else None

    async def _send(self, description: str, port: int) -> None:
        try:
            await self.coordinator.client.trigger(
                self._object.name, self._object.object_id, description, port
            )
        except CortexError as err:
            raise _command_error(err, self._object.name) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        await self._send(self._ports.on_desc, self._ports.on)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self._send(self._ports.off_desc, self._ports.off)
