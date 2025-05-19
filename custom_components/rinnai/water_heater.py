"""Support for Rinnai water heater."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MAX_TEMP, MIN_TEMP, TEMP_STEP
from .coordinator import RinnaiCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rinnai water heater based on a config entry."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        RinnaiWaterHeaterEntity(coordinator, device_id)
        for device_id in coordinator.data["devices"]
    ]

    async_add_entities(entities)


class RinnaiWaterHeaterEntity(CoordinatorEntity, WaterHeaterEntity):
    """Representation of a Rinnai water heater entity."""

    coordinator: RinnaiCoordinator

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str) -> None:
        """Initialize the water heater entity."""
        super().__init__(coordinator)
        self._device_id = device_id

        # Only supports temperature control
        self._attr_supported_features = WaterHeaterEntityFeature.TARGET_TEMPERATURE
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = MIN_TEMP
        self._attr_max_temp = MAX_TEMP
        self._attr_target_temperature_step = TEMP_STEP

        # No longer supports operation mode list, but needs to set default current operation mode
        self._attr_operation_list = []
        self._attr_current_operation = "Hot Water"

        # Use has_entity_name flag to enable proper translation
        self._attr_has_entity_name = True

        self._update_attributes()

    @property
    def _device(self):
        """Get the device object."""
        return self.coordinator.get_device(self._device_id)

    @property
    def _device_state(self):
        """Get the device state object."""
        return self.coordinator.get_device_state(self._device_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        """Update entity attributes based on coordinator data."""
        device = self._device
        if not device:
            self._attr_available = False
            _LOGGER.debug("Water heater device not available")
            return
        self._attr_unique_id = f"{self._device_id}_water_heater"
        self._attr_translation_key = "rinnai"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": device.device_name,
            "manufacturer": "Rinnai",
            "model": device.device_type,
        }
        self._attr_available = device.online

        if not device.online:
            _LOGGER.debug("Water heater device offline")
            return

        # Update state attributes
        state = self._device_state
        if not state:
            _LOGGER.debug("Water heater state not available")
            return

        # Only get hot water temperature setting
        try:
            self._attr_target_temperature = state.hot_water_temp
            _LOGGER.debug(
                "Water heater target temperature: %s°C", self._attr_target_temperature
            )
        except (ValueError, TypeError) as e:
            self._attr_target_temperature = 0
            _LOGGER.debug("Error getting water heater temperature: %s", e)

        # Set fixed operation mode name
        self._attr_current_operation = "Hot Water"
        _LOGGER.debug(
            "Water heater operation mode set to: %s", self._attr_current_operation
        )

        # Log complete device information to help debugging
        _LOGGER.debug(
            "Water heater complete info - Name: %s, Model: %s, Online: %s, Temp: %s°C",
            device.device_name,
            device.device_type,
            device.online,
            self._attr_target_temperature,
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        temperature = int(temperature)
        if temperature < self.min_temp or temperature > self.max_temp:
            _LOGGER.warning(
                "Temperature %s out of range (min: %s, max: %s)",
                temperature,
                self.min_temp,
                self.max_temp,
            )
            return

        # Set hot water temperature
        hex_temperature = hex(temperature)[2:].upper()
        command = {"hotWaterTempSetting": hex_temperature}
        _LOGGER.debug("Setting hot water temperature to %s°C", temperature)

        # Send command and update status
        success = await self.coordinator.async_send_command(self._device_id, command)

        if success:
            # Update local state immediately
            self._attr_target_temperature = float(temperature)
            self.async_write_ha_state()
