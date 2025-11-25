"""Support for Rinnai select entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import RinnaiCoordinator
from .entity import RinnaiEntity
from .core.schedule_manager import RinnaiScheduleManager

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Rinnai select entities."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for device_id in coordinator.data["devices"]:
        device = coordinator.get_device(device_id)
        if not device or not device.config:
            continue
            
        if select_configs := device.config.entities.get("select"):
            for config in select_configs:
                entities.append(RinnaiGenericSelect(coordinator, device_id, config))

    async_add_entities(entities)


class RinnaiGenericSelect(RinnaiEntity, SelectEntity):
    """Representation of a generic Rinnai select entity."""

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any]) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, device_id, config)
        self._attr_options = config["options"]
        self._command_type = config["command_type"]
        self._state_attribute = config.get("state_attribute")
        self._update_attributes()

    @property
    def schedule_manager(self) -> RinnaiScheduleManager | None:
        """Get schedule manager instance."""
        if not hasattr(self, "_schedule_manager"):
            if hasattr(self._device.config, "schedule_config"):
                self._schedule_manager = RinnaiScheduleManager(self._device.config.schedule_config)
            else:
                self._schedule_manager = None
        return self._schedule_manager

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        if self._command_type == "schedule_mode":
            self._update_schedule_mode()

    def _update_schedule_mode(self) -> None:
        if not self.schedule_manager or not self._state_attribute:
            return

        raw_hex = self.get_state_value(self._state_attribute)
        mode_index = self.schedule_manager.parse_mode_index(raw_hex)
        
        if mode_index is not None and 1 <= mode_index <= len(self.options):
            self._attr_current_option = self.options[mode_index - 1]
        else:
            self._attr_current_option = None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if self._command_type == "schedule_mode":
            await self._set_schedule_mode(option)

    async def _set_schedule_mode(self, option: str) -> None:
        if not self.schedule_manager or not self._state_attribute:
            return

        try:
            mode_index = self.options.index(option) + 1
        except ValueError:
            return

        raw_hex = self.get_state_value(self._state_attribute)
        
        # First update mode index
        new_hex = self.schedule_manager.update_mode_index(raw_hex, mode_index)
        if not new_hex:
            return
            
        # Ensure switch is ON when selecting mode
        new_hex = self.schedule_manager.update_status(new_hex, True)

        # Apply preset if configured for this mode
        
        preset_hex = None
        device = self._device
        if device and device.config:
            presets = device.config.features.get("reservation_mode_presets", {})
            preset_hex = presets.get(str(mode_index))
            
        if preset_hex:
            
            # 1. Extract schedule string from preset for this mode
            preset_schedule_str = self.schedule_manager.parse_schedule(preset_hex, mode_index)
            
            # 2. Update our new_hex with this schedule data
            if preset_schedule_str:
                updated_hex = self.schedule_manager.update_schedule_data(new_hex, mode_index, preset_schedule_str)
                if updated_hex:
                    new_hex = updated_hex

        if await self.coordinator.client.save_schedule_hour(self._device_id, new_hex):
            await self.coordinator.async_refresh_schedule(self._device_id)
            self._attr_current_option = option
            self.async_write_ha_state()
