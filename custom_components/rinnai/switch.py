"""Support for Rinnai switches."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
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
    """Set up the Rinnai switches."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for device_id in coordinator.data["devices"]:
        device = coordinator.get_device(device_id)
        if not device or not device.config:
            continue
            
        if switch_configs := device.config.entities.get("switch"):
            for config in switch_configs:
                switch_type = config.get("type", "generic")
                if switch_type == "reservation_switch":
                    entities.append(RinnaiHeatingReservationSwitch(coordinator, device_id, config))
                elif switch_type == "command_switch":
                    entities.append(RinnaiCommandSwitch(coordinator, device_id, config))

    async_add_entities(entities)


class RinnaiCommandSwitch(RinnaiEntity, SwitchEntity):
    """Rinnai command-based toggle switch (e.g., one-key circulation).

    Sends a toggle MQTT command and reads the on/off state from a
    specific byte of a state attribute (e.g., operationMode).
    """

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any]) -> None:
        """Initialize the command switch."""
        super().__init__(coordinator, device_id, config)
        self._command = config["command"]
        self._command_value = config.get("command_value", "31")
        self._state_attribute = config["state_attribute"]
        self._on_state_check = config.get("on_state_check", {})
        self._update_attributes()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        """Determine on/off state from a specific byte in operationMode."""
        raw_value = self.get_state_value(self._state_attribute)
        if raw_value is None:
            self._attr_is_on = None
            return

        raw_str = str(raw_value)

        if self._on_state_check:
            byte_index = self._on_state_check.get("byte_index", 0)
            on_value = self._on_state_check.get("on_value", "")
            # Each "byte" is 2 hex chars. Extract the target byte.
            start = byte_index * 2
            end = start + len(on_value)
            if len(raw_str) >= end:
                actual = raw_str[start:end].upper()
                self._attr_is_on = actual == on_value.upper()
            else:
                self._attr_is_on = False
        else:
            self._attr_is_on = False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on (send toggle command if currently off)."""
        if not self._attr_is_on:
            await self._send_toggle(target_state=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off (send toggle command if currently on)."""
        if self._attr_is_on:
            await self._send_toggle(target_state=False)

    async def _send_toggle(self, target_state: bool) -> None:
        """Send the toggle MQTT command with optimistic state update."""
        _LOGGER.debug(
            "Sending toggle command: %s = %s (target: %s)",
            self._command, self._command_value, "ON" if target_state else "OFF",
        )
        result = await self.coordinator.async_send_command(
            self._device_id, {self._command: self._command_value}
        )
        if result:
            # Optimistic update: set state immediately, MQTT inf/ will confirm later
            self._attr_is_on = target_state
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to send command: %s", self._command)



class RinnaiHeatingReservationSwitch(RinnaiEntity, SwitchEntity):
    """Representation of Rinnai heating reservation switch."""

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any]) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, device_id, config)
        self._attr_translation_key = "heating_reservation"
        self._state_attribute = config["state_attribute"]
        self._update_attributes()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        if not self.schedule_manager:
            return

        raw_hex = self.get_state_value(self._state_attribute)
        self._attr_is_on = self.schedule_manager.parse_status(raw_hex)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._set_reservation_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._set_reservation_state(False)

    async def _set_reservation_state(self, is_on: bool) -> None:
        if not self.schedule_manager:
            return

        raw_hex = self.get_state_value(self._state_attribute)
        new_hex = self.schedule_manager.update_status(raw_hex, is_on)
        
        if not new_hex:
            _LOGGER.warning("Cannot set reservation state: invalid hex or config")
            return
            
        _LOGGER.debug("Setting reservation state to %s", "On" if is_on else "Off")
        
        if await self.coordinator.client.save_schedule_hour(self._device_id, new_hex):
            await self.coordinator.async_refresh_schedule(self._device_id)
            self._attr_is_on = is_on
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to set reservation state")
