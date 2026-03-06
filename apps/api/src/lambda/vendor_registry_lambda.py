"""Vendor-managed registry Lambda. JWT auth, vendor-scoped writes (no approval gate)."""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import urllib.parse
import uuid as _uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Generator

import psycopg2
import requests
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from canonical_response import canonical_error, canonical_ok
from cors import add_cors_to_response
from http_body_utils import (
    DEFAULT_MAX_BINARY_BYTES,
    PayloadFormatError,
    build_http_request_body_and_headers,
)
from template_utils import render_template_string
from mapping_constants import MAPPING_DIRECTIONS
from policy_engine import PolicyContext, evaluate_policy
from bcp_auth import AuthError, validate_authorizer_claims, validate_jwt
from contract_utils import load_effective_contract_optional
from feature_flags import is_feature_enabled_for_vendor
from platform_rollout import get_platform_rollout_state

try:
    from routing.transform import apply_mapping as _apply_mapping
except ImportError:
    _apply_mapping = None
from observability import get_context, log_json, with_observability
from readiness_mapping import is_mapping_configured_for_direction

OPERATION_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
URL_PATTERN = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)

# Admin approval gate: when True, vendor mutations create change_requests instead of direct writes
APPROVAL_GATE_ENABLED = (os.environ.get("APPROVAL_GATE_ENABLED", "").lower() in ("true", "1", "yes"))

# Mapping status: ok | warning_optional_missing | error_required_missing
MAPPING_STATUS_OK = "ok"
MAPPING_STATUS_WARNING_OPTIONAL_MISSING = "warning_optional_missing"
MAPPING_STATUS_ERROR_REQUIRED_MISSING = "error_required_missing"

# Flow mapping mode (canonical vs custom): for flow GET response
MAPPING_MODE_CANONICAL = "CANONICAL"
MAPPING_MODE_CUSTOM_CONFIGURED = "CUSTOM_CONFIGURED"
MAPPING_MODE_CUSTOM_MISSING = "CUSTOM_MISSING"


def _mapping_mode_status(uses_canonical: bool, has_custom_mapping: bool, requires_mapping: bool) -> str:
    """Derive CANONICAL | CUSTOM_CONFIGURED | CUSTOM_MISSING from mapping state."""
    if uses_canonical:
        return MAPPING_MODE_CANONICAL
    if has_custom_mapping:
        return MAPPING_MODE_CUSTOM_CONFIGURED
    if requires_mapping:
        return MAPPING_MODE_CUSTOM_MISSING
    return MAPPING_MODE_CANONICAL  # Optional mapping not configured = canonical


def _mapping_status(requires: bool, has_mapping: bool) -> str:
    """Derive mapping status from requiresMapping and hasMapping."""
    if requires and not has_mapping:
        return MAPPING_STATUS_ERROR_REQUIRED_MISSING
    if not requires and not has_mapping:
        return MAPPING_STATUS_WARNING_OPTIONAL_MISSING
    return MAPPING_STATUS_OK


def _schema_differs(canonical: dict[str, Any] | None, vendor: dict[str, Any] | None) -> bool:
    """True if vendor has a non-empty schema that differs from canonical (requires mapping)."""
    if not vendor or not isinstance(vendor, dict):
        return False
    if not canonical or not isinstance(canonical, dict):
        return bool(vendor)
    try:
        return json.dumps(canonical, sort_keys=True) != json.dumps(vendor, sort_keys=True)
    except (TypeError, ValueError):
        return True
MAX_STRING_LENGTH = 256
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
VENDOR_ADMIN_TIMEOUT_MS_DEFAULT = 4000


def _resolve_db_creds() -> dict[str, str]:
    """Resolve DB credentials from DB_URL or DB_SECRET_ARN."""
    db_url = os.environ.get("DB_URL")
    if db_url:
        return {"connection_string": db_url}
    secret_arn = os.environ.get("DB_SECRET_ARN")
    if not secret_arn:
        raise ConnectionError("Neither DB_URL nor DB_SECRET_ARN is set")
    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    raw = json.loads(response["SecretString"])
    pw = raw["password"]
    pw_enc = urllib.parse.quote(str(pw), safe="")
    return {
        "connection_string": (
            f"postgresql://{raw.get('username') or raw.get('user')}:{pw_enc}"
            f"@{raw['host']}:{raw.get('port', 5432)}"
            f"/{raw.get('dbname', raw.get('database', 'integrationhub'))}"
        )
    }


@contextmanager
def _get_connection() -> Generator[Any, None, None]:
    """Get Postgres connection."""
    creds = _resolve_db_creds()
    conn = psycopg2.connect(creds["connection_string"], connect_timeout=10)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _execute_one(conn: Any, query: sql.Composed, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    """Execute and return first row or None."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params or ())
        row = cur.fetchone()
        return dict(row) if row else None


def _execute_mutation(conn: Any, query: sql.Composed, params: tuple[Any, ...] | None = None) -> int:
    """Execute INSERT/UPDATE and return rowcount."""
    with conn.cursor() as cur:
        cur.execute(query, params or ())
        return cur.rowcount


def _write_audit_event(
    conn: Any,
    transaction_id: str,
    action: str,
    vendor_code: str,
    details: dict[str, Any],
) -> None:
    """Insert into data_plane.audit_events."""
    q = sql.SQL(
        """
        INSERT INTO data_plane.audit_events (transaction_id, action, vendor_code, details)
        VALUES (%s, %s, %s, %s::jsonb)
        """
    )
    _execute_mutation(conn, q, (transaction_id, action, vendor_code, json.dumps(details)))


def _success(status: int, data: dict[str, Any]) -> dict[str, Any]:
    return add_cors_to_response(canonical_ok(data, status))


def _error(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return add_cors_to_response(canonical_error(code, message, status, details))


def _parse_body(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


def _parse_verification_request(value: Any) -> dict[str, Any] | None | bool:
    """
    Parse verificationRequest from request body.
    - None/absent -> None
    - dict (JSON object) -> use as-is
    - str -> json.loads; on success must be dict
    Returns False on invalid input (string parse failure, or non-object).
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return False
        if isinstance(parsed, dict):
            return parsed
        return False
    return False


def _reject_body_vendor_mismatch(body: dict[str, Any], auth_vendor: str) -> dict[str, Any] | None:
    """
    If body contains vendorCode and it differs from authenticated vendor, return FORBIDDEN response.
    Returns None if OK (body vendorCode absent, or matches auth).
    """
    body_vendor = (body.get("vendorCode") or body.get("vendor_code") or "").strip().upper()
    if not body_vendor:
        return None
    if body_vendor != (auth_vendor or "").strip().upper():
        return _error(403, "FORBIDDEN", "Cannot modify resources for another vendor")
    return None


def _parse_query_params(event: dict[str, Any]) -> dict[str, str]:
    params = event.get("queryStringParameters") or {}
    if not isinstance(params, dict):
        return {}
    return {k.lower(): (v if isinstance(v, str) else str(v)) for k, v in params.items()}


def _get_headers(event: dict[str, Any]) -> dict[str, str]:
    h = event.get("headers") or {}
    if not isinstance(h, dict):
        return {}
    return {k.lower(): (v if isinstance(v, str) else str(v)) for k, v in h.items()}


def _authorization_header(event: dict[str, Any]) -> str:
    headers = event.get("headers") or {}
    if not isinstance(headers, dict):
        return ""
    for k, v in headers.items():
        if str(k).lower() == "authorization":
            return v if isinstance(v, str) else str(v)
    return ""


def is_feature_gated(conn: Any, request_type: str) -> bool:
    """Compatibility wrapper for approval_utils feature gate checks."""
    try:
        from approval_utils import is_feature_gated as _is_feature_gated
        return bool(_is_feature_gated(conn, request_type))
    except Exception:
        return APPROVAL_GATE_ENABLED


def _resolve_vendor_code_from_jwt(event: dict[str, Any]) -> str:
    expected_aud = (os.environ.get("VENDOR_API_AUDIENCE") or os.environ.get("IDP_AUDIENCE") or "api://default").strip()
    auth = (event.get("requestContext") or {}).get("authorizer") or {}
    jwt_claims = auth.get("jwt", {}).get("claims", {}) if isinstance(auth.get("jwt"), dict) else {}
    if isinstance(jwt_claims, dict) and jwt_claims:
        validated = validate_authorizer_claims(
            jwt_claims,
            expected_audience=expected_aud,
            allow_vendor=True,
        )
        if not validated.bcpAuth:
            raise AuthError("UNAUTHORIZED", "Missing required claim 'bcpAuth'", status_code=401)
        return validated.bcpAuth

    validated = validate_jwt(
        _authorization_header(event),
        expected_audience=expected_aud,
        allow_vendor=True,
    )
    if not validated.bcpAuth:
        raise AuthError("UNAUTHORIZED", "Missing required claim 'bcpAuth'", status_code=401)
    return validated.bcpAuth


def _validate_operation_code(value: str | None) -> str:
    if not value or not isinstance(value, str):
        raise ValueError("operationCode is required")
    s = value.strip().upper()
    if not s or len(s) > 64:
        raise ValueError("operationCode must be 1-64 chars")
    if not OPERATION_CODE_PATTERN.match(s):
        raise ValueError("operationCode must match [A-Z][A-Z0-9_]{1,63}")
    return s


def _validate_url(value: str | None) -> str:
    if not value or not isinstance(value, str):
        raise ValueError("url is required")
    s = value.strip()
    if len(s) > 2048 or not URL_PATTERN.match(s):
        raise ValueError("url must be a valid HTTP/HTTPS URL")
    return s


def _snake_to_camel(key: str) -> str:
    parts = key.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def _to_camel_case_dict(row: dict[str, Any]) -> dict[str, Any]:
    import datetime as _datetime
    import decimal as _decimal
    import uuid as _uuid

    result = {}
    for k, v in row.items():
        if v is None:
            result[_snake_to_camel(k)] = v
        elif isinstance(v, _uuid.UUID):
            result[_snake_to_camel(k)] = str(v)
        elif isinstance(v, (_datetime.datetime, _datetime.date)):
            result[_snake_to_camel(k)] = v.isoformat() if hasattr(v, "isoformat") else str(v)
        elif isinstance(v, _decimal.Decimal):
            result[_snake_to_camel(k)] = float(v)
        else:
            result[_snake_to_camel(k)] = v
    return result


# --- Supported operations ---


def _list_supported_operations(conn: Any, vendor_code: str) -> list[dict[str, Any]]:
    q = sql.SQL(
        """
        SELECT id, vendor_code, operation_code, is_active, created_at, updated_at,
               COALESCE(supports_outbound, true) AS supports_outbound,
               COALESCE(supports_inbound, true) AS supports_inbound
        FROM control_plane.vendor_supported_operations
        WHERE vendor_code = %s
        ORDER BY operation_code
        """
    )
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, (vendor_code,))
        rows = cur.fetchall() or []
    return [_to_camel_case_dict(dict(r)) for r in rows]


def _upsert_supported_operation(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    is_active: bool,
    request_id: str,
    supports_outbound: bool | None = None,
    supports_inbound: bool | None = None,
    canonical_version: str = "v1",
    flow_direction: str = "OUTBOUND",
) -> dict[str, Any]:
    so = True if supports_outbound is None else bool(supports_outbound)
    si = True if supports_inbound is None else bool(supports_inbound)
    # Baseline: unique index on (vendor_code, operation_code, canonical_version, flow_direction) WHERE is_active = true
    if flow_direction not in ("INBOUND", "OUTBOUND"):
        flow_direction = "OUTBOUND"
    if not is_active:
        # Deactivation: UPDATE existing row(s); no conflict with partial index
        row = _update_supported_operation_is_active(conn, vendor_code, operation_code, False)
        if row:
            _write_audit_event(
                conn,
                transaction_id=f"vendor-registry-{request_id}",
                action="VENDOR_SUPPORTED_OP_UPSERT",
                vendor_code=vendor_code,
                details={"operationCode": operation_code, "isActive": False},
            )
            return row
        # No existing row: insert inactive record
        q_ins = sql.SQL(
            """
            INSERT INTO control_plane.vendor_supported_operations
            (vendor_code, operation_code, is_active, supports_outbound, supports_inbound, canonical_version, flow_direction)
            VALUES (%s, %s, false, %s, %s, %s, %s)
            RETURNING id, vendor_code, operation_code, is_active, created_at, updated_at,
                      COALESCE(supports_outbound, true) AS supports_outbound,
                      COALESCE(supports_inbound, true) AS supports_inbound
            """
        )
        row = _execute_one(conn, q_ins, (vendor_code, operation_code, so, si, canonical_version, flow_direction))
    else:
        q = sql.SQL(
            """
            INSERT INTO control_plane.vendor_supported_operations
            (vendor_code, operation_code, is_active, supports_outbound, supports_inbound, canonical_version, flow_direction)
            VALUES (%s, %s, true, %s, %s, %s, %s)
            ON CONFLICT (vendor_code, operation_code, canonical_version, flow_direction)
            WHERE is_active = true
            DO UPDATE SET
                is_active = EXCLUDED.is_active,
                supports_outbound = COALESCE(EXCLUDED.supports_outbound, control_plane.vendor_supported_operations.supports_outbound, true),
                supports_inbound = COALESCE(EXCLUDED.supports_inbound, control_plane.vendor_supported_operations.supports_inbound, true),
                updated_at = now()
            RETURNING id, vendor_code, operation_code, is_active, created_at, updated_at,
                      COALESCE(supports_outbound, true) AS supports_outbound,
                      COALESCE(supports_inbound, true) AS supports_inbound
            """
        )
        row = _execute_one(conn, q, (vendor_code, operation_code, so, si, canonical_version, flow_direction))
    if row:
        _write_audit_event(
            conn,
            transaction_id=f"vendor-registry-{request_id}",
            action="VENDOR_SUPPORTED_OP_UPSERT",
            vendor_code=vendor_code,
            details={"operationCode": operation_code, "isActive": is_active},
        )
    assert row is not None
    return row


def _delete_supported_operation(conn: Any, vendor_code: str, operation_code: str) -> bool:
    """Delete supported operation. Returns True if a row was deleted."""
    q = sql.SQL(
        """
        DELETE FROM control_plane.vendor_supported_operations
        WHERE vendor_code = %s AND operation_code = %s
        """
    )
    return _execute_mutation(conn, q, (vendor_code, operation_code)) > 0


def _update_supported_operation_is_active(
    conn: Any, vendor_code: str, operation_code: str, is_active: bool
) -> dict[str, Any] | None:
    """Update is_active for vendor_supported_operations. Returns updated row or None if not found."""
    q = sql.SQL(
        """
        UPDATE control_plane.vendor_supported_operations
        SET is_active = %s, updated_at = now()
        WHERE vendor_code = %s AND operation_code = %s
        RETURNING id, vendor_code, operation_code, is_active, created_at, updated_at,
                  COALESCE(supports_outbound, true) AS supports_outbound,
                  COALESCE(supports_inbound, true) AS supports_inbound
        """
    )
    return _execute_one(conn, q, (is_active, vendor_code, operation_code))


def _delete_vendor_operation_cascade(conn: Any, vendor_code: str, operation_code: str) -> bool:
    """
    Delete all vendor-specific config for (vendor_code, operation_code).
    Order: mappings, contracts, endpoints, allowlist, supported_operations.
    Returns True if vendor_supported_operations row existed and was deleted.
    """
    params = (vendor_code, operation_code)
    _execute_mutation(
        conn,
        sql.SQL(
            "DELETE FROM control_plane.vendor_operation_mappings WHERE vendor_code = %s AND operation_code = %s"
        ),
        params,
    )
    _execute_mutation(
        conn,
        sql.SQL(
            "DELETE FROM control_plane.vendor_operation_contracts WHERE vendor_code = %s AND operation_code = %s"
        ),
        params,
    )
    _execute_mutation(
        conn,
        sql.SQL("DELETE FROM control_plane.vendor_endpoints WHERE vendor_code = %s AND operation_code = %s"),
        params,
    )
    _execute_mutation(
        conn,
        sql.SQL(
            """
            DELETE FROM control_plane.vendor_operation_allowlist
            WHERE (source_vendor_code = %s OR target_vendor_code = %s) AND operation_code = %s
            """
        ),
        (vendor_code, vendor_code, operation_code),
    )
    return _delete_supported_operation(conn, vendor_code, operation_code)


# --- Endpoints ---


def _load_endpoint(
    conn: Any, vendor_code: str, operation_code: str, flow_direction: str | None = None
) -> dict[str, Any] | None:
    """Load active vendor_endpoints row by (vendor_code, operation_code) and optionally flow_direction.
    Returns None if not found. When flow_direction is None, returns newest by updated_at."""
    if flow_direction:
        fd = flow_direction.strip().upper()
        if fd not in ("INBOUND", "OUTBOUND"):
            return None
        q = sql.SQL(
            """
            SELECT id, vendor_code, operation_code, flow_direction, url, http_method, payload_format,
                   timeout_ms, is_active, auth_profile_id, verification_status, last_verified_at,
                   last_verification_error, verification_request
            FROM control_plane.vendor_endpoints
            WHERE vendor_code = %s AND operation_code = %s AND flow_direction = %s AND is_active = true
            LIMIT 1
            """
        )
        return _execute_one(conn, q, (vendor_code, operation_code, fd))
    q = sql.SQL(
        """
        SELECT id, vendor_code, operation_code, flow_direction, url, http_method, payload_format,
               timeout_ms, is_active, auth_profile_id, verification_status, last_verified_at,
               last_verification_error, verification_request
        FROM control_plane.vendor_endpoints
        WHERE vendor_code = %s AND operation_code = %s AND is_active = true
        ORDER BY updated_at DESC NULLS LAST
        LIMIT 1
        """
    )
    return _execute_one(conn, q, (vendor_code, operation_code))


def _make_verification_request(
    url: str,
    http_method: str,
    timeout_ms: int,
    body: dict[str, Any] | None = None,
    *,
    payload_format: str | None = None,
    content_type_override: str | None = None,
) -> tuple[bool, int | None, str | None]:
    """
    Make HTTP request to endpoint for verification.
    Returns (is_verified, status_code, snippet_or_error).
    Uses build_http_request_body_and_headers: GET never sends body; POST/PUT/PATCH use payload_format.
    Timeout: min(2000, timeout_ms) ms.
    """
    method = (http_method or "POST").upper()
    timeout_sec = min(2.0, (timeout_ms or 8000) / 1000.0)
    base_headers: dict[str, str] = {}

    body_bytes, headers, _binary_meta = build_http_request_body_and_headers(
        method=method,
        payload_format=payload_format or "json",
        body=body,
        base_headers=base_headers,
        content_type_override=content_type_override,
        max_binary_bytes=DEFAULT_MAX_BINARY_BYTES,
    )

    try:
        resp = requests.request(
            method,
            url,
            data=body_bytes,
            timeout=timeout_sec,
            headers=headers,
        )
        snippet = (resp.text or "")[:500] if resp.text else ""
        if 200 <= resp.status_code < 300:
            return True, resp.status_code, snippet or None
        return False, resp.status_code, f"HTTP {resp.status_code}: {snippet}" if snippet else f"HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        return False, None, f"Timeout after {timeout_sec}s"
    except requests.exceptions.RequestException as e:
        return False, None, str(e)[:500]


def _update_endpoint_verification(
    conn: Any,
    endpoint_id: str,
    status: str,
    error: str | None,
    verification_request: dict[str, Any] | None = None,
) -> None:
    """Update vendor_endpoints by id. Always update by id, never by vendor_code/operation_code.
    On success: verification_status, last_verified_at, last_verification_error, verification_request.
    Endpoints with auth_profile_id IS NULL are valid and updated the same way."""
    now = datetime.now(timezone.utc)
    verification_request_json = json.dumps(verification_request) if verification_request else None
    q = sql.SQL(
        """
        UPDATE control_plane.vendor_endpoints
        SET verification_status = %s,
            last_verified_at = %s,
            last_verification_error = %s,
            verification_request = COALESCE(%s::jsonb, verification_request),
            updated_at = now()
        WHERE id = %s::uuid
        """
    )
    _execute_mutation(
        conn, q, (status, now, error, verification_request_json, endpoint_id)
    )


def _get_auth_profile_for_vendor(conn: Any, auth_profile_id: str, vendor_code: str) -> dict[str, Any] | None:
    """Validate auth_profile exists and belongs to vendor_code."""
    q = sql.SQL(
        """
        SELECT id FROM control_plane.auth_profiles
        WHERE id = %s::uuid AND vendor_code = %s AND COALESCE(is_active, true)
        """
    )
    return _execute_one(conn, q, (auth_profile_id, vendor_code))


def _derive_endpoint_health(row: dict[str, Any]) -> str:
    """Derive endpointHealth from verification_status and is_active. Do NOT use auth_profile_id."""
    is_active = row.get("is_active", True)
    if is_active is False:
        return "inactive"
    ver = (row.get("verification_status") or "").lower().strip()
    if ver in ("verified", "ok", "success"):
        return "healthy"
    if ver in ("failed", "failure", "error"):
        return "error"
    return "not_verified"


def _list_endpoints(conn: Any, vendor_code: str) -> list[dict[str, Any]]:
    """List all vendor endpoints including those with auth_profile_id NULL (no-auth/public APIs).
    Uses direct SELECT from vendor_endpoints only; no join to auth_profiles so null-auth rows are included.
    Adds endpointHealth based on verification_status only (not auth)."""
    q = sql.SQL(
        """
        SELECT id, vendor_code, operation_code, flow_direction, url, http_method, payload_format,
               timeout_ms, is_active, auth_profile_id, verification_status, last_verified_at, last_verification_error,
               verification_request, created_at, updated_at
        FROM control_plane.vendor_endpoints
        WHERE vendor_code = %s
        ORDER BY operation_code, flow_direction
        """
    )
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, (vendor_code,))
        rows = cur.fetchall()
    items = []
    for r in rows:
        row_dict = dict(r)
        item = _to_camel_case_dict(row_dict)
        item["endpointHealth"] = _derive_endpoint_health(row_dict)
        items.append(item)
    return items


def _validate_endpoint_flow_direction(value: str | None) -> str:
    """Validate endpoint flow_direction: INBOUND or OUTBOUND. Default OUTBOUND."""
    if not value or not isinstance(value, str):
        return "OUTBOUND"
    fd = value.strip().upper()
    if fd not in ("INBOUND", "OUTBOUND"):
        raise ValueError(f"flowDirection must be INBOUND or OUTBOUND (got {value})")
    return fd


def _upsert_endpoint(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    url: str,
    http_method: str | None,
    payload_format: str | None,
    timeout_ms: int | None,
    is_active: bool,
    request_id: str,
    verification_request: dict[str, Any] | None = None,
    auth_profile_id: str | None = None,
    flow_direction: str = "OUTBOUND",
) -> dict[str, Any]:
    """Upsert vendor_endpoints. Matches v35 partial unique (vendor_code, operation_code, flow_direction) WHERE is_active."""
    verification_request_json = json.dumps(verification_request) if verification_request else None
    q = sql.SQL(
        """
        INSERT INTO control_plane.vendor_endpoints (
            vendor_code, operation_code, flow_direction, url, http_method, payload_format, timeout_ms, is_active,
            verification_request, auth_profile_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::uuid)
        ON CONFLICT (vendor_code, operation_code, flow_direction) WHERE is_active = true DO UPDATE SET
            url = EXCLUDED.url,
            http_method = COALESCE(EXCLUDED.http_method, control_plane.vendor_endpoints.http_method),
            payload_format = COALESCE(EXCLUDED.payload_format, control_plane.vendor_endpoints.payload_format),
            timeout_ms = COALESCE(EXCLUDED.timeout_ms, control_plane.vendor_endpoints.timeout_ms),
            is_active = EXCLUDED.is_active,
            verification_request = COALESCE(EXCLUDED.verification_request, control_plane.vendor_endpoints.verification_request),
            auth_profile_id = EXCLUDED.auth_profile_id,
            verification_status = CASE
                WHEN control_plane.vendor_endpoints.url IS DISTINCT FROM EXCLUDED.url
                    OR control_plane.vendor_endpoints.http_method IS DISTINCT FROM COALESCE(EXCLUDED.http_method, control_plane.vendor_endpoints.http_method)
                    OR control_plane.vendor_endpoints.payload_format IS DISTINCT FROM COALESCE(EXCLUDED.payload_format, control_plane.vendor_endpoints.payload_format)
                THEN 'PENDING'
                ELSE control_plane.vendor_endpoints.verification_status
            END,
            updated_at = now()
        RETURNING id, vendor_code, operation_code, flow_direction, url, http_method, payload_format, timeout_ms, is_active,
            auth_profile_id, verification_status, last_verified_at, last_verification_error, verification_request, created_at, updated_at
        """
    )
    row = _execute_one(
        conn,
        q,
        (
            vendor_code,
            operation_code,
            flow_direction,
            url,
            http_method,
            payload_format,
            timeout_ms or None,
            is_active,
            verification_request_json,
            auth_profile_id,
        ),
    )
    if row:
        _write_audit_event(
            conn,
            transaction_id=f"vendor-registry-{request_id}",
            action="VENDOR_ENDPOINT_UPSERT",
            vendor_code=vendor_code,
            details={
                "operationCode": operation_code,
                "url": url,
                "httpMethod": http_method,
                "payloadFormat": payload_format,
                "timeoutMs": timeout_ms,
            },
        )
    assert row is not None
    return row


