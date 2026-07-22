"""Command encoding and optimistic-state semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def encode_mqtt_value(value: Any) -> str:
    """Encode an ENL value using the mobile app's wire format."""
    encoded = str(value)
    return encoded.zfill(2) if len(encoded) == 1 else encoded


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
