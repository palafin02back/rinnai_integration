"""Base entity for Rinnai integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import RinnaiCoordinator
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
            if device and device.config and hasattr(device.config, "schedule_config"):
                self._schedule_manager = RinnaiScheduleManager(device.config.schedule_config)
        return self._schedule_manager

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

