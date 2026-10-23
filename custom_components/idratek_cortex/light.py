"""Light platform: IdratekDimmer1 (dimmable), Light and HomeEasyLight (on/off)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.color import brightness_to_value, value_to_brightness

from .api import CortexConnectionError, CortexError, CortexObject
from .const import DOMAIN, LIGHT_TYPES, SwitchedPorts
from .coordinator import CortexConfigEntry, CortexCoordinator
from .entity import CortexEntity

PARALLEL_UPDATES = 1
BRIGHTNESS_SCALE = (1, 100)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CortexConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a light for each supported Cortex lighting object."""
    coordinator = entry.runtime_data
    async_add_entities(
        CortexLight(coordinator, obj, LIGHT_TYPES[obj.type])
        for obj in coordinator.objects.values()
        if obj.type in LIGHT_TYPES
    )


class CortexLight(CortexEntity, LightEntity):
    """A Cortex light."""

    _attr_name = None

    def __init__(
        self, coordinator: CortexCoordinator, obj: CortexObject, ports: SwitchedPorts
    ) -> None:
        """Initialise the light."""
        super().__init__(coordinator, obj)
        self._ports = ports
        dimmable = ports.set_level is not None
        mode = ColorMode.BRIGHTNESS if dimmable else ColorMode.ONOFF
        self._attr_supported_color_modes = {mode}
        self._attr_color_mode = mode

    @property
    def is_on(self) -> bool | None:
        """Return true when the state port is set."""
        reading = self.port(self._ports.state)
        return reading.state if reading else None

    @property
    def brightness(self) -> int | None:
        """Return brightness 1-255 for dimmers."""
        if self._ports.level is None:
            return None
        reading = self.port(self._ports.level)
        if reading is None or reading.value is None or reading.value <= 0:
            return None
        return value_to_brightness(BRIGHTNESS_SCALE, reading.value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on, optionally at a given brightness."""
        try:
            if ATTR_BRIGHTNESS in kwargs and self._ports.set_level is not None:
                percent = round(brightness_to_value(BRIGHTNESS_SCALE, kwargs[ATTR_BRIGHTNESS]))
                await self.coordinator.client.write_port_value(
                    self._object.object_id,
                    self._ports.set_level,
                    percent,
                    name=self._object.name,
                    description=self._ports.set_level_desc,
                )
            else:
                await self.coordinator.client.trigger(
                    self._object.name,
                    self._object.object_id,
                    self._ports.on_desc,
                    self._ports.on,
                )
        except CortexError as err:
            raise _command_error(err, self._object.name) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        try:
            await self.coordinator.client.trigger(
                self._object.name,
                self._object.object_id,
                self._ports.off_desc,
                self._ports.off,
            )
        except CortexError as err:
            raise _command_error(err, self._object.name) from err
        await self.coordinator.async_request_refresh()


def _command_error(err: CortexError, name: str) -> HomeAssistantError:
    key = "cannot_connect" if isinstance(err, CortexConnectionError) else "command_failed"
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders={"name": name, "error": str(err)},
    )