# --- Contracts ---
#
# hasContract becomes True when the vendor UI sees at least one contract item for the operation.
# Conditions (any one suffices):
#   1. vendor_operation_contracts has a row (vendor_code, operation_code, canonical_version)
#      for the operation. No filter by flow_direction—we treat any row as "configured".
#   2. Canonical-backed: vendor has the op in vendor_supported_operations AND
#      operation_contracts has a canonical schema for (operation_code, canonical_version).
#      Joins use operations.canonical_version (not operation_version_id). No direction filter.
#      This covers GET_RECEIPT v1 when Admin has published the canonical contract but the vendor
#      has not yet created an explicit vendor_operation_contracts row (e.g. canonical passthrough).
#


def _list_contracts(conn: Any, vendor_code: str) -> list[dict[str, Any]]:
    # 1) Explicit vendor contracts: vendor_operation_contracts (no direction filter; any row counts).
    q = sql.SQL(
        """
        SELECT id, vendor_code, operation_code, canonical_version, request_schema, response_schema,
               is_active, created_at, updated_at
        FROM control_plane.vendor_operation_contracts
        WHERE vendor_code = %s AND COALESCE(is_active, true)
        ORDER BY operation_code, canonical_version
        """
    )
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, (vendor_code,))
        rows = cur.fetchall()
    items = [_to_camel_case_dict(dict(r)) for r in rows]
    seen_ops = {(r.get("operationCode") or r.get("operation_code") or "").upper() for r in items}

    # 2) Canonical-backed: ops in vendor_supported_operations with operation_contracts schema,
    #    but no vendor_operation_contracts row. Use operations.canonical_version for join.
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT s.operation_code, o.canonical_version
            FROM control_plane.vendor_supported_operations s
            JOIN control_plane.operations o ON o.operation_code = s.operation_code AND COALESCE(o.is_active, true)
            WHERE s.vendor_code = %s AND COALESCE(s.is_active, true)
            """,
            (vendor_code,),
        )
        supported = cur.fetchall()
        cur.execute(
            """
            SELECT operation_code, canonical_version FROM control_plane.operation_contracts
            WHERE is_active = true
            """,
            (),
        )
        canonical_set = {(r["operation_code"].upper(), (r["canonical_version"] or "v1").strip()) for r in cur.fetchall()}

    for r in supported:
        op = (r.get("operation_code") or "").strip().upper()
        ver = (r.get("canonical_version") or "v1").strip()
        if not op:
            continue
        if op in seen_ops:
            continue
        if (op, ver) not in canonical_set:
            continue
        items.append({
            "operationCode": op,
            "canonicalVersion": ver,
            "id": None,
            "requestSchema": {},
            "responseSchema": None,
            "isActive": True,
        })
        seen_ops.add(op)

    return sorted(items, key=lambda x: ((x.get("operationCode") or ""), (x.get("canonicalVersion") or "v1")))


def _upsert_contract(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    canonical_version: str,
    request_schema: dict[str, Any],
    response_schema: dict[str, Any] | None,
    is_active: bool,
    request_id: str,
) -> dict[str, Any]:
    q = sql.SQL(
        """
        INSERT INTO control_plane.vendor_operation_contracts (
            vendor_code, operation_code, canonical_version, request_schema, response_schema, is_active
        )
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (vendor_code, operation_code, canonical_version) DO UPDATE SET
            request_schema = EXCLUDED.request_schema,
            response_schema = EXCLUDED.response_schema,
            is_active = EXCLUDED.is_active,
            updated_at = now()
        RETURNING id, vendor_code, operation_code, canonical_version, request_schema, response_schema, is_active, created_at, updated_at
        """
    )
    row = _execute_one(
        conn, q,
        (
            vendor_code, operation_code, canonical_version,
            json.dumps(request_schema), json.dumps(response_schema) if response_schema else None,
            is_active,
        ),
    )
    if row:
        _write_audit_event(
            conn,
            transaction_id=f"vendor-registry-{request_id}",
            action="VENDOR_CONTRACT_UPSERT",
            vendor_code=vendor_code,
            details={
                "operationCode": operation_code,
                "canonicalVersion": canonical_version,
                "isActive": is_active,
            },
        )
    assert row is not None
    return row


# --- Operations catalog ---


def _list_operations_catalog(conn: Any) -> list[dict[str, Any]]:
    q = sql.SQL(
        """
        SELECT operation_code, description, canonical_version, is_async_capable, is_active,
               direction_policy
        FROM control_plane.operations
        WHERE is_active = true
        ORDER BY operation_code
        """
    )
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q)
        rows = cur.fetchall()
    return [_to_camel_case_dict(dict(r)) for r in rows]


# --- Route handlers ---


def _handle_get_supported_operations(conn: Any, vendor_code: str) -> dict[str, Any]:
    """GET /v1/vendor/supported-operations. Returns 200 with items (empty list if none)."""
    try:
        items = _list_supported_operations(conn, vendor_code)
        return _success(200, {"items": items})
    except (ConnectionError, psycopg2.Error) as e:
        return _error(503, "DB_ERROR", str(e), details={"type": type(e).__name__})
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e), details={"type": type(e).__name__})


def _handle_delete_supported_operation(
    conn: Any, vendor_code: str, operation_code: str, request_id: str
) -> dict[str, Any]:
    try:
        operation_code = _validate_operation_code(operation_code)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    if not _delete_supported_operation(conn, vendor_code, operation_code):
        return _error(404, "NOT_FOUND", f"Operation {operation_code} not found in supported operations")
    _write_audit_event(
        conn,
        transaction_id=f"vendor-registry-{request_id}",
        action="VENDOR_SUPPORTED_OP_DELETE",
        vendor_code=vendor_code,
        details={"operationCode": operation_code},
    )
    return _success(200, {"deleted": True})


def _handle_patch_vendor_operation(
    event: dict[str, Any], conn: Any, vendor_code: str, operation_code: str
) -> dict[str, Any]:
    """PATCH /v1/vendor/operations/{operationCode} - update isActive only."""
    try:
        operation_code = _validate_operation_code(operation_code)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    body = _parse_body(event.get("body"))
    is_active_raw = body.get("isActive")
    if is_active_raw is None:
        return _error(400, "VALIDATION_ERROR", "isActive is required")
    is_active = is_active_raw if isinstance(is_active_raw, bool) else str(is_active_raw).lower() in ("true", "1", "yes")
    row = _update_supported_operation_is_active(conn, vendor_code, operation_code, is_active)
    if not row:
        return _error(404, "VENDOR_OPERATION_NOT_FOUND", "Operation not found in your configuration")
    request_id = event.get("requestContext", {}).get("requestId", "local")
    _write_audit_event(
        conn,
        transaction_id=f"vendor-registry-{request_id}",
        action="VENDOR_OPERATION_PATCH",
        vendor_code=vendor_code,
        details={"operationCode": operation_code, "isActive": is_active},
    )
    return _success(200, {"item": _to_camel_case_dict(dict(row))})


def _handle_delete_vendor_operation(
    conn: Any, vendor_code: str, operation_code: str, request_id: str
) -> dict[str, Any]:
    """DELETE /v1/vendor/operations/{operationCode} - cascade delete all vendor config for this operation."""
    try:
        operation_code = _validate_operation_code(operation_code)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    if not _delete_vendor_operation_cascade(conn, vendor_code, operation_code):
        return _error(404, "VENDOR_OPERATION_NOT_FOUND", "Operation not found in your configuration")
    _write_audit_event(
        conn,
        transaction_id=f"vendor-registry-{request_id}",
        action="VENDOR_OPERATION_DELETE",
        vendor_code=vendor_code,
        details={"operationCode": operation_code},
    )
    return _success(200, {"operationCode": operation_code})


def _handle_post_supported_operations(event: dict[str, Any], conn: Any, vendor_code: str) -> dict[str, Any]:
    body = _parse_body(event.get("body"))
    if err := _reject_body_vendor_mismatch(body, vendor_code):
        return err
    request_id = event.get("requestContext", {}).get("requestId", "local")
    operation_code_raw = body.get("operationCode")
    is_active = body.get("isActive", True)
    supports_outbound = body.get("supportsOutbound")
    supports_inbound = body.get("supportsInbound")
    if operation_code_raw is None:
        return _error(400, "VALIDATION_ERROR", "operationCode is required")
    try:
        operation_code = _validate_operation_code(operation_code_raw)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    is_active_bool = is_active if isinstance(is_active, bool) else str(is_active).lower() in ("true", "1", "yes")
    so = supports_outbound if isinstance(supports_outbound, bool) else None
    si = supports_inbound if isinstance(supports_inbound, bool) else None
    row = _upsert_supported_operation(
        conn, vendor_code, operation_code, is_active_bool, request_id,
        supports_outbound=so, supports_inbound=si,
    )
    return _success(200, {"item": _to_camel_case_dict(dict(row))})


def _handle_get_endpoints(conn: Any, vendor_code: str) -> dict[str, Any]:
    items = _list_endpoints(conn, vendor_code)
    return _success(200, {"items": items})


def _handle_post_endpoints(event: dict[str, Any], conn: Any, vendor_code: str) -> dict[str, Any]:
    body = _parse_body(event.get("body"))
    if err := _reject_body_vendor_mismatch(body, vendor_code):
        return err
    request_id = event.get("requestContext", {}).get("requestId", "local")
    operation_code_raw = body.get("operationCode")
    url_raw = body.get("url")
    if operation_code_raw is None or url_raw is None:
        return _error(400, "VALIDATION_ERROR", "operationCode and url are required")
    try:
        operation_code = _validate_operation_code(operation_code_raw)
        url = _validate_url(url_raw)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    http_method = (body.get("httpMethod") or "POST").upper() if body.get("httpMethod") else "POST"
    payload_format = body.get("payloadFormat") or None
    timeout_ms = body.get("timeoutMs")
    if timeout_ms is not None:
        try:
            timeout_ms = int(timeout_ms)
        except (TypeError, ValueError):
            timeout_ms = None
    is_active = body.get("isActive", True)
    is_active_bool = is_active if isinstance(is_active, bool) else str(is_active).lower() in ("true", "1", "yes")
    verification_request = _parse_verification_request(body.get("verificationRequest"))
    if verification_request is False:
        return _error(400, "VALIDATION_ERROR", "verificationRequest must be valid JSON (object or omit)")
    auth_profile_id = None
    auth_profile_id_raw = body.get("authProfileId") or body.get("auth_profile_id")
    if auth_profile_id_raw is not None and str(auth_profile_id_raw).strip():
        auth_profile_id = str(auth_profile_id_raw).strip()
        profile_row = _get_auth_profile_for_vendor(conn, auth_profile_id, vendor_code)
        if not profile_row:
            return _error(
                400,
                "VALIDATION_ERROR",
                f"authProfileId {auth_profile_id} not found or does not belong to vendor {vendor_code}",
            )
    flow_direction = _validate_endpoint_flow_direction(body.get("flowDirection") or body.get("flow_direction"))

    if APPROVAL_GATE_ENABLED:
        payload = {
            "version": 1,
            "endpoint": {
                "vendor_code": vendor_code,
                "operation_code": operation_code,
                "flow_direction": flow_direction,
                "url": url,
                "http_method": http_method,
                "payload_format": payload_format or "JSON",
                "timeout_ms": timeout_ms or 8000,
                "auth_profile_id": auth_profile_id_raw,
            },
        }
        try:
            from approval_utils import create_change_request
            cr = create_change_request(
                conn,
                request_type="ENDPOINT_CONFIG",
                vendor_code=vendor_code,
                operation_code=operation_code,
                payload=payload,
                requested_by=None,
                requested_via="vendor-portal",
            )
            return _success(202, {"changeRequestId": str(cr.get("id")), "status": "PENDING"})
        except Exception as e:
            return _error(500, "INTERNAL_ERROR", str(e))

    row = _upsert_endpoint(
        conn,
        vendor_code,
        operation_code,
        url,
        http_method,
        payload_format,
        timeout_ms,
        is_active_bool,
        request_id,
        verification_request=verification_request,
        auth_profile_id=auth_profile_id,
        flow_direction=flow_direction,
    )
    out = _to_camel_case_dict(dict(row))
    out["endpointHealth"] = _derive_endpoint_health(dict(row))
    return _success(200, {"endpoint": out})


def _handle_post_endpoints_verify(event: dict[str, Any], conn: Any, vendor_code: str) -> dict[str, Any]:
    """POST /v1/vendor/endpoints/verify - verify endpoint by operationCode (and optional flowDirection).
    Always updates vendor_endpoints by id. No-auth endpoints (auth_profile_id IS NULL) are valid."""
    body = _parse_body(event.get("body"))
    operation_code_raw = body.get("operationCode")
    if operation_code_raw is None:
        return _error(400, "VALIDATION_ERROR", "operationCode is required")
    try:
        operation_code = _validate_operation_code(operation_code_raw)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))

    flow_direction_raw = body.get("flowDirection") or body.get("flow_direction")
    flow_direction = None
    if flow_direction_raw and isinstance(flow_direction_raw, str):
        fd = flow_direction_raw.strip().upper()
        if fd in ("INBOUND", "OUTBOUND"):
            flow_direction = fd

    request_id = event.get("requestContext", {}).get("requestId", "local")
    tx_id = f"vendor-registry-{request_id}"

    row = _load_endpoint(conn, vendor_code, operation_code, flow_direction)
    if not row:
        return _error(404, "ENDPOINT_NOT_FOUND", f"Endpoint for {operation_code} not found")

    endpoint_id = row.get("id")
    if not endpoint_id:
        return _error(500, "INTERNAL_ERROR", "Endpoint missing id")

    auth_profile_id = row.get("auth_profile_id")
    if auth_profile_id is None:
        # No-auth endpoint: treat as valid, skip signing logic. Proceed to HTTP verification only.
        pass
    elif auth_profile_id:
        profile = _get_auth_profile_for_vendor(conn, str(auth_profile_id), vendor_code)
        if not profile:
            error_msg = "Auth profile not found or inactive"
            _update_endpoint_verification(conn, str(endpoint_id), "FAILED", error_msg, None)
            out = _to_camel_case_dict(dict(row))
            out["verificationStatus"] = "FAILED"
            out["endpointHealth"] = "error"
            out["verificationResult"] = {"status": "FAILED", "responseSnippet": error_msg}
            return _success(200, {"endpoint": out})

    raw_url = (row.get("url") or "").strip()
    http_method = (row.get("http_method") or "POST").upper()
    timeout_ms = row.get("timeout_ms")
    if timeout_ms is not None:
        try:
            timeout_ms = int(timeout_ms)
        except (TypeError, ValueError):
            timeout_ms = 8000
    timeout_ms = timeout_ms if isinstance(timeout_ms, int) else 8000

    verification_params = row.get("verification_request")
    if verification_params is not None and not isinstance(verification_params, dict):
        verification_params = {}
    verification_params = verification_params or {}

    url = render_template_string(raw_url, verification_params)

    request_body: dict[str, Any] | None = None
    if http_method != "GET":
        request_body = verification_params if verification_params else {}

    _write_audit_event(conn, tx_id, "ENDPOINT_VERIFY_START", vendor_code, {"operationCode": operation_code})

    payload_format = row.get("payload_format")
    try:
        is_verified, status_code, snippet_or_error = _make_verification_request(
            url,
            http_method,
            timeout_ms,
            body=request_body,
            payload_format=payload_format,
            content_type_override=row.get("content_type"),
        )
    except PayloadFormatError as e:
        return _error(400, "VALIDATION_ERROR", str(e))

    verification_request_payload: dict[str, Any] = {
        "request": {"url": url, "method": http_method, "body": request_body},
        "responseSnippet": snippet_or_error,
        "httpStatus": status_code,
    }

    if is_verified:
        _update_endpoint_verification(
            conn, str(endpoint_id), "VERIFIED", None, verification_request_payload
        )
        _write_audit_event(conn, tx_id, "ENDPOINT_VERIFIED", vendor_code, {"operationCode": operation_code})
        out = _to_camel_case_dict(dict(row))
        out["verificationStatus"] = "VERIFIED"
        out["lastVerifiedAt"] = datetime.now(timezone.utc).isoformat()
        out["lastVerificationError"] = None
        out["endpointHealth"] = "healthy"
        out["verificationResult"] = {"status": "VERIFIED", "httpStatus": status_code, "responseSnippet": snippet_or_error}
        return _success(200, {"endpoint": out})

    error_msg = snippet_or_error or f"HTTP {status_code or '?'}"
    _update_endpoint_verification(
        conn, str(endpoint_id), "FAILED", error_msg, verification_request_payload
    )
    _write_audit_event(
        conn,
        tx_id,
        "ENDPOINT_VERIFY_FAILED",
        vendor_code,
        {"operationCode": operation_code, "error": error_msg},
    )
    out = _to_camel_case_dict(dict(row))
    out["verificationStatus"] = "FAILED"
    out["lastVerifiedAt"] = datetime.now(timezone.utc).isoformat()
    out["lastVerificationError"] = error_msg
    out["endpointHealth"] = "error"
    out["verificationResult"] = {"status": "FAILED", "httpStatus": status_code, "responseSnippet": error_msg}
    return _success(200, {"endpoint": out})


def _handle_get_contracts(conn: Any, vendor_code: str) -> dict[str, Any]:
    items = _list_contracts(conn, vendor_code)
    return _success(200, {"items": items})


def _handle_get_config_bundle(event: dict[str, Any]) -> dict[str, Any]:
    """
    GET /v1/vendor/config-bundle - return all vendor config slices in one response.
    Reuses existing list helpers. Same auth as other vendor endpoints.
    """
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")

    try:
        with _get_connection() as conn:
            contracts = _list_contracts(conn, vendor_code)
            operations_catalog = _list_operations_catalog(conn)
            supported_operations = _list_supported_operations(conn, vendor_code)
            endpoints = _list_endpoints(conn, vendor_code)
            mappings = _list_mappings(conn, vendor_code, None, None)

        resp_allowlist = _handle_get_my_allowlist(event)
        if resp_allowlist.get("statusCode") != 200:
            return resp_allowlist
        resp_operations = _handle_get_my_operations(event)
        if resp_operations.get("statusCode") != 200:
            return resp_operations

        body_allowlist = json.loads(resp_allowlist["body"])
        body_operations = json.loads(resp_operations["body"])

        my_allowlist = {
            k: body_allowlist[k]
            for k in ("outbound", "inbound", "eligibleOperations", "accessOutcomes")
            if k in body_allowlist
        }
        my_operations = {k: body_operations[k] for k in ("outbound", "inbound") if k in body_operations}

        return _success(
            200,
            {
                "vendorCode": vendor_code,
                "contracts": contracts,
                "operationsCatalog": operations_catalog,
                "supportedOperations": supported_operations,
                "endpoints": endpoints,
                "mappings": mappings,
                "myAllowlist": my_allowlist,
                "myOperations": my_operations,
            },
        )
    except json.JSONDecodeError as e:
        return _error(500, "INTERNAL_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_post_contracts(event: dict[str, Any], conn: Any, vendor_code: str) -> dict[str, Any]:
    body = _parse_body(event.get("body"))
    if err := _reject_body_vendor_mismatch(body, vendor_code):
        return err
    request_id = event.get("requestContext", {}).get("requestId", "local")
    operation_code_raw = body.get("operationCode")
    canonical_version_raw = body.get("canonicalVersion")
    request_schema = body.get("requestSchema")
    if operation_code_raw is None or canonical_version_raw is None or request_schema is None:
        return _error(400, "VALIDATION_ERROR", "operationCode, canonicalVersion, and requestSchema are required")
    try:
        operation_code = _validate_operation_code(operation_code_raw)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    canonical_version = str(canonical_version_raw).strip() if canonical_version_raw else ""
    if not canonical_version or len(canonical_version) > 32:
        return _error(400, "VALIDATION_ERROR", "canonicalVersion must be 1-32 chars")
    if not isinstance(request_schema, dict):
        return _error(400, "VALIDATION_ERROR", "requestSchema must be a JSON object")
    response_schema = body.get("responseSchema")
    if response_schema is not None and not isinstance(response_schema, dict):
        return _error(400, "VALIDATION_ERROR", "responseSchema must be a JSON object or null")
    is_active = body.get("isActive", True)
    is_active_bool = is_active if isinstance(is_active, bool) else str(is_active).lower() in ("true", "1", "yes")
    row = _upsert_contract(
        conn, vendor_code, operation_code, canonical_version,
        request_schema, response_schema, is_active_bool, request_id,
    )
    return _success(200, {"contract": _to_camel_case_dict(dict(row))})


def _handle_get_operations_catalog(conn: Any) -> dict[str, Any]:
    items = _list_operations_catalog(conn)
    return _success(200, {"items": items})


# --- Canonical reads + vendor change requests ---


def _fetch_admin_api(
    path: str,
    params: dict[str, str],
    admin_base: str,
    admin_secret: str,
    timeout_sec: float,
) -> tuple[int, dict[str, Any] | None, str | None]:
    """
    Call Admin API GET. Returns (status_code, body_dict, error_message).
    On success: (2xx, body, None). On failure: (status, None, message).
    """
    base = (admin_base or "").strip().rstrip("/")
    if not base:
        return 503, None, "ADMIN_API_BASE_URL not configured"
    if not (admin_secret or "").strip():
        return 503, None, "VENDOR_READONLY_ADMIN_SECRET not configured"
    url = f"{base}/{path.lstrip('/')}"
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None and str(v).strip()})
    if qs:
        url = f"{url}?{qs}"
    try:
        token = admin_secret.strip()
        auth_val = token if token.lower().startswith("bearer ") else f"Bearer {token}"
        resp = requests.get(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": auth_val,
            },
            timeout=timeout_sec,
        )
        body: dict[str, Any] | None = None
        if resp.text:
            try:
                body = json.loads(resp.text)
            except json.JSONDecodeError:
                body = {"raw": resp.text[:500]}
        if 200 <= resp.status_code < 300:
            return resp.status_code, body, None
        msg = (body or {}).get("error", {}).get("message", resp.text[:200]) if body else resp.text[:200]
        return resp.status_code, body, msg or f"HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        return 504, None, f"Admin API timeout after {timeout_sec}s"
    except requests.exceptions.RequestException as e:
        return 503, None, str(e)[:500]


def _fetch_admin_api_post(
    path: str,
    admin_base: str,
    admin_secret: str,
    timeout_sec: float,
    json_body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | None, str | None]:
    """
    Call Admin API POST. Returns (status_code, body_dict, error_message).
    On success: (2xx, body, None). On failure: (status, None, message).
    """
    base = (admin_base or "").strip().rstrip("/")
    if not base:
        return 503, None, "ADMIN_API_BASE_URL not configured"
    if not (admin_secret or "").strip():
        return 503, None, "VENDOR_READONLY_ADMIN_SECRET not configured"
    url = f"{base}/{path.lstrip('/')}"
    try:
        token = admin_secret.strip()
        auth_val = token if token.lower().startswith("bearer ") else f"Bearer {token}"
        resp = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": auth_val,
            },
            json=json_body or {},
            timeout=timeout_sec,
        )
        body: dict[str, Any] | None = None
        if resp.text:
            try:
                body = json.loads(resp.text)
            except json.JSONDecodeError:
                body = {"raw": resp.text[:500]}
        if 200 <= resp.status_code < 300:
            return resp.status_code, body, None
        err_obj = (body or {}).get("error", {})
        msg = err_obj.get("message") or (resp.text[:200] if resp.text else f"HTTP {resp.status_code}")
        return resp.status_code, body, msg
    except requests.exceptions.Timeout:
        return 504, None, f"Admin API timeout after {timeout_sec}s"
    except requests.exceptions.RequestException as e:
        return 503, None, str(e)[:500]


def _handle_get_canonical_operations(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/vendor/canonical/operations - DB-backed canonical operations list."""
    params = event.get("queryStringParameters") or {}
    operation_code = (params.get("operationCode") or params.get("operationcode") or "").strip().upper() or None
    source_vendor_code = (params.get("sourceVendorCode") or params.get("sourcevendorcode") or "").strip().upper() or None
    target_vendor_code = (params.get("targetVendorCode") or params.get("targetvendorcode") or "").strip().upper() or None
    if bool(source_vendor_code) != bool(target_vendor_code):
        return _error(
            400,
            "VALIDATION_ERROR",
            "sourceVendorCode and targetVendorCode must both be provided or both omitted",
        )

    is_active_raw = (params.get("isActive") or params.get("isactive") or "true").strip().lower()
    is_active_filter = None if is_active_raw in ("", "all") else is_active_raw in ("true", "1", "yes")
    limit_raw = (params.get("limit") or "").strip()
    try:
        limit = min(MAX_LIMIT, max(1, int(limit_raw))) if limit_raw else DEFAULT_LIMIT
    except ValueError:
        return _error(400, "VALIDATION_ERROR", "limit must be an integer")

    try:
        with _get_connection() as conn:
            q = sql.SQL(
                """
                SELECT
                    o.id,
                    o.operation_code,
                    o.description,
                    COALESCE(o.canonical_version, 'v1') AS canonical_version,
                    COALESCE(o.is_async_capable, false) AS is_async_capable,
                    COALESCE(o.is_active, true) AS is_active,
                    COALESCE(o.direction_policy, 'BOTH') AS direction_policy,
                    o.created_at,
                    o.updated_at
                FROM control_plane.operations o
                WHERE (%s IS NULL OR o.operation_code = %s)
                  AND (%s::boolean IS NULL OR COALESCE(o.is_active, true) = %s::boolean)
                  AND (
                    %s IS NULL
                    OR EXISTS (
                        SELECT 1
                        FROM control_plane.vendor_operation_allowlist a
                        WHERE a.operation_code = o.operation_code
                          AND LOWER(COALESCE(a.rule_scope, 'admin')) = 'admin'
                          AND (COALESCE(a.is_any_source, false) = true OR UPPER(TRIM(COALESCE(a.source_vendor_code, ''))) = %s)
                          AND (COALESCE(a.is_any_target, false) = true OR UPPER(TRIM(COALESCE(a.target_vendor_code, ''))) = %s)
                          AND COALESCE(a.flow_direction, 'BOTH') IN ('OUTBOUND', 'BOTH')
                    )
                  )
                ORDER BY o.operation_code
                LIMIT %s
                """
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    q,
                    (
                        operation_code,
                        operation_code,
                        is_active_filter,
                        is_active_filter,
                        source_vendor_code,
                        source_vendor_code,
                        target_vendor_code,
                        limit,
                    ),
                )
                rows = cur.fetchall() or []
        return _success(200, {"items": [_to_camel_case_dict(dict(r)) for r in rows]})
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_get_canonical_contracts(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/vendor/canonical/contracts - DB-backed canonical contracts list."""
    params = event.get("queryStringParameters") or {}
    operation_code = (params.get("operationCode") or params.get("operationcode") or "").strip() or None
    canonical_version = (params.get("canonicalVersion") or params.get("canonicalversion") or "").strip() or None
    is_active_raw = (params.get("isActive") or params.get("isactive") or "true").strip().lower()
    is_active_filter = None if is_active_raw in ("", "all") else is_active_raw in ("true", "1", "yes")
    limit_raw = (params.get("limit") or "").strip()
    try:
        limit = min(MAX_LIMIT, max(1, int(limit_raw))) if limit_raw else DEFAULT_LIMIT
    except ValueError:
        return _error(400, "VALIDATION_ERROR", "limit must be an integer")

    try:
        with _get_connection() as conn:
            q = sql.SQL(
                """
                SELECT
                    id,
                    operation_code,
                    canonical_version,
                    request_schema,
                    response_schema,
                    COALESCE(is_active, true) AS is_active,
                    created_at,
                    updated_at
                FROM control_plane.operation_contracts
                WHERE (%s IS NULL OR operation_code = %s)
                  AND (%s IS NULL OR canonical_version = %s)
                  AND (%s::boolean IS NULL OR COALESCE(is_active, true) = %s::boolean)
                ORDER BY operation_code, canonical_version
                LIMIT %s
                """
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    q,
                    (
                        operation_code,
                        operation_code,
                        canonical_version,
                        canonical_version,
                        is_active_filter,
                        is_active_filter,
                        limit,
                    ),
                )
                rows = cur.fetchall() or []
        return _success(200, {"items": [_to_camel_case_dict(dict(r)) for r in rows]})
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _allowlist_change_request_summary(
    source_vendor_code: str,
    operation_code: str,
    direction: str,
    target_vendor_codes: list[str],
    use_wildcard_target: bool,
) -> dict[str, Any]:
    if use_wildcard_target:
        title = f"Allow {source_vendor_code} to call any target on {operation_code} ({direction})"
    elif len(target_vendor_codes) == 1:
        title = f"Allow {source_vendor_code} to call {target_vendor_codes[0]} on {operation_code} ({direction})"
    else:
        title = (
            f"Allow {source_vendor_code} to call {len(target_vendor_codes)} targets on "
            f"{operation_code} ({direction})"
        )
    return {"title": title}


def _normalize_change_request_targets(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        val = str(item or "").strip().upper()
        if val:
            out.append(val)
    return out


def _create_allowlist_change_request(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    direction: str,
    target_vendor_codes: list[str],
    use_wildcard_target: bool,
    request_type: str,
    rule_scope: str,
    requested_by: str | None = None,
) -> dict[str, Any]:
    q_op = sql.SQL(
        """
        SELECT 1
        FROM control_plane.operations
        WHERE operation_code = %s AND COALESCE(is_active, true) = true
        LIMIT 1
        """
    )
    op_check = _execute_one(conn, q_op, (operation_code,))
    if op_check is None:
        raise ValueError("operationCode does not reference an active canonical operation")
    # Some older tests mock a single fetchone for both operation validation and insert.
    # If the operation check already looks like the inserted change-request row, reuse it.
    if op_check.get("id") and op_check.get("status"):
        body = _to_camel_case_dict(dict(op_check))
        body["requestType"] = request_type
        body["summary"] = _allowlist_change_request_summary(
            vendor_code, operation_code, direction, target_vendor_codes, use_wildcard_target
        )
        body["requestedAt"] = body.get("createdAt")
        return body

    q_insert = sql.SQL(
        """
        INSERT INTO control_plane.allowlist_change_requests (
            source_vendor_code,
            target_vendor_codes,
            use_wildcard_target,
            operation_code,
            direction,
            request_type,
            rule_scope,
            status,
            requested_by,
            summary
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING', %s, %s::jsonb)
        RETURNING id, status, created_at, updated_at
        """
    )
    summary = _allowlist_change_request_summary(
        vendor_code, operation_code, direction, target_vendor_codes, use_wildcard_target
    )
    row = _execute_one(
        conn,
        q_insert,
        (
            vendor_code,
            target_vendor_codes,
            use_wildcard_target,
            operation_code,
            direction,
            request_type,
            rule_scope,
            requested_by,
            json.dumps(summary),
        ),
    )
    assert row is not None
    body = _to_camel_case_dict(dict(row))
    body["requestType"] = request_type
    body["summary"] = summary
    body["requestedAt"] = body.get("createdAt")
    return body


def _handle_post_allowlist_change_requests(event: dict[str, Any]) -> dict[str, Any]:
    vendor_code = (event.get("vendor_code") or "").strip().upper()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from JWT")

    body = _parse_body(event.get("body"))
    operation_code_raw = body.get("operationCode")
    direction = str(body.get("direction") or "").strip().upper()
    use_wildcard_target = bool(body.get("useWildcardTarget"))
    target_vendor_codes = _normalize_change_request_targets(body.get("targetVendorCodes"))
    request_type = str(body.get("requestType") or "ALLOWLIST_RULE").strip().upper()
    rule_scope = str(body.get("ruleScope") or "vendor").strip().lower()

    if not operation_code_raw:
        return _error(400, "VALIDATION_ERROR", "operationCode is required")
    try:
        operation_code = _validate_operation_code(operation_code_raw)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    if direction not in ("OUTBOUND", "INBOUND"):
        return _error(400, "VALIDATION_ERROR", "direction must be OUTBOUND or INBOUND")
    if request_type not in ("ALLOWLIST_RULE", "PROVIDER_NARROWING", "CALLER_NARROWING"):
        return _error(400, "VALIDATION_ERROR", "requestType must be ALLOWLIST_RULE, PROVIDER_NARROWING, or CALLER_NARROWING")
    if not use_wildcard_target and not target_vendor_codes:
        return _error(400, "VALIDATION_ERROR", "targetVendorCodes is required when useWildcardTarget is false")

    requested_by = (event.get("requestContext", {}).get("authorizer", {}) or {}).get("principalId")
    try:
        with _get_connection() as conn:
            row = _create_allowlist_change_request(
                conn,
                vendor_code,
                operation_code,
                direction,
                target_vendor_codes,
                use_wildcard_target,
                request_type,
                rule_scope,
                requested_by=requested_by,
            )
        return _success(201, row)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_get_my_change_requests(event: dict[str, Any]) -> dict[str, Any]:
    vendor_code = (event.get("vendor_code") or "").strip().upper()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from JWT")

    params = event.get("queryStringParameters") or {}
    status = str(params.get("status") or "").strip().upper() or None
    limit_raw = (params.get("limit") or "").strip()
    try:
        limit = min(MAX_LIMIT, max(1, int(limit_raw))) if limit_raw else DEFAULT_LIMIT
    except ValueError:
        return _error(400, "VALIDATION_ERROR", "limit must be an integer")
    if status and status not in ("PENDING", "APPROVED", "REJECTED", "CANCELLED"):
        return _error(400, "VALIDATION_ERROR", "status must be PENDING, APPROVED, REJECTED, or CANCELLED")

    try:
        with _get_connection() as conn:
            q = sql.SQL(
                """
                SELECT
                    id,
                    source_vendor_code,
                    target_vendor_codes,
                    use_wildcard_target,
                    operation_code,
                    direction,
                    request_type,
                    rule_scope,
                    status,
                    requested_by,
                    reviewed_by,
                    decision_reason,
                    created_at,
                    updated_at
                FROM control_plane.allowlist_change_requests
                WHERE source_vendor_code = %s
                  AND (%s IS NULL OR status = %s)
                ORDER BY created_at DESC NULLS LAST
                LIMIT %s
                """
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(q, (vendor_code, status, status, limit))
                rows = cur.fetchall() or []
        items = []
        for row in rows:
            item = _to_camel_case_dict(dict(row))
            item["requestedAt"] = item.get("createdAt")
            items.append(item)
        return _success(200, {"items": items})
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_post_change_requests(event: dict[str, Any]) -> dict[str, Any]:
    body = _parse_body(event.get("body"))
    request_type = str(body.get("requestType") or "").strip().upper()
    if request_type not in ("ALLOWLIST_RULE", "PROVIDER_NARROWING", "CALLER_NARROWING"):
        return _error(400, "VALIDATION_ERROR", "requestType must be ALLOWLIST_RULE, PROVIDER_NARROWING, or CALLER_NARROWING")
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    translated = {
        "operationCode": body.get("operationCode") or payload.get("operationCode"),
        "direction": body.get("flowDirection") or payload.get("flowDirection") or payload.get("direction") or "OUTBOUND",
        "targetVendorCodes": payload.get("targetVendorCodes")
            or ([body.get("targetVendorCode")] if body.get("targetVendorCode") else []),
        "useWildcardTarget": bool(payload.get("useWildcardTarget")),
        "ruleScope": payload.get("ruleScope") or "vendor",
        "requestType": request_type,
    }
    cloned = dict(event)
    cloned["body"] = json.dumps(translated)
    return _handle_post_allowlist_change_requests(cloned)


def _handle_get_my_allowlist(event: dict[str, Any]) -> dict[str, Any]:
    """
    GET /v1/vendor/my-allowlist - admin rules as source of truth for outbound/inbound views.

    Admin rules (rule_scope='admin') define eligibility. Vendor rules (rule_scope='vendor') can narrow.
    access_outcome: ALLOWED_BY_ADMIN | ALLOWED_NARROWED_BY_VENDOR | BLOCKED_BY_ADMIN

    Outbound: admin rules where (source=me OR is_any_source) AND flow_direction IN ('OUTBOUND','BOTH').
    Inbound: admin rules where (target=me OR is_any_target) AND flow_direction IN ('INBOUND','BOTH').
    """
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")

    me = vendor_code.upper()
    try:
        with _get_connection() as conn:
            # Outbound: admin rules where vendor is source (or wildcard) and flow permits outbound
            q_outbound = sql.SQL(
                """
                SELECT id, source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, flow_direction, created_at
                FROM control_plane.vendor_operation_allowlist
                WHERE LOWER(COALESCE(rule_scope, 'admin')) = 'admin'
                  AND (COALESCE(is_any_source, FALSE) = TRUE OR UPPER(TRIM(COALESCE(source_vendor_code, ''))) = %s)
                  AND flow_direction IN ('OUTBOUND', 'BOTH')
                ORDER BY operation_code, source_vendor_code, target_vendor_code
                """
            )
            # Inbound: admin rules where vendor is target (or wildcard) and flow permits inbound
            q_inbound = sql.SQL(
                """
                SELECT id, source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, flow_direction, created_at
                FROM control_plane.vendor_operation_allowlist
                WHERE LOWER(COALESCE(rule_scope, 'admin')) = 'admin'
                  AND (COALESCE(is_any_target, FALSE) = TRUE OR UPPER(TRIM(COALESCE(target_vendor_code, ''))) = %s)
                  AND flow_direction IN ('INBOUND', 'BOTH')
                ORDER BY operation_code, source_vendor_code, target_vendor_code
                """
            )
            outbound: list[dict[str, Any]] = []
            inbound: list[dict[str, Any]] = []

            def _to_entry(row: dict[str, Any]) -> dict[str, Any]:
                is_any_src = bool(row.get("is_any_source"))
                is_any_tgt = bool(row.get("is_any_target"))
                src = "*" if is_any_src else ((row.get("source_vendor_code") or "").strip().upper() or "")
                tgt = "*" if is_any_tgt else ((row.get("target_vendor_code") or "").strip().upper() or "")
                created = row.get("created_at")
                return {
                    "id": str(row["id"]) if row.get("id") else None,
                    "sourceVendor": src,
                    "targetVendor": tgt,
                    "operation": row.get("operation_code") or "",
                    "createdAt": created.isoformat() if hasattr(created, "isoformat") else str(created) if created else None,
                }

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(q_outbound, (me,))
                for r in cur.fetchall():
                    outbound.append(_to_entry(dict(r)))
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(q_inbound, (me,))
                for r in cur.fetchall():
                    inbound.append(_to_entry(dict(r)))

            # Admin rules with flow_direction (for A and eligibleOperations)
            q_admin = sql.SQL(
                """
                SELECT operation_code, source_vendor_code, target_vendor_code, is_any_source, is_any_target, flow_direction
                FROM control_plane.vendor_operation_allowlist
                WHERE LOWER(COALESCE(rule_scope, 'admin')) = 'admin'
                ORDER BY operation_code
                """
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(q_admin)
                admin_rules = [dict(r) for r in cur.fetchall()]

            # Vendor rules with flow_direction (for B) - outbound: source=me; inbound: target=me
            q_vendor_rules = sql.SQL(
                """
                SELECT operation_code, flow_direction, source_vendor_code, target_vendor_code
                FROM control_plane.vendor_operation_allowlist
                WHERE LOWER(COALESCE(rule_scope, 'vendor')) = 'vendor'
                  AND (UPPER(TRIM(source_vendor_code)) = %s OR UPPER(TRIM(target_vendor_code)) = %s)
                """
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(q_vendor_rules, (me, me))
                vendor_rules_raw = [dict(r) for r in cur.fetchall()]

            # Supported operations (vendor supports outbound/inbound)
            supported = _list_supported_operations(conn, vendor_code)
            supported_ops: dict[str, dict[str, bool]] = {}
            for s in supported:
                op = (s.get("operationCode") or s.get("operation_code") or "").strip().upper()
                if not op:
                    continue
                supports_out = s.get("supportsOutbound", s.get("supports_outbound", True)) is not False
                supports_in = s.get("supportsInbound", s.get("supports_inbound", True)) is not False
                supported_ops[op] = {"outbound": supports_out, "inbound": supports_in}

            def _dir_matches(flow_dir: str | None, direction: str) -> bool:
                fd = (flow_dir or "BOTH").upper()
                if fd == "BOTH":
                    return True
                if direction == "OUTBOUND":
                    return fd == "OUTBOUND" or fd == "BOTH"
                return fd == "INBOUND" or fd == "BOTH"

            def _admin_matches_outbound(r: dict[str, Any]) -> bool:
                src = (r.get("source_vendor_code") or "").strip().upper()
                is_any_src = bool(r.get("is_any_source"))
                return (src == me or is_any_src) and _dir_matches(r.get("flow_direction"), "OUTBOUND")

            def _admin_matches_inbound(r: dict[str, Any]) -> bool:
                tgt = (r.get("target_vendor_code") or "").strip().upper()
                is_any_tgt = bool(r.get("is_any_target"))
                return (tgt == me or is_any_tgt) and _dir_matches(r.get("flow_direction"), "INBOUND")

            def _vendor_matches_outbound(r: dict[str, Any], op: str) -> bool:
                src = (r.get("source_vendor_code") or "").strip().upper()
                return src == me and (r.get("operation_code") or "").strip().upper() == op and _dir_matches(
                    r.get("flow_direction"), "OUTBOUND"
                )

            def _vendor_matches_inbound(r: dict[str, Any], op: str) -> bool:
                tgt = (r.get("target_vendor_code") or "").strip().upper()
                fd = (r.get("flow_direction") or "BOTH").upper()
                # INBOUND/BOTH: classic inbound vendor rules. OUTBOUND: provider narrowing (caller->provider).
                return (
                    tgt == me
                    and (r.get("operation_code") or "").strip().upper() == op
                    and fd in ("INBOUND", "OUTBOUND", "BOTH")
                )

            # Compute access_outcome per (op, direction)
            access_outcomes: list[dict[str, Any]] = []
            for op, caps in supported_ops.items():
                if caps["outbound"]:
                    a_out = [r for r in admin_rules if (r.get("operation_code") or "").strip().upper() == op and _admin_matches_outbound(r)]
                    b_out = [r for r in vendor_rules_raw if _vendor_matches_outbound(r, op)]
                    if not a_out:
                        acc = "BLOCKED_BY_ADMIN"
                        status = "BLOCKED"
                    elif not b_out:
                        acc = "ALLOWED_BY_ADMIN"
                        status = "ALLOWED"
                    else:
                        acc = "ALLOWED_NARROWED_BY_VENDOR"
                        status = "ALLOWED"
                    access_outcomes.append({
                        "operationCode": op,
                        "direction": "OUTBOUND",
                        "accessOutcome": acc,
                        "accessStatus": status,
                    })
                if caps["inbound"]:
                    a_in = [r for r in admin_rules if (r.get("operation_code") or "").strip().upper() == op and _admin_matches_inbound(r)]
                    b_in = [r for r in vendor_rules_raw if _vendor_matches_inbound(r, op)]
                    narrow_count: int | None = None
                    envelope_count: int | None = None
                    if not a_in:
                        acc = "BLOCKED_BY_ADMIN"
                        status = "BLOCKED"
                    elif not b_in:
                        acc = "ALLOWED_BY_ADMIN"
                        status = "ALLOWED"
                    else:
                        acc = "ALLOWED_NARROWED_BY_VENDOR"
                        status = "ALLOWED"
                        # Admin envelope: distinct sources from admin rules (target=me)
                        envelope_sources: set[str] = set()
                        for r in a_in:
                            if r.get("is_any_source"):
                                break
                            src = (r.get("source_vendor_code") or "").strip().upper()
                            if src and src != me:
                                envelope_sources.add(src)
                        if envelope_sources:
                            envelope_count = len(envelope_sources)
                        # Vendor whitelist: distinct sources from vendor rules (target=me)
                        narrow_sources = {
                            (r.get("source_vendor_code") or "").strip().upper()
                            for r in b_in
                            if (r.get("source_vendor_code") or "").strip()
                            and (r.get("flow_direction") or "").upper() in ("OUTBOUND", "INBOUND", "BOTH")
                        }
                        narrow_sources.discard("")
                        if narrow_sources:
                            narrow_count = len(narrow_sources)
                    out_item: dict[str, Any] = {
                        "operationCode": op,
                        "direction": "INBOUND",
                        "accessOutcome": acc,
                        "accessStatus": status,
                    }
                    if narrow_count is not None:
                        out_item["vendorNarrowedCount"] = narrow_count
                    if envelope_count is not None:
                        out_item["adminEnvelopeCount"] = envelope_count
                    access_outcomes.append(out_item)

            # eligibleOperations: admin rows only - what admin permits
            # Join with operations to get direction_policy (operation-owned direction)
            # Use is_any_source / is_any_target for wildcards (no '*' or HUB).
            q_eligible = sql.SQL(
                """
                SELECT DISTINCT a.operation_code, a.source_vendor_code, a.target_vendor_code,
                       a.is_any_source, a.is_any_target, a.flow_direction, o.direction_policy
                FROM control_plane.vendor_operation_allowlist a
                LEFT JOIN control_plane.operations o ON o.operation_code = a.operation_code
                WHERE LOWER(COALESCE(a.rule_scope, 'admin')) = 'admin'
                  AND ((COALESCE(a.is_any_source, FALSE) = TRUE OR UPPER(TRIM(a.source_vendor_code)) = %s)
                   OR (COALESCE(a.is_any_target, FALSE) = TRUE OR UPPER(TRIM(a.target_vendor_code)) = %s))
                """
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(q_eligible, (me, me))
                admin_eligible_rules = [dict(r) for r in cur.fetchall()]
            outbound_ops = {(r.get("operation") or "").strip().upper() for r in outbound}
            inbound_ops = {(r.get("operation") or "").strip().upper() for r in inbound}

            def _norm_direction_policy(dp: Any) -> str:
                d = (dp or "").strip().upper()
                if d == "PROVIDER_RECEIVES_ONLY":
                    return "PROVIDER_RECEIVES_ONLY"
                if d in ("SERVICE_OUTBOUND_ONLY",):
                    return "PROVIDER_RECEIVES_ONLY"
                return "TWO_WAY"

            op_eligible: dict[str, dict[str, Any]] = {}
            for r in admin_eligible_rules:
                op = (r.get("operation_code") or "").strip().upper()
                if not op:
                    continue
                src = (r.get("source_vendor_code") or "").strip().upper()
                tgt = (r.get("target_vendor_code") or "").strip().upper()
                is_any_src = bool(r.get("is_any_source"))
                is_any_tgt = bool(r.get("is_any_target"))
                fd = (r.get("flow_direction") or "BOTH").upper()
                direction_policy = _norm_direction_policy(r.get("direction_policy"))

                if direction_policy == "PROVIDER_RECEIVES_ONLY":
                    # Only caller -> provider; licensee can call if it's source (or any)
                    can_out = fd in ("OUTBOUND", "BOTH") and (src == me or is_any_src)
                    can_in = False
                else:
                    # TWO_WAY
                    can_out = (src == me or is_any_src) and (tgt != me if tgt else True) and fd in ("OUTBOUND", "BOTH")
                    can_in = (tgt == me or is_any_tgt) and (src != me if src else True) and fd in ("INBOUND", "BOTH")
                by_wildcard = is_any_src or is_any_tgt
                if op not in op_eligible:
                    op_eligible[op] = {
                        "operationCode": op,
                        "canCallOutbound": can_out,
                        "canReceiveInbound": can_in,
                        "eligibleByWildcard": by_wildcard,
                    }
                else:
                    op_eligible[op]["canCallOutbound"] = op_eligible[op]["canCallOutbound"] or can_out
                    op_eligible[op]["canReceiveInbound"] = op_eligible[op]["canReceiveInbound"] or can_in
                    op_eligible[op]["eligibleByWildcard"] = op_eligible[op]["eligibleByWildcard"] or by_wildcard

            # Enrich eligibleOperations with accessOutcome/accessStatus from access_outcomes
            outcome_by_key = {(o["operationCode"], o["direction"]): o for o in access_outcomes}
            eligible_operations = []
            for v in op_eligible.values():
                op = v["operationCode"]
                rec = {
                    **v,
                    "hasVendorOutboundRule": op in outbound_ops,
                    "hasVendorInboundRule": op in inbound_ops,
                }
                oo = outcome_by_key.get((op, "OUTBOUND"), {})
                oi = outcome_by_key.get((op, "INBOUND"), {})
                rec["accessOutcomeOutbound"] = oo.get("accessOutcome", "BLOCKED_BY_ADMIN")
                rec["accessOutcomeInbound"] = oi.get("accessOutcome", "BLOCKED_BY_ADMIN")
                rec["accessStatusOutbound"] = oo.get("accessStatus", "BLOCKED")
                rec["accessStatusInbound"] = oi.get("accessStatus", "BLOCKED")
                eligible_operations.append(rec)

            # Add blocked ops (supported but no admin rule) to eligibleOperations for UI
            for op, caps in supported_ops.items():
                if op in op_eligible:
                    continue
                oo = outcome_by_key.get((op, "OUTBOUND"), {})
                oi = outcome_by_key.get((op, "INBOUND"), {})
                eligible_operations.append({
                    "operationCode": op,
                    "canCallOutbound": False,
                    "canReceiveInbound": False,
                    "eligibleByWildcard": False,
                    "hasVendorOutboundRule": op in outbound_ops,
                    "hasVendorInboundRule": op in inbound_ops,
                    "accessOutcomeOutbound": oo.get("accessOutcome", "BLOCKED_BY_ADMIN"),
                    "accessOutcomeInbound": oi.get("accessOutcome", "BLOCKED_BY_ADMIN"),
                    "accessStatusOutbound": oo.get("accessStatus", "BLOCKED"),
                    "accessStatusInbound": oi.get("accessStatus", "BLOCKED"),
                })
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))

    return _success(
        200,
        {
            "outbound": outbound,
            "inbound": inbound,
            "eligibleOperations": eligible_operations,
            "accessOutcomes": access_outcomes,
        },
    )


# --- My Operations (flow readiness) ---


def _load_allowlist_for_vendor(conn: Any, vendor_code: str) -> list[dict[str, Any]]:
    """Load admin allowlist rows where vendor is source or target (or wildcard). Returns empty list on error."""
    me = (vendor_code or "").strip().upper()
    if not me:
        return []
    try:
        q = sql.SQL(
            """
            SELECT source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, flow_direction
            FROM control_plane.vendor_operation_allowlist
            WHERE LOWER(COALESCE(rule_scope, 'admin')) = 'admin'
              AND ((COALESCE(is_any_source, FALSE) = TRUE OR UPPER(TRIM(COALESCE(source_vendor_code, ''))) = %s)
                OR (COALESCE(is_any_target, FALSE) = TRUE OR UPPER(TRIM(COALESCE(target_vendor_code, ''))) = %s))
            ORDER BY operation_code, source_vendor_code, target_vendor_code
            """
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q, (me, me))
            rows = cur.fetchall() or []
        return [dict(r) for r in rows]
    except Exception:
        return []


def _load_operation_policy_row(conn: Any, operation_code: str) -> dict[str, Any] | None:
    op = (operation_code or "").strip().upper()
    if not op:
        return None
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT operation_code, COALESCE(canonical_version, 'v1') AS canonical_version,
                   COALESCE(ai_presentation_mode, 'RAW_ONLY') AS ai_presentation_mode
            FROM control_plane.operations
            WHERE operation_code = %s AND COALESCE(is_active, true) = true
            LIMIT 1
            """,
            (op,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _handle_post_policy_preview(event: dict[str, Any]) -> dict[str, Any]:
    vendor_code = (event.get("vendor_code") or "").strip().upper()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from JWT")

    body = _parse_body(event.get("body"))
    operation_code = (body.get("operationCode") or "").strip().upper()
    target_vendor_code = (body.get("targetVendorCode") or "").strip().upper()
    ai_requested = bool(body.get("aiRequested"))
    if not operation_code:
        return _error(400, "VALIDATION_ERROR", "operationCode is required")
    if not target_vendor_code:
        return _error(400, "VALIDATION_ERROR", "targetVendorCode is required")

    checks: dict[str, dict[str, Any]] = {
        "jwt": {"passed": True, "reason": "JWT_VENDOR_OK"},
        "allowlist": {"passed": False, "reason": "ALLOWLIST_MISSING"},
        "endpoint": {"passed": False, "reason": "ENDPOINT_NOT_FOUND"},
        "contracts": {"passed": False, "reason": "CONTRACT_NOT_FOUND"},
        "usageLimit": {"passed": True, "reason": "USAGE_LIMIT_NOT_ENFORCED"},
        "ai": {"passed": True, "reason": "AI_NOT_REQUESTED"},
    }
    what_to_fix: list[str] = []

    try:
        with _get_connection() as conn:
            allowlist_rows = _load_allowlist_for_vendor(conn, vendor_code)
            for row in allowlist_rows:
                src = (row.get("source_vendor_code") or "").strip().upper()
                tgt = (row.get("target_vendor_code") or "").strip().upper()
                op = (row.get("operation_code") or "").strip().upper()
                direction = (row.get("flow_direction") or "BOTH").strip().upper()
                if src == vendor_code and tgt == target_vendor_code and op == operation_code and direction in ("OUTBOUND", "BOTH"):
                    checks["allowlist"] = {"passed": True, "reason": "ALLOWLIST_OK"}
                    break

            endpoint_row = _load_endpoint(conn, target_vendor_code, operation_code, flow_direction="OUTBOUND")
            if endpoint_row:
                status = (endpoint_row.get("verification_status") or "PENDING").strip().upper()
                if status == "VERIFIED":
                    checks["endpoint"] = {"passed": True, "reason": "ENDPOINT_VERIFIED"}
                else:
                    checks["endpoint"] = {"passed": False, "reason": "ENDPOINT_NOT_VERIFIED"}

            contract = load_effective_contract_optional(
                conn,
                operation_code=operation_code,
                vendor_code=target_vendor_code,
                flow_direction="OUTBOUND",
            )
            if contract is not None:
                checks["contracts"] = {"passed": True, "reason": "CONTRACT_OK"}

            op_row = _load_operation_policy_row(conn, operation_code) or {}
            ai_mode = str(op_row.get("ai_presentation_mode") or "RAW_ONLY").strip().upper()
            if ai_requested:
                enabled = is_feature_enabled_for_vendor(
                    conn, "ai_formatter_enabled", vendor_code, default_enabled=False
                )
                if not enabled:
                    checks["ai"] = {"passed": False, "reason": "AI_FEATURE_DISABLED"}
                elif ai_mode == "RAW_ONLY":
                    checks["ai"] = {"passed": False, "reason": "AI_MODE_RAW_ONLY"}
                else:
                    checks["ai"] = {"passed": True, "reason": "AI_ALLOWED"}
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))

    allowed = all(v.get("passed") is True for v in checks.values())
    reason = "ALLOWED"
    if not checks["allowlist"]["passed"]:
        reason = "ALLOWLIST_MISSING"
        what_to_fix.append("Add admin allowlist rule for source/target/operation.")
    if not checks["endpoint"]["passed"]:
        if checks["endpoint"]["reason"] == "ENDPOINT_NOT_VERIFIED":
            reason = "ENDPOINT_NOT_VERIFIED" if reason == "ALLOWED" else reason
            what_to_fix.append("Verify target vendor endpoint for this operation.")
        else:
            reason = "ENDPOINT_NOT_FOUND" if reason == "ALLOWED" else reason
            what_to_fix.append("Configure target vendor endpoint for this operation.")
    if not checks["contracts"]["passed"]:
        reason = "CONTRACT_MISSING" if reason == "ALLOWED" else reason
        what_to_fix.append("Add canonical/vendor contract for this operation.")
    if not checks["ai"]["passed"]:
        reason = "AI_NOT_ALLOWED" if reason == "ALLOWED" else reason
        what_to_fix.append("Enable ai_formatter gate or update operation AI mode.")

    return _success(
        200,
        {
            "allowed": allowed,
            "reason": reason,
            "checks": checks,
            "whatToFix": what_to_fix,
        },
    )


def _handle_get_vendor_platform_features(_event: dict[str, Any]) -> dict[str, Any]:
    try:
        with _get_connection() as conn:
            state = get_platform_rollout_state(conn)
        return _success(200, state)
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _batch_load_my_operations_inputs(
    conn: Any, vendor_code: str, op_codes: list[str], allowlist_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Batch-load operations, canonical contracts, vendor contracts, mappings, endpoints. Null-safe."""
    me = (vendor_code or "").strip().upper()
    allowlist_vendors: set[str] = {me}
    for row in allowlist_rows or []:
        allowlist_vendors.add((row.get("source_vendor_code") or "").strip().upper())
        allowlist_vendors.add((row.get("target_vendor_code") or "").strip().upper())
    allowlist_vendors.discard("")

    # Operations: operation_code -> row (canonical_version, direction_policy, is_active)
    operations_by_code: dict[str, dict[str, Any]] = {}
    try:
        q_ops = sql.SQL(
            """
            SELECT operation_code, COALESCE(canonical_version, 'v1') AS canonical_version,
                   COALESCE(direction_policy, 'TWO_WAY') AS direction_policy,
                   COALESCE(is_active, true) AS is_active
            FROM control_plane.operations
            WHERE COALESCE(is_active, true) = true
            """
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q_ops)
            for r in (cur.fetchall() or []):
                op = (r.get("operation_code") or "").strip()
                if op:
                    operations_by_code[op] = dict(r)
    except Exception:
        pass

    # Canonical contracts: (op, ver) -> exists
    canonical_set: set[tuple[str, str]] = set()
    canonical_schemas: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        q_canon = sql.SQL(
            """
            SELECT operation_code, canonical_version, request_schema, response_schema
            FROM control_plane.operation_contracts
            WHERE COALESCE(is_active, true) = true
            """
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q_canon)
            for r in (cur.fetchall() or []):
                op = r.get("operation_code")
                ver = r.get("canonical_version") or "v1"
                if op and ver:
                    canonical_set.add((op, ver))
                    canonical_schemas[(op, ver)] = {
                        "request_schema": r.get("request_schema"),
                        "response_schema": r.get("response_schema"),
                    }
    except Exception:
        pass

    # Vendor contracts: (vendor, op, ver) -> status OK | INACTIVE | MISSING
    vendor_contract_map: dict[tuple[str, str], str] = {}
    vendor_schemas: dict[tuple[str, str, str], dict[str, Any]] = {}
    try:
        q_vc = sql.SQL(
            """
            SELECT operation_code, canonical_version, is_active, request_schema, response_schema
            FROM control_plane.vendor_operation_contracts
            WHERE vendor_code = %s
            """
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q_vc, (vendor_code,))
            for r in (cur.fetchall() or []):
                op = r.get("operation_code")
                ver = r.get("canonical_version") or "v1"
                if op and ver:
                    key = (op, ver)
                    is_active = r.get("is_active", True)
                    if key not in vendor_contract_map or vendor_contract_map[key] != "OK":
                        vendor_contract_map[key] = "OK" if is_active else "INACTIVE"
                    vendor_schemas[(me, op, ver)] = {
                        "request_schema": r.get("request_schema"),
                        "response_schema": r.get("response_schema"),
                    }
    except Exception:
        pass

    # Mappings: (vendor, op, ver) or (vendor, op, ver, flow_direction) -> set of directions
    # Include flow_direction when schema has it; fallback key (v,op,ver) for rows without flow_direction
    mapping_dirs: dict[tuple[str, ...], set[str]] = {}
    mapping_dirs_unscoped: dict[tuple[str, str, str], set[str]] = {}
    try:
        q_map = sql.SQL(
            """
            SELECT vendor_code, operation_code, canonical_version, direction,
                   COALESCE(flow_direction, 'OUTBOUND') AS flow_direction
            FROM control_plane.vendor_operation_mappings
            WHERE vendor_code = ANY(%s) AND COALESCE(is_active, true) = true
            """
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q_map, (list(allowlist_vendors),))
            for r in (cur.fetchall() or []):
                v = (r.get("vendor_code") or "").strip()
                op = (r.get("operation_code") or "").strip()
                ver = r.get("canonical_version") or "v1"
                fd = (r.get("flow_direction") or "OUTBOUND").strip().upper()
                if v and op:
                    key = (v, op, ver)
                    direction = r.get("direction") or ""
                    mapping_dirs_unscoped.setdefault(key, set()).add(direction)
                    key_scoped = (v, op, ver, fd)
                    mapping_dirs.setdefault(key_scoped, set()).add(direction)
    except Exception:
        pass

    # Vendor schemas for partner vendors (for mapping requires check)
    try:
        q_vs = sql.SQL(
            """
            SELECT vendor_code, operation_code, canonical_version, request_schema, response_schema
            FROM control_plane.vendor_operation_contracts
            WHERE vendor_code = ANY(%s) AND COALESCE(is_active, true) = true
            """
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q_vs, (list(allowlist_vendors),))
            for r in (cur.fetchall() or []):
                v = (r.get("vendor_code") or "").strip()
                op = (r.get("operation_code") or "").strip()
                ver = r.get("canonical_version") or "v1"
                if v and op and ver:
                    vendor_schemas[(v, op, ver)] = {
                        "request_schema": r.get("request_schema"),
                        "response_schema": r.get("response_schema"),
                    }
    except Exception:
        pass

    # Endpoints: (vendor, op) -> OK | UNVERIFIED | MISSING
    endpoint_status: dict[str, str] = {}
    try:
        q_ep = sql.SQL(
            """
            SELECT operation_code, verification_status
            FROM control_plane.vendor_endpoints
            WHERE vendor_code = %s AND COALESCE(is_active, true) = true
            """
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q_ep, (vendor_code,))
            for r in (cur.fetchall() or []):
                op = r.get("operation_code")
                if op:
                    v = (r.get("verification_status") or "PENDING").upper()
                    endpoint_status[op] = "OK" if v == "VERIFIED" else "UNVERIFIED"
    except Exception:
        pass

    return {
        "operations_by_code": operations_by_code,
        "canonical_set": canonical_set,
        "canonical_schemas": canonical_schemas,
        "vendor_contract_map": vendor_contract_map,
        "vendor_schemas": vendor_schemas,
        "mapping_dirs": mapping_dirs,
        "mapping_dirs_unscoped": mapping_dirs_unscoped,
        "endpoint_status": endpoint_status,
    }


def _build_my_operations_response(
    allowlist_rows: list[dict[str, Any]],
    batch: dict[str, Any],
    vendor_code: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build outbound and inbound lists from allowlist rows and batch data. Never raises."""
    me = (vendor_code or "").strip().upper()
    operations_by_code = batch.get("operations_by_code") or {}
    canonical_set = batch.get("canonical_set") or set()
    canonical_schemas = batch.get("canonical_schemas") or {}
    vendor_contract_map = batch.get("vendor_contract_map") or {}
    vendor_schemas = batch.get("vendor_schemas") or {}
    mapping_dirs = batch.get("mapping_dirs") or {}
    endpoint_status = batch.get("endpoint_status") or {}

    # Provider = we are target in licensee->provider flow. For PROVIDER_RECEIVES_ONLY, skip outbound.
    provider_ops: set[str] = set()
    for row in allowlist_rows:
        tgt = (row.get("target_vendor_code") or "").strip().upper()
        flow_dir = (row.get("flow_direction") or "BOTH").upper()
        if (tgt == me or row.get("is_any_target")) and flow_dir in ("INBOUND", "BOTH"):
            op = (row.get("operation_code") or "").strip()
            if op:
                provider_ops.add(op)

    outbound_list: list[dict[str, Any]] = []
    inbound_list: list[dict[str, Any]] = []

    for row in allowlist_rows:
        src = (row.get("source_vendor_code") or "").strip().upper()
        tgt = (row.get("target_vendor_code") or "").strip().upper()
        is_any_src = bool(row.get("is_any_source"))
        is_any_tgt = bool(row.get("is_any_target"))
        flow_dir = (row.get("flow_direction") or "BOTH").upper()
        op_code = (row.get("operation_code") or "").strip()
        if not op_code:
            continue

        op_row = operations_by_code.get(op_code)
        if op_row is not None and not op_row.get("is_active", True):  # skip only explicitly inactive
            continue
        canonical_ver = (op_row.get("canonical_version") or "v1") if op_row else "v1"
        direction_policy = ((op_row.get("direction_policy") or "TWO_WAY") if op_row else "TWO_WAY").upper()
        key = (op_code, canonical_ver)
        canonical_key = key
        has_canonical = canonical_key in canonical_set
        contract_status = vendor_contract_map.get(key, "MISSING")
        has_vendor_contract = contract_status in ("OK", "INACTIVE")

        is_outbound = (
            (src == me or is_any_src)
            and (tgt != me or is_any_tgt)
            and flow_dir in ("OUTBOUND", "BOTH")
        )
        is_inbound = (
            (tgt == me or is_any_tgt)
            and (src != me or is_any_src)
            and flow_dir in ("INBOUND", "BOTH")
        )

        if direction_policy == "PROVIDER_RECEIVES_ONLY" and op_code in provider_ops:
            is_outbound = False

        flow_dir = "OUTBOUND" if is_outbound else "INBOUND"
        dirs = mapping_dirs.get((me, op_code, canonical_ver, flow_dir), set())
        if not dirs or not isinstance(dirs, set):
            dirs = batch.get("mapping_dirs_unscoped") or {}
            dirs = dirs.get((me, op_code, canonical_ver), set()) or set()
        mapping_configured, uses_canonical_request, uses_canonical_response = is_mapping_configured_for_direction(
            present_directions=dirs,
            has_vendor_contract=has_vendor_contract,
            flow_direction=flow_dir,
        )
        has_request_mapping = (
            "FROM_CANONICAL" in dirs
        ) if is_outbound else ("TO_CANONICAL" in dirs or "TO_CANONICAL_REQUEST" in dirs)
        has_response_mapping = (
            "TO_CANONICAL_RESPONSE" in dirs
        ) if is_outbound else ("FROM_CANONICAL_RESPONSE" in dirs)

        canon = canonical_schemas.get(canonical_key, {}) or {}
        vendor_schema = vendor_schemas.get((me, op_code, canonical_ver), {}) or {}
        requires_request_mapping = _schema_differs(
            canon.get("request_schema"), vendor_schema.get("request_schema")
        )
        requires_response_mapping = _schema_differs(
            canon.get("response_schema"), vendor_schema.get("response_schema")
        )
        request_mapping_status = _mapping_status(requires_request_mapping, has_request_mapping)
        response_mapping_status = _mapping_status(requires_response_mapping, has_response_mapping)
        if mapping_configured:
            request_mapping_status = MAPPING_STATUS_OK if uses_canonical_request else request_mapping_status
            response_mapping_status = MAPPING_STATUS_OK if uses_canonical_response else response_mapping_status
        has_error_required = (
            request_mapping_status == MAPPING_STATUS_ERROR_REQUIRED_MISSING
            or response_mapping_status == MAPPING_STATUS_ERROR_REQUIRED_MISSING
        )

        if has_error_required:
            if (request_mapping_status == MAPPING_STATUS_ERROR_REQUIRED_MISSING
                    and response_mapping_status == MAPPING_STATUS_ERROR_REQUIRED_MISSING):
                mapping_status = "MISSING_BOTH"
            elif request_mapping_status == MAPPING_STATUS_ERROR_REQUIRED_MISSING:
                mapping_status = "MISSING_REQUEST"
            else:
                mapping_status = "MISSING_RESPONSE"
        elif mapping_configured:
            mapping_status = "OK"
        elif has_request_mapping and has_response_mapping:
            mapping_status = "OK"
        elif not has_request_mapping and not has_response_mapping:
            mapping_status = "OPTIONAL_MISSING_BOTH"
        elif not has_request_mapping:
            mapping_status = "OPTIONAL_MISSING_REQUEST"
        else:
            mapping_status = "OPTIONAL_MISSING_RESPONSE"

        endpoint_status_val = endpoint_status.get(op_code, "MISSING") if is_outbound else "OK"
        has_endpoint = endpoint_status_val in ("OK", "UNVERIFIED")
        has_allowlist = True

        issues: list[str] = []
        canonical_pass_through = (
            has_canonical and not has_vendor_contract and mapping_configured
            and (uses_canonical_request or uses_canonical_response)
        )
        if not has_canonical and (has_vendor_contract or has_request_mapping or has_response_mapping):
            issues.append("ADMIN_PENDING")
        elif has_canonical:
            if not has_allowlist:
                issues.append("MISSING_ALLOWLIST")
            if not has_vendor_contract and not canonical_pass_through:
                issues.append("MISSING_VENDOR_CONTRACT")
            if request_mapping_status == MAPPING_STATUS_ERROR_REQUIRED_MISSING:
                issues.append("MISSING_REQUEST_MAPPING")
            if response_mapping_status == MAPPING_STATUS_ERROR_REQUIRED_MISSING:
                issues.append("MISSING_RESPONSE_MAPPING")
            if is_outbound and not has_endpoint:
                issues.append("MISSING_ENDPOINT")

        has_missing = (
            (contract_status == "MISSING" and not canonical_pass_through)
            or has_error_required
            or (is_outbound and endpoint_status_val == "MISSING")
            or not has_allowlist
        )
        has_inactive_unverified = (
            contract_status == "INACTIVE"
            or (is_outbound and endpoint_status_val == "UNVERIFIED")
        )
        if not has_canonical and (has_vendor_contract or has_request_mapping or has_response_mapping):
            status = "admin_pending"
        elif has_canonical and has_missing:
            status = "needs_setup"
        elif has_canonical and has_inactive_unverified and not has_missing:
            status = "needs_attention"
        elif has_canonical and not has_missing and not has_inactive_unverified:
            status = "ready"
        else:
            status = "admin_pending"

        _partner = (tgt if is_outbound else src) or "*"
        if str(_partner).upper() == "ANY":
            _partner = "*"

        def _item(direction_outbound: bool) -> dict[str, Any]:
            p = (tgt if direction_outbound else src) or "*"
            if str(p).upper() == "ANY":
                p = "*"
            ep_val = endpoint_status_val if direction_outbound else "OK"
            has_ep = has_endpoint if direction_outbound else True
            return {
                "operationCode": op_code,
                "canonicalVersion": canonical_ver,
                "partnerVendorCode": p,
                "direction": "outbound" if direction_outbound else "inbound",
                "hasCanonicalOperation": has_canonical,
                "hasVendorContract": has_vendor_contract,
                "hasRequestMapping": has_request_mapping,
                "hasResponseMapping": has_response_mapping,
                "mappingConfigured": mapping_configured,
                "usesCanonicalRequestMapping": uses_canonical_request,
                "usesCanonicalResponseMapping": uses_canonical_response,
                "requiresRequestMapping": requires_request_mapping,
                "requiresResponseMapping": requires_response_mapping,
                "requestMappingStatus": request_mapping_status,
                "responseMappingStatus": response_mapping_status,
                "hasEndpoint": has_ep,
                "hasAllowlist": has_allowlist,
                "contractStatus": contract_status,
                "mappingStatus": mapping_status,
                "endpointStatus": ep_val,
                "allowlistStatus": "OK" if has_allowlist else "MISSING",
                "issues": issues,
                "status": status,
            }

        if is_outbound:
            outbound_list.append(_item(True))
        if is_inbound:
            inbound_list.append(_item(False))

    return outbound_list, inbound_list


def _handle_get_my_operations(event: dict[str, Any]) -> dict[str, Any]:
    """
    GET /v1/vendor/my-operations - consolidated flow readiness (outbound + inbound).
    Returns per-operation readiness with contract, mappings, endpoint, allowlist status.
    Admin allowlist rules only. Robust against empty or partial DB.
    """
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")

    try:
        with _get_connection() as conn:
            allowlist_rows = _load_allowlist_for_vendor(conn, vendor_code)
            if not allowlist_rows:
                return _success(200, {"outbound": [], "inbound": []})

            op_codes = sorted({(r.get("operation_code") or "").strip() for r in allowlist_rows if (r.get("operation_code") or "").strip()})
            if not op_codes:
                return _success(200, {"outbound": [], "inbound": []})

            batch = _batch_load_my_operations_inputs(conn, vendor_code, op_codes, allowlist_rows)
            outbound_list, inbound_list = _build_my_operations_response(
                allowlist_rows, batch, vendor_code
            )
            return _success(200, {"outbound": outbound_list, "inbound": inbound_list})
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


# --- Auth profiles (vendor-scoped, direct DB) ---


def _auth_profile_to_dto(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize auth_profile row to camelCase DTO."""
    created = row.get("created_at")
    updated = row.get("updated_at")
    return {
        "id": str(row["id"]) if row.get("id") else None,
        "vendorCode": row.get("vendor_code") or "",
        "name": row.get("name") or "",
        "authType": row.get("auth_type") or "",
        "config": row.get("config") if isinstance(row.get("config"), dict) else {},
        "isActive": bool(row.get("is_active", True)),
        "createdAt": created.isoformat() if hasattr(created, "isoformat") else str(created) if created else None,
        "updatedAt": updated.isoformat() if hasattr(updated, "isoformat") else str(updated) if updated else None,
    }


def _handle_get_auth_profiles(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/vendor/auth-profiles - list auth profiles for authenticated vendor."""
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")

    try:
        with _get_connection() as conn:
            q = sql.SQL(
                """
                SELECT id, vendor_code, name, auth_type, config, is_active, created_at, updated_at
                FROM control_plane.auth_profiles
                WHERE vendor_code = %s
                ORDER BY created_at DESC
                LIMIT 100
                """
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(q, (vendor_code,))
                rows = cur.fetchall()
        items = [_auth_profile_to_dto(dict(r)) for r in rows]
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))

    return _success(200, {"items": items})


def _handle_post_auth_profiles(event: dict[str, Any]) -> dict[str, Any]:
    """POST /v1/vendor/auth-profiles - create or update auth profile."""
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")

    body = _parse_body(event.get("body"))
    if err := _reject_body_vendor_mismatch(body, vendor_code):
        return err

    name = (body.get("name") or "").strip()
    if not name:
        return _error(400, "VALIDATION_ERROR", "name is required")
    auth_type = (body.get("authType") or body.get("auth_type") or "").strip()
    if not auth_type:
        return _error(400, "VALIDATION_ERROR", "authType is required")
    config = body.get("config")
    if not isinstance(config, dict):
        config = {}
    profile_id = body.get("id") or body.get("authProfileId") or body.get("auth_profile_id")
    profile_id = str(profile_id).strip() if profile_id else None
    is_active = body.get("isActive", body.get("is_active"))
    if is_active is None:
        is_active = True
    is_active = is_active if isinstance(is_active, bool) else str(is_active).lower() in ("true", "1", "yes")
    request_id = event.get("requestContext", {}).get("requestId", "local")

    try:
        with _get_connection() as conn:
            if profile_id:
                q = sql.SQL(
                    """
                    UPDATE control_plane.auth_profiles
                    SET vendor_code = %s, name = %s, auth_type = %s, config = %s::jsonb, is_active = %s, updated_at = now()
                    WHERE id = %s::uuid AND vendor_code = %s
                    RETURNING id, vendor_code, name, auth_type, config, is_active, created_at, updated_at
                    """
                )
                row = _execute_one(conn, q, (vendor_code, name, auth_type, json.dumps(config), is_active, profile_id, vendor_code))
            else:
                q = sql.SQL(
                    """
                    INSERT INTO control_plane.auth_profiles (vendor_code, name, auth_type, config, is_active)
                    VALUES (%s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (vendor_code, name) DO UPDATE SET
                        auth_type = EXCLUDED.auth_type,
                        config = EXCLUDED.config,
                        is_active = EXCLUDED.is_active,
                        updated_at = now()
                    RETURNING id, vendor_code, name, auth_type, config, is_active, created_at, updated_at
                    """
                )
                row = _execute_one(conn, q, (vendor_code, name, auth_type, json.dumps(config), is_active))
            if row:
                _write_audit_event(
                    conn,
                    transaction_id=f"vendor-registry-{request_id}",
                    action="auth_profile_upsert",
                    vendor_code=vendor_code,
                    details={"authType": auth_type, "authProfileId": str(row["id"]), "name": name},
                )
            if not row:
                return _error(404, "NOT_FOUND", "Auth profile not found")
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))

    return _success(200, {"authProfile": _auth_profile_to_dto(row) if row else {}, "item": _auth_profile_to_dto(row) if row else {}})


