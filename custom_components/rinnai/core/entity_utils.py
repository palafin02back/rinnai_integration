"""Entity utilities for Rinnai integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..core.client import RinnaiClient

_LOGGER = logging.getLogger(__name__)

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
    client: RinnaiClient, 
    device_id: str, 
    steps: list[dict[str, Any]]
) -> bool:
    """
    Execute a sequence of transition steps.
    
    Args:
        client: The RinnaiClient instance.
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
        
        success = await client.send_command(device_id, command)
        if not success:
            _LOGGER.warning("Failed to execute transition step %d: %s", idx + 1, command)
            return False
            
        if delay > 0:
            await asyncio.sleep(delay)
            
    return True
