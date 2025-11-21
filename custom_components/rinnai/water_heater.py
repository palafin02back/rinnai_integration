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

from .const import DOMAIN
from .coordinator import RinnaiCoordinator
from .entity import RinnaiEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rinnai water heater based on a config entry."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for device_id in coordinator.data["devices"]:
        device = coordinator.get_device(device_id)
        if not device or not device.config:
            continue
            
        if wh_configs := device.config.entities.get("water_heater"):
            for config in wh_configs:
                entities.append(RinnaiWaterHeaterEntity(coordinator, device_id, config))

    async_add_entities(entities)


class RinnaiWaterHeaterEntity(RinnaiEntity, WaterHeaterEntity):
    """Representation of a Rinnai water heater entity."""

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any]) -> None:
        """Initialize the water heater entity."""
        super().__init__(coordinator, device_id, config)

        self._attr_supported_features = WaterHeaterEntityFeature.TARGET_TEMPERATURE
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        
        self._attr_min_temp = config.get("min_temp", 35)
        self._attr_max_temp = config.get("max_temp", 65)
        self._attr_target_temperature_step = config.get("step", 1)
        
        self._command_topic = config.get("command_topic", "hotWaterTempSetting")
        self._state_attribute = config.get("state_attribute", "hot_water_temp")

        self._attr_operation_list = []
        self._attr_current_operation = "Hot Water"

        self._update_attributes()

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
            return
            
        self._attr_available = device.online

        # Update temperature
        try:
            self._attr_target_temperature = self.get_state_value(self._state_attribute)
        except (ValueError, TypeError):
            self._attr_target_temperature = 0

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        temperature = int(temperature)
        if temperature < self.min_temp or temperature > self.max_temp:
            return

        hex_temperature = hex(temperature)[2:].upper()
        command = {self._command_topic: hex_temperature}

        success = await self.coordinator.async_send_command(self._device_id, command)

        if success:
            self._attr_target_temperature = float(temperature)
            self.async_write_ha_state()
