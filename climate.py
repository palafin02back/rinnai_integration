"""Support for Rinnai heating climate control."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CODE_TO_MODE, DOMAIN, HEATING_MODES, MAX_TEMP, MIN_TEMP, TEMP_STEP
from .coordinator import RinnaiCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Rinnai climate based on a config entry."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        RinnaiHeatingClimateEntity(coordinator, device_id)
        for device_id in coordinator.data["devices"]
    ]

    async_add_entities(entities)


class RinnaiHeatingClimateEntity(CoordinatorEntity, ClimateEntity):
    """Representation of a Rinnai heating climate entity."""

    coordinator: RinnaiCoordinator

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._device_id = device_id

        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
        )

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = MIN_TEMP
        self._attr_max_temp = MAX_TEMP
        self._attr_target_temperature_step = TEMP_STEP

        self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]

        self._attr_preset_modes = [
            config["display"]
            for mode_key, config in HEATING_MODES.items()
            if mode_key != "standby"  # Exclude "Heating Off"
        ]

        # Use has_entity_name flag to enable proper translation
        self._attr_has_entity_name = True

        self._current_mode = "standby"

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
            return

        self._attr_unique_id = f"{self._device_id}_heating"
        self._attr_translation_key = "rinnai"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": device.device_name,
            "manufacturer": "Rinnai",
            "model": device.device_type,
        }

        # Check if device is online
        self._attr_available = device.online

        # Update state attributes
        state = self._device_state
        if not state:
            return

        # Get current operation mode
        mode_code = state.raw_data.get("operationMode")
        if mode_code and mode_code in CODE_TO_MODE:
            self._current_mode = CODE_TO_MODE[mode_code]

            # Set preset mode
            if self._current_mode != "standby":
                self._attr_preset_mode = HEATING_MODES[self._current_mode]["display"]
            else:
                self._attr_preset_mode = None

            # Set HVAC mode
            if self._current_mode == "standby":
                self._attr_hvac_mode = HVACMode.OFF
                self._attr_hvac_action = HVACAction.OFF
            else:
                self._attr_hvac_mode = HVACMode.HEAT

                # Determine current action based on burning state
                burning_state = state.burning_state
                # Add debug log
                _LOGGER.debug("Current burning state: %s", burning_state)
                # Correctly compare burning state
                if burning_state in ["31", "32"]:
                    self._attr_hvac_action = HVACAction.HEATING
                    _LOGGER.debug("Setting hvac_action to HEATING")
                else:
                    self._attr_hvac_action = HVACAction.IDLE
                    _LOGGER.debug("Setting hvac_action to IDLE")
        else:
            self._current_mode = "standby"
            self._attr_preset_mode = None
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_hvac_action = HVACAction.OFF

        # Get appropriate temperature based on current mode
        if self._current_mode == "normal":
            # Normal mode - use normal heating temperature
            self._attr_target_temperature = state.heating_temp_nm
        elif self._current_mode == "energy_saving":
            # Energy saving mode - use energy saving heating temperature
            self._attr_target_temperature = state.heating_temp_hes
        elif self._current_mode == "outdoor":
            # Outdoor mode - display minimum temperature, representing "LO"
            self._attr_target_temperature = self.min_temp
            # Set an additional flag indicating outdoor mode
            self._attr_extra_state_attributes = {"outdoor_mode": True}
        else:
            # Default to normal temperature for other modes
            self._attr_target_temperature = state.heating_temp_nm

        # Add debug log
        _LOGGER.debug(
            "Climate entity mode: %s, target temp: %s, hvac_mode: %s, preset: %s",
            self._current_mode,
            self._attr_target_temperature,
            self._attr_hvac_mode,
            self._attr_preset_mode,
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
        # froce update data
        await self.coordinator.async_request_refresh()
        # Get latest mode information again to ensure state is up-to-date
        # This helps resolve issues where mode has changed but UI hasn't updated
        state = self._device_state
        if state and state.raw_data.get("operationMode") in CODE_TO_MODE:
            self._current_mode = CODE_TO_MODE[state.raw_data.get("operationMode")]
            _LOGGER.debug(
                "Updating mode before setting temperature: %s", self._current_mode
            )

        # Cannot set temperature if in standby mode
        if self._current_mode == "standby":
            _LOGGER.warning("Cannot set heating temperature when heating is off")
            return

        # Cannot set temperature in outdoor mode
        if self._current_mode == "outdoor":
            _LOGGER.warning("Cannot set heating temperature in outdoor mode")
            return

        # Set appropriate temperature based on current mode
        hex_temperature = hex(temperature)[2:].upper()

        if self._current_mode == "normal":
            # Normal mode - set normal heating temperature
            command = {"heatingTempSettingNM": hex_temperature}
            _LOGGER.debug("Setting normal heating temperature to %s°C", temperature)
        elif self._current_mode == "energy_saving":
            # Energy saving mode - set energy saving heating temperature
            command = {"heatingTempSettingHES": hex_temperature}
            _LOGGER.debug(
                "Setting energy saving heating temperature to %s°C", temperature
            )
        else:
            # Default to normal temperature for other modes
            command = {"heatingTempSettingNM": hex_temperature}
            _LOGGER.debug("Setting heating temperature to %s°C", temperature)

        # Send command
        success = await self.coordinator.async_send_command(self._device_id, command)

        if success:
            # Update local state
            self._attr_target_temperature = float(temperature)
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode == HVACMode.HEAT:
            # If currently in standby mode, switch to normal heating mode
            if self._current_mode == "standby":
                # Switch to normal mode
                normal_config = HEATING_MODES["normal"]
                command = {normal_config["command"]: normal_config["value"]}
                success = await self.coordinator.async_send_command(
                    self._device_id, command
                )

                if success:
                    # Immediately update local state without waiting for MQTT callback
                    self._current_mode = "normal"
                    self._attr_hvac_mode = HVACMode.HEAT
                    self._attr_preset_mode = HEATING_MODES["normal"]["display"]
                    self._attr_hvac_action = HVACAction.IDLE
                    # Get temperature from current device state
                    state = self._device_state
                    if state:
                        self._attr_target_temperature = state.heating_temp_nm

                    _LOGGER.debug("Immediately updating state to normal heating mode")
                    # Immediately update UI
                    self.async_write_ha_state()
                else:
                    _LOGGER.warning("Failed to turn on heating")
            else:
                # 如果采暖已经开启，但hvac_mode设为HEAT，可能是UI刷新，无需发送命令
                _LOGGER.debug(
                    "Heating already on, no command needed for HVAC mode HEAT"
                )

        elif hvac_mode == HVACMode.OFF:
            # 如果已经是关闭状态，无需发送关闭命令
            if self._current_mode == "standby":
                _LOGGER.debug("Heating already off, no command needed")
                return

            # Switch to standby mode - "Heating Off"
            standby_config = HEATING_MODES["standby"]
            command = {standby_config["command"]: standby_config["value"]}

            _LOGGER.debug("Sending command to turn off heating: %s", command)
            success = await self.coordinator.async_send_command(
                self._device_id, command
            )

            if success:
                # Immediately update local state without waiting for MQTT callback
                self._current_mode = "standby"
                self._attr_hvac_mode = HVACMode.OFF
                self._attr_hvac_action = HVACAction.OFF
                self._attr_preset_mode = None

                _LOGGER.debug("Successfully turned off heating")
                self.async_write_ha_state()
            else:
                _LOGGER.warning("Failed to turn off heating")

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        # Find mode configuration matching the display name
        target_mode_key = None
        for mode_key, config in HEATING_MODES.items():
            if config["display"] == preset_mode:
                target_mode_key = mode_key
                break

        if not target_mode_key:
            _LOGGER.warning("Unknown preset mode: %s", preset_mode)
            return

        # If standby mode is selected, handle with set_hvac_mode
        if target_mode_key == "standby":
            await self.async_set_hvac_mode(HVACMode.OFF)
            return

        # Get target mode configuration
        target_config = HEATING_MODES[target_mode_key]
        target_command = target_config["command"]
        target_value = target_config["value"]
        requires_normal = target_config["requires_normal"]
        # froce update data
        await self.coordinator.async_request_refresh()
        # Get current mode
        current_mode_code = self._device_state.raw_data.get("operationMode", "0")
        current_mode_key = CODE_TO_MODE.get(current_mode_code)

        _LOGGER.debug(
            "Switching mode: current=%s, target=%s, requires_normal=%s",
            current_mode_key,
            target_mode_key,
            requires_normal,
        )

        # 检查是否需要先切换到普通模式
        if (
            requires_normal
            and current_mode_key != "normal"
            and target_mode_key != "normal"
            and self._attr_hvac_mode == HVACMode.OFF
        ):
            # Switch to normal mode first
            normal_config = HEATING_MODES["normal"]
            normal_command = {normal_config["command"]: normal_config["value"]}

            # Send command to switch to normal mode
            success = await self.coordinator.async_send_command(
                self._device_id, normal_command
            )

            if success:
                # Immediately update to normal mode
                self._current_mode = "normal"
                self._attr_preset_mode = HEATING_MODES["normal"]["display"]
                self._attr_hvac_mode = HVACMode.HEAT  # 确保HVAC模式为HEAT
                self.async_write_ha_state()

                # Wait a short time to ensure device state updates
                await asyncio.sleep(2)
            else:
                _LOGGER.warning(
                    "Failed to switch to normal mode before %s", preset_mode
                )
                return  # 如果切换到normal模式失败，就不继续后面的操作

        # 如果当前已经是目标模式，无需发送命令
        if current_mode_key == target_mode_key:
            _LOGGER.debug("Already in %s mode, no need to send command", preset_mode)
            return
        # change to normal mode
        if target_mode_key == "normal" and current_mode_key != "standby":
            # 特殊处理从其他模式切换回普通模式的逻辑
            current_mode_config = HEATING_MODES[current_mode_key]
            _LOGGER.debug(
                "Special handling for switching back to normal mode from %s",
                current_mode_key,
            )
            command = {current_mode_config["command"]: current_mode_config["value"]}
        else:
            # Send target mode command
            command = {target_command: target_value}

        _LOGGER.debug("Sending command: %s", command)
        success = await self.coordinator.async_send_command(self._device_id, command)

        if success:
            # Immediately update preset mode state
            self._current_mode = target_mode_key
            self._attr_preset_mode = preset_mode
            self._attr_hvac_mode = HVACMode.HEAT  # Ensure HVAC mode is heat

            # Update target temperature (based on mode)
            state = self._device_state
            if state:
                if target_mode_key == "normal":
                    self._attr_target_temperature = state.heating_temp_nm
                elif target_mode_key == "energy_saving":
                    self._attr_target_temperature = state.heating_temp_hes
                elif target_mode_key == "outdoor":
                    self._attr_target_temperature = self.min_temp

            _LOGGER.debug("Successfully switched to %s mode", preset_mode)
            self.async_write_ha_state()
