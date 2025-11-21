"""Device configuration models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass
class RinnaiDeviceConfig:
    """Rinnai device configuration."""
    name: str
    supported_models: list[str]
    
    # Generic configuration fields
    entities: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    state_mapping: dict[str, str] = field(default_factory=dict)
    processors: dict[str, list[Any]] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)
    
    # API Requests configuration
    requests: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RinnaiDeviceConfig:
        """Create config from dictionary."""
        return cls(
            name=data.get("name", "Unknown"),
            supported_models=data.get("supported_models", []),
            entities=data.get("entities", {}),
            state_mapping=data.get("state_mapping", {}),
            processors=data.get("processors", {}),
            features=data.get("features", {}),
            requests=data.get("requests", {})
        )
