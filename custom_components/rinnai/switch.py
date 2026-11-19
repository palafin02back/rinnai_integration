"""Support for Rinnai switches."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import RinnaiCoordinator
from .core.entity_utils import get_hex_byte, mask_hex_state
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
            mode_lock = asyncio.Lock()
            for config in switch_configs:
                switch_type = config.get("type", "generic")
                if switch_type == "reservation_switch":
                    entities.append(RinnaiHeatingReservationSwitch(coordinator, device_id, config))
                elif switch_type == "c66l_heating_mode":
                    entities.append(RinnaiC66LModeSwitch(coordinator, device_id, config, mode_lock))
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
        state_mask  (optional) – hexadecimal mask for flags packed into a state byte
    """

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any]) -> None:
        super().__init__(coordinator, device_id, config)
        self._command_key: str = config["command_key"]
        self._command_on: str = config["command_on"]
        self._command_off: str = config["command_off"]
        self._state_attribute: str | None = config.get("state_attribute")
        mask = config.get("state_mask")
        self._state_mask = int(mask, 16) if mask is not None else None
        on_config = config.get("on_values", config.get("on_value"))
        if on_config is None and "off_values" not in config:
            on_config = self._command_on
        self._on_values = self._configured_state_values(on_config)
        self._off_values = self._configured_state_values(config.get("off_values"))
        self._update_attributes()

    @staticmethod
    def _configured_state_values(value: Any) -> set[str]:
        """Normalize configured state values for robust comparison."""
        if value is None:
            return set()
        if isinstance(value, list):
            return {str(item).upper() for item in value}
        return {str(value).upper()}

    @staticmethod
    def _normalize_state_value(value: Any) -> str | None:
        """Normalize a raw state value for configured on/off comparisons."""
        return str(value).upper() if value is not None else None

    def _state_is_on(self, normalized: str) -> bool | None:
        """Return whether a normalized state value is on when configured."""
        if self._on_values:
            return normalized in self._on_values
        if self._off_values:
            return normalized not in self._off_values
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        if self._state_attribute:
            val = self.get_state_value(self._state_attribute)
            if self._state_mask is not None:
                val = mask_hex_state(val, self._state_mask)
            normalized = self._normalize_state_value(val)
            if normalized is None:
                self._attr_is_on = None
            elif (is_on := self._state_is_on(normalized)) is not None:
                self._attr_is_on = is_on

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


class RinnaiC66LModeSwitch(RinnaiCommandSwitch):
    """C66L heating modes share a command lock and can switch peers off in one ENL."""

    # Only clear the peers explicitly cleared by C66LControlActivity.
    _clear_on_enable = {
        "outdoorMode": ("ecoMode", "rapidHeating"),
        "rapidHeating": ("outdoorMode",),
        "ecoMode": ("outdoorMode",),
    }

    def __init__(
        self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any],
        mode_lock: asyncio.Lock,
    ) -> None:
        super().__init__(coordinator, device_id, config)
        self._mode_lock = mode_lock

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.get_state_value("power") == "01"
            and self._normalize_state_value(self.get_state_value("summer_winter")) == "AA"
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_mode(False)

    async def _set_mode(self, enable: bool) -> None:
        async with self._mode_lock:
            if not self.available:
                raise HomeAssistantError("C66L heating modes require an online boiler in winter mode")

            key = self._command_key
            if enable and key in ("ecoMode", "outdoorMode"):
                await self._disable_active_schedule()
                if not self.available:
                    raise HomeAssistantError("C66L heating became unavailable")

            command = {}
            if enable:
                for peer in self._clear_on_enable[key]:
                    if self._normalize_state_value(self.get_state_value(peer)) == "AA":
                        command[peer] = "55"
            command[key] = self._command_on if enable else self._command_off
            if not await self.coordinator.async_send_command(self._device_id, command):
                raise HomeAssistantError("Could not send the C66L heating mode command")

            preferences = self._flow_preferences(enable)
            if preferences:
                result = await self.coordinator.client.perform_request(
                    self._device_id, "update_flow_parameter", json_fields=preferences, success_only=True
                )
                if not result:
                    _LOGGER.warning("C66L mode command sent but cloud preference update failed")

    async def _disable_active_schedule(self) -> None:
        schedule = self.get_state_value("heating_reservation_mode")
        if not isinstance(schedule, str) or not schedule.startswith("01"):
            return
        if get_hex_byte(schedule, 0) is None:
            raise HomeAssistantError("Invalid C66L heating reservation data")
        if not await self.coordinator.client.save_schedule_hour(self._device_id, "00" + schedule[2:]):
            raise HomeAssistantError("Could not disable the C66L heating reservation")

    def _flow_preferences(self, enable: bool) -> dict[str, str]:
        """The app stores outdoor and eco selections under separate HTTP keys."""
        if self._command_key == "rapidHeating":
            return {"outDoorModeC66L": "55"} if enable else {}
        selected, other = "outDoorModeC66L", "ecoModeC66L"
        if self._command_key == "ecoMode":
            selected, other = other, selected
        return {selected: "AA", other: "55"} if enable else {selected: "55"}
