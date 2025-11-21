"""Support for Rinnai sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import RinnaiCoordinator
from .entity import RinnaiEntity
from .core.util import decode_schedule_bitmap, format_schedule_string

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Rinnai sensors based on a config entry."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for device_id in coordinator.data["devices"]:
        device = coordinator.get_device(device_id)
        if not device or not device.config:
            continue
            
        # Generic sensors from config
        if sensor_configs := device.config.entities.get("sensor"):
            for config in sensor_configs:
                sensor_type = config.get("type", "generic")
                if sensor_type == "reservation_sensor":
                    entities.append(RinnaiHeatingReservationSensor(coordinator, device_id, config))
                else:
                    entities.append(RinnaiGenericSensor(coordinator, device_id, config))

    async_add_entities(entities)


class RinnaiGenericSensor(RinnaiEntity, SensorEntity, RestoreEntity):
    """Representation of a generic Rinnai sensor defined in config."""

    def __init__(
        self,
        coordinator: RinnaiCoordinator,
        device_id: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_id, config)
        
        # Set up entity description based on config
        description = SensorEntityDescription(
            key=config.get("key"),
            name=config.get("name"),
            device_class=config.get("device_class"),
            state_class=config.get("state_class"),
            native_unit_of_measurement=config.get("unit_of_measurement"),
            entity_category=config.get("entity_category"),
        )
        self.entity_description = description
        self._value_map = config.get("value_map")
        self._state_attribute = config.get("state_attribute")
        self._restored_native_value = None

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                if last_state.state not in (None, "unknown", "unavailable"):
                    if self.device_class in (SensorDeviceClass.DURATION, SensorDeviceClass.GAS, SensorDeviceClass.TEMPERATURE):
                        self._restored_native_value = float(last_state.state)
                    else:
                        self._restored_native_value = last_state.state
            except (ValueError, TypeError):
                pass
        
        self._update_attributes()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle device updates."""
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        """Update sensor attributes based on device state."""
        if not self._state_attribute:
            return

        raw_value = self.get_state_value(self._state_attribute)
        
        if self._value_map and str(raw_value) in self._value_map:
            current_value = self._value_map[str(raw_value)]
        else:
            current_value = raw_value
            
        # Handle cumulative stats restoration
        is_cumulative = self.entity_description.state_class == SensorStateClass.TOTAL_INCREASING
        if (current_value is None or (is_cumulative and current_value == 0)) and self._restored_native_value is not None:
             self._attr_native_value = self._restored_native_value
        else:
             self._attr_native_value = current_value


class RinnaiHeatingReservationSensor(RinnaiEntity, SensorEntity):
    """Representation of Rinnai heating reservation status."""

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any]) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_id, config)
        self._attr_translation_key = "heating_reservation"

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        # Use generic get_state_value to get byteStr or heatingReservationMode
        # The key "byte_str" or "reservation_mode" should be mapped in config
        raw_hex = self.get_state_value("byte_str") or self.get_state_value("reservation_mode")
        
        if not raw_hex or len(raw_hex) < 34:
            self._attr_native_value = "Unknown"
            return

        try:
            status_byte = int(raw_hex[0:2], 16)
            mode_index = int(raw_hex[2:4], 16)
            
            self._attr_native_value = "On" if status_byte == 1 else "Off"
            
            attrs = {
                "current_mode_index": mode_index,
                "raw_hex": raw_hex
            }
            
            # Parse 5 modes
            for i in range(5):
                start_idx = 4 + (i * 6)
                mode_hex = raw_hex[start_idx : start_idx + 6]
                active_hours = decode_schedule_bitmap(mode_hex)
                schedule_str = format_schedule_string(active_hours)
                attrs[f"mode_{i+1}_schedule"] = schedule_str
                
                if (i + 1) == mode_index:
                    attrs["current_schedule"] = schedule_str
            
            self._attr_extra_state_attributes = attrs
            
        except ValueError:
            self._attr_native_value = "Error"
