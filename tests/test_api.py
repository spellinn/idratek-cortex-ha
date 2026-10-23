"""Client wire-format tests against a real local HTTP server (405 regression)."""

from __future__ import annotations

from aiohttp import ClientSession, web
import pytest

from custom_components.idratek_cortex.api import CortexApiError, CortexClient


@pytest.fixture
async def server(socket_enabled, aiohttp_server):
    seen: list[tuple[str, str, str | None]] = []

    async def handler(request: web.Request) -> web.Response:
        seen.append((request.method, request.raw_path, request.headers.get("Authorization")))
        # Mimic Cortex: POST to /Ports/<id>/<port> is the read form and is refused.
        if request.method == "POST" and request.path.count("/") >= 6:
            return web.Response(status=405)
        return web.json_response({})

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handler)
    srv = await aiohttp_server(app)
    srv.seen = seen
    return srv


@pytest.fixture
async def client(server):
    async with ClientSession() as session:
        yield CortexClient(session, "127.0.0.1", server.port, "ha", "pw")


async def test_write_port_uses_documented_post_form(client, server) -> None:
    await client.write_port_value("42", 31, 21.5)
    method, path, auth = server.seen[-1]
    assert (method, path) == ("POST", "/api/v1/json/Ports/42?31=21.5")
    assert auth == "Basic aGE6cHc="


async def test_set_property(client, server) -> None:
    await client.set_property("42", "HVACMode", 1)
    assert server.seen[-1][:2] == ("POST", "/api/v1/json/Properties/42?HVACMode=1")


async def test_trigger_spaces_stay_percent_encoded(client, server) -> None:
    await client.trigger("Outside light", "130", "Turn On", 5)
    assert server.seen[-1][:2] == (
        "POST",
        "/api/v1/json/objects/Outside%20light?Turn%20On=1",
    )


async def test_old_port_path_is_refused_by_cortex(client, server) -> None:
    with pytest.raises(CortexApiError):
        await client._request("POST", "/json/Ports/42/31", json_body={})
