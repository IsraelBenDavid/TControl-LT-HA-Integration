"""Config flow for TControl LT16."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CONNECTION_TYPE,
    CONF_NUM_CHANNELS,
    CONF_SERIAL_PORT,
    CONF_TCP_HOST,
    CONF_TCP_PORT,
    CONNECTION_TYPE_SERIAL,
    CONNECTION_TYPE_TCP,
    DEFAULT_NUM_CHANNELS,
    DEFAULT_SERIAL_PORT,
    DEFAULT_TCP_PORT,
    DOMAIN,
)
from .hub import TControlHub


async def _test_connection(hass: HomeAssistant, hub: TControlHub) -> bool:
    """Test the connection in the executor."""
    return await hass.async_add_executor_job(hub.test_connection)


class TControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TControl LT16."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._connection_type: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1 — choose connection type."""
        if user_input is not None:
            self._connection_type = user_input[CONF_CONNECTION_TYPE]
            if self._connection_type == CONNECTION_TYPE_SERIAL:
                return await self.async_step_serial()
            return await self.async_step_tcp()

        schema = vol.Schema(
            {
                vol.Required(CONF_CONNECTION_TYPE, default=CONNECTION_TYPE_SERIAL): vol.In(
                    {
                        CONNECTION_TYPE_SERIAL: "Serial",
                        CONNECTION_TYPE_TCP: "TCP",
                    }
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2a — serial settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
                CONF_SERIAL_PORT: user_input[CONF_SERIAL_PORT],
                CONF_NUM_CHANNELS: user_input[CONF_NUM_CHANNELS],
            }
            hub = TControlHub(data)

            # Prevent duplicate entries for the same port
            await self.async_set_unique_id(hub.identifier)
            self._abort_if_unique_id_configured()

            if await _test_connection(self.hass, hub):
                return self.async_create_entry(
                    title=f"TControl ({hub.identifier})", data=data
                )
            errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL_PORT, default=DEFAULT_SERIAL_PORT): str,
                vol.Required(CONF_NUM_CHANNELS, default=DEFAULT_NUM_CHANNELS): vol.All(
                    int, vol.Range(min=1, max=16)
                ),
            }
        )
        return self.async_show_form(
            step_id="serial", data_schema=schema, errors=errors
        )

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2b — TCP settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_TCP,
                CONF_TCP_HOST: user_input[CONF_TCP_HOST],
                CONF_TCP_PORT: user_input[CONF_TCP_PORT],
                CONF_NUM_CHANNELS: user_input[CONF_NUM_CHANNELS],
            }
            hub = TControlHub(data)

            await self.async_set_unique_id(hub.identifier)
            self._abort_if_unique_id_configured()

            if await _test_connection(self.hass, hub):
                return self.async_create_entry(
                    title=f"TControl ({hub.identifier})", data=data
                )
            errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_TCP_HOST): str,
                vol.Required(CONF_TCP_PORT, default=DEFAULT_TCP_PORT): int,
                vol.Required(CONF_NUM_CHANNELS, default=DEFAULT_NUM_CHANNELS): vol.All(
                    int, vol.Range(min=1, max=16)
                ),
            }
        )
        return self.async_show_form(step_id="tcp", data_schema=schema, errors=errors)
