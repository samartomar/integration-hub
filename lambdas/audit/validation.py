"""Query parameter validation - prevents invalid input and SQL injection via strict validation."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_OFFSET = 1_000_000
MAX_STRING_LENGTH = 128

# ISO 8601 date/datetime pattern (relaxed)
_ISO_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}"  # YYYY-MM-DD
    r"(T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$"  # optional time + TZ
)


def _parse_int(value: str | None, default: int, min_val: int, max_val: int, name: str) -> int:
    """Parse and validate integer parameter."""
    if value is None or value.strip() == "":
        return default
    try:
        n = int(value.strip())
    except ValueError:
        raise ValueError(f"{name} must be a valid integer")
    if n < min_val:
        raise ValueError(f"{name} must be >= {min_val}")
    if n > max_val:
        raise ValueError(f"{name} must be <= {max_val}")
    return n


def _validate_iso8601(value: str | None) -> str | None:
    """Validate ISO 8601 date/datetime string. Returns normalized string or None."""
    if value is None or not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if not _ISO_PATTERN.match(stripped):
        raise ValueError("date must be ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)")
    try:
        datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"invalid date: {e}") from e
    return stripped


def _validate_string(value: str | None, name: str, max_len: int = MAX_STRING_LENGTH) -> str | None:
    """Validate optional string filter. Returns trimmed string or None."""
    if value is None or not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) > max_len:
        raise ValueError(f"{name} must be at most {max_len} characters")
    return stripped


def validate_query_params(params: dict[str, str] | None) -> dict[str, Any]:
    """
    Validate and parse query parameters for transaction listing.

    Returns validated dict with: limit, offset, date_from, date_to, operation, status,
    transaction_id, correlation_id, source_vendor, target_vendor.

    Raises ValueError on validation failure.
    """
    params = params or {}

    limit = _parse_int(
        params.get("limit"),
        default=DEFAULT_LIMIT,
        min_val=1,
        max_val=MAX_LIMIT,
        name="limit",
    )
    offset = _parse_int(
        params.get("offset"),
        default=0,
        min_val=0,
        max_val=MAX_OFFSET,
        name="offset",
    )

    date_from = _validate_iso8601(params.get("dateFrom") or params.get("date_from"))
    date_to = _validate_iso8601(params.get("dateTo") or params.get("date_to"))

    if date_from and date_to and date_from > date_to:
        raise ValueError("dateFrom must be before or equal to dateTo")

    operation = _validate_string(params.get("operation"), "operation")
    status = _validate_string(params.get("status"), "status")
    transaction_id = _validate_string(params.get("transactionId") or params.get("transaction_id"), "transactionId")
    correlation_id = _validate_string(params.get("correlationId") or params.get("correlation_id"), "correlationId")
    source_vendor = _validate_string(params.get("sourceVendor") or params.get("source_vendor"), "sourceVendor")
    target_vendor = _validate_string(params.get("targetVendor") or params.get("target_vendor"), "targetVendor")

    return {
        "transaction_id": transaction_id,
        "correlation_id": correlation_id,
        "source_vendor": source_vendor,
        "target_vendor": target_vendor,
        "operation": operation,
        "status": status,
        "date_from": date_from,
        "date_to": date_to,
        "limit": limit,
        "offset": offset,
    }
