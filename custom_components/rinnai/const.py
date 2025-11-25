"""Constants for the Rinnai integration."""

from typing import Final

# Integration domain
DOMAIN: Final = "rinnai"

# Configuration keys
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_CONNECT_TIMEOUT: Final = "connect_timeout"

# Attributes and service names
# Attributes and service names
# These are now defined in device configuration JSON files

# Supported platforms
PLATFORMS: Final = frozenset(["sensor", "water_heater", "climate", "switch", "select", "text"])

# Default values
DEFAULT_UPDATE_INTERVAL: Final = 300  # seconds
DEFAULT_CONNECT_TIMEOUT: Final = 30  # seconds

# Rinnai MQTT settings
RINNAI_HOST: Final = "mqtt.rinnai.com.cn"
RINNAI_PORT: Final = 8883

# Device type identifiers
DEVICE_TYPE_WATER_HEATER: Final = "water_heater"

# Entity categories
ENTITY_CATEGORY_DIAGNOSTIC: Final = "diagnostic"
ENTITY_CATEGORY_CONFIG: Final = "config"

HOST: Final = "https://iot.rinnai.com.cn/app"
BASE_URL: Final = HOST

# Rinnai Smart Home app built-in accessKey
AK: Final = "A39C66706B83CCF0C0EE3CB23A39454D"
REFESH_TIME: Final = 86400  # 24 hours

# Centralized API Request Definitions
API_DEFINITIONS: Final = {
    "login": {
        "url": "/V1/login",
        "method": "GET"
    },
    "device_list": {
        "url": "/V1/device/list",
        "method": "GET"
    },
    "device_state": {
        "url": "/V1/device/processParameter",
        "method": "GET"
    },
    "get_schedule": {
        "url": "/V1/device/schedule/getScheduleInfo",
        "method": "GET",
        "params": {
            "mac": "{mac}",
            "type": "{heat_type}"
        }
    },
    "save_schedule": {
        "url": "/V1/device/schedule/saveScheduleHour",
        "method": "POST",
        "data": {
            "byteStr": "{data}",
            "mac": "{mac}",
            "type": "{heat_type}"
        }
    }
}

# MQTT Definitions
MQTT_DEFINITIONS: Final = {
    "topics": {
        "info": "rinnai/SR/01/SR/{mac}/inf/",
        "energy": "rinnai/SR/01/SR/{mac}/stg/",
        "set": "rinnai/SR/01/SR/{mac}/set/"
    },
    "protocol": {
        "info_code": "FFFF",
        "reservation_code": "03F1",
        "energy_pattern": "J05",
        "command_pattern": "J00",
        "command_sum": "1"
    }
}



