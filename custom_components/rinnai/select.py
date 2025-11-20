"""Support for Rinnai select entities."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RinnaiCoordinator

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
        entities.append(RinnaiHeatingReservationModeSelect(coordinator, device_id))

    async_add_entities(entities)


class RinnaiHeatingReservationModeSelect(CoordinatorEntity, SelectEntity):
    """Representation of a Rinnai heating reservation mode select."""

    _attr_options = ["Mode 1", "Mode 2", "Mode 3", "Mode 4", "Mode 5"]

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        
        device = coordinator.get_device(device_id)
        if device:
            self._attr_unique_id = f"{device_id}_reservation_mode"
            self._attr_has_entity_name = True
            self._attr_translation_key = "reservation_mode"
            self._attr_device_info = {
                "identifiers": {(DOMAIN, device_id)},
                "name": device.device_name,
                "manufacturer": "Rinnai",
                "model": device.device_type,
            }
        
        
        self._update_attributes()

    @property
    def _device(self):
        return self.coordinator.get_device(self._device_id)

    @property
    def _device_state(self):
        return self.coordinator.get_device_state(self._device_id)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self._device or not self._device.online:
            return False
            
        # Check if reservation is on
        state = self._device_state
        if not state:
            return False
            
        # Try to get from byteStr (HTTP) first, then heatingReservationMode (MQTT)
        raw_hex = state.raw_data.get("byteStr") or state.raw_data.get("heatingReservationMode")
        
        if not raw_hex or len(raw_hex) < 2:
            return False
            
        try:
            # Byte 0 is status (00=Off, 01=On)
            status_byte = int(raw_hex[0:2], 16)
            return status_byte == 1
        except ValueError:
            return False

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        state = self._device_state
        if not state:
            return

        # Try to get from byteStr (HTTP) first, then heatingReservationMode (MQTT)
        raw_hex = state.raw_data.get("byteStr") or state.raw_data.get("heatingReservationMode")
        if not raw_hex or len(raw_hex) < 4:
            self._attr_current_option = None
            return

        try:
            # Byte 1 is mode index (1-5)
            mode_index = int(raw_hex[2:4], 16)
            if 1 <= mode_index <= 5:
                self._attr_current_option = f"Mode {mode_index}"
            else:
                self._attr_current_option = None
        except ValueError:
            self._attr_current_option = None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        state = self._device_state
        if not state:
            return

        # Try to get from byteStr (HTTP) first, then heatingReservationMode (MQTT)
        raw_hex = state.raw_data.get("byteStr") or state.raw_data.get("heatingReservationMode")
        if not raw_hex or len(raw_hex) < 34:
            _LOGGER.warning("Cannot set reservation mode: heatingReservationMode not available")
            return

        try:
            mode_index = int(option.split(" ")[1])
            
            # Construct new hex
            # Byte 0 is status (Force to 01=On when switching modes)
            # Byte 1 is mode index (at index 2-4)
            new_status_hex = "01"
            new_mode_hex = f"{mode_index:02X}"
            
            # Start building the new hex string
            # We take the original hex, but replace the first 4 characters (Status + Mode Index)
            # new_full_hex = new_status_hex + new_mode_hex + raw_hex[4:]
            
            # Handle presets for Mode 1-3
            device = self._device
            preset_hex = None
            if device and device.config:
                presets = device.config.features.get("reservation_mode_presets", {})
                preset_hex = presets.get(str(mode_index))
            
            if preset_hex and len(preset_hex) == 34:
                # Full hex string preset provided by user
                new_full_hex = preset_hex
                _LOGGER.debug("Applying full preset for Mode %d: %s", mode_index, preset_hex)
            elif preset_hex and len(preset_hex) == 6:
                # If we have a preset, we need to replace the specific 3 bytes (6 chars) for this mode
                # The schedule data starts at index 4 (after Status and Mode Index)
                # Mode 1: index 4-10
                # Mode 2: index 10-16
                # Mode 3: index 16-22
                # Mode 4: index 22-28
                # Mode 5: index 28-34
                
                start_idx = 4 + ((mode_index - 1) * 6)
                end_idx = start_idx + 6
                
                # Reconstruct the full hex string
                # 1. New Status (01)
                # 2. New Mode Index
                # 3. Data before the target mode
                # 4. New Preset Data for the target mode
                # 5. Data after the target mode
                
                new_full_hex = (
                    new_status_hex + 
                    new_mode_hex + 
                    raw_hex[4:start_idx] + 
                    preset_hex + 
                    raw_hex[end_idx:]
                )
                _LOGGER.debug("Applying preset for Mode %d: %s", mode_index, preset_hex)
            else:
                # No preset, just change status and mode index, keep existing schedule data
                new_full_hex = new_status_hex + new_mode_hex + raw_hex[4:]
            
            _LOGGER.debug("Setting reservation mode to %s (%d)", option, mode_index)
            
            # Use HTTP method to save schedule
            if await self.coordinator.client.save_schedule_hour(self._device_id, new_full_hex):
                # Refresh schedule info to confirm change
                await self.coordinator.async_refresh_schedule(self._device_id)
                
                # Optimistic update
                self._attr_current_option = option
                self.async_write_ha_state()
            else:
                _LOGGER.error("Failed to set reservation mode")
            
        except (ValueError, IndexError):
            _LOGGER.error("Invalid option selected: %s", option)
