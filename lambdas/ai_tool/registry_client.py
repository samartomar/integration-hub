"""Registry API client - fetches contracts and operations from Integration Hub."""

from __future__ import annotations

import json
from typing import Any

from config import (
    get_integration_api_key,
    get_registry_contracts_url,
    get_registry_operations_url,
)


def fetch_operations(
    is_active: bool = True,
    source_vendor: str | None = None,
    target_vendor: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch operations from GET /v1/registry/operations.
    Returns list of {operation_code, description, canonical_version}.
    """
    import urllib.request

    url = get_registry_operations_url(is_active, source_vendor, target_vendor)
    headers: dict[str, str] = {"Accept": "application/json"}
    api_key = get_integration_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, method="GET", headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        data = json.loads(body) if body else {}
    return data.get("operations", [])


def fetch_contract(
    operation_code: str,
    canonical_version: str,
) -> dict[str, Any] | None:
    """
    Fetch active contract from GET /v1/registry/contracts.
    API returns { items, nextCursor }. Returns first item if found, else None.
    """
    import urllib.request

    url = get_registry_contracts_url(operation_code, canonical_version)
    headers: dict[str, str] = {"Accept": "application/json"}
    api_key = get_integration_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, method="GET", headers=headers)

    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        data = json.loads(body) if body else {}
    contracts = data.get("contracts") or data.get("items") or []
    return contracts[0] if contracts else None