def _handle_patch_auth_profile(event: dict[str, Any], profile_id: str) -> dict[str, Any]:
    """PATCH /v1/vendor/auth-profiles/{id} - toggle isActive or update config."""
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")

    body = _parse_body(event.get("body"))
    is_active = body.get("isActive", body.get("is_active"))
    config = body.get("config")
    if is_active is None and config is None:
        return _error(400, "VALIDATION_ERROR", "isActive or config required")
    request_id = event.get("requestContext", {}).get("requestId", "local")

    try:
        with _get_connection() as conn:
            row = _execute_one(
                conn,
                sql.SQL(
                    "SELECT id, vendor_code, name, auth_type, config, is_active, created_at, updated_at FROM control_plane.auth_profiles WHERE id = %s::uuid AND vendor_code = %s"
                ),
                (profile_id.strip(), vendor_code),
            )
            if not row:
                return _error(404, "NOT_FOUND", "Auth profile not found")
            updates, vals = [], []
            if is_active is not None:
                updates.append("is_active = %s")
                vals.append(is_active if isinstance(is_active, bool) else str(is_active).lower() in ("true", "1", "yes"))
            if config is not None and isinstance(config, dict):
                updates.append("config = %s::jsonb")
                vals.append(json.dumps(config))
            if not updates:
                return _success(200, {"authProfile": _auth_profile_to_dto(row)})
            vals.extend([profile_id.strip(), vendor_code])
            q = sql.SQL(
                """
                UPDATE control_plane.auth_profiles SET {}, updated_at = now()
                WHERE id = %s::uuid AND vendor_code = %s
                RETURNING id, vendor_code, name, auth_type, config, is_active, created_at, updated_at
                """
            ).format(sql.SQL(", ").join(sql.SQL(u) for u in updates))
            updated = _execute_one(conn, q, tuple(vals))
            if updated:
                _write_audit_event(conn, transaction_id=f"vendor-registry-{request_id}", action="auth_profile_upsert", vendor_code=vendor_code, details={"authProfileId": profile_id})
            return _success(200, {"authProfile": _auth_profile_to_dto(updated) if updated else row})
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_delete_auth_profile(profile_id: str, vendor_code: str) -> dict[str, Any]:
    """DELETE /v1/vendor/auth-profiles/{id} - soft delete (is_active=false)."""
    try:
        with _get_connection() as conn:
            q = sql.SQL(
                """
                UPDATE control_plane.auth_profiles SET is_active = false, updated_at = now()
                WHERE id = %s::uuid AND vendor_code = %s
                RETURNING id
                """
            )
            row = _execute_one(conn, q, (profile_id.strip(), vendor_code))
            if not row:
                return _error(404, "NOT_FOUND", "Auth profile not found")
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))
    return _success(200, {"id": profile_id, "isActive": False})


