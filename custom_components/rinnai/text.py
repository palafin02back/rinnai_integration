"""Support for Rinnai text entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import RinnaiCoordinator
from .entity import RinnaiEntity
from .core.util import decode_schedule_bitmap, format_schedule_string, parse_schedule_string

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Rinnai text entities."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for device_id in coordinator.data["devices"]:
        device = coordinator.get_device(device_id)
        if not device or not device.config:
            continue
            
        if text_configs := device.config.entities.get("text"):
            for config in text_configs:
                entities.append(RinnaiGenericText(coordinator, device_id, config))

    async_add_entities(entities)


class RinnaiGenericText(RinnaiEntity, TextEntity):
    """Representation of a generic Rinnai text entity."""

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any]) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator, device_id, config)
        self._command_type = config.get("command_type")
        self._mode_index = config.get("mode_index")
        self._attr_native_value = "Unknown"
        self._update_attributes()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        if self._command_type == "schedule_data" and self._mode_index:
            self._update_schedule_data()

    def _update_schedule_data(self) -> None:
        raw_hex = self.get_state_value("byte_str") or self.get_state_value("reservation_mode")
        if not raw_hex or len(raw_hex) < 34:
            return

        try:
            start_idx = 4 + (self._mode_index - 1) * 6
            mode_hex = raw_hex[start_idx : start_idx + 6]
            
            active_hours = decode_schedule_bitmap(mode_hex)
            self._attr_native_value = format_schedule_string(active_hours)
        except ValueError:
            pass

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""
        if self._command_type == "schedule_data" and self._mode_index:
            await self._set_schedule_data(value)

    async def _set_schedule_data(self, value: str) -> None:
        raw_hex = self.get_state_value("byte_str") or self.get_state_value("reservation_mode")
        if not raw_hex or len(raw_hex) < 34:
            return

        new_mode_hex = parse_schedule_string(value)
        start_idx = 4 + (self._mode_index - 1) * 6
        
        prefix = raw_hex[:start_idx]
        suffix = raw_hex[start_idx + 6:]
        
        new_full_hex = prefix + new_mode_hex + suffix
        
        if await self.coordinator.client.save_schedule_hour(self._device_id, new_full_hex):
            await self.coordinator.async_refresh_schedule(self._device_id)
            self._attr_native_value = value
            self.async_write_ha_state()
