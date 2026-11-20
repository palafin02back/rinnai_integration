"""Base entity for Rinnai integration."""
from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import RinnaiCoordinator
from .core.command import RinnaiCommand, encode_combined_temperature
from .core.entity_utils import get_state_value
from .core.schedule_manager import RinnaiScheduleManager

_LOGGER = logging.getLogger(__name__)

class RinnaiEntity(CoordinatorEntity, Entity):
    """Base class for Rinnai entities."""

    def __init__(
        self, 
        coordinator: RinnaiCoordinator, 
        device_id: str,
        entity_config: dict[str, Any]
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entity_config = entity_config
        self._schedule_manager: RinnaiScheduleManager | None = None
        
        device = self._device
        if device:
            # Unique ID generation
            # Use the key from config if available, otherwise generate one
            key = entity_config.get("key", "unknown")
            self._attr_unique_id = f"{device_id}_{key}"
            
            self._attr_has_entity_name = True
            
            # Set name if provided in config
            if name := entity_config.get("name"):
                self._attr_name = name
                
            if translation_key := entity_config.get("key"):
                self._attr_translation_key = translation_key
                
            self._attr_device_info = {
                "identifiers": {(DOMAIN, device_id)},
                "name": device.device_name,
                "manufacturer": "Rinnai",
                "model": device.device_type,
            }
            
    @property
    def _device(self):
        """Get the device object."""
        return self.coordinator.get_device(self._device_id)

    @property
    def _device_state(self):
        """Get the device state object."""
        return self.coordinator.get_device_state(self._device_id)
        
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self._device or not self._device.online:
            return False
        return super().available

    @property
    def schedule_manager(self) -> RinnaiScheduleManager | None:
        """Get schedule manager instance (lazy loading)."""
        if self._schedule_manager is None:
            device = self._device
            if device and device.config:
                schedule_config = device.config.schedule_config
                if schedule_channel := self._entity_config.get("schedule_channel"):
                    channel = device.config.schedule_channels.get(schedule_channel, {})
                    schedule_config = channel.get("schedule_config", {})
                    if not schedule_config:
                        return None
                if schedule_config or not schedule_channel:
                    self._schedule_manager = RinnaiScheduleManager(schedule_config)
        return self._schedule_manager

    @property
    def schedule_channel(self) -> str | None:
        """Return the schedule channel selected by this entity."""
        return self._entity_config.get("schedule_channel")

    def packed_temperature_bounds(self, lower: float, upper: float) -> tuple[float, float]:
        """Decode the G58 upper/lower pair, each a two-byte temperature."""
        value = self.get_state_value(self._entity_config["temperature_bounds_attribute"])
        if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{8}", value):
            reported_low, reported_high = int(value[4:6], 16), int(value[:2], 16)
            if 0 < reported_low <= reported_high:
                return reported_low, reported_high
        return lower, upper

    async def async_send_combined_temperature(self, value: float, command_key: str) -> bool:
        """Serialize paired setpoints and preserve both bytes of the other circuit."""
        device = self._device
        mapping = device.config.state_mapping
        peer = mapping[self._entity_config["companion_state_attribute"]]
        target = mapping[self._entity_config["state_attribute"]]
        position = self._entity_config["combined_temperature_position"]
        async with device.temperature_lock:
            raw = device.state_manager.get_display_state().get(peer, device.raw_data.get(peer))
            if not isinstance(raw, str):
                raise ValueError("Missing raw companion temperature report")
            payload = encode_combined_temperature(value, raw, position)
            target_word = payload[:4] if position == "hot_water" else payload[4:]
            return await self.coordinator.async_send_command(
                self._device_id, RinnaiCommand.stateful({command_key: payload}, {target: target_word})
            )

    def get_state_value(self, key: str) -> Any:
        """Get a value from the device state using the configured mapping."""
        device = self._device
        if not device or not device.config:
            return None
            
        return get_state_value(
            self._device_state, 
            key, 
            device.config.state_mapping
        )