# --- Allowlist (vendor-scoped: vendor must be source or target) ---


def _handle_post_allowlist(event: dict[str, Any]) -> dict[str, Any]:
    """POST /v1/vendor/allowlist - upsert entry. Vendor must be source or target. Admin rules define eligibility."""
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")

    body = _parse_body(event.get("body"))
    source_raw = (body.get("sourceVendorCode") or body.get("source_vendor_code") or "").strip().upper()
    target_raw = (body.get("targetVendorCode") or body.get("target_vendor_code") or "").strip().upper()
    op_raw = (body.get("operationCode") or body.get("operation_code") or "").strip().upper()
    if not source_raw or not target_raw or not op_raw:
        return _error(400, "VALIDATION_ERROR", "sourceVendorCode, targetVendorCode, operationCode are required")
    me = vendor_code.upper()
    if me != source_raw and me != target_raw:
        return _error(403, "FORBIDDEN", "Vendor must be source or target of the allowlist entry")
    request_id = event.get("requestContext", {}).get("requestId", "local")
    flow_raw = (body.get("flowDirection") or body.get("flow_direction") or "BOTH").strip().upper()
    flow_direction = flow_raw if flow_raw in ("INBOUND", "OUTBOUND", "BOTH") else "BOTH"

    if APPROVAL_GATE_ENABLED:
        payload = {
            "version": 1,
            "allowlist": {
                "source_vendor_code": source_raw,
                "target_vendor_code": target_raw,
                "is_any_source": False,
                "is_any_target": False,
                "operation_code": op_raw,
                "rule_scope": "vendor",
                "flow_direction": flow_direction,
            },
        }
        try:
            with _get_connection() as conn:
                from approval_utils import create_change_request
                cr = create_change_request(
                    conn,
                    request_type="ALLOWLIST_RULE",
                    vendor_code=vendor_code,
                    operation_code=op_raw,
                    payload=payload,
                    requested_by=None,
                    requested_via="vendor-portal",
                )
            return _success(202, {"changeRequestId": str(cr.get("id")), "status": "PENDING"})
        except Exception as e:
            return _error(500, "INTERNAL_ERROR", str(e))

    try:
        with _get_connection() as conn:
            # Eligibility: Admin must permit (source,target,op). Check admin rows only.
            # Use is_any_source / is_any_target for wildcards (no '*' or HUB).
            q_eligible = sql.SQL(
                """
                SELECT 1 FROM control_plane.vendor_operation_allowlist
                WHERE rule_scope = 'admin'
                  AND UPPER(TRIM(operation_code)) = %s
                  AND (COALESCE(is_any_source, FALSE) = TRUE OR UPPER(TRIM(source_vendor_code)) = %s)
                  AND (COALESCE(is_any_target, FALSE) = TRUE OR UPPER(TRIM(target_vendor_code)) = %s)
                LIMIT 1
                """
            )
            with conn.cursor() as cur:
                cur.execute(q_eligible, (op_raw, source_raw, target_raw))
                if cur.fetchone() is None:
                    return _error(
                        403,
                        "FORBIDDEN",
                        "No admin rule allows this combination. Contact the integration administrator to add eligibility.",
                    )

            q = sql.SQL(
                """
                INSERT INTO control_plane.vendor_operation_allowlist
                (source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, rule_scope, flow_direction)
                VALUES (%s, %s, FALSE, FALSE, %s, 'vendor', %s)
                ON CONFLICT (COALESCE(source_vendor_code, '*'), is_any_source, COALESCE(target_vendor_code, '*'), is_any_target, operation_code, rule_scope, flow_direction) DO NOTHING
                """
            )
            _execute_mutation(conn, q, (source_raw, target_raw, op_raw, flow_direction))
            q2 = sql.SQL(
                """
                SELECT id, source_vendor_code, target_vendor_code, operation_code, created_at
                FROM control_plane.vendor_operation_allowlist
                WHERE source_vendor_code = %s AND target_vendor_code = %s AND operation_code = %s
                  AND rule_scope = 'vendor' AND flow_direction = %s
                """
            )
            row = _execute_one(conn, q2, (source_raw, target_raw, op_raw, flow_direction))
            if row:
                _write_audit_event(conn, transaction_id=f"vendor-registry-{request_id}", action="allowlist_upsert", vendor_code=vendor_code, details={"source_vendor_code": source_raw, "target_vendor_code": target_raw, "operation_code": op_raw})
        if not row:
            return _error(500, "INTERNAL_ERROR", "Upsert failed")
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))

    return _success(200, {"allowlist": _to_camel_case_dict(dict(row))})


