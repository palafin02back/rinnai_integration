"""Configuration manager for Rinnai devices."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from ..models.config import RinnaiDeviceConfig

_LOGGER = logging.getLogger(__name__)

class ConfigManager:
    """Manage device configurations."""

    _instance = None
    _configs: dict[str, RinnaiDeviceConfig] = {}
    _model_map: dict[str, RinnaiDeviceConfig] = {}

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def load_configs(self, config_dir: str) -> None:
        """Load all configurations from directory."""
        if not os.path.exists(config_dir):
            _LOGGER.error("Config directory not found: %s", config_dir)
            return

        for filename in os.listdir(config_dir):
            if filename.endswith(".json"):
                try:
                    file_path = os.path.join(config_dir, filename)
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        config = RinnaiDeviceConfig.from_dict(data)
                        
                        # Use filename (without extension) as key
                        key = filename[:-5]
                        self._configs[key] = config
                        
                        # Map supported models to this config
                        for model in config.supported_models:
                            self._model_map[model] = config
                            
                        _LOGGER.debug("Loaded device config: %s (models: %s)", key, config.supported_models)
                except Exception as e:
                    _LOGGER.error("Failed to load config %s: %s", filename, e)

    def get_config(self, device_model: str = None) -> RinnaiDeviceConfig | None:
        """Get configuration for specific device model."""
        if device_model and device_model in self._model_map:
            return self._model_map[device_model]
            
        _LOGGER.warning("No configuration found for device model: %s", device_model)
        return None

# Global instance
config_manager = ConfigManager()
