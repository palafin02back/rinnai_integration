"""Entity utilities for Rinnai integration."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..coordinator import RinnaiCoordinator

_LOGGER = logging.getLogger(__name__)


def resolve_mode_code(
    code: Any,
    mode_codes: dict[str, list[str]],
    match: str = "exact",
) -> str | None:
    """Resolve a raw operation-mode value without changing legacy matching."""
    normalized = str(code).upper()
    for mode_key, configured_codes in mode_codes.items():
        candidates = [str(item).upper() for item in configured_codes]
        if match == "prefix":
            if any(candidate and normalized.startswith(candidate) for candidate in candidates):
                return mode_key
        elif normalized in candidates:
            return mode_key
    return None


def get_hex_byte(value: Any, byte_index: int) -> str | None:
    """Return one byte from an even-length hexadecimal state value."""
    if byte_index < 0:
        return None
    normalized = str(value).strip().upper()
    if normalized.startswith("0X"):
        normalized = normalized[2:]
    if len(normalized) % 2 or any(char not in "0123456789ABCDEF" for char in normalized):
        return None
    start = byte_index * 2
    if len(normalized) < start + 2:
        return None
    return normalized[start : start + 2]


def normalize_dynamic_mqtt_code(
    code: Any,
    reserved_codes: set[str],
) -> str | None:
    """Validate a device command code learned from an info message."""
    normalized = str(code).strip().upper()
    reserved = {str(item).strip().upper() for item in reserved_codes}
    if normalized in reserved:
        return None
    if len(normalized) != 4 or any(char not in "0123456789ABCDEF" for char in normalized):
        return None
    return normalized

def get_state_value(device_state: Any, attribute_key: str, mapping: dict[str, str] | None = None) -> Any:
    """
    Get value from device state using mapping.
    
    Args:
        device_state: The RinnaiDeviceState object.
        attribute_key: The generic attribute key (e.g., 'target_temperature').
        mapping: The state mapping dictionary from config.
    """
    if not device_state:
        return None
        
    # 1. Try to find mapped key in raw_data (processed data)
    if mapping and attribute_key in mapping:
        mapped_key = mapping[attribute_key]
        if mapped_key in device_state.raw_data:
            return device_state.raw_data[mapped_key]
            
    # 2. Fallback: Try to find attribute directly on state object (legacy support)
    if hasattr(device_state, attribute_key):
        return getattr(device_state, attribute_key)
        
    # 3. Fallback: Try to find key directly in raw_data
    if attribute_key in device_state.raw_data:
        return device_state.raw_data[attribute_key]
        
    return None

async def execute_transition(
    coordinator: "RinnaiCoordinator",
    device_id: str,
    steps: list[dict[str, Any]],
) -> bool:
    """Execute a sequence of transition steps via the coordinator (supports optimistic state).

    Args:
        coordinator: The RinnaiCoordinator instance.
        device_id: The device ID.
        steps: List of transition steps. Each step is a dict with 'cmd', 'value', and optional 'delay'.
    """
    for idx, step in enumerate(steps):
        cmd_key = step.get("cmd")
        cmd_value = step.get("value")
        delay = step.get("delay", 0)

        if not cmd_key or cmd_value is None:
            _LOGGER.warning("Invalid transition step at index %d: %s", idx, step)
            continue

        command = {cmd_key: cmd_value}
        _LOGGER.debug("Executing transition step %d: %s", idx + 1, command)

        success = await coordinator.async_send_command(device_id, command)
        if not success:
            _LOGGER.warning("Failed to execute transition step %d: %s", idx + 1, command)
            return False

        if delay > 0:
            await asyncio.sleep(delay)

    return True
