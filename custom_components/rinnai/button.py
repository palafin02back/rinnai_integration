"""Support for stateless Rinnai device commands."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import RinnaiCoordinator
from .core.command import RinnaiCommand
from .entity import RinnaiEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up configured Rinnai buttons."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[RinnaiCommandButton] = []

    for device_id in coordinator.data["devices"]:
        device = coordinator.get_device(device_id)
        if not device or not device.config:
            continue
        for config in device.config.entities.get("button", []):
            if config.get("type") == "command_button":
                entities.append(RinnaiCommandButton(coordinator, device_id, config))

    _LOGGER.debug("Setting up %d button entities", len(entities))
    async_add_entities(entities)


class RinnaiCommandButton(RinnaiEntity, ButtonEntity):
    """A button for a device command whose protocol semantics are toggle-only."""

    def __init__(
        self,
        coordinator: RinnaiCoordinator,
        device_id: str,
        config: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, device_id, config)
        self._command_key = config["command_key"]
        self._command_value = config["command_value"]

    async def async_press(self) -> None:
        """Send one stateless command and leave state reporting to sensors."""
        if not await self.coordinator.async_send_command(
            self._device_id,
            RinnaiCommand.stateless({self._command_key: self._command_value}),
        ):
            _LOGGER.error("Failed to send button command: %s", self._command_key)