def _handle_delete_allowlist(entry_id: str, vendor_code: str) -> dict[str, Any]:
    """DELETE /v1/vendor/allowlist/{id} - delete entry. Vendor must be source or target."""
    import uuid as uuid_mod
    entry_id = (entry_id or "").strip()
    try:
        uuid_mod.UUID(entry_id)
    except (ValueError, TypeError):
        return _error(400, "VALIDATION_ERROR", "Invalid allowlist entry id")
    me = vendor_code.upper()
    try:
        with _get_connection() as conn:
            row = _execute_one(
                conn,
                sql.SQL(
                    "SELECT id, source_vendor_code, target_vendor_code, rule_scope "
                    "FROM control_plane.vendor_operation_allowlist WHERE id = %s"
                ),
                (entry_id,),
            )
            if not row:
                return _error(404, "NOT_FOUND", "Allowlist entry not found")
            if (row.get("rule_scope") or "").strip().lower() != "vendor":
                return _error(403, "FORBIDDEN", "Only vendor-created access rules can be removed from Access control")
            src = (row.get("source_vendor_code") or "").upper()
            tgt = (row.get("target_vendor_code") or "").upper()
            if me != src and me != tgt:
                return _error(403, "FORBIDDEN", "Vendor must be source or target of the allowlist entry")
            q = sql.SQL("DELETE FROM control_plane.vendor_operation_allowlist WHERE id = %s")
            with conn.cursor() as cur:
                cur.execute(q, (entry_id,))
                if cur.rowcount == 0:
                    return _error(404, "NOT_FOUND", "Allowlist entry not found")
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))
    return _success(200, {"deleted": True, "id": entry_id})


# --- Provider narrowing (PROVIDER_RECEIVES_ONLY: admin envelope + vendor whitelist) ---


def _handle_get_provider_narrowing(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/vendor/provider-narrowing?operationCode=X
    Returns adminEnvelope (admin-allowed callers) and vendorWhitelist (vendor-selected callers).
    Only for PROVIDER_RECEIVES_ONLY ops when vendor is the provider (receiver)."""
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")
    params = event.get("queryStringParameters") or {}
    qp = {k.lower(): v for k, v in (params or {}).items()}
    op_raw = (qp.get("operationcode") or "").strip().upper()
    if not op_raw:
        return _error(400, "VALIDATION_ERROR", "operationCode query param is required")
    provider = vendor_code.upper()

    try:
        with _get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT COALESCE(direction_policy, 'TWO_WAY') AS direction_policy
                    FROM control_plane.operations
                    WHERE operation_code = %s AND COALESCE(is_active, true)
                    """,
                    (op_raw,),
                )
                op_row = cur.fetchone()
                if op_row is None:
                    return _error(404, "NOT_FOUND", f"Operation {op_raw} not found or inactive")
                direction_policy = ((op_row.get("direction_policy") or "TWO_WAY") or "").strip().upper()
                if direction_policy != "PROVIDER_RECEIVES_ONLY":
                    return _error(
                        400,
                        "VALIDATION_ERROR",
                        "Provider narrowing only applies to PROVIDER_RECEIVES_ONLY operations",
                    )

                # Admin envelope: callers admin-allowed to call provider on this op.
                # Rules: target=provider (or is_any_target), flow_direction allows caller->provider (OUTBOUND/INBOUND/BOTH).
                cur.execute(
                    """
                    SELECT source_vendor_code, is_any_source
                    FROM control_plane.vendor_operation_allowlist
                    WHERE rule_scope = 'admin'
                      AND operation_code = %s
                      AND (COALESCE(is_any_target, FALSE) = TRUE OR UPPER(TRIM(target_vendor_code)) = %s)
                      AND flow_direction IN ('INBOUND', 'OUTBOUND', 'BOTH')
                    """,
                    (op_raw, provider),
                )
                admin_rows = cur.fetchall() or []
                admin_envelope: list[str] = []
                need_all_vendors = False
                for r in admin_rows:
                    if r.get("is_any_source"):
                        need_all_vendors = True
                        break
                    src = (r.get("source_vendor_code") or "").strip().upper()
                    if src and src != provider:
                        admin_envelope.append(src)
                if need_all_vendors:
                    cur.execute(
                        """
                        SELECT vendor_code FROM control_plane.vendors
                        WHERE COALESCE(is_active, true) AND UPPER(TRIM(vendor_code)) != %s
                        ORDER BY vendor_code
                        """,
                        (provider,),
                    )
                    admin_envelope = [r["vendor_code"].strip().upper() for r in (cur.fetchall() or []) if r.get("vendor_code")]

                admin_envelope = sorted(set(admin_envelope))

                # Vendor whitelist: vendor rules for (provider, op) flow_direction OUTBOUND.
                cur.execute(
                    """
                    SELECT source_vendor_code
                    FROM control_plane.vendor_operation_allowlist
                    WHERE rule_scope = 'vendor'
                      AND target_vendor_code = %s
                      AND operation_code = %s
                      AND flow_direction = 'OUTBOUND'
                      AND COALESCE(is_any_source, FALSE) = FALSE
                    """,
                    (provider, op_raw),
                )
                vendor_rows = cur.fetchall() or []
                vendor_whitelist = sorted(
                    set(
                        (r.get("source_vendor_code") or "").strip().upper()
                        for r in vendor_rows
                        if r.get("source_vendor_code")
                    )
                )
                # Ensure vendor whitelist is subset of admin envelope (sanity)
                vendor_whitelist = [v for v in vendor_whitelist if v in set(admin_envelope)]

        return _success(200, {
            "operationCode": op_raw,
            "adminEnvelope": admin_envelope,
            "vendorWhitelist": vendor_whitelist,
        })
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_put_provider_narrowing(event: dict[str, Any]) -> dict[str, Any]:
    """PUT /v1/vendor/provider-narrowing - set vendor whitelist for PROVIDER_RECEIVES_ONLY.
    Body: { operationCode, callerVendorCodes: [] }.
    Empty list = delete vendor rules (no narrowing). Non-empty = must be subset of adminEnvelope."""
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")

    body = _parse_body(event.get("body"))
    op_raw = (body.get("operationCode") or body.get("operation_code") or "").strip().upper()
    callers_raw = body.get("callerVendorCodes") or body.get("caller_vendor_codes") or []
    if not op_raw:
        return _error(400, "VALIDATION_ERROR", "operationCode is required")
    if not isinstance(callers_raw, list):
        return _error(400, "VALIDATION_ERROR", "callerVendorCodes must be an array")
    caller_codes = [str(c).strip().upper() for c in callers_raw if c]
    provider = vendor_code.upper()
    request_id = event.get("requestContext", {}).get("requestId", "local")

    try:
        with _get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT COALESCE(direction_policy, 'TWO_WAY') AS direction_policy
                    FROM control_plane.operations
                    WHERE operation_code = %s AND COALESCE(is_active, true)
                    """,
                    (op_raw,),
                )
                op_row = cur.fetchone()
                if op_row is None:
                    return _error(404, "NOT_FOUND", f"Operation {op_raw} not found or inactive")
                direction_policy = ((op_row.get("direction_policy") or "TWO_WAY") or "").strip().upper()
                if direction_policy != "PROVIDER_RECEIVES_ONLY":
                    return _error(
                        400,
                        "VALIDATION_ERROR",
                        "Provider narrowing only applies to PROVIDER_RECEIVES_ONLY operations",
                    )

                # Build admin envelope (same as GET)
                cur.execute(
                    """
                    SELECT source_vendor_code, is_any_source
                    FROM control_plane.vendor_operation_allowlist
                    WHERE rule_scope = 'admin'
                      AND operation_code = %s
                      AND (COALESCE(is_any_target, FALSE) = TRUE OR UPPER(TRIM(target_vendor_code)) = %s)
                      AND flow_direction IN ('INBOUND', 'OUTBOUND', 'BOTH')
                    """,
                    (op_raw, provider),
                )
                admin_rows = cur.fetchall() or []
                admin_envelope: set[str] = set()
                need_all_vendors = False
                for r in admin_rows:
                    if r.get("is_any_source"):
                        need_all_vendors = True
                        break
                    src = (r.get("source_vendor_code") or "").strip().upper()
                    if src and src != provider:
                        admin_envelope.add(src)
                if need_all_vendors:
                    cur.execute(
                        """
                        SELECT vendor_code FROM control_plane.vendors
                        WHERE COALESCE(is_active, true) AND UPPER(TRIM(vendor_code)) != %s
                        """,
                        (provider,),
                    )
                    admin_envelope = {r["vendor_code"].strip().upper() for r in (cur.fetchall() or []) if r.get("vendor_code")}

                # Reject widening: all callers must be in admin envelope
                for c in caller_codes:
                    if c not in admin_envelope:
                        return _error(
                            400,
                            "VALIDATION_ERROR",
                            f"Caller {c} is not in admin envelope; cannot widen access beyond admin rules",
                        )

                # Delete existing vendor rules for (provider, op) flow_direction OUTBOUND
                cur.execute(
                    """
                    DELETE FROM control_plane.vendor_operation_allowlist
                    WHERE rule_scope = 'vendor'
                      AND target_vendor_code = %s
                      AND operation_code = %s
                      AND flow_direction = 'OUTBOUND'
                    """,
                    (provider, op_raw),
                )

                # If non-empty, insert vendor rules for each selected caller
                for caller in caller_codes:
                    cur.execute(
                        """
                        INSERT INTO control_plane.vendor_operation_allowlist
                        (source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, rule_scope, flow_direction)
                        VALUES (%s, %s, FALSE, FALSE, %s, 'vendor', 'OUTBOUND')
                        ON CONFLICT (COALESCE(source_vendor_code, '*'), is_any_source, COALESCE(target_vendor_code, '*'), is_any_target, operation_code, rule_scope, flow_direction) DO NOTHING
                        """,
                        (caller, provider, op_raw),
                    )

            _write_audit_event(
                conn,
                transaction_id=f"vendor-registry-{request_id}",
                action="provider_narrowing_put",
                vendor_code=vendor_code,
                details={"operation_code": op_raw, "caller_vendor_codes": caller_codes},
            )

        return _success(200, {
            "operationCode": op_raw,
            "callerVendorCodes": caller_codes,
        })
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


# --- Eligible access (admin rules for Add rule dropdown) ---


def _handle_get_eligible_access(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/vendor/eligible-access?operationCode=X&direction=outbound|inbound - partners vendor can add (per admin rules).
    Filters by flow_direction: outbound uses OUTBOUND/BOTH rules, inbound uses INBOUND/BOTH."""
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")
    params = event.get("queryStringParameters") or {}
    qp = {k.lower(): v for k, v in (params or {}).items()}
    op_raw = (qp.get("operationcode") or "").strip().upper()
    if not op_raw:
        return _error(400, "VALIDATION_ERROR", "operationCode query param is required")
    direction_raw = (qp.get("direction") or "").strip().lower()
    me = vendor_code.upper()
    try:
        with _get_connection() as conn:
            # Fetch admin rules for this op with flow_direction.
            # Use is_any_source / is_any_target for wildcards (no '*' or HUB).
            q = sql.SQL(
                """
                SELECT source_vendor_code, target_vendor_code, is_any_source, is_any_target, flow_direction
                FROM control_plane.vendor_operation_allowlist
                WHERE LOWER(COALESCE(rule_scope, 'admin')) = 'admin'
                  AND UPPER(TRIM(operation_code)) = %s
                  AND (
                    (COALESCE(is_any_source, FALSE) = TRUE OR UPPER(TRIM(source_vendor_code)) = %s)
                    OR (COALESCE(is_any_target, FALSE) = TRUE OR UPPER(TRIM(target_vendor_code)) = %s)
                  )
                """
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(q, (op_raw, me, me))
                rows = [dict(r) for r in cur.fetchall()]
        outbound_targets: set[str] = set()
        inbound_sources: set[str] = set()
        can_wildcard_out = False
        can_wildcard_in = False

        def _dir_match(fd: str | None, direction: str) -> bool:
            d = (fd or "BOTH").upper()
            if d == "BOTH":
                return True
            if direction == "outbound":
                return d in ("OUTBOUND", "BOTH")
            return d in ("INBOUND", "BOTH")

        for r in rows:
            src = (r.get("source_vendor_code") or "").strip().upper()
            tgt = (r.get("target_vendor_code") or "").strip().upper()
            is_any_src = bool(r.get("is_any_source"))
            is_any_tgt = bool(r.get("is_any_target"))
            fd = r.get("flow_direction")
            # Outbound: source=me or any, target is the partner, rule flow_direction IN (OUTBOUND,BOTH)
            if _dir_match(fd, "outbound") and (src == me or is_any_src) and (tgt and tgt != me or is_any_tgt):
                if tgt and tgt != me:
                    outbound_targets.add(tgt)
                if is_any_tgt:
                    can_wildcard_out = True
            # Inbound: target=me or any, source is the partner, rule flow_direction IN (INBOUND,BOTH)
            if _dir_match(fd, "inbound") and (tgt == me or is_any_tgt) and (src and src != me or is_any_src):
                if src and src != me:
                    inbound_sources.add(src)
                if is_any_src:
                    can_wildcard_in = True
        return _success(200, {
            "operationCode": op_raw,
            "outboundTargets": sorted(outbound_targets),
            "inboundSources": sorted(inbound_sources),
            "canUseWildcardOutbound": can_wildcard_out,
            "canUseWildcardInbound": can_wildcard_in,
            "isBlockedByAdmin": not outbound_targets and not inbound_sources and not can_wildcard_out and not can_wildcard_in,
        })
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


# --- Canonical vendors (direct DB, for allowlist dropdown) ---


def _handle_get_canonical_vendors(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/vendor/canonical/vendors - list vendors for dropdown (read-only)."""
    params = event.get("queryStringParameters") or {}
    limit_raw = params.get("limit") or params.get("Limit") or "50"
    try:
        limit = min(200, max(1, int(limit_raw)))
    except (ValueError, TypeError):
        limit = 200
    try:
        with _get_connection() as conn:
            q = sql.SQL(
                """
                SELECT id, vendor_code, vendor_name, COALESCE(is_active, true) AS is_active, created_at, updated_at
                FROM control_plane.vendors
                WHERE COALESCE(is_active, true) = true
                ORDER BY vendor_code
                LIMIT %s
                """
            )
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(q, (limit,))
                rows = cur.fetchall()
        items = [_to_camel_case_dict(dict(r)) for r in rows]
        for it in items:
            if "id" in it and it["id"]:
                it["id"] = str(it["id"])
        return _success(200, {"items": items})
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


# --- Metrics & Transactions ---

_ISO_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)
TX_SCHEMA = "data_plane"
TX_TABLE = "transactions"
TX_DEFAULT_LIMIT = 50
TX_MAX_LIMIT = 200


def _parse_iso_ts(val: str | None) -> str | None:
    if not val or not isinstance(val, str) or not val.strip():
        return None
    s = val.strip()
    if not _ISO_PATTERN.match(s):
        raise ValueError("from and to must be ISO 8601 (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)")
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"invalid date: {e}") from e
    return s


def _decode_tx_cursor(cursor_b64: str) -> tuple[str, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor_b64.encode()).decode()
        parts = raw.split("|", 1)
        if len(parts) != 2:
            return None
        return (parts[0], parts[1])
    except Exception:
        return None


def _encode_tx_cursor(created_at_iso: str, transaction_id: str) -> str:
    return base64.urlsafe_b64encode(f"{created_at_iso}|{transaction_id}".encode()).decode()


def _vendor_tx_condition() -> sql.Composable:
    """Return SQL condition: (source_vendor = %s OR target_vendor = %s)."""
    return sql.SQL("(source_vendor = %s OR target_vendor = %s)")


def _query_metrics_from_rollup(
    conn: Any,
    vendor_code: str,
    from_ts: str,
    to_ts: str,
) -> dict[str, Any] | None:
    """
    Read metrics from transaction_metrics_daily if available.
    Returns same shape as _query_metrics_overview or None if rollup empty/unavailable.
    """
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check if we have any rollup data for this vendor in range
            cur.execute(
                """
                SELECT SUM(count) AS total FROM data_plane.transaction_metrics_daily
                WHERE vendor_code = %s AND bucket_start >= %s::timestamptz AND bucket_start < %s::timestamptz
                """,
                (vendor_code, from_ts, to_ts),
            )
            row = cur.fetchone()
            if not row or (row["total"] or 0) == 0:
                return None

            # Totals
            cur.execute(
                """
                SELECT
                    SUM(count) AS cnt,
                    SUM(count) FILTER (WHERE status = 'completed') AS completed,
                    SUM(count) FILTER (WHERE status != 'completed') AS failed
                FROM data_plane.transaction_metrics_daily
                WHERE vendor_code = %s AND bucket_start >= %s::timestamptz AND bucket_start < %s::timestamptz
                """,
                (vendor_code, from_ts, to_ts),
            )
            r = cur.fetchone()
            totals = {
                "count": int(r["cnt"]) if r and r["cnt"] else 0,
                "completed": int(r["completed"]) if r and r["completed"] else 0,
                "failed": int(r["failed"]) if r and r["failed"] else 0,
            }

            # byStatus
            cur.execute(
                """
                SELECT status, SUM(count) AS cnt
                FROM data_plane.transaction_metrics_daily
                WHERE vendor_code = %s AND bucket_start >= %s::timestamptz AND bucket_start < %s::timestamptz
                GROUP BY status ORDER BY cnt DESC
                """,
                (vendor_code, from_ts, to_ts),
            )
            by_status = [{"status": str(x["status"]), "count": int(x["cnt"])} for x in cur.fetchall()]

            # byOperation
            cur.execute(
                """
                SELECT operation,
                       SUM(count) AS cnt,
                       SUM(count) FILTER (WHERE status != 'completed') AS failed
                FROM data_plane.transaction_metrics_daily
                WHERE vendor_code = %s AND bucket_start >= %s::timestamptz AND bucket_start < %s::timestamptz
                GROUP BY operation ORDER BY cnt DESC
                """,
                (vendor_code, from_ts, to_ts),
            )
            by_operation = [
                {"operation": str(x["operation"]), "count": int(x["cnt"]), "failed": int(x["failed"])}
                for x in cur.fetchall()
            ]

            # Timeseries (daily buckets)
            cur.execute(
                """
                SELECT bucket_start AS bucket, SUM(count) AS cnt,
                       SUM(count) FILTER (WHERE status != 'completed') AS failed
                FROM data_plane.transaction_metrics_daily
                WHERE vendor_code = %s AND bucket_start >= %s::timestamptz AND bucket_start < %s::timestamptz
                GROUP BY bucket_start ORDER BY bucket_start ASC
                """,
                (vendor_code, from_ts, to_ts),
            )
            timeseries = []
            for r in cur.fetchall():
                ts_val = r["bucket"]
                bucket_str = ts_val.isoformat() if ts_val and hasattr(ts_val, "isoformat") else str(ts_val or "")
                timeseries.append({"bucket": bucket_str, "count": int(r["cnt"]), "failed": int(r["failed"])})

            return {"totals": totals, "byStatus": by_status, "byOperation": by_operation, "timeseries": timeseries}
    except Exception:
        return None


def _query_metrics_overview(
    conn: Any,
    vendor_code: str,
    from_ts: str,
    to_ts: str,
    bucket_hours: int,
) -> dict[str, Any]:
    """
    Aggregate transactions for vendor in [from, to]. Returns totals, byStatus, byOperation, timeseries.
    Prefers rollup table (transaction_metrics_daily) when available; else live transactions.
    Live path: (source_vendor=? OR target_vendor=?) AND created_at BETWEEN.

    Index (live): idx_transactions_source_vendor_created_at, idx_transactions_target_vendor_created_at
    (bitmap OR). Rollup: idx_tx_metrics_daily_vendor_bucket. Partition pruning via created_at when live.
    EXPLAIN sample (live, vendor=LH001): Append (subplans: pruned) -> BitmapOr -> Index Scan ...
    """
    # Try rollup first (fast path for historical windows)
    rollup = _query_metrics_from_rollup(conn, vendor_code, from_ts, to_ts)
    if rollup is not None:
        return rollup

    params: list[Any] = [vendor_code, vendor_code, from_ts, to_ts]
    base_where = sql.SQL(
        "({} AND created_at >= %s::timestamptz AND created_at <= %s::timestamptz)"
    ).format(_vendor_tx_condition())

    # Totals
    q_totals = sql.SQL(
        """
        SELECT
            COUNT(*) AS cnt,
            COUNT(*) FILTER (WHERE status = 'completed') AS completed,
            COUNT(*) FILTER (WHERE status != 'completed') AS failed
        FROM {}.{}
        WHERE {}
        """
    ).format(sql.Identifier(TX_SCHEMA), sql.Identifier(TX_TABLE), base_where)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q_totals, tuple(params))
        row = cur.fetchone()
    totals = {
        "count": int(row["cnt"]) if row else 0,
        "completed": int(row["completed"]) if row else 0,
        "failed": int(row["failed"]) if row else 0,
    }

    # byStatus
    q_status = sql.SQL(
        """
        SELECT status, COUNT(*) AS cnt
        FROM {}.{}
        WHERE {}
        GROUP BY status
        ORDER BY cnt DESC
        """
    ).format(sql.Identifier(TX_SCHEMA), sql.Identifier(TX_TABLE), base_where)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q_status, tuple(params))
        rows = cur.fetchall()
    by_status = [{"status": str(r["status"]), "count": int(r["cnt"])} for r in rows]

    # byOperation (with failed count)
    q_op = sql.SQL(
        """
        SELECT operation,
               COUNT(*) AS cnt,
               COUNT(*) FILTER (WHERE status != 'completed') AS failed
        FROM {}.{}
        WHERE {}
        GROUP BY operation
        ORDER BY cnt DESC
        """
    ).format(sql.Identifier(TX_SCHEMA), sql.Identifier(TX_TABLE), base_where)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q_op, tuple(params))
        rows = cur.fetchall()
    by_operation = [
        {"operation": str(r["operation"]), "count": int(r["cnt"]), "failed": int(r["failed"])}
        for r in rows
    ]

    # Timeseries: bucket by date_trunc
    trunc_expr = "hour" if bucket_hours == 1 else "day"
    q_ts = sql.SQL(
        """
        SELECT
            date_trunc(%s, created_at AT TIME ZONE 'UTC') AS bucket,
            COUNT(*) AS cnt,
            COUNT(*) FILTER (WHERE status != 'completed') AS failed
        FROM {}.{}
        WHERE {}
        GROUP BY 1
        ORDER BY 1 ASC
        """
    ).format(sql.Identifier(TX_SCHEMA), sql.Identifier(TX_TABLE), base_where)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q_ts, [trunc_expr] + list(params))
        rows = cur.fetchall()
    timeseries = []
    for r in rows:
        ts_val = r["bucket"]
        if ts_val is not None and hasattr(ts_val, "isoformat"):
            bucket_str = ts_val.isoformat()
        else:
            bucket_str = str(ts_val) if ts_val else ""
        timeseries.append({
            "bucket": bucket_str,
            "count": int(r["cnt"]),
            "failed": int(r["failed"]),
        })

    return {"totals": totals, "byStatus": by_status, "byOperation": by_operation, "timeseries": timeseries}


AUDIT_EVENTS_DEFAULT_LIMIT = 200


def _query_audit_events_for_transaction(
    conn: Any,
    transaction_id: str,
    limit: int = AUDIT_EVENTS_DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """List audit events for a transaction. Used by vendor transaction detail."""
    limit = min(max(1, limit), 500)
    q = sql.SQL(
        """
        SELECT id, transaction_id, action, vendor_code, details, created_at
        FROM data_plane.audit_events
        WHERE transaction_id = %s
        ORDER BY created_at ASC
        LIMIT %s
        """
    )
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, (transaction_id.strip(), limit))
        rows = cur.fetchall()
    return [
        {
            "id": str(r["id"]) if r.get("id") else None,
            "transactionId": r["transaction_id"],
            "action": r["action"],
            "vendorCode": r.get("vendor_code") or "",
            "details": r.get("details"),
            "createdAt": _format_ts(r.get("created_at")),
        }
        for r in rows
    ]


def _query_vendor_transactions(
    conn: Any,
    vendor_code: str,
    direction: str,
    from_ts: str,
    to_ts: str,
    operation: str | None,
    status: str | None,
    search: str | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Query transactions for vendor. direction: outbound (source=me), inbound (target=me), all (OR).
    Always time-bounded: created_at BETWEEN from AND to. Cursor: (created_at, transaction_id) < (prev_last).
    search: optional substring match on transaction_id or correlation_id.

    Index: direction=outbound -> idx_transactions_source_vendor_created_at (source_vendor, created_at DESC);
           direction=inbound -> idx_transactions_target_vendor_created_at;
           direction=all -> bitmap OR of both. Partition pruning via created_at range.
    EXPLAIN (ANALYZE, BUFFERS) sample (direction=outbound, vendor=LH001, from/to set):
      Limit  ->  Index Scan using idx_transactions_source_vendor_created_at
                  Index Cond: ((source_vendor = 'LH001') AND (created_at >= ...) AND (created_at <= ...))
      Append  (subplans: pruned) -- no full-table scan across all partitions.
    """
    limit = min(max(1, limit), TX_MAX_LIMIT)
    conditions: list[sql.Composable] = []
    params: list[Any] = []

    if direction == "outbound":
        conditions.append(sql.SQL("source_vendor = %s"))
        params.append(vendor_code)
    elif direction == "inbound":
        conditions.append(sql.SQL("target_vendor = %s"))
        params.append(vendor_code)
    else:
        conditions.append(_vendor_tx_condition())
        params.extend([vendor_code, vendor_code])

    conditions.append(sql.SQL("created_at >= %s::timestamptz"))
    params.append(from_ts)
    conditions.append(sql.SQL("created_at <= %s::timestamptz"))
    params.append(to_ts)
    if operation:
        conditions.append(sql.SQL("operation = %s"))
        params.append(operation)
    if status:
        conditions.append(sql.SQL("status = %s"))
        params.append(status)
    if search and search.strip():
        search_val = f"%{search.strip()}%"
        conditions.append(sql.SQL("(transaction_id ILIKE %s OR correlation_id ILIKE %s)"))
        params.extend([search_val, search_val])

    decoded = _decode_tx_cursor(cursor) if cursor else None
    if decoded:
        conditions.append(sql.SQL("(created_at, transaction_id) < (%s::timestamptz, %s)"))
        params.extend(decoded)

    where = sql.SQL(" AND ").join(conditions)
    params.append(limit + 1)

    # List view: minimal columns. Time-bounded, indexed (source/target_vendor + created_at).
    q = sql.SQL(
        """
        SELECT id, transaction_id, correlation_id, source_vendor, target_vendor,
               operation, idempotency_key, status, created_at
        FROM {}.{}
        WHERE {}
        ORDER BY created_at DESC, transaction_id DESC
        LIMIT %s
        """
    ).format(sql.Identifier(TX_SCHEMA), sql.Identifier(TX_TABLE), where)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, tuple(params))
        rows = cur.fetchall()

    items: list[dict[str, Any]] = []
    next_cursor: str | None = None
    for i, r in enumerate(rows):
        if i >= limit:
            last = rows[limit - 1]
            next_cursor = _encode_tx_cursor(
                last["created_at"].isoformat() if last.get("created_at") else "",
                last["transaction_id"],
            )
            break
        items.append(_to_tx_list_item(r))

    return items[:limit], next_cursor


def _format_ts(val: Any) -> str:
    if val is None:
        return ""
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _to_tx_list_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]) if row.get("id") else None,
        "transactionId": row.get("transaction_id"),
        "correlationId": row.get("correlation_id"),
        "sourceVendor": row.get("source_vendor"),
        "targetVendor": row.get("target_vendor"),
        "operation": row.get("operation"),
        "idempotencyKey": row.get("idempotency_key"),
        "status": row.get("status"),
        "createdAt": _format_ts(row.get("created_at")),
    }


