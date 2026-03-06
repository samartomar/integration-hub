"""Integration Hub API configuration. No raw endpoint construction."""

from __future__ import annotations

import os
import re
from urllib.parse import quote, urljoin, urlparse

# Pre-defined path constants - never from input
_EXECUTE_PATH = "/v1/integrations/execute"
_REGISTRY_CONTRACTS_PATH = "/v1/registry/contracts"
_REGISTRY_OPERATIONS_PATH = "/v1/registry/operations"


def get_admin_api_base_url() -> str:
    """Get Admin API base URL (registry, audit). Uses ADMIN_API_URL."""
    base: str | None = os.environ.get("ADMIN_API_URL")
    if not base or not isinstance(base, str):
        raise ValueError("ADMIN_API_URL must be set for registry/audit calls")
    base = base.strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise ValueError("ADMIN_API_URL must be a valid HTTPS/HTTP URL")
    if not _is_safe_host(parsed.netloc):
        raise ValueError("ADMIN_API_URL has invalid host format")
    return urljoin(base + "/", "")


def get_integration_hub_base_url() -> str:
    """Get Integration Hub API base URL (legacy; registry uses Admin API)."""
    return get_admin_api_base_url()


def get_integration_hub_api_url() -> str:
    """
    Get Integration Hub API execute URL from environment.

    INTEGRATION_HUB_API_URL = base URL (e.g. https://xxx.execute-api.region.amazonaws.com).
    Path /v1/integrations/execute is appended. Uses urljoin - no f-string or + concatenation.
    Raises ValueError if invalid.
    """
    base: str | None = (
        os.environ.get("VENDOR_API_URL")
        or os.environ.get("INTEGRATION_HUB_API_URL")
        or os.environ.get("INTEGRATION_API_URL")
    )
    if not base or not isinstance(base, str):
        raise ValueError("VENDOR_API_URL (or INTEGRATION_HUB_API_URL) must be set")

    base = base.strip().rstrip("/")
    parsed = urlparse(base)

    if parsed.scheme not in ("https", "http"):
        raise ValueError("INTEGRATION_HUB_API_URL must use HTTPS or HTTP")
    if not parsed.netloc:
        raise ValueError("INTEGRATION_HUB_API_URL must have a valid host")
    if not _is_safe_host(parsed.netloc):
        raise ValueError("INTEGRATION_HUB_API_URL has invalid host format")

    return urljoin(base + "/", _EXECUTE_PATH)


def get_registry_contracts_url(operation_code: str, canonical_version: str) -> str:
    """Build GET /v1/registry/contracts URL with query params (Admin API)."""
    base = get_admin_api_base_url().rstrip("/") + "/"
    qs = f"operationCode={quote(operation_code)}&canonicalVersion={quote(canonical_version)}"
    return urljoin(base, f"{_REGISTRY_CONTRACTS_PATH}?{qs}")


def get_registry_operations_url(
    is_active: bool = True,
    source_vendor: str | None = None,
    target_vendor: str | None = None,
) -> str:
    """Build GET /v1/registry/operations URL with query params (Admin API)."""
    base = get_admin_api_base_url().rstrip("/") + "/"
    parts = [f"isActive={str(is_active).lower()}"]
    if source_vendor and target_vendor:
        parts.append(f"sourceVendor={quote(source_vendor)}&targetVendor={quote(target_vendor)}")
    qs = "&".join(parts)
    return urljoin(base, f"{_REGISTRY_OPERATIONS_PATH}?{qs}")


def _is_safe_host(netloc: str) -> bool:
    """Validate host format - alphanumeric, dots, hyphens. Allows port."""
    host = netloc.split(":")[0] if ":" in netloc else netloc
    return bool(re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$", host))


def get_integration_api_key() -> str | None:
    """
    Get optional API key from environment.
    HttpApi does not use API key; REST API with Usage Plan may require it.
    Returns None if not set.
    """
    key: str | None = os.environ.get("INTEGRATION_API_KEY") or os.environ.get("INTEGRATION_HUB_API_KEY")
    if not key or not isinstance(key, str):
        return None
    return key.strip() or None
