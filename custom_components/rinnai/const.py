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
ATTR_HOT_WATER_TEMP: Final = "hot_water_temperature"
ATTR_HEATING_TEMP_NM: Final = "heating_temperature_nm"
ATTR_HEATING_TEMP_HES: Final = "heating_temperature_hes"
ATTR_ENERGY_SAVING_MODE: Final = "energy_saving_mode"
ATTR_OUTDOOR_MODE: Final = "outdoor_mode"
ATTR_RAPID_HEATING: Final = "rapid_heating"
ATTR_SUMMER_WINTER: Final = "summer_winter"
ATTR_GAS_USAGE: Final = "gas_usage"
ATTR_SUPPLY_TIME: Final = "supply_time"
ATTR_BURNING_STATE: Final = "burning_state"
# 新增属性常量
ATTR_TOTAL_POWER_SUPPLY_TIME: Final = "total_power_supply_time"
ATTR_TOTAL_HEATING_BURNING_TIME: Final = "total_heating_burning_time"
ATTR_TOTAL_HOT_WATER_BURNING_TIME: Final = "total_hot_water_burning_time"
ATTR_HEATING_BURNING_TIMES: Final = "heating_burning_times"
ATTR_HOT_WATER_BURNING_TIMES: Final = "hot_water_burning_times"

# Supported platforms
PLATFORMS: Final = frozenset(["sensor", "water_heater", "climate"])

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
LOGIN_URL: Final = f"{HOST}/V1/login"
INFO_URL: Final = f"{HOST}/V1/device/list"
PROCESS_PARAMETER_URL: Final = f"{HOST}/V1/device/processParameter"

# Rinnai Smart Home app built-in accessKey
AK: Final = "A39C66706B83CCF0C0EE3CB23A39454D"
REFESH_TIME: Final = 86400  # 24 hours



