"""Operation service - validation and create_operation."""

from __future__ import annotations

import uuid
from typing import Any

from repository import operation_repository


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
    """Validate operation name. Returns trimmed name or raises ValueError."""
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


def create_operation(name: str | None, description: Any = None) -> dict[str, Any]:
    """
    Create an operation. Validates input and delegates to repository.
    Raises ValueError on validation failure.
    """
    validated_name = _validate_name(name)
    validated_description = _validate_description(description)
    return operation_repository.insert(validated_name, validated_description)


def list_operations() -> list[dict[str, Any]]:
    """List all operations."""
    return operation_repository.list_all()


def get_operation(operation_id: str | None) -> dict[str, Any] | None:
    """Get an operation by ID."""
    if not operation_id:
        return None
    try:
        validated_id = _validate_uuid(operation_id, "operation_id")
    except ValueError:
        return None
    return operation_repository.get_by_id(validated_id)


def update_operation(
    operation_id: str,
    name: str | None = None,
    description: Any = None,
) -> dict[str, Any] | None:
    """Update an operation. Returns updated row or None if not found."""
    validated_id = _validate_uuid(operation_id, "operation_id")
    validated_name = _validate_name(name) if name is not None else None
    validated_description = _validate_description(description) if description is not None else None
    return operation_repository.update(validated_id, validated_name, validated_description)


def delete_operation(operation_id: str) -> bool:
    """Delete an operation. Returns True if deleted."""
    validated_id = _validate_uuid(operation_id, "operation_id")
    return operation_repository.delete(validated_id)
