"""Climate platform: Cortex HVAC objects (heating, optional cooling)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import CortexApiError, CortexError
from .const import (
    DISABLED_SENTINEL,
    DOMAIN,
    HVAC_MODE_PROPERTY,
    HVAC_PORTS,
    TYPE_HVAC,
)
from .coordinator import CortexConfigEntry
from .entity import CortexEntity
from .light import _command_error

PARALLEL_UPDATES = 1

PAINT_TO_MODE = {
    "H": HVACMode.HEAT,
    "C": HVACMode.COOL,
    "A": HVACMode.AUTO,
    "O": HVACMode.OFF,
}
# HVACMode property values (Cortex help: Properties of an HVAC are 0,1,2,3).
VALUE_TO_MODE = {0: HVACMode.OFF, 1: HVACMode.HEAT, 2: HVACMode.COOL, 3: HVACMode.AUTO}
MODE_TO_VALUE = {mode: value for value, mode in VALUE_TO_MODE.items()}
MODE_TO_DESCRIPTION = {
    HVACMode.OFF: (HVAC_PORTS.mode_off, "Mode Off"),
    HVACMode.HEAT: (HVAC_PORTS.mode_heat, "Mode Heating"),
    HVACMode.COOL: (HVAC_PORTS.mode_cool, "Mode Cooling"),
    HVACMode.AUTO: (HVAC_PORTS.mode_auto, "Mode Auto"),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CortexConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a thermostat for each HVAC object."""
    coordinator = entry.runtime_data
    async_add_entities(
        CortexClimate(coordinator, obj)
        for obj in coordinator.objects.values()
        if obj.type == TYPE_HVAC
    )


class CortexClimate(CortexEntity, ClimateEntity):
    """A Cortex HVAC object."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 30.0
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    # -- helpers -------------------------------------------------------------
    def _value(self, port: int) -> float | None:
        reading = self.port(port)
        return reading.value if reading else None

    @property
    def _cooling_enabled(self) -> bool:
        value = self._value(HVAC_PORTS.cool_setpoint)
        return value is not None and value > DISABLED_SENTINEL + 1

    # -- state ---------------------------------------------------------------
    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Cooling and auto are only offered when a cooling setpoint exists."""
        if self._cooling_enabled:
            return [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO]
        return [HVACMode.OFF, HVACMode.HEAT]

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Mode from the HVACMode property (PaintString prefix on older firmware)."""
        state = self.object_state
        if state is None:
            return None
        if state.hvac_mode is not None:
            return VALUE_TO_MODE.get(state.hvac_mode)
        if state.paint_string:
            return PAINT_TO_MODE.get(state.paint_string.strip()[:1].upper())
        return None

    @property
    def hvac_action(self) -> HVACAction | None:
        """Heating demand (port 17) and cooling demand (port 18)."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        heat, cool = self.port(HVAC_PORTS.heat_demand), self.port(HVAC_PORTS.cool_demand)
        if heat and heat.state:
            return HVACAction.HEATING
        if cool and cool.state:
            return HVACAction.COOLING
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        """Room temperature in degrees C."""
        return self._value(HVAC_PORTS.room_temp)

    @property
    def target_temperature(self) -> float | None:
        """Active setpoint for the current mode."""
        port = (
            HVAC_PORTS.cool_setpoint
            if self.hvac_mode == HVACMode.COOL
            else HVAC_PORTS.heat_setpoint
        )
        value = self._value(port)
        return None if value is None or value <= DISABLED_SENTINEL + 1 else value

    # Forward-compatible names (developer docs: legacy names removed in 2027.11).
    @property
    def native_current_temperature(self) -> float | None:
        """Room temperature in degrees C."""
        return self.current_temperature

    @property
    def native_target_temperature(self) -> float | None:
        """Active setpoint in degrees C."""
        return self.target_temperature

    # -- commands ------------------------------------------------------------
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Select a mode by pulsing the matching Mode input port."""
        if hvac_mode not in self.hvac_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_mode",
                translation_placeholders={"mode": str(hvac_mode)},
            )
        port, description = MODE_TO_DESCRIPTION[hvac_mode]
        client = self.coordinator.client
        try:
            try:
                await client.set_property(
                    self._object.object_id, HVAC_MODE_PROPERTY, MODE_TO_VALUE[hvac_mode]
                )
            except CortexApiError:
                await client.trigger(
                    self._object.name, self._object.object_id, description, port
                )
        except CortexError as err:
            raise _command_error(err, self._object.name) from err
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Write a temporary setpoint (port 31 heating, 32 cooling)."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        port = (
            HVAC_PORTS.set_cool_setpoint
            if self.hvac_mode == HVACMode.COOL
            else HVAC_PORTS.set_heat_setpoint
        )
        try:
            await self.coordinator.client.write_port_value(
                self._object.object_id, port, temperature
            )
        except CortexError as err:
            raise _command_error(err, self._object.name) from err
        await self.coordinator.async_request_refresh()
