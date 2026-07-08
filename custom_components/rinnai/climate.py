"""Support for Rinnai heating climate control."""
from __future__ import annotations

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

from .const import DOMAIN
from .coordinator import RinnaiCoordinator
from .entity import RinnaiEntity
from .core.entity_utils import execute_transition

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
        if not device or not device.config:
            continue
            
        if climate_configs := device.config.entities.get("climate"):
            for config in climate_configs:
                entities.append(RinnaiHeatingClimateEntity(coordinator, device_id, config))

    _LOGGER.debug("Setting up %d climate entities", len(entities))
    async_add_entities(entities)


class RinnaiHeatingClimateEntity(RinnaiEntity, ClimateEntity):
    """Representation of a Rinnai heating climate entity."""

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any]) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, device_id, config)

        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
        )
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        
        # Mandatory configuration
        self._attr_min_temp = config["min_temp"]
        self._attr_max_temp = config["max_temp"]
        self._attr_target_temperature_step = config["step"]
        
        self._modes_config = config["modes"]
        self._transitions = config["transitions"]
        self._mode_codes = config["mode_codes"]
        self._temp_settings = config["temp_settings"]
        self._active_states = config["active_states"]
        
        # Defaults config
        defaults = config.get("defaults", {})
        self._off_mode = defaults.get("off_mode", "standby")
        self._on_mode = defaults.get("on_mode", "normal")
        self._action_attribute = defaults.get("action_attribute", "burning_state")
        
        # Build preset modes list (excluding off mode)
        self._attr_preset_modes = []
        for mode_key, mode_data in self._modes_config.items():
            if mode_key != self._off_mode:
                self._attr_preset_modes.append(mode_data.get("label"))

        self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
        
        # Current internal mode key
        self._current_mode = self._off_mode

        self._update_attributes()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attributes()
        self.async_write_ha_state()

    def _get_mode_from_code(self, code: str) -> str:
        """Resolve mode key from operation mode code."""
        for mode_key, codes in self._mode_codes.items():
            if code in codes:
                return mode_key
        _LOGGER.debug(
            "Device %s: unknown operation mode code '%s', defaulting to '%s'",
            self._device_id, code, self._off_mode,
        )
        return self._off_mode

    def _update_temperature_attributes(self) -> None:
        """Update temperature attributes based on current mode."""
        # Reset min/max to defaults
        self._attr_min_temp = self._entity_config["min_temp"]
        self._attr_max_temp = self._entity_config["max_temp"]
        
        temp_config = self._temp_settings.get(self._current_mode)
        if not temp_config:
            # Fallback
            self._attr_target_temperature = self.get_state_value("heating_temp_nm")
            return
            
        if "fixed" in temp_config:
            fixed_temp = temp_config["fixed"]
            self._attr_target_temperature = fixed_temp
            self._attr_min_temp = fixed_temp
            self._attr_max_temp = fixed_temp
        elif "read" in temp_config:
            read_attr = temp_config["read"]
            self._attr_target_temperature = self.get_state_value(read_attr)

    def _update_attributes(self) -> None:
        """Update entity attributes based on coordinator data."""
        device = self._device
        if not device:
            self._attr_available = False
            return

        self._attr_available = device.online

        # Get current operation mode
        mode_code = self.get_state_value("operation_mode")
        self._current_mode = self._get_mode_from_code(str(mode_code))
        
        # Set preset & HVAC mode
        if self._current_mode == self._off_mode:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_hvac_action = HVACAction.OFF
            self._attr_preset_mode = None
        else:
            self._attr_hvac_mode = HVACMode.HEAT
            
            # Set preset mode label
            mode_data = self._modes_config.get(self._current_mode)
            if mode_data:
                self._attr_preset_mode = mode_data.get("label")
            
            # Determine action
            burning_state = str(self.get_state_value(self._action_attribute))
            if burning_state in self._active_states:
                self._attr_hvac_action = HVACAction.HEATING
            else:
                self._attr_hvac_action = HVACAction.IDLE

        self._update_temperature_attributes()
        self._attr_current_temperature = self._attr_target_temperature

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        temperature = int(temperature)
        
        # Check if current mode supports temp setting
        temp_config = self._temp_settings.get(self._current_mode)
        if not temp_config or "write" not in temp_config:
            _LOGGER.warning("Cannot set temperature in %s mode", self._current_mode)
            return

        write_cmd = temp_config["write"]
        hex_temperature = hex(temperature)[2:].upper()
        command = {write_cmd: hex_temperature}
        
        success = await self.coordinator.async_send_command(self._device_id, command)
        if success:
            self._attr_target_temperature = float(temperature)
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        target_mode = None
        if hvac_mode == HVACMode.HEAT:
            if self._current_mode == self._off_mode:
                target_mode = self._on_mode
        elif hvac_mode == HVACMode.OFF:
            if self._current_mode != self._off_mode:
                target_mode = self._off_mode
                
        if target_mode:
            await self._perform_transition(target_mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        target_mode = None
        for mode_key, mode_data in self._modes_config.items():
            if mode_data.get("label") == preset_mode:
                target_mode = mode_key
                break
                
        if target_mode:
            await self._perform_transition(target_mode)

    async def _perform_transition(self, target_mode: str) -> None:
        """Execute transition to target mode."""
        if self._current_mode == target_mode:
            return
            
        transition_key = f"{self._current_mode}_to_{target_mode}"
        steps = self._transitions.get(transition_key)
        
        if not steps:
            _LOGGER.warning("No transition defined for %s", transition_key)
            return
            
        _LOGGER.debug("Executing transition: %s", transition_key)
        
        if await execute_transition(self.coordinator, self._device_id, steps):
            self._current_mode = target_mode
            self._update_attributes()
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.warning(
                "Device %s: transition '%s' failed (command send error)",
                self._device_id, transition_key,
            )
