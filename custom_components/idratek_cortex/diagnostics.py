"""Diagnostics for Idratek Cortex."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import CortexConfigEntry

TO_REDACT = {CONF_HOST, CONF_PASSWORD, CONF_USERNAME}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CortexConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with credentials redacted."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "objects": {
            oid: {"name": obj.name, "type": obj.type, "parent": obj.parent}
            for oid, obj in coordinator.objects.items()
        },
        "data": {
            oid: {
                "paint_string": state.paint_string,
                "ports": {
                    str(p): {"value": r.value, "state": r.state}
                    for p, r in state.ports.items()
                },
            }
            for oid, state in (coordinator.data or {}).items()
        },
    }
