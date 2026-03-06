"""Shared JWT auth helper for Admin, Vendor, and Runtime APIs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from jwt_auth import JwtAuthConfig, JwtValidationError, validate_jwt_for_authorizer


class AuthError(Exception):
    """Authentication/authorization failure with HTTP semantics."""

    def __init__(self, code: str, message: str, *, status_code: int = 401) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass
class ValidatedClaims:
    """Normalized claims contract used by API handlers."""

    subject: str
    bcpAuth: str | None
    roles: list[str]
    scopes: list[str]
    raw_claims: dict[str, Any]


def _validate_claims_payload(
    claims: dict[str, Any],
    *,
    required_role: str | None,
    required_scope: str | None,
    allow_vendor: bool,
) -> ValidatedClaims:
    subject = str(claims.get("sub") or "").strip()
    roles = _normalize_roles(claims)
    scopes = _normalize_scopes(claims)
    vendor_code = str(claims.get("bcpAuth") or "").strip().upper() or None

    if allow_vendor and not vendor_code:
        raise AuthError("UNAUTHORIZED", "Missing required claim 'bcpAuth'", status_code=401)

    if required_role:
        required = required_role.strip()
        if required and required.lower() not in {r.lower() for r in roles}:
            raise AuthError("FORBIDDEN", f"Missing required role '{required}'", status_code=403)

    if required_scope:
        required = required_scope.strip()
        if required and required not in set(scopes):
            raise AuthError("FORBIDDEN", f"Missing required scope '{required}'", status_code=403)

    return ValidatedClaims(
        subject=subject,
        bcpAuth=vendor_code,
        roles=roles,
        scopes=scopes,
        raw_claims=dict(claims),
    )


def validate_authorizer_claims(
    claims: dict[str, Any],
    *,
    expected_audience: str,
    required_role: str | None = None,
    required_scope: str | None = None,
    allow_vendor: bool = True,
) -> ValidatedClaims:
    """Validate already-authorized JWT claims payload (from API Gateway authorizer context)."""
    if not isinstance(claims, dict):
        raise AuthError("UNAUTHORIZED", "Missing JWT claims", status_code=401)
    expected = (expected_audience or "").strip()
    if expected and claims.get("aud") is not None:
        aud = claims.get("aud")
        aud_set = set(aud) if isinstance(aud, list) else {str(aud)} if aud is not None else set()
        if expected not in {str(v).strip() for v in aud_set if str(v).strip()}:
            raise AuthError("UNAUTHORIZED", "Invalid token audience", status_code=401)
    return _validate_claims_payload(
        claims,
        required_role=required_role,
        required_scope=required_scope,
        allow_vendor=allow_vendor,
    )


def _is_dev_environment() -> bool:
    env = (os.environ.get("ENVIRONMENT") or os.environ.get("RUN_ENV") or "").strip().lower()
    return env in ("dev", "local")


def _enforce_dev_only_bypass_flags() -> None:
    bypass = (os.environ.get("AUTH_BYPASS") or "").strip().lower() in ("1", "true", "yes")
    if bypass and not _is_dev_environment():
        raise RuntimeError("AUTH_BYPASS is allowed only when ENVIRONMENT=dev/local")


def _extract_bearer_token(raw_header_or_token: str | None) -> str:
    raw = (raw_header_or_token or "").strip()
    if not raw:
        raise AuthError("UNAUTHORIZED", "Missing Authorization header", status_code=401)
    if raw.lower().startswith("bearer "):
        token = raw[7:].strip()
    else:
        token = raw
    if not token:
        raise AuthError("UNAUTHORIZED", "Authorization token is empty", status_code=401)
    return token


def _normalize_roles(claims: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("roles", "groups"):
        raw = claims.get(key)
        if isinstance(raw, list):
            values.extend([str(v).strip() for v in raw if str(v).strip()])
        elif isinstance(raw, str) and raw.strip():
            values.extend([part.strip() for part in raw.replace(",", " ").split() if part.strip()])
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        k = v.lower()
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def _normalize_scopes(claims: dict[str, Any]) -> list[str]:
    raw = claims.get("scp")
    values: list[str] = []
    if isinstance(raw, list):
        values = [str(v).strip() for v in raw if str(v).strip()]
    elif isinstance(raw, str) and raw.strip():
        values = [part.strip() for part in raw.split() if part.strip()]
    return values


def validate_jwt(
    token: str,
    *,
    expected_audience: str,
    required_role: str | None = None,
    required_scope: str | None = None,
    allow_vendor: bool = True,
) -> ValidatedClaims:
    """
    Validate JWT against issuer/JWKS and enforce persona-specific requirements.
    """
    _enforce_dev_only_bypass_flags()
    issuer = (os.environ.get("IDP_ISSUER") or "").strip().rstrip("/")
    if not issuer:
        raise AuthError("UNAUTHORIZED", "IDP_ISSUER is not configured", status_code=401)
    audience = (expected_audience or "").strip()
    if not audience:
        raise AuthError("UNAUTHORIZED", "Expected audience is required", status_code=401)
    jwks_url = (os.environ.get("IDP_JWKS_URL") or f"{issuer}/v1/keys").strip()

    jwt_cfg = JwtAuthConfig(
        issuer=issuer,
        jwks_uri=jwks_url,
        audiences=[audience],
        vendor_claim="bcpAuth",
        allowed_alg="RS256",
        clock_skew_seconds=60,
        allowed_algs=["RS256"],
    )
    try:
        claims = validate_jwt_for_authorizer(_extract_bearer_token(token), jwt_cfg)
    except JwtValidationError as e:
        raise AuthError("UNAUTHORIZED", e.message or "Invalid token", status_code=401) from e

    return _validate_claims_payload(
        claims,
        required_role=required_role,
        required_scope=required_scope,
        allow_vendor=allow_vendor,
    )

