"""Protocol contracts for commands sent to Rinnai devices."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

CORE_DIR = Path(__file__).parents[1] / "custom_components" / "rinnai" / "core"
sys.path.insert(0, str(CORE_DIR))

from command import RinnaiCommand, build_mqtt_command_message  # noqa: E402


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
