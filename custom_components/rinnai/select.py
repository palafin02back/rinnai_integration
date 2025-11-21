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
        self._attr_options = config.get("options", [])
        self._command_type = config.get("command_type")
        self._update_attributes()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        if self._command_type == "schedule_mode":
            self._update_schedule_mode()

    def _update_schedule_mode(self) -> None:
        raw_hex = self.get_state_value("byte_str") or self.get_state_value("reservation_mode")
        if not raw_hex or len(raw_hex) < 4:
            self._attr_current_option = None
            return

        try:
            # Byte 1 is mode index (1-5)
            mode_index = int(raw_hex[2:4], 16)
            if 1 <= mode_index <= 5 and mode_index <= len(self.options):
                # Assuming options are ordered "Mode 1", "Mode 2"...
                # Or we can try to match index
                self._attr_current_option = self.options[mode_index - 1]
            else:
                self._attr_current_option = None
        except (ValueError, IndexError):
            self._attr_current_option = None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if self._command_type == "schedule_mode":
            await self._set_schedule_mode(option)

    async def _set_schedule_mode(self, option: str) -> None:
        try:
            mode_index = self.options.index(option) + 1
        except ValueError:
            return

        raw_hex = self.get_state_value("byte_str") or self.get_state_value("reservation_mode")
        if not raw_hex or len(raw_hex) < 34:
            return

        # Construct new hex
        new_status_hex = "01"
        new_mode_hex = f"{mode_index:02X}"
        
        # Handle presets
        device = self._device
        preset_hex = None
        if device and device.config:
            presets = device.config.features.get("reservation_mode_presets", {})
            preset_hex = presets.get(str(mode_index))
        
        if preset_hex and len(preset_hex) == 34:
            new_full_hex = preset_hex
        elif preset_hex and len(preset_hex) == 6:
            start_idx = 4 + ((mode_index - 1) * 6)
            end_idx = start_idx + 6
            new_full_hex = (
                new_status_hex + 
                new_mode_hex + 
                raw_hex[4:start_idx] + 
                preset_hex + 
                raw_hex[end_idx:]
            )
        else:
            new_full_hex = new_status_hex + new_mode_hex + raw_hex[4:]
        
        if await self.coordinator.client.save_schedule_hour(self._device_id, new_full_hex):
            await self.coordinator.async_refresh_schedule(self._device_id)
            self._attr_current_option = option
            self.async_write_ha_state()
