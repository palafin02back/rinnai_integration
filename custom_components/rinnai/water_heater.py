"""Support for Rinnai water heater."""
from __future__ import annotations

import asyncio
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
from .relative_temperature import (
    async_set_relative_temperature,
    current_temperature,
    resolve_target_temperature,
)

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

    _LOGGER.debug("Setting up %d water_heater entities", len(entities))
    async_add_entities(entities)


class RinnaiWaterHeaterEntity(RinnaiEntity, WaterHeaterEntity):
    """Representation of a Rinnai water heater entity."""

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any]) -> None:
        """Initialize the water heater entity."""
        super().__init__(coordinator, device_id, config)

        self._attr_supported_features = WaterHeaterEntityFeature.TARGET_TEMPERATURE
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        
        # Mandatory configuration - no defaults
        self._configured_min_temp = config["min_temp"]
        self._configured_max_temp = config["max_temp"]
        self._attr_min_temp = self._configured_min_temp
        self._attr_max_temp = self._configured_max_temp
        self._attr_target_temperature_step = config["step"]
        
        self._state_attribute = config["state_attribute"]
        self._min_temp_attribute = config.get("min_temp_attribute")
        self._max_temp_attribute = config.get("max_temp_attribute")
        self._relative_temperature_control = config.get("relative_temperature_control")
        self._command_topic = config.get("command_topic")
        # Standard devices still require command_topic. Relative control is an
        # explicit opt-in for devices that can only step temperature up/down.
        if not self._relative_temperature_control and not self._command_topic:
            raise KeyError("command_topic")
        # "hex2" → 2-char (G56 style: 40°C → "28")
        # "hex4" → 4-char (E-series style: 40°C → "2800")
        self._temp_format = config.get("temp_format", "hex2")
        
        # Operation mode name from config, default to "Hot Water" if not specified (display only)
        self._operation_mode = config.get("operation_mode", "Hot Water")
        self._changing_operation_template = config.get("changing_operation_template")
        self._temperature_notice_attribute = config.get(
            "temperature_notice_attribute", "温度提示"
        )
        self._attr_operation_list = [self._operation_mode]
        self._attr_current_operation = self._operation_mode
        if self._relative_temperature_control:
            self._attr_extra_state_attributes = {}

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

        self._update_temperature_range()

        # Update temperature
        try:
            self._attr_target_temperature = self.get_state_value(self._state_attribute)
        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Device %s: failed to parse water heater temperature (attr=%s): %s",
                self._device_id, self._state_attribute, err,
            )
            self._attr_target_temperature = 0
        self._attr_current_temperature = self._attr_target_temperature

    def _update_temperature_range(self) -> None:
        """Update min/max temperature from optional state attributes."""
        min_temp = self._temperature_bound(
            self._min_temp_attribute,
            self._configured_min_temp,
        )
        max_temp = self._temperature_bound(
            self._max_temp_attribute,
            self._configured_max_temp,
        )

        if min_temp > max_temp:
            _LOGGER.warning(
                "Device %s: invalid dynamic water heater range [%s, %s]; "
                "using configured range [%s, %s]",
                self._device_id,
                min_temp,
                max_temp,
                self._configured_min_temp,
                self._configured_max_temp,
            )
            min_temp = self._configured_min_temp
            max_temp = self._configured_max_temp

        self._attr_min_temp = min_temp
        self._attr_max_temp = max_temp

    def _temperature_bound(self, attribute: str | None, fallback: int | float) -> int | float:
        """Return a configured temperature bound, falling back on bad data."""
        if not attribute:
            return fallback

        try:
            value = self.get_state_value(attribute)
            if value is None:
                return fallback
            return int(value)
        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Device %s: failed to parse water heater temperature bound "
                "(attr=%s): %s",
                self._device_id,
                attribute,
                err,
            )
            return fallback

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        temperature = int(temperature)
        if temperature < self.min_temp or temperature > self.max_temp:
            _LOGGER.warning(
                "Device %s: temperature %s°C out of range [%s, %s]",
                self._device_id, temperature, self.min_temp, self.max_temp,
            )
            return

        if self._relative_temperature_control:
            await self._async_set_relative_temperature(temperature)
            return

        hex_temperature = hex(temperature)[2:].upper().zfill(2)
        if self._temp_format == "hex4":
            hex_temperature = hex_temperature + "00"
        command = {self._command_topic: hex_temperature}

        success = await self.coordinator.async_send_command(self._device_id, command)

        if success:
            self._attr_target_temperature = float(temperature)
            self.async_write_ha_state()

    async def _async_set_relative_temperature(self, temperature: int) -> None:
        """Set target temperature via configured relative up/down commands."""
        control = self._relative_temperature_control or {}
        target = resolve_target_temperature(
            self._device_id,
            temperature,
            control,
            self.get_state_value,
        )
        if target.target is None:
            return

        if target.adjusted:
            self._set_temperature_notice(target.requested, target.target)
        else:
            self._clear_temperature_notice()

        if current_temperature(self._state_attribute, self.get_state_value) == target.target:
            return

        self._set_changing_operation(target.target)
        try:
            result = await async_set_relative_temperature(
                device_id=self._device_id,
                target_temperature=target.target,
                state_attribute=self._state_attribute,
                control=control,
                allowed_temps=target.allowed_temps,
                get_state_value=self.get_state_value,
                send_command=self._async_send_relative_temperature_command,
                refresh_state=self._async_refresh_after_relative_temperature_step,
            )
            if result.reached_target:
                self._attr_target_temperature = float(target.target)
                self.async_write_ha_state()
        finally:
            self._restore_operation()

    def _set_changing_operation(self, temperature: int) -> None:
        """Show a configured in-progress operation while relative control runs."""
        if not self._changing_operation_template:
            return

        operation = self._changing_operation_template.format(temperature=temperature)
        self._set_current_operation(operation)

    def _set_temperature_notice(self, requested: int, temperature: int) -> None:
        """Show that an unsupported target was adjusted to a supported value."""
        control = self._relative_temperature_control or {}
        template = control.get(
            "unsupported_temperature_template",
            "Unsupported {requested}C; using nearest supported {temperature}C",
        )
        notice = template.format(requested=requested, temperature=temperature)
        self._attr_extra_state_attributes = {
            self._temperature_notice_attribute: notice,
        }
        self._set_current_operation(notice)

    def _clear_temperature_notice(self) -> None:
        """Clear the last unsupported-temperature notice if present."""
        if not self._attr_extra_state_attributes:
            return

        self._attr_extra_state_attributes = {}
        if self._attr_current_operation != self._operation_mode:
            self._set_current_operation(self._operation_mode)
            return

        self.async_write_ha_state()

    def _restore_operation(self) -> None:
        """Restore the configured normal operation label."""
        if self._attr_current_operation == self._operation_mode:
            return

        self._set_current_operation(self._operation_mode)

    def _set_current_operation(self, operation: str) -> None:
        """Update the operation label shown by Home Assistant."""
        self._attr_operation_list = [self._operation_mode]
        if operation != self._operation_mode:
            self._attr_operation_list.append(operation)
        self._attr_current_operation = operation
        self.async_write_ha_state()

    async def _async_send_relative_temperature_command(
        self,
        command: dict[str, Any],
    ) -> bool:
        """Send one relative temperature command."""
        return await self.coordinator.async_send_command(self._device_id, command)

    async def _async_refresh_after_relative_temperature_step(self) -> None:
        """Refresh state after a relative temperature command when possible."""
        control = self._relative_temperature_control or {}
        try:
            delay = float(control.get("step_delay_seconds", 0))
        except (ValueError, TypeError):
            delay = 0
        if delay > 0:
            await asyncio.sleep(delay)

        refresh_device_state = getattr(self.coordinator, "async_refresh_device_state", None)
        if refresh_device_state:
            if await refresh_device_state(self._device_id):
                self._update_attributes()
                return

        refresh = getattr(self.coordinator, "async_request_refresh", None)
        if refresh:
            await refresh()
        self._update_attributes()
