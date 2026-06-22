"""Helpers for devices that adjust temperature with relative commands."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

GetStateValue = Callable[[str], Any]
SendCommand = Callable[[dict[str, Any]], Awaitable[bool]]
RefreshState = Callable[[], Awaitable[None]]


@dataclass(slots=True)
class RelativeTemperatureTarget:
    """Resolved target for relative temperature control."""

    requested: int
    target: int | None
    allowed_temps: list[int] | None = None
    adjusted: bool = False


@dataclass(slots=True)
class RelativeTemperatureResult:
    """Result of a relative temperature change."""

    reached_target: bool = False
    command_sent: bool = False


def current_temperature(
    state_attribute: str,
    get_state_value: GetStateValue,
) -> int | None:
    """Return the current integer temperature from mapped device state."""
    try:
        current = get_state_value(state_attribute)
        return int(current) if current is not None else None
    except (ValueError, TypeError):
        return None


def resolve_target_temperature(
    device_id: str,
    temperature: int,
    control: dict[str, Any],
    get_state_value: GetStateValue,
) -> RelativeTemperatureTarget:
    """Resolve and validate a requested relative-control target temperature."""
    allowed_temps = _allowed_temperatures_for_current_mode(
        device_id, control, get_state_value
    )
    if allowed_temps is None or temperature in allowed_temps:
        return RelativeTemperatureTarget(
            requested=temperature,
            target=temperature,
            allowed_temps=allowed_temps,
        )

    if not allowed_temps or not control.get("adjust_unsupported_temperature"):
        _LOGGER.warning(
            "Device %s: temperature %sC is not allowed for current mode",
            device_id,
            temperature,
        )
        return RelativeTemperatureTarget(
            requested=temperature,
            target=None,
            allowed_temps=allowed_temps,
        )

    target = nearest_supported_temperature(temperature, allowed_temps)
    _LOGGER.warning(
        "Device %s: temperature %sC is not allowed for current mode; using nearest supported %sC",
        device_id,
        temperature,
        target,
    )
    return RelativeTemperatureTarget(
        requested=temperature,
        target=target,
        allowed_temps=allowed_temps,
        adjusted=True,
    )


async def async_set_relative_temperature(
    *,
    device_id: str,
    target_temperature: int,
    state_attribute: str,
    control: dict[str, Any],
    allowed_temps: list[int] | None,
    get_state_value: GetStateValue,
    send_command: SendCommand,
    refresh_state: RefreshState,
) -> RelativeTemperatureResult:
    """Adjust temperature step-by-step with configured relative commands."""
    command_key = control.get("command_key")
    increase_value = control.get("increase")
    decrease_value = control.get("decrease")
    if not command_key or increase_value is None or decrease_value is None:
        _LOGGER.warning(
            "Device %s: invalid relative temperature control config",
            device_id,
        )
        return RelativeTemperatureResult()

    current = current_temperature(state_attribute, get_state_value)
    if current is None:
        _LOGGER.warning(
            "Device %s: cannot set relative temperature without current state",
            device_id,
        )
        return RelativeTemperatureResult()

    if current == target_temperature:
        return RelativeTemperatureResult(reached_target=True)

    max_steps = _relative_temperature_steps(
        current, target_temperature, allowed_temps
    )
    refresh_retries = _refresh_retries(control)
    result = RelativeTemperatureResult()

    for _ in range(max_steps):
        current = current_temperature(state_attribute, get_state_value)
        if current is None:
            return result
        if current == target_temperature:
            result.reached_target = True
            return result

        command_value = increase_value if target_temperature > current else decrease_value
        if not await send_command({command_key: command_value}):
            return result
        result.command_sent = True

        previous_temperature = current
        for _ in range(refresh_retries):
            await refresh_state()
            current = current_temperature(state_attribute, get_state_value)
            if current == target_temperature or current != previous_temperature:
                break
        if current == target_temperature:
            result.reached_target = True
            return result
        if current == previous_temperature:
            _LOGGER.warning(
                "Device %s: temperature did not change after relative command; stopping",
                device_id,
            )
            return result

    return result


def nearest_supported_temperature(
    temperature: int,
    allowed_temps: list[int],
) -> int:
    """Return the closest allowed target, preferring the warmer value on ties."""
    return min(
        allowed_temps,
        key=lambda allowed: (abs(allowed - temperature), -allowed),
    )


def _relative_temperature_steps(
    current_temperature: int,
    target_temperature: int,
    allowed_temps: list[int] | None,
) -> int:
    """Return how many relative commands may be needed to reach a target."""
    if (
        allowed_temps
        and current_temperature in allowed_temps
        and target_temperature in allowed_temps
    ):
        return max(
            abs(
                allowed_temps.index(target_temperature)
                - allowed_temps.index(current_temperature)
            ),
            1,
        )

    return max(abs(target_temperature - current_temperature), 1)


def _allowed_temperatures_for_current_mode(
    device_id: str,
    control: dict[str, Any],
    get_state_value: GetStateValue,
) -> list[int] | None:
    """Return configured allowed temperatures for the current raw mode."""
    allowed_by_mode = control.get("allowed_temps_by_mode")
    if not allowed_by_mode:
        return None

    mode_attribute = control.get("mode_attribute", "operation_mode")
    raw_mode = get_state_value(mode_attribute)
    if raw_mode is None:
        _LOGGER.warning(
            "Device %s: cannot validate temperature without %s",
            device_id,
            mode_attribute,
        )
        return []

    allowed = allowed_by_mode.get(str(raw_mode).upper())
    if allowed is None:
        _LOGGER.warning(
            "Device %s: unknown operation mode %s for temperature validation",
            device_id,
            raw_mode,
        )
        return []

    return [int(temp) for temp in allowed]


def _refresh_retries(control: dict[str, Any]) -> int:
    """Return how many times to poll state after a relative step."""
    try:
        return max(1, int(control.get("refresh_retries", 1)))
    except (ValueError, TypeError):
        return 1
