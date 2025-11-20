"""Support for Rinnai water heater sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any, Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_BURNING_STATE,
    ATTR_GAS_USAGE,
    ATTR_HEATING_BURNING_TIMES,
    ATTR_HEATING_TEMP_HES,
    ATTR_HEATING_TEMP_NM,
    ATTR_HOT_WATER_BURNING_TIMES,
    ATTR_HOT_WATER_TEMP,
    ATTR_SUPPLY_TIME,
    ATTR_TOTAL_HEATING_BURNING_TIME,
    ATTR_TOTAL_HOT_WATER_BURNING_TIME,
    ATTR_TOTAL_POWER_SUPPLY_TIME,
    DOMAIN,
)
from .coordinator import RinnaiCoordinator
from .models.device import RinnaiDevice

_LOGGER = logging.getLogger(__name__)


from homeassistant.helpers.restore_state import RestoreEntity

from .core.util import decode_schedule_bitmap, format_schedule_string

@dataclass
class RinnaiSensorEntityDescription(SensorEntityDescription):
    """Describes Rinnai sensor entity."""

    value_fn: Callable[[Any, Any], Any] = lambda _, __: None


SENSOR_TYPES: Final[tuple[RinnaiSensorEntityDescription, ...]] = (
    RinnaiSensorEntityDescription(
        key=ATTR_HOT_WATER_TEMP,
        translation_key="hot_water_temperature",
        name="Hot Water Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda _, state: state.hot_water_temp if state else 0,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_HEATING_TEMP_NM,
        translation_key="heating_temperature_nm",
        name="Heating Temperature (Normal Mode)",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda _, state: state.heating_temp_nm if state else 0,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_HEATING_TEMP_HES,
        translation_key="heating_temperature_hes",
        name="Heating Temperature (Energy Saving)",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda _, state: state.heating_temp_hes if state else 0,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_BURNING_STATE,
        translation_key="burning_state",
        name="Burning State",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _, state: state.burning_state_ha if state else "Standby",
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_GAS_USAGE,
        translation_key="gas_usage",
        name="Gas Usage",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="m³",
        value_fn=lambda _, state: state.gas_used if state else None,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_SUPPLY_TIME,
        translation_key="supply_time",
        name="Supply Time",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda _, state: round(state.supply_time*10/24, 2) if state else None,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_TOTAL_POWER_SUPPLY_TIME,
        translation_key="total_power_supply_time",
        name="Total Power Supply Time",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda _, state: round(state.total_power_supply_time*10/24, 2)
        if state
        else None,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_TOTAL_HEATING_BURNING_TIME,
        translation_key="total_heating_burning_time",
        name="Total Heating Burning Time",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda _, state: state.total_heating_burning_time
        if state
        else None,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_TOTAL_HOT_WATER_BURNING_TIME,
        translation_key="total_hot_water_burning_time",
        name="Total Hot Water Burning Time",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda _, state: state.total_hot_water_burning_time
        if state
        else None,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_HEATING_BURNING_TIMES,
        translation_key="heating_burning_times",
        name="Heating Burning Times",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="次",
        value_fn=lambda _, state: state.heating_burning_times * 100 if state else None,
    ),
    RinnaiSensorEntityDescription(
        key=ATTR_HOT_WATER_BURNING_TIMES,
        translation_key="hot_water_burning_times",
        name="Hot Water Burning Times",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="次",
        value_fn=lambda _, state: state.hot_water_burning_times * 100 if state else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Rinnai sensors based on a config entry."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        RinnaiSensor(coordinator, device_id, description)
        for device_id in coordinator.data["devices"]
        for description in SENSOR_TYPES
    ]
    
    # Add reservation sensor
    for device_id in coordinator.data["devices"]:
        entities.append(RinnaiHeatingReservationSensor(coordinator, device_id))

    async_add_entities(entities)


class RinnaiSensor(CoordinatorEntity, SensorEntity, RestoreEntity):
    """Representation of a Rinnai sensor."""

    coordinator: RinnaiCoordinator
    entity_description: RinnaiSensorEntityDescription

    def __init__(
        self,
        coordinator: RinnaiCoordinator,
        device_id: str,
        description: RinnaiSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = device_id
        self._restored_native_value = None

        device = coordinator.get_device(device_id)
        if device:
            self._attr_unique_id = f"{device_id}_{description.key}"
            self._attr_has_entity_name = True
            self._attr_device_info = {
                "identifiers": {(DOMAIN, device_id)},
                "name": device.device_name,
                "manufacturer": "Rinnai",
                "model": device.device_type,
            }
        else:
            self._attr_unique_id = f"{device_id}_{description.key}"
            self._attr_name = f"Rinnai Device {description.name}"

        if description.key == ATTR_BURNING_STATE:
            self._attr_translation_key = "burning_state"

        self._update_attributes()

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        if (last_state := await self.async_get_last_state()) is not None:
            # Try to restore native value if it's a number
            try:
                if last_state.state not in (None, "unknown", "unavailable"):
                    if self.device_class in (SensorDeviceClass.DURATION, SensorDeviceClass.GAS, SensorDeviceClass.TEMPERATURE):
                        self._restored_native_value = float(last_state.state)
                    else:
                        self._restored_native_value = last_state.state
            except (ValueError, TypeError):
                _LOGGER.warning("Could not restore state for %s: %s", self.entity_id, last_state.state)

        # Trigger update to use restored value if needed
        self._update_attributes()

    @property
    def _device(self):
        """Get the device object."""
        return self.coordinator.get_device(self._device_id)

    @property
    def _device_state(self):
        """Get the device state object."""
        return self.coordinator.get_device_state(self._device_id)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self._device or not self._device.online:
            return False
        if self.entity_description.key in [
            ATTR_HOT_WATER_TEMP,
            ATTR_HEATING_TEMP_NM,
            ATTR_HEATING_TEMP_HES,
        ]:
            return True
        state = self._device_state
        if not state:
            return False

        mode_code = state.raw_data.get("operationMode")
        if (
            not mode_code
            or not self._device.config
            or mode_code not in self._device.config.code_to_mode
        ):
            return False

        return True

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle device updates."""
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        """Update sensor attributes based on device state."""
        device = self._device
        if not device:
            self._attr_available = False
            return

        state = self.coordinator.get_device_state(self._device_id)
        current_value = self.entity_description.value_fn(device, state)
        
        # # If current value is None or 0 (and 0 might be invalid for cumulative stats), try to use restored value
        # # Note: 0 is valid for some sensors, but for cumulative counters like total time, 0 usually means "not initialized"
        is_cumulative = self.entity_description.state_class == SensorStateClass.TOTAL_INCREASING
        
        if (current_value is None or (is_cumulative and current_value == 0)) and self._restored_native_value is not None:
             self._attr_native_value = self._restored_native_value
        else:
             self._attr_native_value = current_value
             


class RinnaiHeatingReservationSensor(CoordinatorEntity, SensorEntity):
    """Representation of Rinnai heating reservation status."""

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        
        device = coordinator.get_device(device_id)
        if device:
            self._attr_unique_id = f"{device_id}_heating_reservation"
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
            return

        # Parse heatingReservationMode
        # Format: [Status 1B] [Index 1B] [Mode1 3B] ... [Mode5 3B]
        raw_hex = state.raw_data.get("byteStr") or state.raw_data.get("heatingReservationMode")
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
