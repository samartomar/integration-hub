"""Onboarding Lambda - vendor bootstrap with JWT-only identity."""

from __future__ import annotations

import json
import os
import urllib.parse
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import psycopg2
from bcp_auth import AuthError, validate_authorizer_claims, validate_jwt
from canonical_response import canonical_error, canonical_ok, policy_denied_response
from cors import add_cors_to_response
from observability import log_json, with_observability
from policy_engine import PolicyContext, evaluate_policy


def _resolve_db_url() -> str:
    """Resolve DB URL from DB_URL or DB_SECRET_ARN."""
    db_url = os.environ.get("DB_URL")
    if db_url:
        return db_url
    secret_arn = os.environ.get("DB_SECRET_ARN")
    if not secret_arn:
        raise ConnectionError("Neither DB_URL nor DB_SECRET_ARN is set")
    import boto3

    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=secret_arn)
    raw = json.loads(resp["SecretString"])
    user = raw.get("username") or raw.get("user")
    pw = raw["password"]
    host = raw.get("host") or raw.get("hostname", "localhost")
    port = str(raw.get("port", 5432))
    dbname = raw.get("dbname") or raw.get("database", "integrationhub")
    pw_enc = urllib.parse.quote(str(pw), safe="")
    return f"postgresql://{user}:{pw_enc}@{host}:{port}/{dbname}"


@contextmanager
def _get_connection() -> Generator[Any, None, None]:
    """Get Postgres connection."""
    url = _resolve_db_url()
    conn = psycopg2.connect(url, connect_timeout=10)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _success(payload: dict[str, Any], status: int = 200) -> dict[str, Any]:
    return add_cors_to_response(canonical_ok(payload, status))


def _error(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return add_cors_to_response(canonical_error(code, message, status, details))


def _parse_body(raw: str | dict | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


def _validate_vendor_code(value: Any) -> str:
    """Validate and normalize vendor code (non-empty, reasonable length)."""
    if not value or not isinstance(value, str):
        raise ValueError("vendorCode is required")
    code = value.strip().upper()
    if not code:
        raise ValueError("vendorCode cannot be empty")
    if len(code) > 64:
        raise ValueError("vendorCode must be at most 64 characters")
    return code


def _ensure_vendor(conn: Any, vendor_code: str, vendor_name: str) -> None:
    """Ensure vendor exists in control_plane.vendors."""
    from psycopg2 import sql

    q = sql.SQL(
        """
        INSERT INTO control_plane.vendors (vendor_code, vendor_name)
        VALUES (%s, %s)
        ON CONFLICT (vendor_code) DO UPDATE SET
            vendor_name = EXCLUDED.vendor_name,
            updated_at = now()
        """
    )
    with conn.cursor() as cur:
        cur.execute(q, (vendor_code, vendor_name or vendor_code))


def _get_headers(event: dict[str, Any]) -> dict[str, str]:
    h = event.get("headers") or {}
    if not isinstance(h, dict):
        return {}
    return {k.lower(): (v if isinstance(v, str) else str(v)) for k, v in h.items()}


def _authorization_header(event: dict[str, Any]) -> str:
    return _get_headers(event).get("authorization", "")


def _resolve_vendor_claims(event: dict[str, Any]) -> tuple[str, list[str]]:
    expected_aud = (
        os.environ.get("VENDOR_API_AUDIENCE")
        or os.environ.get("IDP_AUDIENCE")
        or "api://default"
    ).strip()
    auth = (event.get("requestContext") or {}).get("authorizer") or {}
    jwt_claims = auth.get("jwt", {}).get("claims", {}) if isinstance(auth.get("jwt"), dict) else {}
    if isinstance(jwt_claims, dict) and jwt_claims:
        validated = validate_authorizer_claims(
            jwt_claims,
            expected_audience=expected_aud,
            allow_vendor=True,
        )
    else:
        validated = validate_jwt(
            _authorization_header(event),
            expected_audience=expected_aud,
            allow_vendor=True,
        )
    if not validated.bcpAuth:
        raise AuthError("UNAUTHORIZED", "Missing required claim 'bcpAuth'", status_code=401)
    return validated.bcpAuth, validated.roles


def _handler_impl(event: dict[str, Any], context: object) -> dict[str, Any]:
    """
    POST /v1/onboarding/register
    Body: { vendorCode?, vendorName? }
    Returns: { vendorCode, status }

    JWT-only identity:
    - vendor identity is resolved from JWT claim "bcpAuth"
    - body vendorCode must match the authenticated vendor if provided
    """
    body = _parse_body(event.get("body"))
    vendor_code_raw = body.get("vendorCode") or body.get("vendor_code")
    vendor_name = (body.get("vendorName") or body.get("vendor_name") or "").strip()
    try:
        vendor_code, groups = _resolve_vendor_claims(event)
    except AuthError as e:
        return _error(e.status_code, "FORBIDDEN" if e.status_code == 403 else "AUTH_ERROR", e.message)

    requested_vendor: str | None = None
    if vendor_code_raw:
        try:
            requested_vendor = _validate_vendor_code(vendor_code_raw)
        except ValueError as e:
            return _error(400, "VALIDATION_ERROR", str(e))

    decision = evaluate_policy(
        PolicyContext(
            surface="VENDOR",
            action="REGISTRY_WRITE",
            vendor_code=vendor_code,
            target_vendor_code=None,
            operation_code=None,
            requested_source_vendor_code=requested_vendor,
            is_admin=False,
            groups=groups,
            query={},
        )
    )
    if not decision.allow:
        return add_cors_to_response(policy_denied_response(decision))

    try:
        with _get_connection() as conn:
            _ensure_vendor(conn, vendor_code, vendor_name or vendor_code)
        return _success({"vendorCode": vendor_code, "status": "REGISTERED"})

    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(
            500,
            "INTERNAL_ERROR",
            str(e),
            details={"type": type(e).__name__},
        )


def _safe_handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Catch unhandled exceptions to return structured 500 instead of generic API Gateway error."""
    try:
        return with_observability(_handler_impl, "onboarding")(event, context)
    except Exception as e:
        log_json(
            "ERROR",
            "onboarding_unhandled",
            error=str(e),
            errorType=type(e).__name__,
        )
        return _error(
            500,
            "INTERNAL_ERROR",
            str(e),
            details={"type": type(e).__name__},
        )


handler = _safe_handler
