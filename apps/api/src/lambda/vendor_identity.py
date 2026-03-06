"""Vendor identity exceptions and stubs. control_plane.vendor_api_keys table has been removed."""

from __future__ import annotations

from typing import Any


class VendorAuthError(Exception):
    """Invalid or missing API key. Maps to 401."""
    def __init__(self, message: str = "Missing or invalid API key"):
        super().__init__(message)


class VendorForbiddenError(Exception):
    """Vendor inactive. Maps to 403."""
    def __init__(self, message: str, vendor_code: str):
        super().__init__(message)
        self.vendor_code = vendor_code


def resolve_vendor_code(conn: Any, api_key: str | None) -> str:
    """No-op: vendor_api_keys table removed. Raises VendorAuthError if called."""
    raise VendorAuthError("API key auth no longer supported; vendor_api_keys table removed")


def resolve_vendor_and_key_id(conn: Any, api_key: str | None) -> tuple[str, str | None]:
    """No-op: vendor_api_keys table removed. Raises VendorAuthError if called."""
    raise VendorAuthError("API key auth no longer supported; vendor_api_keys table removed")
