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
        self._command_type = config["command_type"]
        self._mode_index = config.get("mode_index")
        self._state_attribute = config.get("state_attribute")
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
        if not self.schedule_manager or not self._state_attribute:
            return

        raw_hex = self.get_state_value(self._state_attribute)
        schedule_str = self.schedule_manager.parse_schedule(raw_hex, self._mode_index)
        
        if schedule_str:
            self._attr_native_value = schedule_str

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""
        if self._command_type == "schedule_data" and self._mode_index:
            await self._set_schedule_data(value)

    async def _set_schedule_data(self, value: str) -> None:
        if not self.schedule_manager or not self._state_attribute:
            return

        raw_hex = self.get_state_value(self._state_attribute)
        new_hex = self.schedule_manager.update_schedule_data(raw_hex, self._mode_index, value)
        
        if not new_hex:
            return
            
        if await self.coordinator.client.save_schedule_hour(self._device_id, new_hex):
            await self.coordinator.async_refresh_schedule(self._device_id)
            self._attr_native_value = value
            self.async_write_ha_state()
