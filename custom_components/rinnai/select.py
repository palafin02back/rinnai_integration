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

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        state = self._device_state
        if not state:
            return

        raw_hex = state.raw_data.get("heatingReservationMode")
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

        raw_hex = state.raw_data.get("heatingReservationMode")
        if not raw_hex or len(raw_hex) < 34:
            _LOGGER.warning("Cannot set reservation mode: heatingReservationMode not available")
            return

        try:
            mode_index = int(option.split(" ")[1])
            
            # Construct new hex
            # Byte 1 is at index 2-4
            new_mode_hex = f"{mode_index:02X}"
            new_full_hex = raw_hex[:2] + new_mode_hex + raw_hex[4:]
            
            _LOGGER.debug("Setting reservation mode to %s (%d)", option, mode_index)
            
            command = {"heatingReservationMode": new_full_hex}
            await self.coordinator.async_send_command(self._device_id, command)
            
            # Optimistic update
            self._attr_current_option = option
            self.async_write_ha_state()
            
        except (ValueError, IndexError):
            _LOGGER.error("Invalid option selected: %s", option)
