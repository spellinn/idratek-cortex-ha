"""Receive Cortex Web API Client callbacks (webhook push)."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from homeassistant.components import webhook
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import DOMAIN, LOGGER
from .coordinator import CortexConfigEntry

ID_KEYS = ("id", "idnumber", "object", "objectid")


def webhook_id_for(entry_id: str) -> str:
    """Webhook ID for a config entry."""
    return f"{DOMAIN}_{entry_id}"


def webhook_urls(hass: HomeAssistant, entry_id: str) -> list[tuple[str, str]]:
    """Return (label, full URL) pairs that Cortex could use, most useful first.

    Cortex is a Windows application and may not resolve '.local' mDNS names, so
    an IP based URL is always offered as well.
    """
    hook = webhook_id_for(entry_id)
    path = webhook.async_generate_path(hook)
    candidates: list[tuple[str, dict[str, Any]]] = [
        ("Address you are using now", {"require_current_request": True}),
        (
            "Internal URL (Settings, System, Network)",
            {"allow_external": False, "allow_cloud": False, "allow_ip": False},
        ),
        (
            "IP address",
            {"allow_external": False, "allow_cloud": False, "allow_ip": True,
             "prefer_external": False},
        ),
    ]
    urls: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, kwargs in candidates:
        try:
            base = get_url(hass, **kwargs)
        except NoURLAvailableError:
            continue
        if base not in seen:
            seen.add(base)
            urls.append((label, f"{base}{path}"))
    if not urls:
        urls.append(("Path only", path))
    return urls


def _extract_id(data: Any) -> str | None:
    """Find an object ID in query parameters or a JSON body (any nesting)."""
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in ID_KEYS and isinstance(value, str | int):
                return str(value)
        for value in data.values():
            if (found := _extract_id(value)) is not None:
                return found
    return None


async def _object_id_from_request(request: web.Request) -> str | None:
    if (found := _extract_id(dict(request.query))) is not None:
        return found
    if request.can_read_body:
        try:
            return _extract_id(await request.json())
        except ValueError:
            try:
                return _extract_id(dict(await request.post()))
            except ValueError:
                return None
    return None


def async_register_push(hass: HomeAssistant, entry: CortexConfigEntry) -> None:
    """Register the webhook; unregister automatically on unload."""
    coordinator = entry.runtime_data

    async def _handle(
        hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> web.Response:
        object_id = await _object_id_from_request(request)
        if object_id is not None and object_id in coordinator.objects:
            LOGGER.debug("Cortex push for object %s", object_id)
            await coordinator.async_refresh_object(object_id)
        else:
            LOGGER.debug("Cortex push without a known object id (%s); full refresh", object_id)
            await coordinator.async_request_refresh()
        return web.Response(status=200)

    hook = webhook_id_for(entry.entry_id)
    webhook.async_register(
        hass,
        DOMAIN,
        "Idratek Cortex",
        hook,
        _handle,
        local_only=True,
        allowed_methods=["GET", "POST", "PUT"],
    )
    entry.async_on_unload(lambda: webhook.async_unregister(hass, hook))
