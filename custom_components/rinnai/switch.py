"""Support for Rinnai switches."""
from __future__ import annotations

import logging
from homeassistant.components.switch import SwitchEntity
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
    """Set up the Rinnai switches."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for device_id in coordinator.data["devices"]:
        # Add heating reservation switch
        entities.append(RinnaiHeatingReservationSwitch(coordinator, device_id))

    async_add_entities(entities)


class RinnaiHeatingReservationSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of Rinnai heating reservation switch."""

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._device_id = device_id
        
        device = coordinator.get_device(device_id)
        if device:
            self._attr_unique_id = f"{device_id}_heating_reservation_switch"
            self._attr_has_entity_name = True
            self._attr_translation_key = "heating_reservation"
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
            self._attr_is_on = None
            return

        # Try to get from byteStr (HTTP) first, then heatingReservationMode (MQTT)
        raw_hex = state.raw_data.get("byteStr") or state.raw_data.get("heatingReservationMode")
        
        if not raw_hex or len(raw_hex) < 2:
            self._attr_is_on = None
            return

        try:
            # Byte 0 is status (00=Off, 01=On)
            status_byte = int(raw_hex[0:2], 16)
            self._attr_is_on = (status_byte == 1)
        except ValueError:
            self._attr_is_on = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._set_reservation_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._set_reservation_state(False)

    async def _set_reservation_state(self, is_on: bool) -> None:
        state = self._device_state
        if not state:
            return

        # Try to get from byteStr (HTTP) first, then heatingReservationMode (MQTT)
        raw_hex = state.raw_data.get("byteStr") or state.raw_data.get("heatingReservationMode")
        
        if not raw_hex or len(raw_hex) < 34:
            _LOGGER.warning("Cannot set reservation state: schedule data not available")
            return

        # Construct new hex
        # Byte 0 is at index 0-2
        new_status_hex = "01" if is_on else "00"
        new_full_hex = new_status_hex + raw_hex[2:]
        
        _LOGGER.debug("Setting reservation state to %s", "On" if is_on else "Off")
        
        # Use HTTP method to save schedule
        if await self.coordinator.client.save_schedule_hour(self._device_id, new_full_hex):
            # Refresh schedule info to confirm change
            await self.coordinator.async_refresh_schedule(self._device_id)
            
            # Optimistic update
            self._attr_is_on = is_on
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set reservation state")
