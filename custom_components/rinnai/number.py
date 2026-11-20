"""Support for Rinnai number entities (writable temperature setpoints)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import RinnaiCoordinator
from .core.command import encode_temperature
from .entity import RinnaiEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rinnai number entities based on a config entry."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for device_id in coordinator.data["devices"]:
        device = coordinator.get_device(device_id)
        if not device or not device.config:
            continue

        if number_configs := device.config.entities.get("number"):
            for config in number_configs:
                entities.append(RinnaiNumberEntity(coordinator, device_id, config))

    _LOGGER.debug("Setting up %d number entities", len(entities))
    async_add_entities(entities)


class RinnaiNumberEntity(RinnaiEntity, NumberEntity):
    """A writable number entity that sends an ENL command on value change.

    Config keys:
        command_key       – ENL parameter name (e.g. "roomTempSetting")
        state_attribute   – state_mapping key to read current value
        min               – minimum value (float)
        max               – maximum value (float)
        step              – step size (float, default 1)
        unit_of_measurement – e.g. "°C" (default "°C")
        device_class      – HA device class (default "temperature")
        temp_format       – "hex2" (default) or "hex4" encoding for the ENL value
    """

    def __init__(
        self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any]
    ) -> None:
        super().__init__(coordinator, device_id, config)
        self._command_key: str = config["command_key"]
        self._state_attribute: str = config["state_attribute"]
        self._heating_limits = config.get("c66l_heating_limits")
        self._temp_format: str = config.get("temp_format", "hex2")
        self._combined_temperature_position = config.get(
            "combined_temperature_position"
        )

        self._attr_native_min_value = float(config["min"])
        self._attr_native_max_value = float(config["max"])
        self._attr_native_step = float(config.get("step", 1))
        self._attr_native_unit_of_measurement = config.get(
            "unit_of_measurement", UnitOfTemperature.CELSIUS
        )
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_mode = NumberMode.BOX
        self._update_attributes()

    def _heating_limit(self) -> int | None:
        circuit = str(self.get_state_value("heatingOutWaterTempControl")).upper()
        eco = str(self.get_state_value("ecoMode")).upper()
        return self._heating_limits.get(circuit, {}).get(eco)

    @property
    def available(self) -> bool:
        return super().available and (not self._heating_limits or self._heating_limit() is not None)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        device = self._device
        if not device:
            # Availability is handled by RinnaiEntity.available
            return
        if self._entity_config.get("temperature_bounds_attribute"):
            self._attr_native_min_value, self._attr_native_max_value = self.packed_temperature_bounds(
                self._entity_config["min"], self._entity_config["max"]
            )
        if self._heating_limits:
            self._attr_native_max_value = self._heating_limit() or self._entity_config["max"]
        try:
            val = self.get_state_value(self._state_attribute)
            self._attr_native_value = float(val) if val is not None else None
        except (ValueError, TypeError):
            self._attr_native_value = None

    async def async_set_native_value(self, value: float) -> None:
        """Send the new setpoint to the device."""
        if self._combined_temperature_position and not self._attr_native_min_value <= value <= self._attr_native_max_value:
            raise ValueError("Temperature is outside the reported heating range")
        if self._heating_limits:
            limit = self._heating_limit()
            if limit is None or not self._attr_native_min_value <= value <= limit:
                raise ValueError("Temperature is outside the current C66L heating range")
            if value > 60 and value % 5:
                raise ValueError("C66L heating setpoints above 60°C use 5°C increments")
        try:
            if self._combined_temperature_position:
                success = await self.async_send_combined_temperature(value, self._command_key)
            else:
                encoded = encode_temperature(value, self._temp_format)
                success = await self.coordinator.async_send_command(self._device_id, {self._command_key: encoded})
        except (TypeError, ValueError) as err:
            _LOGGER.warning("Cannot encode setpoint %s: %s", value, err)
            return

        if success:
            self._attr_native_value = value
            self.async_write_ha_state()
