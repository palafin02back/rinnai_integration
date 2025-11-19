"""Data update coordinator for Rinnai integration."""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .core.client import RinnaiClient
from .const import DOMAIN
from .models.device import RinnaiDevice, RinnaiDeviceState

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.energy_data"


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

        hass.create_task(self._load_energy_data())

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
                # Initial state load - treat as remote update
                self._devices[device_id].update_state(
                    self.client.device_states[device_id], is_command=False
                )

    def _process_device_states(self) -> None:
        """Process device states from client into structured format."""
        for device_id, state_data in self.client.device_states.items():
            if device_id in self._devices:
                _LOGGER.debug(
                    "Received state data from client: %s: %s", device_id, state_data
                )

                # Use State Manager to update state
                self._devices[device_id].update_state(state_data, is_command=False)

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
            # Use State Manager to set desired state (Optimistic Update)
            self._devices[device_id].update_state(command, is_command=True)

            # update data to coordinator
            self.async_set_updated_data(self.data)

            # 更新协调器的数据结构，确保引用正确
            self.data["device_states"][device_id] = self._devices[device_id].state

            # 记录命令后的状态
            device = self._devices[device_id]
            state = device.state
            _LOGGER.info("===== Command Post-State =====")
            _LOGGER.info("Device: %s (%s)", device.device_name, device_id)
            
            # Log raw state manager state for debugging
            _LOGGER.debug("State Manager Remote State: %s", device.state_manager.raw_remote_state)

            # 记录模式变化
            _LOGGER.info(
                "  Operation Mode: %s",
                state.operation_mode,
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
                device.config.code_to_mode.get(state.operation_mode, "Unknown")
                if device.config
                else "Unknown",
                state.operation_mode,
            )
            _LOGGER.info(
                "  Burning State: %s",
                state.burning_state_ha,
            )
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
