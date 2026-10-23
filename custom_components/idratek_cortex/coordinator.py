"""DataUpdateCoordinator for Idratek Cortex."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CortexAuthError,
    CortexClient,
    CortexConnectionError,
    CortexError,
    CortexObject,
    PortReading,
)
from .const import (
    CONFIRM_DELAY,
    DOMAIN,
    HVAC_MODE_PROPERTY,
    LOGGER,
    READ_PORTS,
    SUPPORTED_TYPES,
    TYPE_HVAC,
)

type CortexConfigEntry = ConfigEntry[CortexCoordinator]


@dataclass(slots=True)
class CortexObjectState:
    """Latest readings for one Cortex object."""

    ports: dict[int, PortReading] = field(default_factory=dict)
    hvac_mode: int | None = None  # HVACMode property: 0 off, 1 heat, 2 cool, 3 auto
    paint_string: str | None = None  # fallback mode source, e.g. "H 22.00"

    def __eq__(self, other: object) -> bool:
        """Compare by content so always_update=False can suppress no-op updates."""
        return (
            isinstance(other, CortexObjectState)
            and self.ports == other.ports
            and self.hvac_mode == other.hvac_mode
            and self.paint_string == other.paint_string
        )


class CortexCoordinator(DataUpdateCoordinator[dict[str, CortexObjectState]]):
    """Poll Cortex objects and expose them to the entity platforms."""

    config_entry: CortexConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: CortexConfigEntry,
        client: CortexClient,
        scan_interval: int,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            always_update=False,
        )
        self.client = client
        self.objects: dict[str, CortexObject] = {}
        self._confirm_tasks: dict[str, asyncio.Task[None]] = {}

    async def _async_setup(self) -> None:
        """Load the object list once; runs before the first refresh."""
        try:
            all_objects = await self.client.get_objects()
        except CortexAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except CortexError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err
        self.objects = {
            oid: obj for oid, obj in all_objects.items() if obj.type in SUPPORTED_TYPES
        }
        LOGGER.debug(
            "Cortex exposes %d objects, %d supported", len(all_objects), len(self.objects)
        )

    async def _async_update_data(self) -> dict[str, CortexObjectState]:
        """Fetch the ports we care about for every supported object."""
        try:
            async with asyncio.TaskGroup() as group:
                tasks = {
                    oid: group.create_task(self._read_object(obj))
                    for oid, obj in self.objects.items()
                }
        except* CortexAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except* CortexConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        except* CortexError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err.exceptions[0])},
            ) from err
        return {oid: task.result() for oid, task in tasks.items()}

    async def _read_object(self, obj: CortexObject) -> CortexObjectState:
        ports = READ_PORTS[obj.type]
        readings = await asyncio.gather(
            *(self.client.read_port(obj.object_id, port) for port in ports)
        )
        state = CortexObjectState(ports=dict(zip(ports, readings, strict=True)))
        if obj.type == TYPE_HVAC:
            props = await self.client.get_properties(obj.object_id)
            try:
                state.hvac_mode = int(props[HVAC_MODE_PROPERTY])
            except (KeyError, TypeError, ValueError):
                # Older firmware: infer from the object's PaintString instead.
                fresh = await self.client.get_object(obj.object_id)
                if fresh is not None:
                    paint = fresh.attributes.get("PaintString")
                    state.paint_string = str(paint) if paint is not None else None
        return state

    async def async_refresh_object(self, object_id: str) -> None:
        """Re-read a single object (used by webhook pushes) and notify listeners."""
        obj = self.objects.get(object_id)
        if obj is None:
            return
        try:
            fresh = await self._read_object(obj)
        except CortexError as err:
            LOGGER.debug("Push refresh of %s failed (%s); full refresh", object_id, err)
            await self.async_request_refresh()
            return
        self.async_set_updated_data({**(self.data or {}), object_id: fresh})


    async def async_apply_push(self, object_id: str, port: int, raw_value: str) -> bool:
        """Apply a value carried by a Cortex callback, then confirm with one read.

        Returns False when the push cannot be applied (unknown object or port, or
        an unparseable value); the caller should fall back to a refresh.
        """
        obj = self.objects.get(object_id)
        if obj is None or not self.data or object_id not in self.data:
            return False
        if port not in READ_PORTS[obj.type]:
            return False
        value = parse_cortex_number(raw_value)
        if value is None:
            return False
        current = self.data[object_id]
        previous = current.ports.get(port)
        # Binary ports report 0 or 100 (Cortex help); a port with a State is binary.
        state = value > 0 if previous is not None and previous.state is not None else None
        updated = replace(
            current, ports={**current.ports, port: PortReading(value, state)}
        )
        self.async_set_updated_data({**self.data, object_id: updated})
        self._schedule_confirm(object_id)
        return True

    def _schedule_confirm(self, object_id: str) -> None:
        if (pending := self._confirm_tasks.pop(object_id, None)) is not None:
            pending.cancel()
        self._confirm_tasks[object_id] = self.config_entry.async_create_background_task(
            self.hass,
            self._confirm(object_id),
            f"{DOMAIN}_confirm_{object_id}",
        )

    async def _confirm(self, object_id: str) -> None:
        await asyncio.sleep(CONFIRM_DELAY)
        await self.async_refresh_object(object_id)


def parse_cortex_number(raw: str) -> float | None:
    """Parse text substituted by a Cortex tag, for example "0.00", "100" or "1,5"."""
    text = str(raw).strip().replace(",", ".")
    lowered = text.lower()
    if lowered in ("true", "on"):
        return 100.0
    if lowered in ("false", "off"):
        return 0.0
    try:
        return float(text)
    except ValueError:
        return None
