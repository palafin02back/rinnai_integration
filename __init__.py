"""The Rinnai integration."""

from __future__ import annotations

import logging
from typing import TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import RinnaiClient
from .const import (
    CONF_CONNECT_TIMEOUT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import RinnaiCoordinator

_LOGGER = logging.getLogger(__name__)

RinnaiConfigEntry = TypeVar("RinnaiConfigEntry", bound=ConfigEntry)


async def async_setup_entry(hass: HomeAssistant, entry: RinnaiConfigEntry) -> bool:
    """Set up Rinnai from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Extract configuration
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    update_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    connect_timeout = entry.options.get(CONF_CONNECT_TIMEOUT, DEFAULT_CONNECT_TIMEOUT)

    # Create unified client
    client = RinnaiClient(
        hass=hass,
        username=username,
        password=password,
        update_interval=update_interval,
        connect_timeout=connect_timeout,
    )

    # Initialize client
    if not await client.async_initialize():
        raise ConfigEntryNotReady("Failed to initialize Rinnai client")

    # Create data coordinator
    coordinator = RinnaiCoordinator(
        hass=hass,
        client=client,
        update_interval=update_interval,
    )

    # Initial data fetch
    await coordinator.async_config_entry_first_refresh()

    if not coordinator.data.get("devices"):
        raise ConfigEntryNotReady("No devices found")

    # Store the coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up all supported platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: RinnaiConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: RinnaiCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.async_close()

    return unload_ok