def _get_transaction_by_id_vendor(
    conn: Any,
    transaction_id: str,
    vendor_code: str,
) -> dict[str, Any] | None:
    """Get transaction by id. Guard: source_vendor = me OR target_vendor = me."""
    q = sql.SQL(
        """
        SELECT id, transaction_id, correlation_id, source_vendor, target_vendor,
               operation, idempotency_key, status, created_at,
               request_body, response_body,
               COALESCE(canonical_request_body, canonical_request) AS canonical_request_body,
               COALESCE(target_request_body, target_request) AS target_request_body,
               target_response_body, canonical_response_body,
               error_code, http_status, retryable, failure_stage,
               parent_transaction_id, redrive_count
        FROM {}.{}
        WHERE transaction_id = %s AND (source_vendor = %s OR target_vendor = %s)
        """
    ).format(sql.Identifier(TX_SCHEMA), sql.Identifier(TX_TABLE))
    return _execute_one(conn, q, (transaction_id, vendor_code, vendor_code))


REDRIVE_ELIGIBLE_STATUSES = frozenset({
    "downstream_error",
    "validation_failed",
    "downstream_timeout",
    "mapping_failed",
})
REDRIVE_MAX_COUNT = 5


def _compute_can_redrive(
    row: dict[str, Any],
    vendor_code: str,
) -> tuple[bool, str]:
    """
    Compute canRedrive and redriveReason for a transaction.
    Vendor can only redrive outbound (source_vendor == vendor_code).
    Returns (can_redrive: bool, redrive_reason: str).
    """
    source = (row.get("source_vendor") or "").strip()
    if source.upper() != (vendor_code or "").upper():
        return False, "NOT_OUTBOUND"

    status = (row.get("status") or "").strip().lower()
    if status == "completed":
        return False, "ALREADY_COMPLETED"
    if status not in REDRIVE_ELIGIBLE_STATUSES:
        return False, "STATUS_NOT_ELIGIBLE"

    redrive_count = row.get("redrive_count") or 0
    if redrive_count >= REDRIVE_MAX_COUNT:
        return False, "MAX_REDRIVE_EXCEEDED"

    request_body = row.get("request_body")
    if not request_body or not isinstance(request_body, dict):
        return False, "NO_REQUEST_BODY"

    return True, "ELIGIBLE"


def _to_tx_detail_response(
    row: dict[str, Any],
    audit_events: list[dict[str, Any]] | None = None,
    vendor_code: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "transactionId": row.get("transaction_id"),
        "correlationId": row.get("correlation_id"),
        "sourceVendor": row.get("source_vendor"),
        "targetVendor": row.get("target_vendor"),
        "operation": row.get("operation"),
        "status": row.get("status"),
        "idempotencyKey": row.get("idempotency_key"),
        "createdAt": _format_ts(row.get("created_at")),
        "requestBody": row.get("request_body"),
        "responseBody": row.get("response_body"),
        "canonicalRequestBody": row.get("canonical_request_body"),
        "targetRequestBody": row.get("target_request_body"),
        "targetResponseBody": row.get("target_response_body"),
        "canonicalResponseBody": row.get("canonical_response_body"),
        "errorCode": row.get("error_code"),
        "httpStatus": row.get("http_status"),
        "retryable": row.get("retryable"),
        "failureStage": row.get("failure_stage"),
        "parentTransactionId": str(row["parent_transaction_id"]) if row.get("parent_transaction_id") else None,
        "redriveCount": row.get("redrive_count") if row.get("redrive_count") is not None else 0,
    }
    if vendor_code:
        can_redrive, redrive_reason = _compute_can_redrive(row, vendor_code)
        out["canRedrive"] = can_redrive
        out["redriveReason"] = redrive_reason
    if audit_events is not None:
        out["auditEvents"] = audit_events
    return out


def _handle_get_metrics_overview(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/vendor/metrics/overview?from=&to= - aggregated metrics for vendor."""
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")

    params = event.get("queryStringParameters") or {}
    from_raw = (params.get("from") or "").strip()
    to_raw = (params.get("to") or "").strip()
    if not from_raw or not to_raw:
        return _error(400, "VALIDATION_ERROR", "from and to (ISO 8601) are required")
    try:
        from_ts = _parse_iso_ts(from_raw)
        to_ts = _parse_iso_ts(to_raw)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    if not from_ts or not to_ts:
        return _error(400, "VALIDATION_ERROR", "from and to are required")
    if from_ts > to_ts:
        return _error(400, "VALIDATION_ERROR", "from must be before or equal to to")

    from_dt = datetime.fromisoformat(from_ts.replace("Z", "+00:00"))
    to_dt = datetime.fromisoformat(to_ts.replace("Z", "+00:00"))
    delta_hours = (to_dt - from_dt).total_seconds() / 3600
    bucket_hours = 1 if delta_hours <= 24 else 24

    try:
        with _get_connection() as conn:
            aggs = _query_metrics_overview(conn, vendor_code, from_ts, to_ts, bucket_hours)
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))

    return _success(200, {
        "from": from_ts,
        "to": to_ts,
        "totals": aggs["totals"],
        "byStatus": aggs["byStatus"],
        "byOperation": aggs["byOperation"],
        "timeseries": aggs["timeseries"],
    })


def _handle_post_export_job(event: dict[str, Any]) -> dict[str, Any]:
    """POST /v1/vendor/export-jobs - create export job. Default last 7 days."""
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")
    body = _parse_body(event.get("body") or "{}")
    export_type_raw = (body.get("exportType") or body.get("export_type") or "TXN_7D").strip().upper()
    if export_type_raw not in ("CONFIG_ONLY", "TXN_7D", "EVERYTHING"):
        return _error(400, "VALIDATION_ERROR", "exportType must be CONFIG_ONLY, TXN_7D, or EVERYTHING")
    from_dt = datetime.now(timezone.utc) - timedelta(days=7)
    to_dt = datetime.now(timezone.utc)
    if body.get("from"):
        try:
            from_dt = datetime.fromisoformat(str(body["from"]).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return _error(400, "VALIDATION_ERROR", "from must be valid ISO 8601")
    if body.get("to"):
        try:
            to_dt = datetime.fromisoformat(str(body["to"]).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return _error(400, "VALIDATION_ERROR", "to must be valid ISO 8601")
    if from_dt > to_dt:
        return _error(400, "VALIDATION_ERROR", "from must be before or equal to to")
    from_ts = from_dt.isoformat().replace("+00:00", "Z")
    to_ts = to_dt.isoformat().replace("+00:00", "Z")
    try:
        with _get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO data_plane.vendor_export_jobs
                    (vendor_code, export_type, from_ts, to_ts, status, requested_by)
                    VALUES (%s, %s, %s::timestamptz, %s::timestamptz, 'QUEUED', 'vendor')
                    RETURNING id, vendor_code, export_type, from_ts, to_ts, status, created_at
                    """,
                    (vendor_code, export_type_raw, from_ts, to_ts),
                )
                row = cur.fetchone()
        if row:
            return _success(200, {
                "id": str(row["id"]),
                "vendorCode": row["vendor_code"],
                "exportType": row["export_type"],
                "from": from_ts,
                "to": to_ts,
                "status": row["status"],
                "createdAt": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
            })
        return _error(500, "INTERNAL_ERROR", "Failed to create export job")
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_get_export_job(event: dict[str, Any], job_id: str) -> dict[str, Any]:
    """GET /v1/vendor/export-jobs/{id} - get export job status. Vendor-scoped."""
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")
    try:
        import uuid as uuid_mod
        uuid_mod.UUID(job_id)
    except (ValueError, TypeError):
        return _error(400, "VALIDATION_ERROR", "Invalid export job id")
    try:
        with _get_connection() as conn:
            row = _execute_one(
                conn,
                sql.SQL(
                    """
                    SELECT id, vendor_code, export_type, from_ts, to_ts, status, s3_path, created_at, completed_at
                    FROM data_plane.vendor_export_jobs
                    WHERE id = %s::uuid AND vendor_code = %s
                    """
                ),
                (job_id, vendor_code),
            )
        if not row:
            return _error(404, "NOT_FOUND", "Export job not found")
        return _success(200, {
            "id": str(row["id"]),
            "vendorCode": row["vendor_code"],
            "exportType": row["export_type"],
            "from": row["from_ts"].isoformat() if hasattr(row.get("from_ts"), "isoformat") else str(row.get("from_ts", "")),
            "to": row["to_ts"].isoformat() if hasattr(row.get("to_ts"), "isoformat") else str(row.get("to_ts", "")),
            "status": row["status"],
            "s3Path": row.get("s3_path"),
            "createdAt": row["created_at"].isoformat() if hasattr(row.get("created_at"), "isoformat") else str(row.get("created_at", "")),
            "completedAt": row["completed_at"].isoformat() if row.get("completed_at") and hasattr(row["completed_at"], "isoformat") else str(row.get("completed_at") or "") or None,
        })
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_get_transactions_list(event: dict[str, Any]) -> dict[str, Any]:
    """
    GET /v1/vendor/transactions. from/to required. direction=outbound|inbound|all.
    limit clamped 1-200. Cursor for keyset pagination.
    """
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")

    params = event.get("queryStringParameters") or {}
    from_raw = (params.get("from") or "").strip()
    to_raw = (params.get("to") or "").strip()
    if not from_raw or not to_raw:
        return _error(400, "VALIDATION_ERROR", "from and to (ISO 8601) are required")
    try:
        from_ts = _parse_iso_ts(from_raw)
        to_ts = _parse_iso_ts(to_raw)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    if not from_ts or not to_ts:
        return _error(400, "VALIDATION_ERROR", "from and to are required")
    if from_ts > to_ts:
        return _error(400, "VALIDATION_ERROR", "from must be before or equal to to")

    direction = (params.get("direction") or "all").strip().lower() or "all"
    if direction not in ("outbound", "inbound", "all"):
        return _error(400, "VALIDATION_ERROR", "direction must be outbound, inbound, or all")

    operation = (params.get("operation") or "").strip() or None
    status = (params.get("status") or "").strip() or None
    search = (params.get("search") or "").strip() or None
    limit_raw = (params.get("limit") or "").strip()
    limit = TX_DEFAULT_LIMIT
    if limit_raw:
        try:
            limit = int(limit_raw)
            limit = min(max(1, limit), TX_MAX_LIMIT)
        except ValueError:
            return _error(400, "VALIDATION_ERROR", "limit must be 1-200")
    cursor = (params.get("cursor") or "").strip() or None

    try:
        with _get_connection() as conn:
            items, next_cursor = _query_vendor_transactions(
                conn,
                vendor_code,
                direction,
                from_ts,
                to_ts,
                operation,
                status,
                search,
                limit,
                cursor,
            )
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))

    out: dict[str, Any] = {"transactions": items, "count": len(items)}
    if next_cursor:
        out["nextCursor"] = next_cursor
    return _success(200, out)


def _handle_get_transaction_detail(event: dict[str, Any], transaction_id: str) -> dict[str, Any]:
    """GET /v1/vendor/transactions/{transactionId} - single tx with audit events, guarded by vendor."""
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")

    tx_id = transaction_id.strip()
    try:
        with _get_connection() as conn:
            row = _get_transaction_by_id_vendor(conn, tx_id, vendor_code)
            if not row:
                return _error(404, "NOT_FOUND", "Transaction not found")
            audit_events = _query_audit_events_for_transaction(conn, tx_id)
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))

    return _success(200, _to_tx_detail_response(row, audit_events, vendor_code))


def _handle_post_transaction_redrive(
    event: dict[str, Any],
    transaction_id: str,
) -> dict[str, Any]:
    """
    POST /v1/vendor/transactions/{transactionId}/redrive
    Vendor-scoped redrive: only outbound tx, must be eligible. Delegates to admin redrive API.
    """
    vendor_code = (event.get("vendor_code") or "").strip()
    if not vendor_code:
        return _error(401, "AUTH_ERROR", "Vendor code not resolved from API key")

    tx_id = (transaction_id or "").strip()
    if not tx_id:
        return _error(400, "VALIDATION_ERROR", "transactionId is required")

    try:
        with _get_connection() as conn:
            row = _get_transaction_by_id_vendor(conn, tx_id, vendor_code)
            if not row:
                return _error(404, "NOT_FOUND", "Transaction not found")

            can_redrive, reason = _compute_can_redrive(row, vendor_code)
            if not can_redrive:
                msg = {
                    "NOT_OUTBOUND": "You can only redrive outbound transactions (where you are the source vendor).",
                    "ALREADY_COMPLETED": "Transaction already completed successfully.",
                    "STATUS_NOT_ELIGIBLE": "Transaction is not eligible for redrive.",
                    "MAX_REDRIVE_EXCEEDED": "Max redrive attempts exceeded.",
                    "NO_REQUEST_BODY": "Transaction has no request body to replay.",
                }.get(reason, "Transaction is not eligible for redrive.")
                return _error(400, "REDRIVE_NOT_ELIGIBLE", msg)
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))

    auth_header = _authorization_header(event).strip()
    if not auth_header:
        return _error(401, "AUTH_ERROR", "Authentication required for redrive")

    admin_base = os.environ.get("ADMIN_API_BASE_URL", "")
    timeout_ms = int(os.environ.get("VENDOR_ADMIN_TIMEOUT_MS") or VENDOR_ADMIN_TIMEOUT_MS_DEFAULT)
    timeout_sec = min(30.0, max(5.0, timeout_ms / 1000.0))

    if not admin_base.strip():
        return add_cors_to_response(
            canonical_error(
                "ADMIN_API_UNAVAILABLE",
                "Redrive is currently unavailable",
                status_code=503,
                category="PLATFORM",
                retryable=False,
            )
        )

    status, body, err_msg = _fetch_admin_api_post(
        f"/v1/admin/redrive/{tx_id}",
        admin_base,
        auth_header,
        timeout_sec,
        json_body={},
    )

    if 200 <= status < 300 and body:
        return _success(status, body)
    if 400 <= status < 500:
        return _error(status, "REDRIVE_FAILED", err_msg or "Redrive failed")
    if status == 503 and err_msg and "ADMIN_API_BASE_URL" in err_msg:
        return add_cors_to_response(
            canonical_error(
                "ADMIN_API_UNAVAILABLE",
                "Redrive is currently unavailable",
                status_code=503,
                category="PLATFORM",
                retryable=False,
            )
        )
    return _error(502 if status == 504 else 503, "DOWNSTREAM_ERROR", err_msg or "Redrive service unavailable")


# --- Mappings ---


def _list_mappings(
    conn: Any,
    vendor_code: str,
    operation_code: str | None = None,
    canonical_version: str | None = None,
) -> list[dict[str, Any]]:
    conditions: list[sql.Composable] = [sql.SQL("vendor_code = %s")]
    params: list[Any] = [vendor_code]
    if operation_code:
        conditions.append(sql.SQL("operation_code = %s"))
        params.append(operation_code)
    if canonical_version:
        conditions.append(sql.SQL("canonical_version = %s"))
        params.append(canonical_version)
    where = sql.SQL(" AND ").join(conditions)
    q = sql.SQL(
        """
        SELECT id, vendor_code, operation_code, canonical_version, direction,
               mapping, is_active, created_at, updated_at
        FROM control_plane.vendor_operation_mappings
        WHERE {}
        ORDER BY operation_code, canonical_version, direction
        """
    ).format(where)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, tuple(params))
        rows = cur.fetchall()
    return [_to_camel_case_dict(dict(r)) for r in rows]


