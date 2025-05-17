"""Config flow for the Rinnai integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .client import RinnaiClient
from .const import (
    CONF_CONNECT_TIMEOUT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]

    client = RinnaiClient(
        hass=hass,
        username=username,
        password=password,
        connect_timeout=DEFAULT_CONNECT_TIMEOUT,
    )

    if not await client.login():
        raise InvalidAuth("Invalid credentials")

    if not await client.fetch_devices():
        raise CannotConnect("No devices found")

    # Get first device info
    devices = client.devices
    if not devices:
        raise CannotConnect("No devices found")

    # Use the first device's name as the title
    device_id = next(iter(devices))
    title = devices[device_id].get("deviceName", "Rinnai Water Heater")

    # Clean up client
    await client.async_close()

    return {"title": title}


class RinnaiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Rinnai."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return RinnaiOptionsFlowHandler(config_entry)


class RinnaiOptionsFlowHandler(OptionsFlow):
    """Handle Rinnai options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = {
            vol.Optional(
                CONF_UPDATE_INTERVAL,
                default=self.config_entry.options.get(
                    CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
            vol.Optional(
                CONF_CONNECT_TIMEOUT,
                default=self.config_entry.options.get(
                    CONF_CONNECT_TIMEOUT, DEFAULT_CONNECT_TIMEOUT
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=60)),
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(options))


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
