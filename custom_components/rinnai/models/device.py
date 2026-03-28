"""Data models for Rinnai integration."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from ..core.config_manager import config_manager
from .config import RinnaiDeviceConfig
from ..core.state_manager import RinnaiStateManager
from ..core.processor import process_data

_LOGGER = logging.getLogger(__name__)


@dataclass
class RinnaiDeviceState:
    """Representation of a Rinnai device state with dynamic fields."""

    # Raw data from device (processed)
    raw_data: dict[str, Any] = field(default_factory=dict)

    # Device configuration
    config: RinnaiDeviceConfig | None = None

    def update_from_api_data(self, api_data: dict[str, Any]) -> None:
        """Update state from API data."""
        if not self.config:
            # If no config, just update raw data directly
            self.raw_data.update(api_data)
            return

        # Process data using generic processor
        processed_data = process_data(api_data, self.config.processors)
        
        # Update internal state
        self.raw_data.update(processed_data)
        
        _LOGGER.debug("Updated device state with processed data: %s", processed_data)


@dataclass
class RinnaiDevice:
    """Representation of a Rinnai device."""

    device_id: str
    device_name: str = "Rinnai Device"
    device_type: str = "Unknown"
    auth_code: str = "FFFF"
    online: bool = False

    # Device state information
    state: RinnaiDeviceState = field(default_factory=RinnaiDeviceState)

    # Raw data from API
    raw_data: dict[str, Any] = field(default_factory=dict)

    # State Manager
    state_manager: RinnaiStateManager = field(default_factory=RinnaiStateManager)
    
    # Device Configuration
    config: RinnaiDeviceConfig | None = None

    def update_from_api_data(self, api_data: dict[str, Any]) -> None:
        """Update device from API data."""
        # Store raw data
        self.raw_data.update(api_data)

        # Update basic device properties
        self.device_name = api_data.get("name", self.device_name)
        
        new_device_type = api_data.get("deviceType", self.device_type)
        if new_device_type != self.device_type:
            self.device_type = new_device_type
            # Reload config if device type changed
            self.config = config_manager.get_config(self.device_type)
            self.state.config = self.config
            
        self.auth_code = api_data.get("authCode", self.auth_code)

        # Update online status
        online_status = api_data.get("online")
        if online_status is not None:
            self.online = online_status == "1"
            
        # Also update the state object with this data
        self.state.update_from_api_data(api_data)
            
    def update_state(self, state_data: dict[str, Any], is_command: bool = False) -> None:
        """Update device state using State Manager."""
        if is_command:
            self.state_manager.set_desired(state_data)
        else:
            self.state_manager.update_remote(state_data)
            
        # Get final display state
        display_state = self.state_manager.get_display_state()
        
        # Update the state object
        self.state.update_from_api_data(display_state)
