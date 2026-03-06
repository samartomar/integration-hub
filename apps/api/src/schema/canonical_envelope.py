"""Canonical envelope shape for operation requests and responses.

Standard structure wrapping operation payloads with metadata for correlation,
audit, and routing. Direction: REQUEST | RESPONSE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CanonicalEnvelope:
    """Standard envelope wrapping operation payloads."""

    operation_code: str
    version: str
    direction: str  # REQUEST | RESPONSE
    correlation_id: str
    timestamp: str  # ISO 8601 datetime
    context: dict[str, Any]
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to API-friendly dict (camelCase keys)."""
        return {
            "operationCode": self.operation_code,
            "version": self.version,
            "direction": self.direction,
            "correlationId": self.correlation_id,
            "timestamp": self.timestamp,
            "context": self.context,
            "payload": self.payload,
        }


# JSON Schema for envelope validation
# direction: REQUEST | RESPONSE
# timestamp: ISO-8601 datetime-compatible
# correlationId: non-empty string
# context: object
# payload: object
ENVELOPE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["operationCode", "version", "direction", "correlationId", "timestamp", "context", "payload"],
    "properties": {
        "operationCode": {"type": "string", "minLength": 1},
        "version": {"type": "string", "minLength": 1},
        "direction": {"type": "string", "enum": ["REQUEST", "RESPONSE"]},
        "correlationId": {"type": "string", "minLength": 1},
        "timestamp": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$"},
        "context": {"type": "object", "additionalProperties": True},
        "payload": {"type": "object"},
    },
    "additionalProperties": False,
}


def build_envelope(
    operation_code: str,
    version: str,
    direction: str,
    payload: dict[str, Any],
    *,
    correlation_id: str = "corr-example",
    timestamp: str = "2025-03-06T12:00:00Z",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical envelope dict from operation metadata and payload."""
    return {
        "operationCode": operation_code,
        "version": version,
        "direction": direction,
        "correlationId": correlation_id,
        "timestamp": timestamp,
        "context": context or {},
        "payload": payload,
    }