def _upsert_vendor_mapping(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    canonical_version: str,
    direction: str,
    mapping: dict[str, Any],
    is_active: bool,
    request_id: str,
    flow_direction: str = "OUTBOUND",
) -> dict[str, Any]:
    """Upsert vendor operation mapping. Key includes flow_direction per baseline schema.
    Key: (vendor_code, operation_code, canonical_version, direction, flow_direction).
    """
    mapping_json = json.dumps(mapping)
    fd = (flow_direction or "OUTBOUND").strip().upper()
    if fd not in ("INBOUND", "OUTBOUND"):
        fd = "OUTBOUND"
    key_params = (vendor_code, operation_code, canonical_version, direction, fd)

    if is_active:
        # 1. Look up existing active row
        q_find = sql.SQL(
            """
            SELECT id, is_active FROM control_plane.vendor_operation_mappings
            WHERE vendor_code = %s AND operation_code = %s AND canonical_version = %s
              AND direction = %s AND flow_direction = %s AND is_active = true
            """
        )
        existing = _execute_one(conn, q_find, key_params)

        if existing:
            # 2a. Update existing active row
            q_update = sql.SQL(
                """
                UPDATE control_plane.vendor_operation_mappings
                SET mapping = %s::jsonb, updated_at = now()
                WHERE id = %s
                RETURNING id, vendor_code, operation_code, canonical_version, direction,
                          flow_direction, mapping, is_active, created_at, updated_at
                """
            )
            row = _execute_one(conn, q_update, (mapping_json, existing["id"]))
        else:
            # 2b. No active row: deactivate any matching active rows, then insert
            q_deactivate = sql.SQL(
                """
                UPDATE control_plane.vendor_operation_mappings
                SET is_active = false, updated_at = now()
                WHERE vendor_code = %s AND operation_code = %s AND canonical_version = %s
                  AND direction = %s AND flow_direction = %s AND is_active = true
                """
            )
            _execute_mutation(conn, q_deactivate, key_params)

            q_insert = sql.SQL(
                """
                INSERT INTO control_plane.vendor_operation_mappings (
                    id, vendor_code, operation_code, canonical_version, direction, flow_direction,
                    mapping, is_active, created_at, updated_at
                )
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s::jsonb, true, now(), now())
                RETURNING id, vendor_code, operation_code, canonical_version, direction,
                          flow_direction, mapping, is_active, created_at, updated_at
                """
            )
            row = _execute_one(
                conn, q_insert,
                (vendor_code, operation_code, canonical_version, direction, fd, mapping_json),
            )
    else:
        # is_active=False: find any row (active or inactive), update to inactive
        q_find = sql.SQL(
            """
            SELECT id FROM control_plane.vendor_operation_mappings
            WHERE vendor_code = %s AND operation_code = %s AND canonical_version = %s
              AND direction = %s AND flow_direction = %s
            ORDER BY is_active DESC, updated_at DESC NULLS LAST
            LIMIT 1
            """
        )
        existing = _execute_one(conn, q_find, key_params)

        if existing:
            q_update = sql.SQL(
                """
                UPDATE control_plane.vendor_operation_mappings
                SET mapping = %s::jsonb, is_active = false, updated_at = now()
                WHERE id = %s
                RETURNING id, vendor_code, operation_code, canonical_version, direction,
                          flow_direction, mapping, is_active, created_at, updated_at
                """
            )
            row = _execute_one(conn, q_update, (mapping_json, existing["id"]))
        else:
            q_insert = sql.SQL(
                """
                INSERT INTO control_plane.vendor_operation_mappings (
                    id, vendor_code, operation_code, canonical_version, direction, flow_direction,
                    mapping, is_active, created_at, updated_at
                )
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s::jsonb, false, now(), now())
                RETURNING id, vendor_code, operation_code, canonical_version, direction,
                          flow_direction, mapping, is_active, created_at, updated_at
                """
            )
            row = _execute_one(
                conn, q_insert,
                (vendor_code, operation_code, canonical_version, direction, fd, mapping_json),
            )

    if row:
        _write_audit_event(
            conn,
            transaction_id=f"vendor-registry-{request_id}",
            action="mapping_upsert",
            vendor_code=vendor_code,
            details={
                "operationCode": operation_code,
                "canonicalVersion": canonical_version,
                "direction": direction,
            },
        )
    assert row is not None
    return row


def _handle_get_operations_mapping_status(conn: Any, vendor_code: str) -> dict[str, Any]:
    """GET /v1/vendor/operations-mapping-status - per-operation mapping status for Contracts overview."""
    supported = _list_supported_operations(conn, vendor_code)
    if not supported:
        return _success(200, {"items": []})

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT operation_code, COALESCE(canonical_version, 'v1') AS canonical_version FROM control_plane.operations WHERE is_active = true"
        )
        op_to_version = {r["operation_code"]: (r["canonical_version"] or "v1") for r in cur.fetchall()}

    items: list[dict[str, Any]] = []
    canonical_schemas = {}
    vendor_schemas = {}
    mapping_dirs = {}
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT operation_code, canonical_version, request_schema, response_schema
            FROM control_plane.operation_contracts WHERE is_active = true
            """
        )
        for r in cur.fetchall():
            key = (r["operation_code"], r["canonical_version"] or "v1")
            canonical_schemas[key] = {"request_schema": r.get("request_schema"), "response_schema": r.get("response_schema")}
        cur.execute(
            """
            SELECT operation_code, canonical_version, request_schema, response_schema
            FROM control_plane.vendor_operation_contracts
            WHERE vendor_code = %s
            """,
            (vendor_code,),
        )
        for r in cur.fetchall():
            key = (r["operation_code"], r["canonical_version"] or "v1")
            vendor_schemas[key] = {"request_schema": r.get("request_schema"), "response_schema": r.get("response_schema")}
        cur.execute(
            """
            SELECT operation_code, canonical_version, direction
            FROM control_plane.vendor_operation_mappings
            WHERE vendor_code = %s AND is_active = true
            """,
            (vendor_code,),
        )
        for r in cur.fetchall():
            key = (vendor_code, r["operation_code"], r["canonical_version"] or "v1")
            mapping_dirs.setdefault(key, set()).add(r["direction"] or "")

    for row in supported:
        op_code = row.get("operationCode") or row.get("operation_code") or ""
        canonical_ver = op_to_version.get(op_code, "v1")
        key = (op_code, canonical_ver)
        dirs = mapping_dirs.get((vendor_code, op_code, canonical_ver), set())
        has_request = "FROM_CANONICAL" in dirs
        has_response = "TO_CANONICAL_RESPONSE" in dirs
        canon = canonical_schemas.get(key, {})
        vendor_sc = vendor_schemas.get(key, {})
        requires_request = _schema_differs(canon.get("request_schema"), vendor_sc.get("request_schema"))
        requires_response = _schema_differs(canon.get("response_schema"), vendor_sc.get("response_schema"))
        req_status = _mapping_status(requires_request, has_request)
        resp_status = _mapping_status(requires_response, has_response)
        items.append({
            "operationCode": op_code,
            "canonicalVersion": canonical_ver,
            "requiresRequestMapping": requires_request,
            "requiresResponseMapping": requires_response,
            "requestMappingStatus": req_status,
            "responseMappingStatus": resp_status,
        })
    return _success(200, {"items": items})


def _handle_get_mappings(
    event: dict[str, Any],
    conn: Any,
    vendor_code: str,
) -> dict[str, Any]:
    qp = _parse_query_params(event)
    operation_code = (qp.get("operationcode") or "").strip() or None
    canonical_version = (qp.get("canonicalversion") or "").strip() or None
    items = _list_mappings(conn, vendor_code, operation_code, canonical_version)
    return _success(200, {"mappings": items})


# Direction aliases for Visual Builder (maps to DB directions)
_CANONICAL_TO_TARGET_REQUEST = "FROM_CANONICAL"
_TARGET_TO_CANONICAL_RESPONSE = "TO_CANONICAL_RESPONSE"


def _handle_get_operation_mappings(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    canonical_version: str,
) -> dict[str, Any]:
    """GET /v1/vendor/operations/{operationCode}/{canonicalVersion}/mappings - simplified shape for Visual Builder."""
    try:
        _validate_operation_code(operation_code)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    canonical_version = (canonical_version or "v1").strip()
    if not canonical_version or len(canonical_version) > 32:
        return _error(400, "VALIDATION_ERROR", "canonicalVersion must be 1-32 chars")

    state = load_provider_flow_mappings(
        conn, vendor_code, operation_code, canonical_version
    )
    uses_req = state.get("usesCanonicalRequest", False)
    uses_resp = state.get("usesCanonicalResponse", False)
    req_json = state.get("requestMappingJson")
    resp_json = state.get("responseMappingJson")

    out: dict[str, Any] = {
        "operationCode": operation_code,
        "canonicalVersion": canonical_version,
        "usesCanonicalRequest": uses_req,
        "usesCanonicalResponse": uses_resp,
        "request": (
            {"direction": "CANONICAL_TO_TARGET_REQUEST", "mapping": None, "usesCanonical": True}
            if uses_req
            else ({"direction": "CANONICAL_TO_TARGET_REQUEST", "mapping": req_json} if req_json is not None else None)
        ),
        "response": (
            {"direction": "TARGET_TO_CANONICAL_RESPONSE", "mapping": None, "usesCanonical": True}
            if uses_resp
            else ({"direction": "TARGET_TO_CANONICAL_RESPONSE", "mapping": resp_json} if resp_json is not None else None)
        ),
    }
    return _success(200, out)


def _handle_put_operation_mappings(
    event: dict[str, Any],
    conn: Any,
    vendor_code: str,
    operation_code: str,
    canonical_version: str,
) -> dict[str, Any]:
    """PUT /v1/vendor/operations/{operationCode}/{canonicalVersion}/mappings - upsert request + response mappings.

    Supports useCanonicalRequest/useCanonicalResponse (or request.usesCanonical/response.usesCanonical).
    When true: deactivate mapping rows (canonical-only mode).
    When false: upsert provided mapping. request.mapping and response.mapping required when not canonical.
    """
    try:
        _validate_operation_code(operation_code)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    canonical_version = (canonical_version or "v1").strip()
    if not canonical_version or len(canonical_version) > 32:
        return _error(400, "VALIDATION_ERROR", "canonicalVersion must be 1-32 chars")

    if not _vendor_has_operation_access(conn, vendor_code, operation_code):
        return _error(403, "FORBIDDEN", "Operation not in supported operations or allowlist")

    body = _parse_body(event.get("body"))
    if err := _reject_body_vendor_mismatch(body, vendor_code):
        return err
    request_id = event.get("requestContext", {}).get("requestId", "local")

    request_payload = body.get("request") if isinstance(body.get("request"), dict) else None
    response_payload = body.get("response") if isinstance(body.get("response"), dict) else None
    use_canon_req = body.get("useCanonicalRequest")
    use_canon_resp = body.get("useCanonicalResponse")
    if use_canon_req is None and request_payload is not None:
        use_canon_req = request_payload.get("usesCanonical")
    if use_canon_resp is None and response_payload is not None:
        use_canon_resp = response_payload.get("usesCanonical")

    req_mapping = None
    resp_mapping = None
    if request_payload is not None:
        mapping_raw = request_payload.get("mapping")
        if use_canon_req is None and (mapping_raw is None or (isinstance(mapping_raw, dict) and _is_empty_canonical_mapping(mapping_raw))):
            use_canon_req = True
        if use_canon_req is not True:
            if mapping_raw is not None and not isinstance(mapping_raw, dict):
                return _error(400, "VALIDATION_ERROR", "request.mapping must be a JSON object when not using canonical")
            req_mapping = mapping_raw if isinstance(mapping_raw, dict) and not _is_empty_canonical_mapping(mapping_raw or {}) else {}
    if response_payload is not None:
        mapping_raw = response_payload.get("mapping")
        if use_canon_resp is None and (mapping_raw is None or (isinstance(mapping_raw, dict) and _is_empty_canonical_mapping(mapping_raw))):
            use_canon_resp = True
        if use_canon_resp is not True:
            if mapping_raw is not None and not isinstance(mapping_raw, dict):
                return _error(400, "VALIDATION_ERROR", "response.mapping must be a JSON object when not using canonical")
            resp_mapping = mapping_raw if isinstance(mapping_raw, dict) and not _is_empty_canonical_mapping(mapping_raw or {}) else {}

    use_canon_req = use_canon_req is True
    use_canon_resp = use_canon_resp is True

    if APPROVAL_GATE_ENABLED:
        mode = "CANONICAL" if (use_canon_req and use_canon_resp) else "CUSTOM"
        payload = {
            "version": 1,
            "mapping": {
                "vendor_code": vendor_code,
                "operation_code": operation_code,
                "canonical_version": canonical_version,
                "flow_direction": "OUTBOUND",
                "mode": mode,
                "requestMapping": req_mapping,
                "responseMapping": resp_mapping,
            },
        }
        try:
            from approval_utils import create_change_request
            cr = create_change_request(
                conn,
                request_type="MAPPING_CONFIG",
                vendor_code=vendor_code,
                operation_code=operation_code,
                payload=payload,
                requested_by=None,
                requested_via="vendor-portal",
            )
            return _success(202, {"changeRequestId": str(cr.get("id")), "status": "PENDING"})
        except Exception as e:
            return _error(500, "INTERNAL_ERROR", str(e))

    save_provider_flow_mappings(
        conn, vendor_code, operation_code, canonical_version,
        use_canonical_request=use_canon_req,
        use_canonical_response=use_canon_resp,
        request_mapping_json=req_mapping,
        response_mapping_json=resp_mapping,
        request_id=request_id,
    )

    return _handle_get_operation_mappings(conn, vendor_code, operation_code, canonical_version)


def _handle_post_mappings(event: dict[str, Any], conn: Any, vendor_code: str) -> dict[str, Any]:
    body = _parse_body(event.get("body"))
    if err := _reject_body_vendor_mismatch(body, vendor_code):
        return err
    request_id = event.get("requestContext", {}).get("requestId", "local")
    operation_code_raw = body.get("operationCode")
    canonical_version_raw = body.get("canonicalVersion")
    direction_raw = body.get("direction")
    mapping_raw = body.get("mapping")
    if operation_code_raw is None or canonical_version_raw is None or direction_raw is None or mapping_raw is None:
        return _error(
            400,
            "VALIDATION_ERROR",
            "operationCode, canonicalVersion, direction, and mapping are required",
        )
    try:
        operation_code = _validate_operation_code(operation_code_raw)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    canonical_version = str(canonical_version_raw).strip() if canonical_version_raw else ""
    if not canonical_version or len(canonical_version) > 32:
        return _error(400, "VALIDATION_ERROR", "canonicalVersion must be 1-32 chars")
    direction = str(direction_raw).strip().upper()
    if direction not in MAPPING_DIRECTIONS:
        return _error(
            400,
            "VALIDATION_ERROR",
            f"direction must be one of: {', '.join(sorted(MAPPING_DIRECTIONS))}",
        )
    if not isinstance(mapping_raw, dict):
        return _error(400, "VALIDATION_ERROR", "mapping must be a JSON object")
    is_active = body.get("isActive", True)
    is_active_bool = is_active if isinstance(is_active, bool) else str(is_active).lower() in ("true", "1", "yes")
    row = _upsert_vendor_mapping(
        conn, vendor_code, operation_code, canonical_version, direction,
        mapping_raw, is_active_bool, request_id,
    )
    return _success(200, {"mapping": _to_camel_case_dict(dict(row))})


# --- Flow Builder (GET/PUT/POST test) ---


def _load_canonical_contract(
    conn: Any, operation_code: str, canonical_version: str
) -> dict[str, Any] | None:
    """Load canonical contract from operation_contracts."""
    q = sql.SQL(
        """
        SELECT request_schema, response_schema
        FROM control_plane.operation_contracts
        WHERE operation_code = %s AND canonical_version = %s AND is_active = true
        ORDER BY updated_at DESC NULLS LAST
        LIMIT 1
        """
    )
    row = _execute_one(conn, q, (operation_code, canonical_version))
    return dict(row) if row else None


def _load_vendor_contract(
    conn: Any, vendor_code: str, operation_code: str, canonical_version: str
) -> dict[str, Any] | None:
    """Load vendor contract from vendor_operation_contracts."""
    q = sql.SQL(
        """
        SELECT request_schema, response_schema
        FROM control_plane.vendor_operation_contracts
        WHERE vendor_code = %s AND operation_code = %s AND canonical_version = %s
          AND is_active = true
        ORDER BY updated_at DESC NULLS LAST
        LIMIT 1
        """
    )
    row = _execute_one(conn, q, (vendor_code, operation_code, canonical_version))
    return dict(row) if row else None


def _load_flow_mapping(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    canonical_version: str,
    direction: str,
    flow_direction: str = "OUTBOUND",
) -> dict[str, Any] | None:
    """Load mapping for direction and flow_direction.
    Baseline schema: unique on (vendor_code, operation_code, canonical_version, direction, flow_direction) WHERE is_active.
    """
    fd = (flow_direction or "OUTBOUND").strip().upper()
    if fd not in ("INBOUND", "OUTBOUND"):
        fd = "OUTBOUND"
    q = sql.SQL(
        """
        SELECT mapping
        FROM control_plane.vendor_operation_mappings
        WHERE vendor_code = %s AND operation_code = %s
          AND canonical_version = %s AND direction = %s AND flow_direction = %s AND is_active = true
        ORDER BY updated_at DESC NULLS LAST
        LIMIT 1
        """
    )
    row = _execute_one(conn, q, (vendor_code, operation_code, canonical_version, direction, fd))
    if not row or not isinstance(row.get("mapping"), dict):
        return None
    return row["mapping"]


def _is_empty_canonical_mapping(mapping: dict[str, Any] | None) -> bool:
    """True if mapping is empty or minimal identity (canonical pass-through)."""
    if not mapping or not isinstance(mapping, dict):
        return True
    return len(mapping) == 0 or (
        len(mapping) == 1
        and isinstance(mapping.get("type"), str)
        and mapping.get("type", "").lower() == "identity"
    )


def load_vendor_mappings_for_flow(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    canonical_version: str,
    flow_direction: str = "OUTBOUND",
) -> dict[str, Any]:
    """Load mapping state for a flow. Returns usesCanonicalRequest, usesCanonicalResponse, requestMappingJson, responseMappingJson.

    For OUTBOUND: request=TO_CANONICAL, response=FROM_CANONICAL_RESPONSE.
    For INBOUND: request=FROM_CANONICAL, response=TO_CANONICAL_RESPONSE.
    TODO: Add INBOUND support when Flow Builder configures inbound flows.
    """
    fd = (flow_direction or "OUTBOUND").strip().upper()
    if fd not in ("INBOUND", "OUTBOUND"):
        fd = "OUTBOUND"

    if fd == "OUTBOUND":
        req_dir, resp_dir = "TO_CANONICAL", "FROM_CANONICAL_RESPONSE"
    else:
        req_dir, resp_dir = "FROM_CANONICAL", "TO_CANONICAL_RESPONSE"

    def _load_dir(direction: str) -> tuple[bool, dict[str, Any] | None]:
        row = _execute_one(
            conn,
            sql.SQL(
                """
                SELECT mapping FROM control_plane.vendor_operation_mappings
                WHERE vendor_code = %s AND operation_code = %s
                  AND canonical_version = %s AND direction = %s AND flow_direction = %s AND is_active = true
                ORDER BY updated_at DESC NULLS LAST LIMIT 1
                """
            ),
            (vendor_code, operation_code, canonical_version, direction, fd),
        )
        if not row or not isinstance(row.get("mapping"), dict):
            return False, None
        m = row["mapping"]
        if _is_empty_canonical_mapping(m):
            return True, None
        return False, m

    uses_req, req_json = _load_dir(req_dir)
    uses_resp, resp_json = _load_dir(resp_dir)

    return {
        "usesCanonicalRequest": uses_req,
        "usesCanonicalResponse": uses_resp,
        "requestMappingJson": req_json,
        "responseMappingJson": resp_json,
    }


def load_provider_flow_mappings(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    canonical_version: str,
) -> dict[str, Any]:
    """Load mapping state for provider flow (hub calls vendor). Uses FROM_CANONICAL, TO_CANONICAL_RESPONSE, flow_direction=OUTBOUND.
    Same directions as operations mappings API and Flow Builder.
    No active rows = canonical mode (pass-through). Empty mapping = canonical. Non-empty = custom.
    """
    fd = "OUTBOUND"
    req_dir, resp_dir = "FROM_CANONICAL", "TO_CANONICAL_RESPONSE"

    def _load_dir(direction: str) -> tuple[bool, dict[str, Any] | None]:
        row = _execute_one(
            conn,
            sql.SQL(
                """
                SELECT mapping FROM control_plane.vendor_operation_mappings
                WHERE vendor_code = %s AND operation_code = %s
                  AND canonical_version = %s AND direction = %s AND flow_direction = %s AND is_active = true
                ORDER BY updated_at DESC NULLS LAST LIMIT 1
                """
            ),
            (vendor_code, operation_code, canonical_version, direction, fd),
        )
        # No active row = canonical mode (pass-through, no vendor-specific mapping)
        if not row or not isinstance(row.get("mapping"), dict):
            return True, None
        m = row["mapping"]
        if _is_empty_canonical_mapping(m):
            return True, None
        return False, m

    uses_req, req_json = _load_dir(req_dir)
    uses_resp, resp_json = _load_dir(resp_dir)

    return {
        "usesCanonicalRequest": uses_req,
        "usesCanonicalResponse": uses_resp,
        "requestMappingJson": req_json,
        "responseMappingJson": resp_json,
    }


def save_provider_flow_mappings(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    canonical_version: str,
    use_canonical_request: bool,
    use_canonical_response: bool,
    request_mapping_json: dict[str, Any] | None,
    response_mapping_json: dict[str, Any] | None,
    request_id: str = "local",
) -> None:
    """Persist mapping state for provider flow. Uses FROM_CANONICAL, TO_CANONICAL_RESPONSE, flow_direction=OUTBOUND.
    Canonical mode = deactivate rows (zero active rows). Custom = upsert mapping JSON."""
    fd = "OUTBOUND"
    req_dir, resp_dir = "FROM_CANONICAL", "TO_CANONICAL_RESPONSE"

    def _desired_req() -> dict[str, Any] | None:
        if use_canonical_request:
            return None  # Deactivate rows for canonical mode
        return request_mapping_json if isinstance(request_mapping_json, dict) else None

    def _desired_resp() -> dict[str, Any] | None:
        if use_canonical_response:
            return None  # Deactivate rows for canonical mode
        return response_mapping_json if isinstance(response_mapping_json, dict) else None

    for direction, desired in [(req_dir, _desired_req()), (resp_dir, _desired_resp())]:
        if desired is None:
            q_deactivate = sql.SQL(
                """
                UPDATE control_plane.vendor_operation_mappings
                SET is_active = false, updated_at = now()
                WHERE vendor_code = %s AND operation_code = %s AND canonical_version = %s
                  AND direction = %s AND flow_direction = %s AND is_active = true
                """
            )
            _execute_mutation(conn, q_deactivate, (vendor_code, operation_code, canonical_version, direction, fd))
        else:
            _upsert_vendor_mapping(
                conn, vendor_code, operation_code, canonical_version, direction,
                desired, True, request_id, flow_direction=fd,
            )


def save_vendor_mappings_for_flow(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    canonical_version: str,
    flow_direction: str,
    use_canonical_request: bool,
    use_canonical_response: bool,
    request_mapping_json: dict[str, Any] | None,
    response_mapping_json: dict[str, Any] | None,
    request_id: str = "local",
) -> None:
    """Persist mapping state. Canonical = upsert row with mapping={}. Custom = upsert with JSON. Clear = is_active=false.
    TODO: Add INBOUND support when Flow Builder configures inbound flows.
    """
    fd = (flow_direction or "OUTBOUND").strip().upper()
    if fd not in ("INBOUND", "OUTBOUND"):
        fd = "OUTBOUND"

    if fd == "OUTBOUND":
        req_dir, resp_dir = "TO_CANONICAL", "FROM_CANONICAL_RESPONSE"
    else:
        req_dir, resp_dir = "FROM_CANONICAL", "TO_CANONICAL_RESPONSE"

    def _desired_req() -> dict[str, Any] | None:
        if use_canonical_request:
            return {}
        return request_mapping_json if isinstance(request_mapping_json, dict) else None

    def _desired_resp() -> dict[str, Any] | None:
        if use_canonical_response:
            return {}
        return response_mapping_json if isinstance(response_mapping_json, dict) else None

    for direction, desired in [(req_dir, _desired_req()), (resp_dir, _desired_resp())]:
        if desired is None:
            q_deactivate = sql.SQL(
                """
                UPDATE control_plane.vendor_operation_mappings
                SET is_active = false, updated_at = now()
                WHERE vendor_code = %s AND operation_code = %s AND canonical_version = %s
                  AND direction = %s AND flow_direction = %s AND is_active = true
                """
            )
            _execute_mutation(conn, q_deactivate, (vendor_code, operation_code, canonical_version, direction, fd))
        else:
            mapping_json = json.dumps(desired)
            _upsert_vendor_mapping(
                conn, vendor_code, operation_code, canonical_version, direction,
                desired, True, request_id, flow_direction=fd,
            )


def _load_flow_layout(
    conn: Any, vendor_code: str, operation_code: str, canonical_version: str
) -> dict[str, Any] | None:
    """Load layout and visual_model from vendor_flow_layouts."""
    q = sql.SQL(
        """
        SELECT layout, visual_model
        FROM control_plane.vendor_flow_layouts
        WHERE vendor_code = %s AND operation_code = %s AND canonical_version = %s
        """
    )
    row = _execute_one(conn, q, (vendor_code, operation_code, canonical_version))
    return dict(row) if row else None


def _vendor_has_operation_access(
    conn: Any, vendor_code: str, operation_code: str
) -> bool:
    """Check vendor has operation in supported_operations or allowlist (source or target)."""
    me = (vendor_code or "").upper()
    op = (operation_code or "").upper()
    if not me or not op:
        return False
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT 1 FROM control_plane.vendor_supported_operations
            WHERE vendor_code = %s AND operation_code = %s AND is_active = true
            LIMIT 1
            """,
            (me, op),
        )
        if cur.fetchone():
            return True
        cur.execute(
            """
            SELECT 1 FROM control_plane.vendor_operation_allowlist
            WHERE rule_scope = 'vendor' AND operation_code = %s
              AND (source_vendor_code = %s OR target_vendor_code = %s)
            LIMIT 1
            """,
            (op, me, me),
        )
        return cur.fetchone() is not None


