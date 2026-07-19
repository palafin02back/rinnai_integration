"""Regression tests for the isolated Q85 device support."""
from __future__ import annotations

import json
from pathlib import Path
import sys

CORE_DIR = Path(__file__).parents[1] / "custom_components" / "rinnai" / "core"
sys.path.insert(0, str(CORE_DIR))

from entity_utils import (  # noqa: E402
    get_hex_byte,
    normalize_dynamic_mqtt_code,
    resolve_mode_code,
)

CONFIG_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "rinnai"
    / "devices"
    / "0F060001.json"
)


def load_q85() -> dict:
    """Load the Q85 JSON as the integration does."""
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_q85_temperature_encoding_and_ranges() -> None:
    config = load_q85()
    water_heater = config["entities"]["water_heater"][0]
    climate = config["entities"]["climate"][0]

    assert config["processors"]["hotWaterTempSetting"] == ["hex_to_int"]
    assert water_heater["command_topic"] == "hotWaterTempSetting"
    assert (water_heater["min_temp"], water_heater["max_temp"]) == (35, 60)
    assert (climate["min_temp"], climate["max_temp"]) == (40, 80)


def test_q85_operation_mode_prefixes() -> None:
    climate = load_q85()["entities"]["climate"][0]
    mode_codes = climate["mode_codes"]

    assert climate["mode_match"] == "prefix"
    assert resolve_mode_code("020000", mode_codes, "prefix") == "standby"
    assert resolve_mode_code("12000C", mode_codes, "prefix") == "standby"
    assert resolve_mode_code("03000C", mode_codes, "prefix") == "normal"
    assert resolve_mode_code("430000", mode_codes, "prefix") == "energy_saving"
    assert resolve_mode_code("830000", mode_codes, "prefix") == "outdoor"
    assert resolve_mode_code("FF0000", mode_codes, "prefix") is None


def test_q85_has_every_mode_transition() -> None:
    climate = load_q85()["entities"]["climate"][0]
    modes = set(climate["modes"])
    expected = {
        f"{source}_to_{target}"
        for source in modes
        for target in modes
        if source != target
    }

    assert set(climate["transitions"]) == expected
    assert all(
        step["value"] == "31"
        for steps in climate["transitions"].values()
        for step in steps
    )


def test_q85_circulation_is_stateless_button() -> None:
    config = load_q85()
    buttons = config["entities"]["button"]
    switches = config["entities"]["switch"]
    status = next(
        sensor
        for sensor in config["entities"]["sensor"]
        if sensor["key"] == "circulation_status"
    )

    assert not any(switch["key"] == "water_circulation" for switch in switches)
    assert buttons == [
        {
            "key": "water_circulation",
            "name": "一键循环",
            "type": "command_button",
            "command_key": "temporaryCycleInsulationSetting",
            "command_value": "31",
        }
    ]
    assert get_hex_byte("03000C", status["byte_index"]) == status["on_value"]
    assert get_hex_byte("030000", status["byte_index"]) == "00"
    assert get_hex_byte("invalid", status["byte_index"]) is None


def test_dynamic_mqtt_code_rejects_protocol_message_codes() -> None:
    reserved = {"0", "FFFF", "03F1"}

    assert normalize_dynamic_mqtt_code("1a2b", reserved) == "1A2B"
    assert normalize_dynamic_mqtt_code("FFFF", reserved) is None
    assert normalize_dynamic_mqtt_code("03F1", reserved) is None
    assert normalize_dynamic_mqtt_code("123", reserved) is None
    assert normalize_dynamic_mqtt_code("ZZZZ", reserved) is None


def test_q85_schedule_shape_is_explicit() -> None:
    config = load_q85()

    assert config["features"]["heat_type"] == "Q85_HEAT_OVEN"
    assert config["features"]["dynamic_mqtt_code"] is True
    assert config["schedule_config"] == {
        "total_length": 34,
        "status_byte_index": 0,
        "mode_byte_index": 1,
        "data_start_byte_index": 2,
        "bytes_per_mode": 3,
        "mode_count": 5,
    }
