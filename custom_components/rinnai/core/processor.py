"""Data processor for Rinnai integration."""
from __future__ import annotations

import logging
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)

def hex_to_int(value: Any, *args) -> int:
    """Convert hex string to integer."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if not value:
            return 0
        try:
            return int(value, 16)
        except ValueError:
            _LOGGER.warning("Failed to convert hex value: %s", value)
            return 0
    return 0

def multiply(value: Any, factor: float | int) -> float | int:
    """Multiply value by factor."""
    try:
        result = float(value) * float(factor)
        # Return int if the result is effectively an integer
        if result.is_integer():
            return int(result)
        return result
    except (ValueError, TypeError):
        return 0

def divide(value: Any, factor: float | int) -> float:
    """Divide value by factor."""
    try:
        if float(factor) == 0:
            return 0.0
        return float(value) / float(factor)
    except (ValueError, TypeError):
        return 0.0

def to_type(value: Any, target_type: str) -> Any:
    """Convert value to target type."""
    try:
        if target_type == "int":
            return int(float(value))
        elif target_type == "float":
            return float(value)
        elif target_type == "str":
            return str(value)
    except (ValueError, TypeError):
        pass
    return value

PROCESSORS: dict[str, Callable] = {
    "hex_to_int": hex_to_int,
    "multiply": multiply,
    "divide": divide,
    "to_type": to_type,
}

def process_value(value: Any, processor_configs: list[dict[str, Any] | str]) -> Any:
    """
    Process a single value through a chain of processors.
    
    Args:
        value: The value to process.
        processor_configs: List of processor configurations. 
                           Can be a string (name only) or dict ({"func": "name", "args": [...]}).
    """
    result = value
    for config in processor_configs:
        func_name = ""
        args = []
        
        if isinstance(config, str):
            func_name = config
        elif isinstance(config, dict):
            func_name = config.get("func", "")
            args = config.get("args", [])
            
        if processor_func := PROCESSORS.get(func_name):
            try:
                result = processor_func(result, *args)
            except Exception as e:
                _LOGGER.warning("Error in processor %s: %s", func_name, e)
        else:
            _LOGGER.warning("Unknown processor: %s", func_name)
            
    return result

def process_data(raw_data: dict[str, Any], config_processors: dict[str, list[Any]]) -> dict[str, Any]:
    """Process raw data dictionary based on configuration."""
    processed_data = {}
    
    # First copy all raw data
    processed_data.update(raw_data)
    
    # Apply processors
    for field, processor_list in config_processors.items():
        if field in raw_data:
            processed_data[field] = process_value(raw_data[field], processor_list)
            
    return processed_data