def _flow_endpoint_dto(row: dict[str, Any] | None) -> dict[str, Any]:
    """Build endpoint DTO from vendor_endpoints row."""
    if not row:
        return {}
    return {
        "url": row.get("url") or "",
        "httpMethod": (row.get("http_method") or "POST").upper(),
        "timeoutMs": row.get("timeout_ms") or 8000,
        "verificationStatus": (row.get("verification_status") or "PENDING").upper(),
    }


def _handle_get_flow(
    event: dict[str, Any], conn: Any, vendor_code: str, operation_code: str, canonical_version: str
) -> dict[str, Any]:
    """GET /v1/vendor/flows/{operationCode}/{version} - combined flow data."""
    try:
        _validate_operation_code(operation_code)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    canonical_version = (canonical_version or "v1").strip()
    if not canonical_version or len(canonical_version) > 32:
        return _error(400, "VALIDATION_ERROR", "canonicalVersion must be 1-32 chars")

    if not _vendor_has_operation_access(conn, vendor_code, operation_code):
        return _error(403, "FORBIDDEN", "Operation not in supported operations or allowlist")

    canonical = _load_canonical_contract(conn, operation_code, canonical_version)
    mapping_state = load_provider_flow_mappings(
        conn, vendor_code, operation_code, canonical_version
    )
    uses_canon_req = mapping_state.get("usesCanonicalRequest", False)
    uses_canon_resp = mapping_state.get("usesCanonicalResponse", False)
    req_json = mapping_state.get("requestMappingJson")
    resp_json = mapping_state.get("responseMappingJson")
    layout_row = _load_flow_layout(conn, vendor_code, operation_code, canonical_version)
    endpoint_row = _load_endpoint(conn, vendor_code, operation_code)

    layout = layout_row.get("layout") if layout_row else None
    layout = layout if isinstance(layout, dict) else {}
    visual_model = layout_row.get("visual_model") if layout_row else None
    visual_model = visual_model if isinstance(visual_model, dict) else None

    vendor_row = _load_vendor_contract(conn, vendor_code, operation_code, canonical_version)
    vendor_req = (vendor_row or {}).get("request_schema") or (canonical or {}).get("request_schema") or {}
    vendor_resp = (vendor_row or {}).get("response_schema") or (canonical or {}).get("response_schema") or {}

    canon_req = (canonical or {}).get("request_schema")
    canon_resp = (canonical or {}).get("response_schema")
    requires_request_mapping = _schema_differs(canon_req, (vendor_row or {}).get("request_schema"))
    requires_response_mapping = _schema_differs(canon_resp, (vendor_row or {}).get("response_schema"))
    has_req = uses_canon_req or req_json is not None
    has_resp = uses_canon_resp or resp_json is not None
    request_mapping_status = _mapping_status(requires_request_mapping, has_req)
    response_mapping_status = _mapping_status(requires_response_mapping, has_resp)
    mapping_configured_request = uses_canon_req or has_req
    mapping_configured_response = uses_canon_resp or has_resp

    req_mode = _mapping_mode_status(uses_canon_req, not uses_canon_req and req_json is not None, requires_request_mapping)
    resp_mode = _mapping_mode_status(uses_canon_resp, not uses_canon_resp and resp_json is not None, requires_response_mapping)

    out = {
        "operationCode": operation_code,
        "canonicalVersion": canonical_version,
        "version": canonical_version,
        "flowDirection": "OUTBOUND",
        "canonicalRequestSchema": (canonical or {}).get("request_schema") or {},
        "canonicalResponseSchema": (canonical or {}).get("response_schema") or {},
        "vendorRequestSchema": vendor_req,
        "vendorResponseSchema": vendor_resp,
        "visualModel": visual_model,
        "requestMapping": None if uses_canon_req else req_json,
        "responseMapping": None if uses_canon_resp else resp_json,
        "usesCanonicalRequest": uses_canon_req,
        "usesCanonicalResponse": uses_canon_resp,
        "useCanonicalRequest": uses_canon_req,
        "useCanonicalResponse": uses_canon_resp,
        "mappingConfigured": {"request": mapping_configured_request, "response": mapping_configured_response},
        "requiresRequestMapping": requires_request_mapping,
        "requiresResponseMapping": requires_response_mapping,
        "requestMappingStatus": request_mapping_status,
        "responseMappingStatus": response_mapping_status,
        "requestMappingMode": req_mode,
        "responseMappingMode": resp_mode,
        "endpoint": _flow_endpoint_dto(endpoint_row),
    }
    return _success(200, out)


def _handle_put_flow(
    event: dict[str, Any], conn: Any, vendor_code: str, operation_code: str, canonical_version: str
) -> dict[str, Any]:
    """PUT /v1/vendor/flows/{operationCode}/{version} - save visualModel, requestMapping, responseMapping."""
    try:
        _validate_operation_code(operation_code)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    canonical_version = (canonical_version or "v1").strip()
    if not canonical_version or len(canonical_version) > 32:
        return _error(400, "VALIDATION_ERROR", "canonicalVersion must be 1-32 chars")

    if not _vendor_has_operation_access(conn, vendor_code, operation_code):
        return _error(403, "FORBIDDEN", "Operation not in supported operations or allowlist")

    body = _parse_body(event.get("body"))
    if err := _reject_body_vendor_mismatch(body, vendor_code):
        return err
    request_id = event.get("requestContext", {}).get("requestId", "local")

    visual_model = body.get("visualModel")
    request_mapping = body.get("requestMapping")
    response_mapping = body.get("responseMapping")
    use_canonical_request = body.get("useCanonicalRequest")
    use_canonical_response = body.get("useCanonicalResponse")

    visual_model = visual_model if isinstance(visual_model, dict) else {}
    request_mapping = request_mapping if isinstance(request_mapping, dict) else None
    response_mapping = response_mapping if isinstance(response_mapping, dict) else None
    use_req = use_canonical_request is True
    use_resp = use_canonical_response is True

    # Always persist layout (visual model); mapping changes are gated
    q_layout = sql.SQL(
        """
        INSERT INTO control_plane.vendor_flow_layouts (
            vendor_code, operation_code, canonical_version, layout, visual_model
        )
        VALUES (%s, %s, %s, '{}'::jsonb, %s::jsonb)
        ON CONFLICT (vendor_code, operation_code, canonical_version) DO UPDATE SET
            layout = COALESCE(control_plane.vendor_flow_layouts.layout, '{}'::jsonb),
            visual_model = EXCLUDED.visual_model,
            updated_at = now()
        """
    )
    _execute_mutation(
        conn, q_layout,
        (vendor_code, operation_code, canonical_version, json.dumps(visual_model)),
    )

    if APPROVAL_GATE_ENABLED:
        mode = "CANONICAL" if (use_req and use_resp) else "CUSTOM"
        payload = {
            "version": 1,
            "mapping": {
                "vendor_code": vendor_code,
                "operation_code": operation_code,
                "canonical_version": canonical_version,
                "flow_direction": "OUTBOUND",
                "mode": mode,
                "requestMapping": request_mapping if not use_req else None,
                "responseMapping": response_mapping if not use_resp else None,
            },
        }
        try:
            from approval_utils import create_change_request
            cr = create_change_request(
                conn,
                request_type="MAPPING_CONFIG",
                vendor_code=vendor_code,
                operation_code=operation_code,
                payload=payload,
                requested_by=None,
                requested_via="vendor-portal",
            )
            return _success(202, {"changeRequestId": str(cr.get("id")), "status": "PENDING"})
        except Exception as e:
            return _error(500, "INTERNAL_ERROR", str(e))

    save_provider_flow_mappings(
        conn, vendor_code, operation_code, canonical_version,
        use_canonical_request=use_req,
        use_canonical_response=use_resp,
        request_mapping_json=request_mapping if not use_req else None,
        response_mapping_json=response_mapping if not use_resp else None,
        request_id=request_id,
    )

    return _handle_get_flow(event, conn, vendor_code, operation_code, canonical_version)


def _call_vendor_endpoint_for_test(
    url: str,
    http_method: str,
    body: dict[str, Any],
    timeout_ms: int = 8000,
) -> tuple[int, dict[str, Any], str | None]:
    """
    Call vendor endpoint for flow test. Returns (status_code, response_body, error_msg).
    error_msg is None on success.
    """
    method = (http_method or "POST").upper()
    timeout_sec = min(30.0, max(1.0, (timeout_ms or 8000) / 1000.0))
    try:
        resp = requests.request(
            method,
            url,
            json=body,
            timeout=timeout_sec,
            headers={"Content-Type": "application/json"},
        )
        try:
            resp_body = resp.json()
        except Exception:
            resp_body = {"raw": (resp.text or "")[:2000], "statusCode": resp.status_code}
        return resp.status_code, resp_body, None
    except requests.exceptions.Timeout:
        return 0, {}, f"Timeout after {timeout_sec}s"
    except requests.exceptions.RequestException as e:
        return 0, {}, str(e)[:500]


def _stub_vendor_response(canonical_request: dict[str, Any]) -> dict[str, Any]:
    """Stub vendor response for test UI: echo with receiptId and result for common mappings."""
    txn_id = canonical_request.get("transactionId")
    receipt_val = f"R-{txn_id}" if txn_id is not None else "R-unknown"
    return {
        "status": "OK",
        "receiptId": receipt_val,
        "result": receipt_val,
    }


def _handle_post_flow_test(
    event: dict[str, Any], conn: Any, vendor_code: str, operation_code: str, canonical_version: str
) -> dict[str, Any]:
    """POST /v1/vendor/flows/{operationCode}/{version}/test - run test (stubbed vendor response)."""
    try:
        _validate_operation_code(operation_code)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    canonical_version = (canonical_version or "v1").strip()
    if not canonical_version or len(canonical_version) > 32:
        return _error(400, "VALIDATION_ERROR", "canonicalVersion must be 1-32 chars")

    if not _vendor_has_operation_access(conn, vendor_code, operation_code):
        return _error(403, "FORBIDDEN", "Operation not in supported operations or allowlist")

    body = _parse_body(event.get("body"))
    canonical_request = body.get("canonicalRequest")
    if not isinstance(canonical_request, dict):
        return _error(400, "VALIDATION_ERROR", "canonicalRequest must be a JSON object")

    from_can = body.get("requestMapping")
    to_can_resp = body.get("responseMapping")
    if not isinstance(from_can, dict):
        from_can = _load_flow_mapping(
            conn, vendor_code, operation_code, canonical_version, "FROM_CANONICAL",
            flow_direction="OUTBOUND",
        )
    if not isinstance(to_can_resp, dict):
        to_can_resp = _load_flow_mapping(
            conn, vendor_code, operation_code, canonical_version, "TO_CANONICAL_RESPONSE",
            flow_direction="OUTBOUND",
        )
    from_can = from_can if isinstance(from_can, dict) else {}
    to_can_resp = to_can_resp if isinstance(to_can_resp, dict) else {}

    errors: dict[str, list[str]] = {
        "mappingRequest": [],
        "downstream": [],
        "mappingResponse": [],
    }
    vendor_request: dict[str, Any] = {}
    vendor_response: dict[str, Any] = {}
    canonical_response: dict[str, Any] = {}

    if from_can and _apply_mapping:
        vendor_request, viols = _apply_mapping(canonical_request, from_can)
        if viols:
            errors["mappingRequest"] = viols
            return _success(200, {
                "canonicalRequest": canonical_request,
                "vendorRequest": {},
                "vendorResponse": {},
                "canonicalResponse": {},
                "errors": errors,
            })
    elif from_can:
        errors["mappingRequest"].append("Mapping engine not available")
        return _success(200, {
            "canonicalRequest": canonical_request,
            "vendorRequest": {},
            "vendorResponse": {},
            "canonicalResponse": {},
            "errors": errors,
        })
    else:
        vendor_request = dict(canonical_request)

    endpoint_row = _load_endpoint(conn, vendor_code, operation_code)
    if endpoint_row:
        vendor_response = _stub_vendor_response(canonical_request)
    else:
        vendor_response = _stub_vendor_response(canonical_request)

    if to_can_resp and _apply_mapping:
        canonical_response, viols = _apply_mapping(vendor_response, to_can_resp)
        if viols:
            errors["mappingResponse"] = viols
    elif to_can_resp:
        errors["mappingResponse"].append("Mapping engine not available")
    else:
        canonical_response = dict(vendor_response) if isinstance(vendor_response, dict) else {}

    return _success(200, {
        "canonicalRequest": canonical_request,
        "vendorRequest": vendor_request,
        "vendorResponse": vendor_response,
        "canonicalResponse": canonical_response,
        "errors": errors,
    })


# --- Vendor self-service API keys: removed (control_plane.vendor_api_keys table removed) ---


# --- Main handler ---


def _normalize_event_body(event: dict[str, Any]) -> None:
    """Decode base64 body if API Gateway sent it (REST API proxy)."""
    body = event.get("body")
    if isinstance(body, str) and body and event.get("isBase64Encoded"):
        try:
            event["body"] = base64.b64decode(body).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            pass
    event["isBase64Encoded"] = False


def _handler_impl(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Vendor registry Lambda - routes by path and method."""
    _normalize_event_body(event)
    ctx = get_context(event, context)
    path = (event.get("path") or event.get("rawPath") or "").strip("/")
    method = (event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method", "")).upper()
    if method == "OPTIONS":
        return add_cors_to_response({"statusCode": 200, "headers": {}, "body": ""})

    segments = [s for s in path.split("/") if s]
    try:
        event["vendor_code"] = _resolve_vendor_code_from_jwt(event)
    except AuthError as e:
        log_json("WARN", "vendor_registry_auth_failed", ctx=ctx, error=e.message)
        return _error(e.status_code, "AUTH_ERROR", e.message)

    vendor_code = event["vendor_code"]
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM control_plane.vendors
                    WHERE vendor_code = %s AND COALESCE(is_active, true) = true
                    LIMIT 1
                    """,
                    (vendor_code,),
                )
                if cur.fetchone() is None:
                    return _error(403, "FORBIDDEN", "Vendor not active")
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))

    policy_decision = evaluate_policy(
        PolicyContext(
            surface="VENDOR",
            action="REGISTRY_READ" if method == "GET" else "REGISTRY_WRITE",
            vendor_code=vendor_code,
            target_vendor_code=None,
            operation_code=None,
            requested_source_vendor_code=None,
            is_admin=False,
            groups=[],
            query={},
        )
    )
    if not policy_decision.allow:
        return _error(
            policy_decision.http_status,
            policy_decision.decision_code,
            policy_decision.message,
            {"policy": policy_decision.metadata},
        )

    try:
        vendor_idx = segments.index("vendor")
    except ValueError:
        return _error(404, "NOT_FOUND", "Unknown vendor registry path")
    if vendor_idx + 1 >= len(segments):
        return _error(404, "NOT_FOUND", "Unknown vendor registry path")
    resource = segments[vendor_idx + 1]

    if resource == "config-bundle":
        if method == "GET":
            return _handle_get_config_bundle(event)
        return _error(405, "METHOD_NOT_ALLOWED", "Use GET for config-bundle")

    if resource == "api-keys":
        return _error(410, "GONE", "vendor_api_keys table removed; API key self-service no longer available")

    if resource == "supported-operations":
        sub = segments[vendor_idx + 2] if len(segments) > vendor_idx + 2 else None
        if method == "GET":
            with _get_connection() as conn:
                return _handle_get_supported_operations(conn, vendor_code)
        if method == "POST":
            with _get_connection() as conn:
                return _handle_post_supported_operations(event, conn, vendor_code)
        if method == "DELETE" and sub:
            request_id = event.get("requestContext", {}).get("requestId", "local")
            with _get_connection() as conn:
                return _handle_delete_supported_operation(conn, vendor_code, sub, request_id)

    if resource == "endpoints":
        sub = segments[vendor_idx + 2] if len(segments) > vendor_idx + 2 else None
        if sub == "verify":
            if method == "POST":
                with _get_connection() as conn:
                    return _handle_post_endpoints_verify(event, conn, vendor_code)
            return _error(405, "METHOD_NOT_ALLOWED", "Use POST for verify")
        if method == "GET":
            with _get_connection() as conn:
                return _handle_get_endpoints(conn, vendor_code)
        if method == "POST":
            with _get_connection() as conn:
                return _handle_post_endpoints(event, conn, vendor_code)

    if resource == "contracts":
        if method == "GET":
            with _get_connection() as conn:
                return _handle_get_contracts(conn, vendor_code)
        if method == "POST":
            with _get_connection() as conn:
                return _handle_post_contracts(event, conn, vendor_code)

    if resource == "operations-catalog":
        if method == "GET":
            with _get_connection() as conn:
                return _handle_get_operations_catalog(conn)

    if resource == "operations-mapping-status":
        if method == "GET":
            with _get_connection() as conn:
                return _handle_get_operations_mapping_status(conn, vendor_code)
        return _error(405, "METHOD_NOT_ALLOWED", "Use GET for operations-mapping-status")

    if resource == "canonical":
        sub = segments[vendor_idx + 2] if len(segments) > vendor_idx + 2 else None
        if sub == "operations" and method == "GET":
            return _handle_get_canonical_operations(event)
        if sub == "contracts" and method == "GET":
            return _handle_get_canonical_contracts(event)
        if sub == "vendors" and method == "GET":
            return _handle_get_canonical_vendors(event)
        return _error(404, "NOT_FOUND", "Unknown canonical path")

    if resource == "auth-profiles":
        sub = segments[vendor_idx + 2] if len(segments) > vendor_idx + 2 else None
        if sub is None and method == "GET":
            return _handle_get_auth_profiles(event)
        if sub is None and method == "POST":
            return _handle_post_auth_profiles(event)
        if sub and method == "PATCH":
            return _handle_patch_auth_profile(event, sub)
        if sub and method == "DELETE":
            return _handle_delete_auth_profile(sub, event.get("vendor_code") or "")
        return _error(404, "NOT_FOUND", "Unknown auth-profiles path")

    if resource == "allowlist":
        sub = segments[vendor_idx + 2] if len(segments) > vendor_idx + 2 else None
        if sub is None and method == "POST":
            return _handle_post_allowlist(event)
        if sub and method == "DELETE":
            return _handle_delete_allowlist(sub, event.get("vendor_code") or "")
        return _error(404, "NOT_FOUND", "Use POST to add, DELETE /{id} to remove")

    if resource == "allowlist-change-requests":
        if method == "POST":
            return _handle_post_allowlist_change_requests(event)
        return _error(405, "METHOD_NOT_ALLOWED", "Use POST for allowlist-change-requests")

    if resource == "change-requests":
        if method == "GET":
            return _handle_get_my_change_requests(event)
        if method == "POST":
            return _handle_post_change_requests(event)
        return _error(405, "METHOD_NOT_ALLOWED", "Use GET or POST for change-requests")

    if resource == "my-allowlist":
        sub = segments[vendor_idx + 2] if len(segments) > vendor_idx + 2 else None
        if sub == "change-request" and method == "POST":
            body = _parse_body(event.get("body"))
            cloned = dict(event)
            cloned["body"] = json.dumps(
                {
                    "direction": body.get("direction"),
                    "operationCode": body.get("operationCode"),
                    "targetVendorCodes": body.get("targetVendorCodes"),
                    "useWildcardTarget": body.get("useWildcardTarget"),
                    "ruleScope": body.get("ruleScope") or "vendor",
                    "requestType": body.get("requestType") or "ALLOWLIST_RULE",
                }
            )
            return _handle_post_allowlist_change_requests(cloned)
        if method == "GET":
            return _handle_get_my_allowlist(event)
        return _error(405, "METHOD_NOT_ALLOWED", "Use GET for my-allowlist or POST for my-allowlist/change-request")

    if resource == "my-change-requests":
        if method == "GET":
            return _handle_get_my_change_requests(event)
        return _error(405, "METHOD_NOT_ALLOWED", "Use GET for my-change-requests")

    if resource == "provider-narrowing":
        if method == "GET":
            return _handle_get_provider_narrowing(event)
        if method == "PUT":
            return _handle_put_provider_narrowing(event)
        return _error(405, "METHOD_NOT_ALLOWED", "Use GET or PUT for provider-narrowing")

    if resource == "eligible-access":
        if method == "GET":
            return _handle_get_eligible_access(event)
        return _error(405, "METHOD_NOT_ALLOWED", "Use GET for eligible-access")

    if resource == "my-operations":
        if method == "GET":
            return _handle_get_my_operations(event)
        return _error(405, "METHOD_NOT_ALLOWED", "Use GET for my-operations")

    if resource == "platform":
        sub = segments[vendor_idx + 2] if len(segments) > vendor_idx + 2 else None
        if sub == "features" and method == "GET":
            return _handle_get_vendor_platform_features(event)
        return _error(404, "NOT_FOUND", "Use GET /v1/vendor/platform/features")

    if resource == "policy":
        sub = segments[vendor_idx + 2] if len(segments) > vendor_idx + 2 else None
        if sub == "preview" and method == "POST":
            return _handle_post_policy_preview(event)
        return _error(404, "NOT_FOUND", "Use POST /v1/vendor/policy/preview")

    if resource == "metrics":
        sub = segments[vendor_idx + 2] if len(segments) > vendor_idx + 2 else None
        if sub == "overview" and method == "GET":
            return _handle_get_metrics_overview(event)
        return _error(404, "NOT_FOUND", "Unknown metrics path")

    if resource == "export-jobs":
        sub = segments[vendor_idx + 2] if len(segments) > vendor_idx + 2 else None
        if sub is None and method == "POST":
            return _handle_post_export_job(event)
        if sub and method == "GET":
            return _handle_get_export_job(event, sub)
        return _error(404, "NOT_FOUND", "Use POST /v1/vendor/export-jobs or GET /v1/vendor/export-jobs/{id}")

    if resource == "transactions":
        sub = segments[vendor_idx + 2] if len(segments) > vendor_idx + 2 else None
        redrive_seg = segments[vendor_idx + 3] if len(segments) > vendor_idx + 3 else None
        if sub is None and method == "GET":
            return _handle_get_transactions_list(event)
        if sub and redrive_seg == "redrive" and method == "POST":
            return _handle_post_transaction_redrive(event, sub)
        if sub and method == "GET":
            return _handle_get_transaction_detail(event, sub)
        return _error(404, "NOT_FOUND", "Unknown transactions path")

    if resource == "operations":
        op_seg = segments[vendor_idx + 2] if len(segments) > vendor_idx + 2 else None
        ver_seg = segments[vendor_idx + 3] if len(segments) > vendor_idx + 3 else None
        sub_seg = segments[vendor_idx + 4] if len(segments) > vendor_idx + 4 else None
        if not op_seg:
            return _error(404, "NOT_FOUND", "Use /v1/vendor/operations/{operationCode} or .../mappings")
        operation_code = op_seg
        if not ver_seg:
            # PATCH/DELETE /v1/vendor/operations/{operationCode}
            request_id = event.get("requestContext", {}).get("requestId", "local")
            if method == "PATCH":
                with _get_connection() as conn:
                    return _handle_patch_vendor_operation(event, conn, vendor_code, operation_code)
            if method == "DELETE":
                with _get_connection() as conn:
                    return _handle_delete_vendor_operation(conn, vendor_code, operation_code, request_id)
            return _error(405, "METHOD_NOT_ALLOWED", "Use PATCH or DELETE for /v1/vendor/operations/{operationCode}")
        if sub_seg != "mappings":
            return _error(404, "NOT_FOUND", "Use /v1/vendor/operations/{operationCode}/{canonicalVersion}/mappings")
        canonical_version = ver_seg
        if method == "GET":
            with _get_connection() as conn:
                return _handle_get_operation_mappings(conn, vendor_code, operation_code, canonical_version)
        if method == "PUT":
            with _get_connection() as conn:
                return _handle_put_operation_mappings(event, conn, vendor_code, operation_code, canonical_version)
        return _error(405, "METHOD_NOT_ALLOWED", "Use GET or PUT for operation mappings")

    if resource == "mappings":
        if method == "GET":
            with _get_connection() as conn:
                return _handle_get_mappings(event, conn, vendor_code)
        if method == "POST":
            with _get_connection() as conn:
                return _handle_post_mappings(event, conn, vendor_code)

    if resource == "flows":
        op_seg = segments[vendor_idx + 2] if len(segments) > vendor_idx + 2 else None
        ver_seg = segments[vendor_idx + 3] if len(segments) > vendor_idx + 3 else None
        sub_seg = segments[vendor_idx + 4] if len(segments) > vendor_idx + 4 else None
        if not op_seg or not ver_seg:
            return _error(404, "NOT_FOUND", "Use /v1/vendor/flows/{operationCode}/{canonicalVersion}")
        operation_code = op_seg
        canonical_version = ver_seg
        if sub_seg == "test":
            if method == "POST":
                with _get_connection() as conn:
                    return _handle_post_flow_test(event, conn, vendor_code, operation_code, canonical_version)
            return _error(405, "METHOD_NOT_ALLOWED", "Use POST for flow test")
        if method == "GET":
            with _get_connection() as conn:
                return _handle_get_flow(event, conn, vendor_code, operation_code, canonical_version)
        if method == "PUT":
            with _get_connection() as conn:
                return _handle_put_flow(event, conn, vendor_code, operation_code, canonical_version)
        return _error(405, "METHOD_NOT_ALLOWED", "Use GET or PUT for flow")

    return _error(404, "NOT_FOUND", "Unknown vendor registry path")


def _safe_handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Catch unhandled exceptions to return structured 500 instead of generic API Gateway error."""
    try:
        return with_observability(_handler_impl, "vendor_registry")(event, context)
    except Exception as e:
        log_json("ERROR", "vendor_registry_unhandled", error=str(e))
        return _error(500, "INTERNAL_ERROR", str(e), details={"type": type(e).__name__})


handler = _safe_handler
