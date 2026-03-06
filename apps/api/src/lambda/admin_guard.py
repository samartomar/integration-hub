"""Admin guard: validate JWT + required admin role."""

from __future__ import annotations

import os
from typing import Any

from bcp_auth import AuthError, validate_authorizer_claims, validate_jwt
from canonical_response import canonical_error


def _authorization_header(event: dict[str, Any]) -> str:
    headers = event.get("headers") or {}
    if not isinstance(headers, dict):
        return ""
    for k, v in headers.items():
        if str(k).lower() == "authorization":
            return v if isinstance(v, str) else str(v)
    return ""


def require_admin_secret(event: dict[str, Any]) -> dict[str, Any] | None:
    """
    Validate JWT token and required admin role.
    Returns canonical error (401/403) on failure, otherwise None.
    """
    expected_aud = (os.environ.get("ADMIN_API_AUDIENCE") or os.environ.get("IDP_AUDIENCE") or "api://default").strip()
    required_role = (os.environ.get("ADMIN_REQUIRED_ROLE") or "").strip() or None
    try:
        auth = (event.get("requestContext") or {}).get("authorizer") or {}
        jwt_claims = auth.get("jwt", {}).get("claims", {}) if isinstance(auth.get("jwt"), dict) else {}
        if isinstance(jwt_claims, dict) and jwt_claims:
            validate_authorizer_claims(
                jwt_claims,
                expected_audience=expected_aud,
                required_role=required_role,
                allow_vendor=False,
            )
        else:
            validate_jwt(
                _authorization_header(event),
                expected_audience=expected_aud,
                required_role=required_role,
                allow_vendor=False,
            )
        return None
    except AuthError as e:
        return canonical_error("AUTH_ERROR", e.message, status_code=e.status_code)
