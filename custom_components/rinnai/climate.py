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
    """Set up Rinnai climate based on a config entry."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for device_id in coordinator.data["devices"]:
        device = coordinator.get_device(device_id)
        if device and device.config and device.config.heating_modes:
            entities.append(RinnaiHeatingClimateEntity(coordinator, device_id))
        else:
            _LOGGER.debug("Device %s does not support heating, skipping climate entity", device_id)

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
        
        # Initialize attributes from device config
        device = self._device
        if device and device.config:
            self._attr_min_temp = device.config.temperature.min
            self._attr_max_temp = device.config.temperature.max
            self._attr_target_temperature_step = device.config.temperature.step
            
            self._attr_preset_modes = [
                config.display
                for mode_key, config in device.config.heating_modes.items()
                if mode_key != device.config.off_mode_key  # Exclude Off mode
            ]

        self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]

        # Use has_entity_name flag to enable proper translation
        self._attr_has_entity_name = True

        self._current_mode = device.config.off_mode_key if device and device.config else "standby"

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

    def _update_temperature_attributes(self) -> None:
        """Update temperature attributes based on current mode."""
        device = self._device
        state = self._device_state
        
        if not device or not device.config:
            return

        # Reset min/max to defaults
        if device.config.temperature:
            self._attr_min_temp = device.config.temperature.min
            self._attr_max_temp = device.config.temperature.max
        
        # Get appropriate temperature based on current mode
        mode_config = device.config.heating_modes.get(self._current_mode)
        if mode_config:
            if mode_config.temperature_attribute:
                attr_name = mode_config.temperature_attribute
                
                # Check if this attribute is a fixed value in configuration
                fix_temp_map = device.config.features.get("fix_temperature_attribute", {})
                if attr_name in fix_temp_map:
                    fixed_temp = fix_temp_map[attr_name]
                    self._attr_target_temperature = fixed_temp
                    # Lock min/max to fixed value to prevent adjustment
                    self._attr_min_temp = fixed_temp
                    self._attr_max_temp = fixed_temp
                    self._attr_extra_state_attributes = {"special_mode": True}
                elif hasattr(state, attr_name):
                    self._attr_target_temperature = getattr(state, attr_name)
                else:
                    # Fallback
                    self._attr_target_temperature = state.heating_temp_nm
            else:
                # Fallback if no attribute specified
                self._attr_target_temperature = state.heating_temp_nm

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
        if not state or not device.config:
            return

        # Get current operation mode
        mode_code = state.raw_data.get("operationMode")
        code_to_mode = device.config.code_to_mode
        
        off_mode = device.config.off_mode_key
        
        if mode_code and mode_code in code_to_mode:
            self._current_mode = code_to_mode[mode_code]

            # Set preset mode
            if self._current_mode != off_mode:
                self._attr_preset_mode = device.config.heating_modes[self._current_mode].display
            else:
                self._attr_preset_mode = None

            # Set HVAC mode
            if self._current_mode == off_mode:
                self._attr_hvac_mode = HVACMode.OFF
                self._attr_hvac_action = HVACAction.OFF
            else:
                self._attr_hvac_mode = HVACMode.HEAT

                # Determine current action based on burning state
                burning_state = state.burning_state
                # Add debug log
                _LOGGER.debug("Current burning state: %s", burning_state)
                # Correctly compare burning state
                if burning_state in device.config.active_heating_states:
                    self._attr_hvac_action = HVACAction.HEATING
                    _LOGGER.debug("Setting hvac_action to HEATING")
                else:
                    self._attr_hvac_action = None
                    _LOGGER.debug("Setting hvac_action to None (Idle)")
        else:
            self._current_mode = off_mode
            self._attr_preset_mode = None
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_hvac_action = HVACAction.OFF

        # Update temperature attributes
        self._update_temperature_attributes()

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
        
        device = self._device
        if not device or not device.config:
            return
            
        # Get latest mode information again to ensure state is up-to-date
        state = self._device_state
        code_to_mode = device.config.code_to_mode
        off_mode = device.config.off_mode_key
        
        if state and state.raw_data.get("operationMode") in code_to_mode:
            self._current_mode = code_to_mode[state.raw_data.get("operationMode")]
            _LOGGER.debug(
                "Updating mode before setting temperature: %s", self._current_mode
            )

        # Cannot set temperature if in off mode
        if self._current_mode == off_mode:
            _LOGGER.warning("Cannot set heating temperature when heating is off")
            return

        # Get mode config
        mode_config = device.config.heating_modes.get(self._current_mode)
        if not mode_config:
            _LOGGER.warning("Unknown mode config for %s", self._current_mode)
            return

        # Check if temperature setting is supported for this mode
        if not mode_config.temp_set_command:
             _LOGGER.warning("Cannot set heating temperature in %s mode", self._current_mode)
             return

        # Set appropriate temperature based on current mode
        hex_temperature = hex(temperature)[2:].upper()
        command = {mode_config.temp_set_command: hex_temperature}
        _LOGGER.debug("Setting %s temperature to %s°C", self._current_mode, temperature)

        # Send command
        success = await self.coordinator.async_send_command(self._device_id, command)

        if success:
            # Update local state
            self._attr_target_temperature = float(temperature)
            self.async_write_ha_state()

    def _get_transition_steps(
        self, current_mode_key: str, target_mode_key: str
    ) -> list[dict[str, Any]]:
        """Calculate transition steps from current mode to target mode."""
        device = self._device
        if not device or not device.config or not device.config.heating_modes:
            return []

        steps = []
        target_config = device.config.heating_modes.get(target_mode_key)
        
        # If target is invalid or same as current, no steps needed
        if not target_config or current_mode_key == target_mode_key:
            return []

        off_mode = device.config.off_mode_key
        normal_mode = device.config.normal_mode_key

        # Logic for mode switching
        if current_mode_key == off_mode:
            if target_mode_key == normal_mode:
                # Off -> Normal: Just turn on
                steps.append({
                    "command": {target_config.command: target_config.value},
                    "wait_time": 0,
                    "description": "Turn on normal heating"
                })
            elif target_config.requires_normal:
                # Off -> Special (requires normal): Turn on Normal first, then Special
                normal_config = device.config.heating_modes.get(normal_mode)
                if normal_config:
                    steps.append({
                        "command": {normal_config.command: normal_config.value},
                        "wait_time": 2,
                        "description": "Turn on normal heating first"
                    })
                steps.append({
                    "command": {target_config.command: target_config.value},
                    "wait_time": 0,
                    "description": f"Switch to {target_mode_key} mode"
                })
            else:
                # Off -> Special (no normal req): Direct switch
                steps.append({
                    "command": {target_config.command: target_config.value},
                    "wait_time": 0,
                    "description": f"Switch to {target_mode_key} mode"
                })
        
        elif current_mode_key == normal_mode:
            # Normal -> Special: Direct switch (usually toggles the special mode on)
            steps.append({
                "command": {target_config.command: target_config.value},
                "wait_time": 0,
                "description": f"Switch to {target_mode_key} mode"
            })
            
        else:
            # Current is a special mode (e.g. Energy Saving, Outdoor)
            
            # If target is Normal, we just need to toggle OFF the current special mode
            if target_mode_key == normal_mode:
                current_config = device.config.heating_modes.get(current_mode_key)
                if current_config:
                    steps.append({
                        "command": {current_config.command: current_config.value},
                        "wait_time": 2,
                        "description": f"Close {current_mode_key} mode to return to normal"
                    })
            
            # If target is another Special mode
            else:
                # Usually we need to close current special mode first, then open new one
                current_config = device.config.heating_modes.get(current_mode_key)
                if current_config:
                    steps.append({
                        "command": {current_config.command: current_config.value},
                        "wait_time": 2,
                        "description": f"Close current {current_mode_key} mode"
                    })
                
                steps.append({
                    "command": {target_config.command: target_config.value},
                    "wait_time": 0,
                    "description": f"Switch to {target_mode_key} mode"
                })
                
        return steps

    async def _execute_transition(self, steps: list[dict[str, Any]]) -> bool:
        """Execute a sequence of transition steps."""
        for idx, step in enumerate(steps):
            _LOGGER.debug(
                "Step %d: %s - %s",
                idx + 1,
                step["description"],
                step["command"],
            )
            success = await self.coordinator.async_send_command(
                self._device_id, step["command"]
            )
            if not success:
                _LOGGER.warning(
                    "Failed at step %d: %s", idx + 1, step["description"]
                )
                return False
            
            if step["wait_time"] > 0:
                await asyncio.sleep(step["wait_time"])
                await self.coordinator.async_request_refresh()
        return True

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        device = self._device
        if not device or not device.config or not device.config.heating_modes:
            return

        off_mode = device.config.off_mode_key
        normal_mode = device.config.normal_mode_key

        target_mode_key = None
        if hvac_mode == HVACMode.HEAT:
            if self._current_mode == off_mode:
                target_mode_key = normal_mode
            else:
                _LOGGER.debug("Heating already on")
                return
        elif hvac_mode == HVACMode.OFF:
            if self._current_mode != off_mode:
                target_mode_key = off_mode
            else:
                _LOGGER.debug("Heating already off")
                return

        if not target_mode_key:
            return

        # Get transition steps
        steps = self._get_transition_steps(self._current_mode, target_mode_key)
        
        # Execute steps
        if await self._execute_transition(steps):
            # Optimistic update
            self._current_mode = target_mode_key
            if target_mode_key == off_mode:
                self._attr_hvac_mode = HVACMode.OFF
                self._attr_hvac_action = HVACAction.OFF
                self._attr_preset_mode = None
            else:
                self._attr_hvac_mode = HVACMode.HEAT
                self._attr_hvac_action = HVACAction.IDLE
                normal_config = device.config.heating_modes.get(normal_mode)
                if normal_config:
                    self._attr_preset_mode = normal_config.display
                
                # Update temp
                self._update_temperature_attributes()
            
            self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        device = self._device
        if not device or not device.config or not device.config.heating_modes:
            return

        # Find mode configuration matching the display name
        target_mode_key = None
        for mode_key, config in device.config.heating_modes.items():
            if config.display == preset_mode:
                target_mode_key = mode_key
                break

        if not target_mode_key:
            _LOGGER.warning("Unknown preset mode: %s", preset_mode)
            return

        # Force update data
        await self.coordinator.async_request_refresh()

        # Get current mode
        current_mode_code = self._device_state.raw_data.get("operationMode", "0")
        code_to_mode = device.config.code_to_mode
        off_mode = device.config.off_mode_key
        current_mode_key = code_to_mode.get(current_mode_code, off_mode)

        _LOGGER.debug(
            "Switching mode: current=%s, target=%s",
            current_mode_key,
            target_mode_key,
        )

        # Get transition steps
        steps = self._get_transition_steps(current_mode_key, target_mode_key)
        
        if not steps:
            _LOGGER.debug("No transition steps needed")
            return

        # Execute steps
        if await self._execute_transition(steps):
            # Optimistic state update
            self._current_mode = target_mode_key
            self._attr_preset_mode = preset_mode
            self._attr_hvac_mode = HVACMode.HEAT if target_mode_key != off_mode else HVACMode.OFF
            
            # Update target temperature based on new mode
            self._update_temperature_attributes()

            _LOGGER.debug("Successfully switched to %s mode", preset_mode)
            self.async_write_ha_state()
