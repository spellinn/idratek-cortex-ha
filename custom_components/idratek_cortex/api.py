"""Async client for the Idratek Cortex Web API (JSON, HTTP Basic auth)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import LOGGER, MAX_CONCURRENT_REQUESTS, REQUEST_TIMEOUT


class CortexError(Exception):
    """Base error for the Cortex client."""


class CortexConnectionError(CortexError):
    """The controller could not be reached."""


class CortexAuthError(CortexError):
    """The controller rejected the credentials or the object is not exposed."""


class CortexApiError(CortexError):
    """The controller returned an unexpected response."""


@dataclass(frozen=True, slots=True)
class CortexObject:
    """A Cortex control object as listed by /api/v1/Objects.json."""

    object_id: str
    name: str
    type: str
    parent: str | None
    attributes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PortReading:
    """Value and state of one object port."""

    value: float | None
    state: bool | None


def _to_float(raw: Any) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _to_bool(raw: Any) -> bool | None:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in ("true", "1"):
            return True
        if lowered in ("false", "0"):
            return False
    return None


def _find_objects(data: Any) -> list[dict[str, Any]]:
    """Collect every dict that looks like a Cortex object, whatever the nesting."""
    found: list[dict[str, Any]] = []
    if isinstance(data, dict):
        if "IDNumber" in data and "ControlObjectType" in data:
            found.append(data)
        else:
            for value in data.values():
                found.extend(_find_objects(value))
    elif isinstance(data, list):
        for item in data:
            found.extend(_find_objects(item))
    return found


def _as_object(raw: dict[str, Any]) -> CortexObject:
    return CortexObject(
        object_id=str(raw["IDNumber"]),
        name=str(raw.get("FriendlyName", raw["IDNumber"])),
        type=str(raw["ControlObjectType"]),
        parent=raw.get("Parent"),
        attributes=raw,
    )


class CortexClient:
    """Thin async wrapper around the Cortex Web API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        username: str,
        password: str,
    ) -> None:
        """Initialise the client with a shared Home Assistant websession."""
        self._session = session
        self._base = f"http://{host}:{port}/api/v1"
        self._auth = aiohttp.BasicAuth(username, password)
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
    ) -> Any:
        url = f"{self._base}{path}"
        try:
            async with (
                self._semaphore,
                asyncio.timeout(REQUEST_TIMEOUT),
                self._session.request(
                    method,
                    url,
                    auth=self._auth,
                    headers={"Accept": "application/json"},
                    json=json_body,
                ) as response,
            ):
                if response.status in (401, 403):
                    raise CortexAuthError(f"HTTP {response.status} from {path}")
                if response.status >= 400:
                    raise CortexApiError(f"HTTP {response.status} from {path}")
                if response.status == 204:
                    return None
                text = await response.text()
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CortexConnectionError(str(err)) from err

        if not text.strip():
            return None
        try:
            return json.loads(text)
        except ValueError as err:
            raise CortexApiError(f"Invalid JSON from {path}") from err

    # ------------------------------------------------------------------ reads
    async def get_objects(self) -> dict[str, CortexObject]:
        """Return every object exposed by the Web API, keyed by object ID."""
        data = await self._request("GET", "/Objects.json")
        return {obj.object_id: obj for obj in map(_as_object, _find_objects(data))}

    async def get_object(self, object_id: str) -> CortexObject | None:
        """Return one object including live attributes such as PaintString."""
        data = await self._request("GET", f"/Objects.json/{quote(object_id, safe='')}")
        for raw in _find_objects(data):
            if str(raw["IDNumber"]) == object_id:
                return _as_object(raw)
        return None

    async def read_port(self, object_id: str, port: int) -> PortReading:
        """Read one port: CortexAPI.PortEvent.{Value,State}."""
        data = await self._request("GET", f"/json/Ports/{quote(object_id, safe='')}/{port}")
        try:
            event = data["CortexAPI"]["PortEvent"]
        except (KeyError, TypeError) as err:
            raise CortexApiError(f"Unexpected port payload for {object_id}/{port}") from err
        return PortReading(_to_float(event.get("Value")), _to_bool(event.get("State")))

    # ---------------------------------------------------------------- actions
    async def write_port_value(self, object_id: str, port: int, value: float | str) -> None:
        """Write a value to a ValueIn port."""
        body = {"CortexAPI": {"PortEvent": {"Value": str(value)}}}
        await self._request(
            "POST", f"/json/Ports/{quote(object_id, safe='')}/{port}", json_body=body
        )

    async def trigger(self, object_name: str, object_id: str, description: str, port: int) -> None:
        """Fire an In port.

        Primary: POST /json/objects/<name>?<port description>=1 (the form
        documented in the Cortex/HA integration guide). Fallback: write 1 to
        the port directly.
        """
        try:
            await self._request(
                "POST",
                # Spaces must be %20 (not '+'): Cortex matches the description text.
                f"/json/objects/{quote(object_name, safe='')}?{quote(description, safe='')}=1",
                json_body={},
            )
        except CortexApiError as err:
            LOGGER.debug(
                "Named trigger %s/%s failed (%s); writing port %s directly",
                object_name,
                description,
                err,
                port,
            )
            await self.write_port_value(object_id, port, 1)
