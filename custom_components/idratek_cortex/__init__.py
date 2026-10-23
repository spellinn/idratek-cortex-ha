"""The Idratek Cortex integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CortexClient
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import CortexConfigEntry, CortexCoordinator
from .push import async_register_push

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: CortexConfigEntry) -> bool:
    """Set up Idratek Cortex from a config entry."""
    client = CortexClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = CortexCoordinator(
        hass,
        entry,
        client,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=MANUFACTURER,
        name=f"Cortex ({entry.data[CONF_HOST]})",
        model="Cortex",
    )

    async_register_push(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload_on_options(hass: HomeAssistant, entry: CortexConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CortexConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: CortexConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow removal only of devices whose Cortex object no longer exists."""
    if (DOMAIN, entry.entry_id) in device_entry.identifiers:
        return False  # the hub itself
    live = {f"{entry.entry_id}_{oid}" for oid in entry.runtime_data.objects}
    return not any(
        domain == DOMAIN and ident in live for domain, ident in device_entry.identifiers
    )
