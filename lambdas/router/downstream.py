"""Downstream invocation layer - invoke_downstream."""

from __future__ import annotations

from typing import Any


def invoke_downstream(envelope: dict[str, Any]) -> dict[str, Any]:
    """
    Invoke downstream integration (vendor adapter, external API, etc.).

    Stub: returns mock success response. Will call Integration API or
    vendor-specific adapters when implemented.
    """
    _ = envelope  # Used when implemented
    return {
        "status": "success",
        "sourceVendor": envelope.get("sourceVendor"),
        "targetVendor": envelope.get("targetVendor"),
        "operation": envelope.get("operation"),
        "idempotencyKey": envelope.get("idempotencyKey"),
    }
