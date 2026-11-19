"""Protocol contracts for commands sent to Rinnai devices."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

CORE_DIR = Path(__file__).parents[1] / "custom_components" / "rinnai" / "core"
sys.path.insert(0, str(CORE_DIR))

from command import (  # noqa: E402
    RinnaiCommand,
    build_conditional_payload,
    build_mqtt_command_message,
    decode_time_hex_pair,
    encode_combined_temperature,
    encode_temperature,
    encode_time_hex_pair,
)


@pytest.mark.parametrize(
    ("device_data", "command", "expected_enl"),
    [
        (
            {"authCode": "A56C", "classID": "0F06000C"},
            {"summerWinter": "31"},
            [{"data": "31", "id": "summerWinter"}],
        ),
        (
            {"authCode": "A85C", "classID": "0F060001"},
            {"temporaryCycleInsulationSetting": "31"},
            [{"data": "31", "id": "temporaryCycleInsulationSetting"}],
        ),
        (
            {"authCode": "E32C", "classID": "02720E32"},
            {"hotWaterTempOperate": "01"},
            [{"data": "01", "id": "hotWaterTempOperate"}],
        ),
    ],
)
def test_working_device_mqtt_payloads_are_preserved(
    device_data: dict[str, str],
    command: dict[str, str],
    expected_enl: list[dict[str, str]],
) -> None:
    """Known-working devices keep their exact command payloads."""
    protocol = {"info_code": "FFFF", "command_pattern": "J00", "command_sum": "1"}

    message = build_mqtt_command_message(device_data, command, protocol)

    assert message == {
        "code": device_data["authCode"],
        "enl": expected_enl,
        "id": device_data["classID"],
        "ptn": "J00",
        "sum": "1",
    }
    assert json.loads(json.dumps(message)) == message


def test_legacy_dict_command_remains_stateful() -> None:
    """Existing callers retain their optimistic state behavior."""
    command = RinnaiCommand.coerce({"power": "01"})

    assert command.payload == {"power": "01"}
    assert command.optimistic_state == {"power": "01"}


def test_stateless_command_has_no_optimistic_state() -> None:
    """Action commands can be sent without pretending they are device state."""
    command = RinnaiCommand.stateless({"forceRegen": "01"})

    assert command.payload == {"forceRegen": "01"}
    assert command.optimistic_state == {}


def test_conditional_payload_adds_only_matching_state_resets() -> None:
    state = {"operation_mode": "03", "heating_reservation": "31"}
    rules = [
        {
            "state_attribute": "operation_mode",
            "not_in_values": ["0", "00", "2", "02"],
            "command": {"operationMode": "00"},
        },
        {
            "state_attribute": "heating_reservation",
            "in_values": ["1", "01", "31"],
            "command": {"heatingReservationSetting": "30"},
        },
    ]

    assert build_conditional_payload(
        {"rapidHeatingSetting": "01"}, rules, state.get
    ) == {
        "operationMode": "00",
        "heatingReservationSetting": "30",
        "rapidHeatingSetting": "01",
    }

    state.update(operation_mode="02", heating_reservation="30")
    assert build_conditional_payload(
        {"rapidHeatingSetting": "01"}, rules, state.get
    ) == {"rapidHeatingSetting": "01"}


def test_single_character_values_use_the_mobile_app_wire_format() -> None:
    """The official app zero-pads every one-character ENL value."""
    message = build_mqtt_command_message(
        {"authCode": "AUTH", "classID": "0272000D"},
        {"cycleModeSetting": "1", "operationMode": 0},
        {"info_code": "FFFF", "command_pattern": "J00", "command_sum": "1"},
    )

    assert message["enl"] == [
        {"data": "01", "id": "cycleModeSetting"},
        {"data": "00", "id": "operationMode"},
    ]


@pytest.mark.parametrize(
    ("value", "temp_format", "expected"),
    [
        (40, "hex2", "28"),
        (40, "hex4", "2800"),
        (20, "hex_fraction", "1400"),
        (20.5, "hex_fraction", "1405"),
    ],
)
def test_temperature_encoding_matches_device_families(
    value: float,
    temp_format: str,
    expected: str,
) -> None:
    assert encode_temperature(value, temp_format) == expected


@pytest.mark.parametrize(
    ("value", "companion", "position", "expected"),
    [
        (45, 55, "hot_water", "2D003700"),
        (60, 42, "heating", "2A003C00"),
    ],
)
def test_g58_combined_temperature_encoding(
    value: float,
    companion: float,
    position: str,
    expected: str,
) -> None:
    assert encode_combined_temperature(value, companion, position) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("00:00", "00,00"), ("02:30", "02,1E"), ("23:59", "17,3B")],
)
def test_softener_regeneration_time_encoding(value: str, expected: str) -> None:
    assert encode_time_hex_pair(value) == expected
    assert decode_time_hex_pair(expected) == value


@pytest.mark.parametrize("value", ["24:00", "12:60", "invalid"])
def test_softener_regeneration_time_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        encode_time_hex_pair(value)
