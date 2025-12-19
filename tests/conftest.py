"""Common test fixtures for Rinnai integration tests."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# Add custom_components to path for imports
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *args: f(*args))
    hass.loop = MagicMock()
    hass.create_task = MagicMock()
    return hass


@pytest.fixture
def sample_device_config():
    """Sample device configuration for testing."""
    return {
        "name": "Test Boiler",
        "features": {
            "heat_type": "G56_HEAT_OVEN",
            "energy_data_keys": ["gasUsed", "supplyTime"],
        },
        "schedule_config": {
            "total_length": 34,
            "status_byte_index": 0,
            "mode_byte_index": 1,
            "data_start_byte_index": 2,
            "bytes_per_mode": 3,
            "mode_count": 5,
        },
        "processors": {
            "hotWaterTempSetting": ["hex_to_int"],
            "gasConsumption": [
                "hex_to_int",
                {"func": "divide", "args": [10000]}
            ],
        },
        "state_mapping": {
            "hot_water_temp": "hotWaterTempSetting",
            "gas_usage": "gasConsumption",
        },
    }


@pytest.fixture
def sample_api_response():
    """Sample API response for testing."""
    return {
        "success": True,
        "data": {
            "list": [
                {
                    "id": "test_device_001",
                    "name": "Test Water Heater",
                    "deviceType": "0F06000C",
                    "mac": "AA:BB:CC:DD:EE:FF",
                    "online": "1",
                    "authCode": "FFFF",
                }
            ]
        }
    }


@pytest.fixture  
def sample_device_state():
    """Sample device state data for testing."""
    return {
        "hotWaterTempSetting": "28",  # hex for 40°C
        "heatingTempSettingNM": "37",  # hex for 55°C
        "operationMode": "3",
        "burningState": "31",
        "gasConsumption": "00002710",  # 10000 in hex
    }


@pytest.fixture
def sample_schedule_hex():
    """Sample schedule hex string for testing."""
    # Status: ON (01), Mode: 3 (03), then schedule data
    return "0103DB446CDB006E4818C680017F80017F"
