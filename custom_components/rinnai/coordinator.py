"""Data update coordinator for Rinnai integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
import time
from typing import Any, ClassVar

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import RinnaiClient
from .const import BURNING_STATES, CODE_TO_MODE, DOMAIN, GAS_CONSUMPTION_MAX_DIGITS

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.energy_data"


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

        # Update typed fields using mapping
        for api_field, (obj_field, converter) in self._field_mapping.items():
            if api_field in api_data:
                value = api_data[api_field]

                if not value:
                    continue

                if converter:
                    try:
                        setattr(self, obj_field, converter(value))
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            "Failed to convert %s value '%s' to %s",
                            obj_field,
                            value,
                            converter.__name__,
                        )
                else:
                    setattr(self, obj_field, value)

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
                    if len(gas_value) > GAS_CONSUMPTION_MAX_DIGITS:
                        gas_value = gas_value[-GAS_CONSUMPTION_MAX_DIGITS:]

                    # Convert hex string to integer - using int() for small enough values
                    gas_int = int(gas_value, 16)

                    # Convert to cubic meters (divide by 1000)
                    gas_consumption = float(gas_int) / 1000.0
                    self.gas_used = round(gas_consumption, 3)

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


class RinnaiCoordinator(DataUpdateCoordinator):
    """Data update coordinator for Rinnai devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: RinnaiClient,
        update_interval: int = 300,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.client = client
        self._first_update = True
        self._devices: dict[str, RinnaiDevice] = {}
        self._last_http_update: dict[str, float] = {}
        self.data = {"devices": {}, "device_states": {}}

        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

        self._load_energy_data()

    async def _load_energy_data(self) -> None:
        """Load saved energy data from storage."""
        try:
            if saved_data := await self._store.async_load():
                for device_id, energy_data in saved_data.items():
                    if device := self._devices.get(device_id):
                        device.state.gas_used = energy_data.get("gas_used", 0.0)
                        device.state.supply_time = energy_data.get("supply_time", 0)
                        device.state.total_power_supply_time = energy_data.get(
                            "total_power_supply_time", 0
                        )
                        device.state.total_heating_burning_time = energy_data.get(
                            "total_heating_burning_time", 0
                        )
                        device.state.total_hot_water_burning_time = energy_data.get(
                            "total_hot_water_burning_time", 0
                        )
                        device.state.heating_burning_times = energy_data.get(
                            "heating_burning_times", 0
                        )
                        device.state.hot_water_burning_times = energy_data.get(
                            "hot_water_burning_times", 0
                        )
                        device.state.raw_data.update(energy_data)

                        _LOGGER.debug(
                            "Loaded saved energy data for device %s", device_id
                        )
        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.error("Error loading energy data: %s", err)

    async def _save_energy_data(self) -> None:
        """Save energy data to storage."""
        try:
            energy_data = {}
            for device_id, device in self._devices.items():
                state = device.state
                energy_data[device_id] = {
                    "gas_used": state.gas_used,
                    "supply_time": state.supply_time,
                    "total_power_supply_time": state.total_power_supply_time,
                    "total_heating_burning_time": state.total_heating_burning_time,
                    "total_hot_water_burning_time": state.total_hot_water_burning_time,
                    "heating_burning_times": state.heating_burning_times,
                    "hot_water_burning_times": state.hot_water_burning_times,
                }

            await self._store.async_save(energy_data)
            _LOGGER.debug("Saved energy data for all devices")
        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.error("Error saving energy data: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via API."""

        def handle_error(msg: str) -> None:
            """Handle error in data update."""
            _LOGGER.error(msg)
            raise HomeAssistantError(msg)

        try:
            # Ensure we're logged in (needed for both HTTP and potentially MQTT operations)
            if not await self.client.login():
                handle_error("Failed to login to Rinnai API")

            # Only fetch devices during first update or when devices list is empty
            if self._first_update or not self.client.devices:
                _LOGGER.debug("Performing initial/full HTTP update for devices")
                if not await self.client.fetch_devices():
                    _LOGGER.warning("Failed to fetch devices from HTTP API")

                # 初始化时，获取每个设备的状态
                for device_id in self.client.devices:
                    _LOGGER.debug("Fetching initial state for device: %s", device_id)
                    if not await self.client.fetch_device_state(device_id):
                        _LOGGER.warning(
                            "Failed to fetch state for device: %s", device_id
                        )

                self._first_update = False

                # Process initial device data
                self._process_devices_data()
            else:
                _LOGGER.debug("Skipping HTTP device fetch, using MQTT data only")

                # 对于没有 MQTT 更新或超过一定时间未更新的设备，强制从 HTTP API 获取状态
                current_time = time.time()
                for device_id in self.client.devices:
                    # 检查设备状态是否为空或上次更新时间是否超过阈值
                    device_state = self.client.device_states.get(device_id, {})
                    if (
                        not device_state
                        or getattr(self, "_last_http_update", {}).get(device_id, 0)
                        < current_time - 3600
                    ):
                        _LOGGER.debug(
                            "Fetching HTTP state update for device: %s", device_id
                        )
                        if await self.client.fetch_device_state(device_id):
                            # 更新最后 HTTP 获取时间
                            self._last_http_update[device_id] = current_time

                # MQTT updates happen independently in the client through subscriptions
                # Process any state updates from MQTT
                self._process_device_states()

            # 打印设备状态详细信息
            self._log_device_states()

        except (ValueError, TypeError, KeyError) as err:
            handle_error(f"Error updating Rinnai data: {err}")

        # Return structured data for Home Assistant entities
        return {
            "devices": self._devices,
            "device_states": {
                device_id: device.state for device_id, device in self._devices.items()
            },
            # Also include raw data for backward compatibility
            "raw_devices": self.client.devices,
            "raw_device_states": self.client.device_states,
        }

    def _process_devices_data(self) -> None:
        """Process devices data from client into structured format."""
        for device_id, device_data in self.client.devices.items():
            # Create device if it doesn't exist
            if device_id not in self._devices:
                self._devices[device_id] = RinnaiDevice(device_id=device_id)

            # Update device with API data
            self._devices[device_id].update_from_api_data(device_data)

            # Process initial state if available
            if device_id in self.client.device_states:
                self._devices[device_id].state.update_from_api_data(
                    self.client.device_states[device_id]
                )

    def _process_device_states(self) -> None:
        """Process device states from client into structured format."""
        for device_id, state_data in self.client.device_states.items():
            if device_id in self._devices:
                _LOGGER.debug(
                    "Received state data from client: %s: %s", device_id, state_data
                )

                self._devices[device_id].state.update_from_api_data(state_data)

                # 保存能源数据
                self.hass.create_task(self._save_energy_data())
            else:
                _LOGGER.warning(
                    "Received state for unknown device %s, fetching device info",
                    device_id,
                )
                # This shouldn't normally happen, but if it does, we'll process devices again
                self._process_devices_data()

    def process_device_states(self) -> None:
        """Process device states from client (public method)."""
        self._process_device_states()
        # update data to coordinator
        self.async_set_updated_data(self.data)

    async def async_send_command(self, device_id: str, command: dict[str, Any]) -> bool:
        """Send command to a device."""

        result = await self.client.send_command(device_id, command)

        # If command was successful, update our internal state anticipating the change
        # This improves responsiveness of the UI before the next MQTT update
        if result and device_id in self._devices:
            # 获取当前设备状态
            device = self._devices[device_id]
            old_state = device.state

            old_operation_mode = old_state.operation_mode if old_state else "Unknown"

            self._devices[device_id].state.update_from_api_data(command)

            # update data to coordinator
            self.async_set_updated_data(self.data)

            # 更新协调器的数据结构，确保引用正确
            self.data["device_states"][device_id] = self._devices[device_id].state

            # 记录命令后的状态
            device = self._devices[device_id]
            state = device.state
            _LOGGER.info("===== Command Post-State =====")
            _LOGGER.info("Device: %s (%s)", device.device_name, device_id)

            # 记录模式变化
            new_operation_mode = state.operation_mode
            if old_operation_mode != new_operation_mode:
                _LOGGER.info(
                    "  Operation Mode Change: %s -> %s",
                    old_operation_mode,
                    new_operation_mode,
                )
            else:
                _LOGGER.info(
                    "  Operation Mode: %s",
                    new_operation_mode,
                )

            for cmd_key, cmd_value in command.items():
                current_value = state.raw_data.get(cmd_key, "Not Set")
                _LOGGER.info("  %s: %s -> %s", cmd_key, cmd_value, current_value)

            _LOGGER.info("======================")
        else:
            _LOGGER.warning("Command Send Failed: %s", command)

        return result

    def get_device(self, device_id: str) -> RinnaiDevice | None:
        """Get device by ID, with graceful handling of missing devices."""
        return self._devices.get(device_id)

    def get_device_state(self, device_id: str) -> RinnaiDeviceState | None:
        """Get device state by ID, with graceful handling of missing devices."""
        device = self.get_device(device_id)
        return device.state if device else None

    def _log_device_states(self) -> None:
        """Log detailed state information for all devices."""
        for device_id, device in self._devices.items():
            state = device.state
            _LOGGER.info("===== Device Status Sync =====")
            _LOGGER.info(
                "Device: %s (%s), Online: %s",
                device.device_name,
                device_id,
                device.online,
            )
            _LOGGER.info(
                "Type: %s, Auth Code: %s", device.device_type, device.auth_code
            )

            # Log basic status information
            _LOGGER.info("Basic Status:")
            _LOGGER.info(
                "  Operation Mode: %s (Code: %s)",
                CODE_TO_MODE[state.operation_mode],
                state.operation_mode,
            )
            _LOGGER.info("  Burning State: %s", BURNING_STATES[state.burning_state])
            _LOGGER.info("  Hot Water Temperature Setting: %s°C", state.hot_water_temp)
            _LOGGER.info("  Heating Temperature (Normal): %s°C", state.heating_temp_nm)
            _LOGGER.info(
                "  Heating Temperature (Energy Saving): %s°C", state.heating_temp_hes
            )

            # Log control parameters
            _LOGGER.info("Control Parameters:")
            _LOGGER.info("  Room Temperature Control: %s", state.room_temp_control)
            _LOGGER.info(
                "  Heating Output Water Temperature Control: %s",
                state.heating_water_temp_control,
            )
            _LOGGER.info("  Reservation Mode: %s", state.heating_reservation_mode)

            # Log energy usage data
            _LOGGER.info("Energy Data:")
            _LOGGER.info("  Gas Usage: %.3f m³", state.gas_used)
            _LOGGER.info("  Supply Time: %.2f hours", state.supply_time)
            _LOGGER.info(
                "  Total Power Supply Time: %.2f hours",
                state.total_power_supply_time,
            )
            _LOGGER.info(
                "  Total Heating Burning Time: %.2f hours",
                state.total_heating_burning_time,
            )
            _LOGGER.info(
                "  Total Hot Water Burning Time: %.2f hours",
                state.total_hot_water_burning_time,
            )
            _LOGGER.info(
                "  Heating Burning Times: %s times", state.heating_burning_times
            )
            _LOGGER.info(
                "  Hot Water Burning Times: %s times", state.hot_water_burning_times
            )

            # Log raw data
            _LOGGER.debug("Device Raw Data: %s", device.raw_data)
            _LOGGER.debug("State Raw Data: %s", state.raw_data)
            _LOGGER.info("===========================")
