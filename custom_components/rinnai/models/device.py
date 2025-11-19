"""Data models for Rinnai integration."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, ClassVar


from ..core.config_manager import config_manager
from .config import RinnaiDeviceConfig
from ..core.state_manager import RinnaiStateManager

_LOGGER = logging.getLogger(__name__)


@dataclass
class RinnaiDeviceState:
    """Representation of a Rinnai device state with typed fields."""

    # Operation mode (e.g., winter, summer, energy saving)
    operation_mode: str = ""
    # Hot water temperature setting (target) in celsius
    hot_water_temp: int = 0
    # Normal mode heating temperature in celsius
    heating_temp_nm: int = 0
    # Energy saving mode heating temperature in celsius
    heating_temp_hes: int = 0
    # Current burning state (on/off/standby)
    burning_state: str = ""
    # Room temperature control setting
    room_temp_control: int = 0
    # Heating output water temperature control
    heating_water_temp_control: int = 0
    # Heating reservation mode
    heating_reservation_mode: str = ""
    # Last check point
    last_check_point: str = ""
    # Byte string
    byte_string: str = ""

    # Energy usage data
    gas_used: float = 0.0
    supply_time: int = 0
    # New energy usage data fields
    total_power_supply_time: int = 0
    total_heating_burning_time: int = 0
    total_hot_water_burning_time: int = 0
    heating_burning_times: int = 0
    hot_water_burning_times: int = 0

    # Raw data from device
    raw_data: dict[str, Any] = field(default_factory=dict)

    # Device configuration
    config: RinnaiDeviceConfig | None = None

    # Field mapping between API fields and object properties
    _field_mapping: ClassVar[dict[str, tuple[str, type | None]]] = {
        # Standard API field mapping
        "operationMode": ("operation_mode", None),
        "hotWaterTempSetting": ("hot_water_temp", None),
        "heatingTempSettingNM": ("heating_temp_nm", None),
        "heatingTempSettingHES": ("heating_temp_hes", None),
        "burningState": ("burning_state", None),
        "roomTempControl": ("room_temp_control", None),
        "heatingOutWaterTempControl": ("heating_water_temp_control", None),
        "heatingReservationMode": ("heating_reservation_mode", None),
        "gasUsed": ("gas_used", float),
        "supplyTime": ("supply_time", int),
        "byteStr": ("byte_string", None),
        "lastCheckPoint": ("last_check_point", None),
        # Energy related raw field mapping
        "gasConsumption": (
            "gas_used",
            float,
        ),  # Hex gas consumption that needs special handling
        "actualUseTime": ("supply_time", int),  # Hex supply time
        "totalPowerSupplyTime": (
            "total_power_supply_time",
            int,
        ),  # Hex total power supply time
        "totalHeatingBurningTime": (
            "total_heating_burning_time",
            int,
        ),  # Hex total heating burning time
        "totalHotWaterBurningTime": (
            "total_hot_water_burning_time",
            int,
        ),  # Hex total hot water burning time
        "heatingBurningTimes": (
            "heating_burning_times",
            int,
        ),  # Hex heating burning times
        "hotWaterBurningTimes": (
            "hot_water_burning_times",
            int,
        ),  # Hex hot water burning times
    }

    # List of fields that need hex conversion
    _hex_fields: ClassVar[list[str]] = [
        "hotWaterTempSetting",
        "heatingTempSettingNM",
        "heatingTempSettingHES",
        "roomTempControl",
        "heatingOutWaterTempControl",
        "actualUseTime",
        "totalPowerSupplyTime",
        "totalHeatingBurningTime",
        "totalHotWaterBurningTime",
        "heatingBurningTimes",
        "hotWaterBurningTimes",
    ]

    def update_from_api_data(self, api_data: dict[str, Any]) -> None:
        """Update state from API data."""
        # Store raw data
        self.raw_data.update(api_data)

        # Process hex values
        self._process_hex_values(api_data)

        # Process special gas consumption data
        self._process_gas_consumption(api_data)

        # Prepare field mapping
        # Start with default mapping
        mapping = dict(self._field_mapping)
        
        # Override with config mapping if available
        if self.config and self.config.field_mapping:
            for api_field, attr_name in self.config.field_mapping.items():
                # Find the type from default mapping if it exists, otherwise assume str
                target_type = None
                for _, (default_attr, default_type) in self._field_mapping.items():
                    if default_attr == attr_name:
                        target_type = default_type
                        break
                
                mapping[api_field] = (attr_name, target_type)

        # Update typed fields using mapping
        for api_field, (attr_name, field_type) in mapping.items():
            if api_field in api_data:
                value = api_data[api_field]

                if value is None:
                    continue

                if field_type:
                    try:
                        if field_type == int:
                            # Handle empty strings or non-numeric values gracefully
                            if isinstance(value, str) and not value.strip():
                                value = 0
                            else:
                                value = int(value)
                        elif field_type == float:
                            if isinstance(value, str) and not value.strip():
                                value = 0.0
                            else:
                                value = float(value)
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            "Failed to convert field %s value %s to %s",
                            api_field,
                            value,
                            field_type,
                        )
                        continue
                setattr(self, attr_name, value)

    def _process_hex_values(self, api_data: dict[str, Any]) -> None:
        """Process values that need hex conversion."""
        for field_name in self._hex_fields:
            if hex_value := api_data.get(field_name):
                try:
                    # Ensure value is string and convert from hex
                    if isinstance(hex_value, str):
                        # Add more detailed logs
                        original_value = hex_value
                        int_value = int(hex_value, 16)
                        api_data[field_name] = int_value
                        _LOGGER.debug(
                            "Converting hex value: %s: %s -> %s",
                            field_name,
                            original_value,
                            int_value,
                        )
                except ValueError:
                    _LOGGER.warning(
                        "Failed to convert hex value %s: %s", field_name, hex_value
                    )

    def _process_gas_consumption(self, api_data: dict[str, Any]) -> None:
        if gas_value := api_data.get("gasConsumption"):
            try:
                if isinstance(gas_value, str):
                    # Get last N characters to handle common format issues
                    # Rinnai seems to send very long strings with leading zeros
                    # Handle gas consumption digits truncation based on config
                    if self.config:
                        max_digits = self.config.features.get("gas_consumption_digits")
                        if max_digits and isinstance(max_digits, int) and max_digits > 0:
                            if len(gas_value) > max_digits:
                                gas_value = gas_value[-max_digits:]

                    # Convert hex string to integer - using int() for small enough values
                    gas_int = int(gas_value, 16)

                    # Convert to cubic meters (divide by 1000)
                    gas_consumption = float(gas_int) / 10000.0
                    self.gas_used = round(gas_consumption, 2)

                    # Update gasUsed field in api_data
                    api_data["gasUsed"] = self.gas_used
                    _LOGGER.debug(
                        "Processed gas consumption: %s -> %s m³",
                        gas_value,
                        self.gas_used,
                    )
            except ValueError as e:
                _LOGGER.warning(
                    "Failed to process gas consumption value: %s (%s)",
                    gas_value,
                    str(e),
                )

    @property
    def is_energy_saving(self) -> bool:
        """Determine if the mode is energy saving."""
        if not self.operation_mode:
            return False
        if "Energy Saving" in self.operation_mode:
            return True
        if self.config:
            return self.operation_mode in self.config.energy_saving_codes
        return False

    @property
    def is_outdoor(self) -> bool:
        """Determine if the mode is outdoor mode."""
        if not self.operation_mode:
            return False
        if "Outdoor" in self.operation_mode:
            return True
        if self.config:
            return self.operation_mode in self.config.outdoor_codes
        return False

    @property
    def is_rapid_heating(self) -> bool:
        """Determine if the mode is rapid heating."""
        if not self.operation_mode:
            return False
        if "Fast" in self.operation_mode:
            return True
        if self.config:
            return self.operation_mode in self.config.rapid_heating_codes
        return False

    @property
    def is_heating_off(self) -> bool:
        """Determine if heating is off."""
        if not self.operation_mode:
            return True
        if any(
            off_mode in self.operation_mode
            for off_mode in ["Power Off", "Heating Off", "Standby"]
        ):
            return True
        if self.config:
            return self.operation_mode in self.config.heating_off_codes
        return False

    @property
    def burning_state_ha(self) -> str:
        """Get burning state formatted for Home Assistant."""
        if not self.burning_state:
            return "Standby"
        if self.burning_state.isdigit():
            if self.config:
                return self.config.burning_states.get(self.burning_state, self.burning_state)
            # Fallback if no config (shouldn't happen)
            return self.burning_state
        return self.burning_state


@dataclass
class RinnaiDevice:
    """Representation of a Rinnai device with typed fields."""

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
    config: RinnaiDeviceConfig = field(init=False)

    def __post_init__(self):
        """Initialize configuration."""
        # Load configuration based on device type
        self.config = config_manager.get_config(self.device_type)
        self.state.config = self.config

    def update_from_api_data(self, api_data: dict[str, Any]) -> None:
        """Update device from API data."""
        # Store raw data
        self.raw_data.update(api_data)

        # Update basic device properties
        self.device_name = api_data.get("name", self.device_name)
        self.device_type = api_data.get("deviceType", self.device_type)
        self.auth_code = api_data.get("authCode", self.auth_code)

        # Update online status
        online_status = api_data.get("online")
        if online_status is not None:
            self.online = online_status == "1"
            
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
