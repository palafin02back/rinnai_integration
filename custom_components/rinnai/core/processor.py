"""Data processor for Rinnai integration."""
from __future__ import annotations

import logging
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)

PROCESSORS: dict[str, Callable] = {}

def processor(func, name: str = None):
    if not name:
        name = func.__name__
    if name in PROCESSORS:
        raise Exception("processor with name " + name + " is already defined.")
    PROCESSORS[name] = func
    return func

@processor
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

@processor
def hex4_to_int(value: Any, *args) -> int:
    """Convert hex string to integer."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if len(value) >= 2:
            try:
                return int(value[:-2], 16)
            except ValueError:
                pass
    _LOGGER.warning("Failed to convert hex4 value: %s", value)
    return 0

@processor
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

@processor
def divide(value: Any, factor: float | int) -> float:
    """Divide value by factor."""
    try:
        if float(factor) == 0:
            return 0.0
        return float(value) / float(factor)
    except (ValueError, TypeError):
        return 0.0

@processor
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
                _LOGGER.warning("Error in processor '%s' (value=%r): %s", func_name, result, e)
        else:
            _LOGGER.warning("Unknown processor: '%s'", func_name)
            
    return result

def process_data(raw_data: dict[str, Any], config_processors: dict[str, list[Any]]) -> dict[str, Any]:
    """Process raw data dictionary based on configuration."""
    processed_data = {}
    
    # First copy all raw data
    processed_data.update(raw_data)
    
    # Apply processors
    for field, processor_list in config_processors.items():
        if field in raw_data:
            try:
                processed_data[field] = process_value(raw_data[field], processor_list)
            except Exception as e:
                _LOGGER.warning("Failed to process field '%s' (value=%r): %s", field, raw_data[field], e)
            
    return processed_data
