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

    _LOGGER.debug("Setting up %d switch entities", len(entities))
    async_add_entities(entities)


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


class RinnaiCommandSwitch(RinnaiEntity, SwitchEntity):
    """A generic switch that sends an ENL command on toggle.

    Config keys:
        command_key  – ENL parameter name (e.g. "power")
        command_on   – value to send when turning on  (e.g. "31")
        command_off  – value to send when turning off (e.g. "30")
        state_attribute (optional) – state_mapping key to read current state
        on_value    (optional) – raw value that means "on"; defaults to command_on
    """

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any]) -> None:
        super().__init__(coordinator, device_id, config)
        self._command_key: str = config["command_key"]
        self._command_on: str = config["command_on"]
        self._command_off: str = config["command_off"]
        self._state_attribute: str | None = config.get("state_attribute")
        self._on_value: str = config.get("on_value", self._command_on)
        self._update_attributes()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        if self._state_attribute:
            val = self.get_state_value(self._state_attribute)
            self._attr_is_on = (val == self._on_value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if await self.coordinator.async_send_command(
            self._device_id, {self._command_key: self._command_on}
        ):
            self._attr_is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if await self.coordinator.async_send_command(
            self._device_id, {self._command_key: self._command_off}
        ):
            self._attr_is_on = False
            self.async_write_ha_state()
