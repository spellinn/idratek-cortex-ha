"""Config flow for Idratek Cortex."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import probatio

from homeassistant.config_entries import (
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CortexAuthError, CortexClient, CortexError, CortexObject
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    TYPE_HOUSE,
)
from .coordinator import CortexConfigEntry
from .push import push_cheatsheet, webhook_urls

USER_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): str,
        probatio.Required(CONF_PORT, default=DEFAULT_PORT): int,
        probatio.Required(CONF_USERNAME): str,
        probatio.Required(CONF_PASSWORD): str,
    }
)
REAUTH_SCHEMA = probatio.Schema(
    {probatio.Required(CONF_USERNAME): str, probatio.Required(CONF_PASSWORD): str}
)


def _identify(objects: dict[str, CortexObject], host: str, port: int) -> tuple[str, str]:
    """Return (unique_id, title). Prefer the House object, which survives IP changes."""
    for obj in objects.values():
        if obj.type == TYPE_HOUSE:
            return f"house-{obj.object_id}", f"Cortex: {obj.name}"
    return f"{host}:{port}", f"Cortex ({host})"


class CortexConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Idratek Cortex."""

    VERSION = 1

    async def _validate(
        self, host: str, port: int, username: str, password: str
    ) -> tuple[dict[str, CortexObject] | None, str | None]:
        """Connect and list objects. Returns (objects, error key)."""
        client = CortexClient(async_get_clientsession(self.hass), host, port, username, password)
        try:
            return await client.get_objects(), None
        except CortexAuthError:
            return None, "invalid_auth"
        except CortexError:
            return None, "cannot_connect"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initial step: host and credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            objects, error = await self._validate(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if objects is not None:
                unique_id, title = _identify(objects, user_input[CONF_HOST], user_input[CONF_PORT])
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=title, data=user_input)
            errors["base"] = error or "unknown"
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after credentials were rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            objects, error = await self._validate(
                entry.data[CONF_HOST],
                entry.data[CONF_PORT],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if objects is not None:
                unique_id, _ = _identify(objects, entry.data[CONF_HOST], entry.data[CONF_PORT])
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
            errors["base"] = error or "unknown"
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                REAUTH_SCHEMA, user_input or {CONF_USERNAME: entry.data[CONF_USERNAME]}
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change host, port or credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            objects, error = await self._validate(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if objects is not None:
                unique_id, _ = _identify(objects, user_input[CONF_HOST], user_input[CONF_PORT])
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
            errors["base"] = error or "unknown"
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: CortexConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return CortexOptionsFlow()


class CortexOptionsFlow(OptionsFlow):
    """Polling interval and the Cortex push webhook URL."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        urls = webhook_urls(self.hass, self.config_entry.entry_id)
        url_list = "\n".join(f"- {label}: `{url}`" for label, url in urls)
        first_url = urls[0][1]
        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): probatio.All(int, probatio.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL))
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "webhook_urls": url_list,
                "webhook_url": first_url,
                "push_objects": push_cheatsheet(self.config_entry.runtime_data)
                if self.config_entry.state is ConfigEntryState.LOADED
                else "Reload the integration to list objects.",
            },
        )
