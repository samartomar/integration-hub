"""Vendor service - validation and create_vendor."""

from __future__ import annotations

import uuid
from typing import Any

from repository import vendor_repository


def _validate_uuid(value: str | None, field_name: str) -> str:
    """Validate UUID string for id parameters."""
    if not value or not isinstance(value, str):
        raise ValueError(f"{field_name} is required")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} cannot be empty")
    try:
        uuid.UUID(stripped)
    except ValueError:
        raise ValueError(f"{field_name} must be a valid UUID") from None
    return stripped


def _validate_name(name: str | None) -> str:
    """Validate vendor name. Returns trimmed name or raises ValueError."""
    if name is None or not isinstance(name, str):
        raise ValueError("name is required and must be a string")
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("name cannot be empty")
    return trimmed


def _validate_description(description: Any) -> str | None:
    """Validate description. Returns None or string."""
    if description is None:
        return None
    if not isinstance(description, str):
        raise ValueError("description must be a string")
    return description.strip() or None


def create_vendor(name: str | None, description: Any = None) -> dict[str, Any]:
    """
    Create a vendor. Validates input and delegates to repository.
    Raises ValueError on validation failure.
    """
    validated_name = _validate_name(name)
    validated_description = _validate_description(description)
    return vendor_repository.insert(validated_name, validated_description)


def list_vendors() -> list[dict[str, Any]]:
    """List all vendors."""
    return vendor_repository.list_all()


def get_vendor(vendor_id: str | None) -> dict[str, Any] | None:
    """Get a vendor by ID."""
    if not vendor_id:
        return None
    try:
        validated_id = _validate_uuid(vendor_id, "vendor_id")
    except ValueError:
        return None
    return vendor_repository.get_by_id(validated_id)


def update_vendor(
    vendor_id: str,
    name: str | None = None,
    description: Any = None,
) -> dict[str, Any] | None:
    """Update a vendor. Returns updated row or None if not found."""
    validated_id = _validate_uuid(vendor_id, "vendor_id")
    validated_name = _validate_name(name) if name is not None else None
    validated_description = _validate_description(description) if description is not None else None
    return vendor_repository.update(validated_id, validated_name, validated_description)


def delete_vendor(vendor_id: str) -> bool:
    """Delete a vendor. Returns True if deleted."""
    validated_id = _validate_uuid(vendor_id, "vendor_id")
    return vendor_repository.delete(validated_id)
