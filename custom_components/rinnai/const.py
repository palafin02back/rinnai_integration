"""Constants for the Rinnai integration."""

from typing import Final

# Integration domain
DOMAIN: Final = "rinnai"

# Configuration keys
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_CONNECT_TIMEOUT: Final = "connect_timeout"

# Data processing configuration
GAS_CONSUMPTION_MAX_DIGITS: Final = 8  # Use last 8 digits of gas consumption hex value

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

# Temperature ranges
MIN_TEMP: Final = 35
MAX_TEMP: Final = 65
TEMP_STEP: Final = 1

# 模式映射定义
HEATING_MODES: Final = {
    # Mode name: {display: display name, codes: [mode code list], command: command name, value: command value, requires_normal: whether need to switch to normal mode first}
    "normal": {
        "display": "Normal Heating",
        "codes": ["3"],
        "command": "summerWinter",
        "value": "31",
        "requires_normal": False,
    },
    "energy_saving": {
        "display": "Heating Energy Saving",
        "codes": ["B", "4B"],
        "command": "energySavingMode",
        "value": "31",
        "requires_normal": True,
    },
    "outdoor": {
        "display": "Heating Outdoor",
        "codes": ["13", "53"],
        "command": "outdoorMode",
        "value": "31",
        "requires_normal": True,
    },
    "rapid": {
        "display": "Fast Heating",
        "codes": ["43", "4B", "53", "63"],
        "command": "rapidHeating",
        "value": "31",
        "requires_normal": True,
    },
    "standby": {
        "display": "Heating Off",
        "codes": ["0", "1", "2"],
        "command": "summerWinter",
        "value": "31",
        "requires_normal": False,
    },
    # Temporarily hide scheduled mode
    # "scheduled": {
    #     "display": "Heating Scheduled",
    #     "codes": ["23", "63"],
    #     "command": "scheduledMode",
    #     "value": "31",
    #     "requires_normal": True,
    # },
}

# Map mode codes to mode names
CODE_TO_MODE: Final = {
    code: mode for mode, config in HEATING_MODES.items() for code in config["codes"]
}

# Extract various mode code lists for helper functions
NORMAL_HEATING_CODES: Final = HEATING_MODES["normal"]["codes"]
ENERGY_SAVING_CODES: Final = HEATING_MODES["energy_saving"]["codes"]
OUTDOOR_MODES_CODES: Final = HEATING_MODES["outdoor"]["codes"]
RAPID_HEATING_CODES: Final = HEATING_MODES["rapid"]["codes"]
HEATING_OFF_MODES_CODES: Final = HEATING_MODES["standby"]["codes"]

# Burning state mapping
BURNING_STATES: Final = {
    "30": "Standby",
    "31": "Heating Water",
    "32": "Burning",
    "33": "Error",
}

HOST: Final = "https://iot.rinnai.com.cn/app"
LOGIN_URL: Final = f"{HOST}/V1/login"
INFO_URL: Final = f"{HOST}/V1/device/list"
PROCESS_PARAMETER_URL: Final = f"{HOST}/V1/device/processParameter"

# Rinnai Smart Home app built-in accessKey
AK: Final = "A39C66706B83CCF0C0EE3CB23A39454D"
REFESH_TIME: Final = 86400  # 24 hours
# State parameters
STATE_PARAMETERS: Final = {
    "operationMode",
    "roomTempControl",
    "heatingOutWaterTempControl",
    "burningState",
    "hotWaterTempSetting",
    "heatingTempSettingNM",
    "heatingTempSettingHES",
}


# Helper methods - for unified state determination
def is_energy_saving_mode(operation_mode: str) -> bool:
    """Determine if the mode is energy saving. Can handle text status or numeric code."""
    if not operation_mode:
        return False

    # If it's text status
    if "Energy Saving" in operation_mode:
        return True

    # If it's numeric code, check if it's in energy saving mode codes
    return operation_mode in ENERGY_SAVING_CODES


def is_outdoor_mode(operation_mode: str) -> bool:
    """Determine if the mode is outdoor mode. Can handle text status or numeric code."""
    if not operation_mode:
        return False

    # If it's text status
    if "Outdoor" in operation_mode:
        return True

    # If it's numeric code
    return operation_mode in OUTDOOR_MODES_CODES


def is_rapid_heating_mode(operation_mode: str) -> bool:
    """Determine if the mode is rapid heating. Can handle text status or numeric code."""
    if not operation_mode:
        return False

    # If it's text status
    if "Fast" in operation_mode:
        return True

    # If it's numeric code
    return operation_mode in RAPID_HEATING_CODES


def is_heating_off_mode(operation_mode: str) -> bool:
    """Determine if heating is off. Can handle text status or numeric code."""
    if not operation_mode:
        return True

    # If it's text status
    if any(
        off_mode in operation_mode
        for off_mode in ["Power Off", "Heating Off", "Standby"]
    ):
        return True

    # If it's numeric code
    return operation_mode in HEATING_OFF_MODES_CODES


def get_burning_state_ha(burning_state: str) -> str:
    """Get burning state formatted for Home Assistant. Can handle text status or numeric code."""
    if not burning_state:
        return "Standby"

    # If it's numeric code
    if burning_state.isdigit():
        return BURNING_STATES.get(burning_state)

    return burning_state
