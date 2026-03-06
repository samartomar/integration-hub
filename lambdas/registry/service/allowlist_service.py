"""Allowlist service - validation and create_allowlist."""

from __future__ import annotations

import uuid
from typing import Any

from repository import allowlist_repository, operation_repository, vendor_repository


def _validate_uuid(value: Any, field_name: str) -> str:
    """Validate UUID string. Returns value or raises ValueError."""
    if value is None or not isinstance(value, str):
        raise ValueError(f"{field_name} is required and must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} cannot be empty")
    try:
        uuid.UUID(stripped)
    except ValueError:
        raise ValueError(f"{field_name} must be a valid UUID") from None
    return stripped


def create_allowlist(vendor_id: Any, operation_id: Any) -> dict[str, Any]:
    """
    Create an allowlist entry. Validates UUIDs and references exist.
    Raises ValueError on validation failure.
    """
    validated_vendor_id = _validate_uuid(vendor_id, "vendor_id")
    validated_operation_id = _validate_uuid(operation_id, "operation_id")

    if vendor_repository.get_by_id(validated_vendor_id) is None:
        raise ValueError("vendor_id does not exist")
    if operation_repository.get_by_id(validated_operation_id) is None:
        raise ValueError("operation_id does not exist")

    existing = allowlist_repository.get_by_vendor_operation(
        validated_vendor_id, validated_operation_id
    )
    if existing:
        raise ValueError(
            "allowlist entry already exists for this vendor and operation"
        )

    return allowlist_repository.insert(validated_vendor_id, validated_operation_id)


def list_allowlist() -> list[dict[str, Any]]:
    """List all allowlist entries."""
    return allowlist_repository.list_all()


def get_allowlist(allowlist_id: str | None) -> dict[str, Any] | None:
    """Get an allowlist entry by ID."""
    if not allowlist_id:
        return None
    try:
        validated_id = _validate_uuid(allowlist_id, "allowlist_id")
    except ValueError:
        return None
    return allowlist_repository.get_by_id(validated_id)


def delete_allowlist(allowlist_id: str) -> bool:
    """Delete an allowlist entry. Returns True if deleted."""
    validated_id = _validate_uuid(allowlist_id, "allowlist_id")
    return allowlist_repository.delete(validated_id)
