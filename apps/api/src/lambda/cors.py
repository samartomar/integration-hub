"""CORS headers for Lambda proxy responses. Used when API Gateway does not add them (e.g. REST API)."""

from __future__ import annotations

import os
from typing import Any


def _cors_headers() -> dict[str, str]:
    """Build CORS headers from ADMIN_UI_ORIGIN env. Default * for POC."""
    origin = os.environ.get("ADMIN_UI_ORIGIN", "").strip()
    if not origin:
        origin = "*"
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "content-type, authorization, x-vendor-code",
        "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
    }


def add_cors_to_response(response: dict[str, Any]) -> dict[str, Any]:
    """Merge CORS headers into a Lambda proxy response. Returns modified dict."""
    headers = response.get("headers") or {}
    for k, v in _cors_headers().items():
        headers[k] = v
    response["headers"] = headers
    return response
