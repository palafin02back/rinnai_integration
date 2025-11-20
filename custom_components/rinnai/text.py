"""Support for Rinnai heating schedule configuration."""
from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RinnaiCoordinator
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
        # Add configuration for Mode 4 and Mode 5
        entities.append(RinnaiHeatingScheduleTextEntity(coordinator, device_id, 4))
        entities.append(RinnaiHeatingScheduleTextEntity(coordinator, device_id, 5))

    async_add_entities(entities)


class RinnaiHeatingScheduleTextEntity(CoordinatorEntity, TextEntity):
    """Representation of a Rinnai heating schedule configuration."""

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str, mode_index: int) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._mode_index = mode_index
        
        device = coordinator.get_device(device_id)
        if device:
            self._attr_unique_id = f"{device_id}_schedule_mode_{mode_index}"
            self._attr_has_entity_name = True
            self._attr_translation_key = f"schedule_mode_{mode_index}"
            self._attr_device_info = {
                "identifiers": {(DOMAIN, device_id)},
                "name": device.device_name,
                "manufacturer": "Rinnai",
                "model": device.device_type,
            }
        
        
        self._attr_native_value = "Unknown"
        self._update_attributes()

    @property
    def _device(self):
        return self.coordinator.get_device(self._device_id)

    @property
    def _device_state(self):
        return self.coordinator.get_device_state(self._device_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        state = self._device_state
        if not state:
            return

        raw_hex = state.raw_data.get("heatingReservationMode")
        if not raw_hex or len(raw_hex) < 34:
            return

        try:
            # Mode 1 starts at index 4 (byte 2)
            # Mode N starts at 4 + (N-1)*6
            start_idx = 4 + (self._mode_index - 1) * 6
            mode_hex = raw_hex[start_idx : start_idx + 6]
            
            active_hours = decode_schedule_bitmap(mode_hex)
            self._attr_native_value = format_schedule_string(active_hours)
            
        except ValueError:
            pass

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""
        state = self._device_state
        if not state:
            return

        raw_hex = state.raw_data.get("heatingReservationMode")
        if not raw_hex or len(raw_hex) < 34:
            _LOGGER.warning("Cannot set schedule: heatingReservationMode not available")
            return

        # Parse input to hex
        new_mode_hex = parse_schedule_string(value)
        
        # Construct new full hex string
        start_idx = 4 + (self._mode_index - 1) * 6
        
        # Keep everything else the same
        prefix = raw_hex[:start_idx]
        suffix = raw_hex[start_idx + 6:]
        
        new_full_hex = prefix + new_mode_hex + suffix
        
        _LOGGER.debug("Updating schedule for Mode %d: %s -> %s", self._mode_index, value, new_mode_hex)
        
        # Send command
        command = {"heatingReservationMode": new_full_hex}
        await self.coordinator.async_send_command(self._device_id, command)
        
        # Optimistic update
        self._attr_native_value = value
        self.async_write_ha_state()
