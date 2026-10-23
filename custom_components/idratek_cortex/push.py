"""Receive Cortex Web API Client callbacks (webhook push)."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from homeassistant.components import webhook
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import DECIMAL_PUSH_PORTS, DOMAIN, LOGGER, PUSH_PORTS, TYPE_HVAC
from .coordinator import CortexConfigEntry, CortexCoordinator

ID_KEYS = ("id", "idnumber", "object", "objectid")
PORT_KEYS = ("port", "portnumber")
VALUE_KEYS = ("value",)


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


def push_cheatsheet(coordinator: CortexCoordinator) -> str:
    """Markdown list of the id/port values to enter in each Cortex Web API Client entry."""
    lines: list[str] = []
    for obj in sorted(coordinator.objects.values(), key=lambda o: (o.type, o.name.lower())):
        if obj.type == TYPE_HVAC:
            lines.append(f"- {obj.name} (HVAC): `id` = {obj.object_id} only")
            continue
        for port, label in PUSH_PORTS.get(obj.type, ()):
            fmt = "?" if (obj.type, port) in DECIMAL_PUSH_PORTS else "?0"
            lines.append(
                f"- {obj.name} ({obj.type}): `id` = {obj.object_id}, `port` = {port}, "
                f"`value` = `<{obj.name}.{label}={fmt}>`"
            )
    return "\n".join(lines) or "No pushable objects found."


def _flatten(data: Any, into: dict[str, str]) -> None:
    """Collect scalar values by lower-case key from any nesting; first one wins."""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict | list):
                _flatten(value, into)
            elif value is not None:
                into.setdefault(str(key).lower(), str(value))
    elif isinstance(data, list):
        for item in data:
            _flatten(item, into)


async def _params(request: web.Request) -> dict[str, str]:
    """Query parameters first, then a JSON or form body."""
    params: dict[str, str] = {}
    _flatten(dict(request.query), params)
    if request.can_read_body:
        try:
            _flatten(await request.json(), params)
        except ValueError:
            try:
                _flatten(dict(await request.post()), params)
            except ValueError:
                pass
    return params


def _first(params: dict[str, str], keys: tuple[str, ...]) -> str | None:
    return next((params[key] for key in keys if key in params), None)


def async_register_push(hass: HomeAssistant, entry: CortexConfigEntry) -> None:
    """Register the webhook; unregister automatically on unload."""
    coordinator = entry.runtime_data

    async def _handle(
        hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> web.Response:
        params = await _params(request)
        object_id = _first(params, ID_KEYS)
        if object_id is None or object_id not in coordinator.objects:
            LOGGER.debug("Cortex push without a known object id (%s); full refresh", object_id)
            await coordinator.async_request_refresh()
            return web.Response(status=200)

        port_text, value = _first(params, PORT_KEYS), _first(params, VALUE_KEYS)
        if port_text is not None and value is not None and port_text.strip().isdigit():
            if await coordinator.async_apply_push(object_id, int(port_text), value):
                LOGGER.debug("Cortex push applied: %s port %s = %s", object_id, port_text, value)
                return web.Response(status=200)
            LOGGER.debug(
                "Cortex push for %s port %s value %r not applicable; refreshing",
                object_id,
                port_text,
                value,
            )
        await coordinator.async_refresh_object(object_id)
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
