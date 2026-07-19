"""Device configuration models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass
class RinnaiDeviceConfig:
    """Rinnai device configuration."""
    name: str
    
    # Generic configuration fields
    entities: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    state_mapping: dict[str, str] = field(default_factory=dict)
    processors: dict[str, list[Any]] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)
    
    # API Requests configuration
    supported_requests: list[str] = field(default_factory=list)
    
    # Schedule configuration
    schedule_config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RinnaiDeviceConfig:
        """Create config from dictionary."""
        return cls(
            name=data.get("name", "Unknown"),
            entities=data.get("entities", {}),
            state_mapping=data.get("state_mapping", {}),
            processors=data.get("processors", {}),
            features=data.get("features", {}),
            supported_requests=data.get("supported_requests", []),
            schedule_config=data.get("schedule_config", {})
        )
