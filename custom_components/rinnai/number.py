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
        self._temp_format: str = config.get("temp_format", "hex2")

        self._attr_native_min_value = float(config["min"])
        self._attr_native_max_value = float(config["max"])
        self._attr_native_step = float(config.get("step", 1))
        self._attr_native_unit_of_measurement = config.get(
            "unit_of_measurement", UnitOfTemperature.CELSIUS
        )
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_mode = NumberMode.BOX
        self._update_attributes()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        device = self._device
        if not device:
            self._attr_available = False
            return
        self._attr_available = device.online
        try:
            val = self.get_state_value(self._state_attribute)
            self._attr_native_value = float(val) if val is not None else None
        except (ValueError, TypeError):
            self._attr_native_value = None

    async def async_set_native_value(self, value: float) -> None:
        """Send the new setpoint to the device."""
        int_value = int(value)
        hex_val = hex(int_value)[2:].upper().zfill(2)
        if self._temp_format == "hex4":
            hex_val = hex_val + "00"

        if await self.coordinator.async_send_command(
            self._device_id, {self._command_key: hex_val}
        ):
            self._attr_native_value = value
            self.async_write_ha_state()
