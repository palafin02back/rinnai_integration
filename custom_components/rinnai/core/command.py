"""Command encoding and optimistic-state semantics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from collections.abc import Callable, Iterable
from typing import Any, Mapping


def encode_mqtt_value(value: Any) -> str:
    """Encode an ENL value using the mobile app's wire format."""
    encoded = str(value)
    return encoded.zfill(2) if len(encoded) == 1 else encoded


def encode_temperature(value: int | float, temp_format: str = "hex2") -> str:
    """Encode a temperature using a device family's wire representation."""
    numeric = Decimal(str(value))
    whole = int(numeric)
    if numeric < 0 or whole > 0xFF:
        raise ValueError(f"temperature out of encodable range: {value}")

    encoded = f"{whole:02X}"
    if temp_format == "hex2":
        if numeric != whole:
            raise ValueError("hex2 temperatures must be whole numbers")
        return encoded
    if temp_format == "hex4":
        if numeric != whole:
            raise ValueError("hex4 temperatures must be whole numbers")
        return f"{encoded}00"
    if temp_format == "hex_fraction":
        tenths = (numeric - whole) * 10
        if tenths != tenths.to_integral_value() or not 0 <= tenths <= 9:
            raise ValueError("hex_fraction temperatures support one decimal place")
        return f"{encoded}0{int(tenths)}"
    raise ValueError(f"unsupported temperature format: {temp_format}")


def encode_combined_temperature(
    value: int | float,
    companion: int | float,
    position: str,
) -> str:
    """Encode G58's hot-water and heating temperatures as one ENL value."""
    encoded_value = encode_temperature(value, "hex4")
    encoded_companion = encode_temperature(companion, "hex4")
    if position == "hot_water":
        return encoded_value + encoded_companion
    if position == "heating":
        return encoded_companion + encoded_value
    raise ValueError(f"unsupported combined temperature position: {position}")


def encode_time_hex_pair(value: str) -> str:
    """Encode HH:MM as the softener's comma-separated hexadecimal pair."""
    match = re.fullmatch(r"(\d{2}):(\d{2})", value)
    if not match:
        raise ValueError("time must use HH:MM format")
    hour, minute = (int(part) for part in match.groups())
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("time is outside the 00:00-23:59 range")
    return f"{hour:02X},{minute:02X}"


def decode_time_hex_pair(value: str) -> str:
    """Decode the softener's comma-separated hexadecimal pair as HH:MM."""
    match = re.fullmatch(r"([0-9A-Fa-f]{1,2}),([0-9A-Fa-f]{1,2})", value)
    if not match:
        raise ValueError("time must use a hexadecimal hour,minute pair")
    hour, minute = (int(part, 16) for part in match.groups())
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("decoded time is outside the 00:00-23:59 range")
    return f"{hour:02d}:{minute:02d}"


def build_conditional_payload(
    base_payload: Mapping[str, Any],
    rules: Iterable[Mapping[str, Any]],
    get_state_value: Callable[[str], Any],
) -> dict[str, Any]:
    """Prepend configured commands whose state predicates currently match."""
    payload: dict[str, Any] = {}
    for rule in rules:
        state_attribute = rule.get("state_attribute")
        command = rule.get("command")
        if not state_attribute or not isinstance(command, Mapping):
            continue
        raw_value = get_state_value(str(state_attribute))
        if raw_value is None:
            continue
        value = str(raw_value).upper()
        in_values = {str(item).upper() for item in rule.get("in_values", [])}
        not_in_values = {
            str(item).upper() for item in rule.get("not_in_values", [])
        }
        if in_values and value not in in_values:
            continue
        if not_in_values and value in not_in_values:
            continue
        payload.update(command)
    payload.update(base_payload)
    return payload


def build_mqtt_command_message(
    device_data: Mapping[str, Any],
    payload: Mapping[str, Any],
    protocol: Mapping[str, str],
) -> dict[str, Any]:
    """Build the MQTT command body shared by every device family."""
    return {
        "code": device_data.get("authCode", protocol["info_code"]),
        "enl": [
            {"data": encode_mqtt_value(value), "id": key}
            for key, value in payload.items()
        ],
        "id": device_data.get("classID"),
        "ptn": protocol["command_pattern"],
        "sum": protocol["command_sum"],
    }


@dataclass(frozen=True, slots=True)
class RinnaiCommand:
    """A wire payload and the state effect HA may show optimistically."""

    payload: dict[str, Any]
    optimistic_state: dict[str, Any]

    @classmethod
    def stateful(
        cls,
        payload: Mapping[str, Any],
        optimistic_state: Mapping[str, Any] | None = None,
    ) -> RinnaiCommand:
        """Create a command whose payload represents a resulting device state."""
        wire_payload = dict(payload)
        return cls(
            payload=wire_payload,
            optimistic_state=dict(
                wire_payload if optimistic_state is None else optimistic_state
            ),
        )

    @classmethod
    def stateless(cls, payload: Mapping[str, Any]) -> RinnaiCommand:
        """Create an action command that has no direct state representation."""
        return cls(payload=dict(payload), optimistic_state={})

    @classmethod
    def coerce(
        cls, command: RinnaiCommand | Mapping[str, Any]
    ) -> RinnaiCommand:
        """Preserve the stateful behavior of existing dictionary callers."""
        return command if isinstance(command, cls) else cls.stateful(command)
