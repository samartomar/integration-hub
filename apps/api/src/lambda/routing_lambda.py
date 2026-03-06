"""Routing Lambda - strict structure with control plane validation and downstream call."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.parse
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

import psycopg2
import psycopg2.errors
import requests
from psycopg2.extras import Json, RealDictCursor

from admin_guard import require_admin_secret
from canonical_error import (
    ErrorCode,
    allowlist_denied,
    allowlist_vendor_denied,
    auth_error,
    build_error,
    contract_not_found,
    db_error,
    endpoint_not_found,
    downstream_connection_error,
    downstream_http_error,
    downstream_http_error_response_body,
    downstream_invalid_response,
    downstream_timeout,
    endpoint_not_verified,
    forbidden,
    in_flight_error,
    internal_error,
    invalid_json,
    mapping_failed,
    mapping_not_found,
    operation_not_found,
    schema_validation_failed,
    to_response_body,
    vendor_not_found,
)
from cors import add_cors_to_response
from http_body_utils import (
    DEFAULT_MAX_BINARY_BYTES,
    PayloadFormatError,
    build_http_request_body_and_headers,
)
from observability import emit_metric, get_context, get_context_from_parsed, get_current_ctx, log_json, with_observability
from mapping_constants import FROM_CANONICAL_RESPONSE, TO_CANONICAL_REQUEST
from routing.transform import apply_mapping
from policy_engine import PolicyContext, evaluate_policy
from jwt_auth import (
    JwtValidationError,
    load_jwt_auth_config_from_env,
    validate_jwt_and_map_vendor,
)
from vendor_identity import VendorAuthError, VendorForbiddenError, resolve_vendor_code

try:
    from aws_xray_sdk.core import xray_recorder
except ImportError:
    xray_recorder = None  # type: ignore[assignment]

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]


def _xray_subsegment(name: str):
    """Context manager for X-Ray subsegment. No-op if xray_recorder unavailable."""
    if xray_recorder is None:
        from contextlib import nullcontext
        return nullcontext()
    return xray_recorder.in_subsegment(name)

MIN_DOWNSTREAM_TIMEOUT_SEC = 5
MAX_DOWNSTREAM_TIMEOUT_SEC = 10

FAILURE_STATUSES: frozenset[str] = frozenset({
    "failed",
    "validation_failed",
    "mapping_failed",
    "db_error",
    "internal_error",
    "downstream_error",
    "downstream_failed",
})


class EndpointNotVerifiedError(Exception):
    """Raised when vendor endpoint verification_status is not VERIFIED."""


class OAuthTokenFetchError(Exception):
    """Raised when OAuth2 token fetch fails. Holds canonical error dict for API response."""

    def __init__(self, canonical_error: dict[str, Any]) -> None:
        self.canonical_error = canonical_error
        super().__init__(canonical_error.get("message", "OAuth token fetch failed"))


# --- DB connection (psycopg2 + Secrets Manager) ---


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
    response = client.get_secret_value(SecretId=secret_arn)
    raw = json.loads(response["SecretString"])
    user = raw.get("username") or raw.get("user")
    password = raw["password"]
    host = raw["host"]
    port = str(raw.get("port", 5432))
    dbname = raw.get("dbname") or raw.get("database", "integrationhub")
    password_enc = urllib.parse.quote(str(password), safe="")
    return f"postgresql://{user}:{password_enc}@{host}:{port}/{dbname}"


@contextmanager
def _get_connection() -> Generator[Any, None, None]:
    """Get Postgres connection."""
    db_url = _resolve_db_url()
    conn = psycopg2.connect(db_url, connect_timeout=10, options="-c client_encoding=UTF8")
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- Parse request ---


def _normalize_str(val: Any) -> str | None:
    """Normalize string: strip; if empty after strip return None. Never return ''."""
    if val is None or not isinstance(val, str):
        return None
    s = val.strip()
    return s if s else None


def parse_request_envelope(
    event: dict[str, Any], source_from_api_key: str
) -> tuple[str, str, str, str, dict[str, Any], dict[str, Any]]:
    """
    Parse request envelope for /v1/integrations/execute.

    source_from_api_key: derived from JWT (not from body).
    Body required: targetVendor, operation, parameters.
    Body optional: idempotencyKey (string, generated UUID if missing).

    Returns (source_vendor_code, target_vendor_code, operation_code, idempotency_key, parameters, payload).
    Raises ValueError on validation failure.
    """
    body_raw = event.get("body") or "{}"
    try:
        payload = json.loads(body_raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON body: {e}") from e

    target = payload.get("targetVendor")
    if target and str(target).strip().upper() in ("HUB", "LH000"):
        raise ValueError("Deprecated vendor codes are not accepted. Provide the actual target vendor code.")
    operation = payload.get("operation")
    idempotency_key_raw = payload.get("idempotencyKey")
    parameters_raw = payload.get("parameters")

    if not target or not isinstance(target, str):
        raise ValueError("targetVendor is required and must be a non-empty string")
    if not operation or not isinstance(operation, str):
        raise ValueError("operation is required and must be a non-empty string")
    if idempotency_key_raw is not None and not isinstance(idempotency_key_raw, str):
        raise ValueError("idempotencyKey must be a string when provided")
    if parameters_raw is not None and not isinstance(parameters_raw, dict):
        raise ValueError("parameters must be an object when provided")

    target = target.strip()
    operation = operation.strip()
    trimmed = (idempotency_key_raw or "").strip()
    idempotency_key = trimmed if trimmed else str(uuid.uuid4())
    parameters = parameters_raw if isinstance(parameters_raw, dict) else {}

    return source_from_api_key, target, operation, idempotency_key, parameters, payload


# --- Validate control plane ---


def validate_control_plane(
    conn: Any,
    source_vendor_code: str,
    target_vendor_code: str,
    operation_code: str,
) -> dict[str, Any]:
    """
    Validate using DB:
    - vendor exists and active (source + target)
    - operation exists and active
    - allowlist permits (source, target, operation)
    - endpoint exists for target+operation and active
    Returns endpoint dict with url, http_method, timeout_ms.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT 1 FROM control_plane.vendors
            WHERE vendor_code = %s AND COALESCE(is_active, true)
            """,
            (source_vendor_code,),
        )
        if cur.fetchone() is None:
            raise ValueError(f"Source vendor {source_vendor_code} not found or inactive")

        cur.execute(
            """
            SELECT 1 FROM control_plane.vendors
            WHERE vendor_code = %s AND COALESCE(is_active, true)
            """,
            (target_vendor_code,),
        )
        if cur.fetchone() is None:
            raise ValueError(f"Target vendor {target_vendor_code} not found or inactive")

        cur.execute(
            """
            SELECT operation_code, canonical_version, COALESCE(direction_policy, 'TWO_WAY') AS direction_policy
            FROM control_plane.operations
            WHERE operation_code = %s AND COALESCE(is_active, true)
            """,
            (operation_code,),
        )
        op_row = cur.fetchone()
        if op_row is None:
            raise ValueError(f"Operation {operation_code} not found or inactive")
        canonical_version = op_row.get("canonical_version") or "v1"
        direction_policy = (op_row.get("direction_policy") or "TWO_WAY").strip().upper()

        # Before allowlist: confirm target vendor supports operation
        cur.execute(
            """
            SELECT 1 FROM control_plane.vendor_supported_operations
            WHERE vendor_code = %s AND operation_code = %s AND is_active = true
            """,
            (target_vendor_code, operation_code),
        )
        if cur.fetchone() is None:
            raise ValueError("Target vendor does not support operation")

        # Admin rules (rule_scope='admin') define allowed access; use is_any_source/is_any_target for wildcards.
        # flow_direction: OUTBOUND = source sends to target; INBOUND = target receives from source; BOTH = either.
        cur.execute(
            """
            SELECT 1 FROM control_plane.vendor_operation_allowlist
            WHERE rule_scope = 'admin'
              AND operation_code = %s
              AND (COALESCE(is_any_source, FALSE) = TRUE OR source_vendor_code = %s)
              AND (COALESCE(is_any_target, FALSE) = TRUE OR target_vendor_code = %s)
              AND flow_direction IN ('INBOUND', 'OUTBOUND', 'BOTH')
            LIMIT 1
            """,
            (operation_code, source_vendor_code, target_vendor_code),
        )
        if cur.fetchone() is None:
            raise ValueError(
                f"Allowlist violation: {source_vendor_code} -> {target_vendor_code} "
                f"for {operation_code} not permitted"
            )

        # 2. For PROVIDER_RECEIVES_ONLY: provider (target) can narrow which callers are allowed.
        # Vendor rules: rule_scope='vendor', target_vendor_code=provider, flow_direction='OUTBOUND'.
        if direction_policy == "PROVIDER_RECEIVES_ONLY":
            provider = target_vendor_code
            cur.execute(
                """
                SELECT source_vendor_code, is_any_source
                FROM control_plane.vendor_operation_allowlist
                WHERE rule_scope = 'vendor'
                  AND target_vendor_code = %s
                  AND operation_code = %s
                  AND flow_direction = 'OUTBOUND'
                  AND COALESCE(is_any_source, FALSE) = FALSE
                """,
                (provider, operation_code),
            )
            vendor_rules = cur.fetchall() or []
            if vendor_rules:
                allowed_sources = {
                    r["source_vendor_code"].strip().upper()
                    for r in vendor_rules
                    if r.get("source_vendor_code")
                }
                source_upper = source_vendor_code.strip().upper()
                if source_upper not in allowed_sources:
                    raise ValueError(
                        f"ALLOWLIST_VENDOR_DENIED: Provider narrowed access; {source_vendor_code} not in whitelist "
                        f"for {operation_code} -> {provider}"
                    )

        # Target receives the call -> use flow_direction = 'INBOUND'
        cur.execute(
            """
            SELECT e.url, e.http_method, e.payload_format, e.timeout_ms, e.verification_status, e.auth_profile_id AS ep_auth_profile_id,
                   ap.id AS auth_profile_id, ap.vendor_code AS ap_vendor_code, ap.name AS ap_name,
                   ap.auth_type AS ap_auth_type, ap.config AS ap_config, ap.is_active AS ap_is_active
            FROM control_plane.vendor_endpoints e
            LEFT JOIN control_plane.auth_profiles ap
              ON e.auth_profile_id = ap.id AND COALESCE(ap.is_active, true)
            WHERE e.vendor_code = %s AND e.operation_code = %s AND e.flow_direction = 'INBOUND' AND e.is_active = true
            ORDER BY e.updated_at DESC NULLS LAST
            LIMIT 1
            """,
            (target_vendor_code, operation_code),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(
                f"No active endpoint for {target_vendor_code} + {operation_code}"
            )
        if (row.get("verification_status") or "").upper() != "VERIFIED":
            raise EndpointNotVerifiedError(
                f"Endpoint for {target_vendor_code} + {operation_code} is not verified "
                f"(status: {row.get('verification_status') or 'PENDING'})"
            )
        ep_auth_profile_id = row.get("ep_auth_profile_id")
        if ep_auth_profile_id and not row.get("ap_auth_type"):
            raise ValueError(
                f"Auth profile {ep_auth_profile_id} is missing or inactive for target endpoint"
            )
        result: dict[str, Any] = {
            "url": row["url"],
            "http_method": row["http_method"],
            "payload_format": row.get("payload_format"),
            "timeout_ms": row["timeout_ms"],
            "verification_status": row["verification_status"],
            "canonical_version": canonical_version,
        }
        if row.get("auth_profile_id") and row.get("ap_auth_type"):
            result["auth_profile"] = {
                "id": str(row["auth_profile_id"]),
                "vendor_code": row.get("ap_vendor_code"),
                "name": row.get("ap_name"),
                "auth_type": row.get("ap_auth_type"),
                "config": row.get("ap_config") if isinstance(row.get("ap_config"), dict) else {},
                "is_active": bool(row.get("ap_is_active", True)),
            }
        else:
            result["auth_profile"] = None
        return result


def load_operation_contract(
    conn: Any,
    operation_code: str,
    canonical_version: str,
    vendor_code: str | None = None,
) -> dict[str, Any] | None:
    """
    Load active contract for (operation_code, canonical_version).
    When vendor_code provided: only vendor_operation_contracts (no fallback).
    Returns contract row with request_schema, response_schema or None if not found.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if vendor_code:
            cur.execute(
                """
                SELECT operation_code, canonical_version, request_schema, response_schema
                FROM control_plane.vendor_operation_contracts
                WHERE vendor_code = %s AND operation_code = %s AND canonical_version = %s
                  AND is_active = true
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
                """,
                (vendor_code, operation_code, canonical_version),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        cur.execute(
            """
            SELECT operation_code, canonical_version, request_schema, response_schema
            FROM control_plane.operation_contracts
            WHERE operation_code = %s AND canonical_version = %s AND is_active = true
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """,
            (operation_code, canonical_version),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def load_operation_version(conn: Any, operation_code: str) -> str | None:
    """
    Load canonical_version for active operation.
    Returns version string or None if operation not found/inactive.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT canonical_version FROM control_plane.operations
            WHERE operation_code = %s AND COALESCE(is_active, true)
            """,
            (operation_code,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return row.get("canonical_version") or "v1"


def load_vendor_mapping(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    canonical_version: str,
    direction: str,
    flow_direction: str = "OUTBOUND",
) -> dict[str, Any] | None:
    """
    Load active mapping for (vendor, operation, version, direction, flow_direction).
    direction: TO_CANONICAL | FROM_CANONICAL | TO_CANONICAL_RESPONSE | FROM_CANONICAL_RESPONSE
    flow_direction: OUTBOUND (default) or INBOUND.
    Returns mapping dict (outKey -> selectorOrConst) or None.
    When None: canonical pass-through (no vendor-specific transform).
    """
    fd = (flow_direction or "OUTBOUND").strip().upper()
    if fd not in ("INBOUND", "OUTBOUND"):
        fd = "OUTBOUND"
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT mapping FROM control_plane.vendor_operation_mappings
            WHERE vendor_code = %s AND operation_code = %s
              AND canonical_version = %s AND direction = %s
              AND flow_direction = %s AND is_active = true
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """,
            (vendor_code, operation_code, canonical_version, direction, fd),
        )
        row = cur.fetchone()
        if row is None:
            return None
        m = row.get("mapping")
        if not isinstance(m, dict):
            return None
        # Empty mapping = canonical pass-through; routing treats as no transform
        if len(m) == 0 or (len(m) == 1 and m.get("type") == "identity"):
            return None
        return m


def _format_jsonschema_violations(err: "jsonschema.ValidationError") -> list[str]:
    """Flatten jsonschema ValidationError into consistent violation strings: 'field: constraint'."""
    violations: list[str] = []

    def _normalize_msg(msg: str) -> str:
        """Normalize common jsonschema messages to consistent constraint descriptions."""
        if "is a required property" in msg:
            return "required"
        if "is too short" in msg:
            return "length must be at least minimum"
        if "is too long" in msg:
            return "length must be at most maximum"
        if "is not of type" in msg:
            return msg.replace("is not of type", "must be type")
        return msg

    def collect(e: "jsonschema.ValidationError") -> None:
        path_str = ".".join(str(p) for p in e.path) if e.path else "value"
        norm = _normalize_msg(e.message)
        violations.append(f"{path_str}: {norm}")
        for c in e.context:
            collect(c)

    collect(err)
    return violations


def validate_request_schema(parameters: dict[str, Any], request_schema: dict[str, Any]) -> None:
    """
    Validate parameters against request_schema using jsonschema.
    Raises jsonschema.ValidationError with violations on failure.
    """
    if jsonschema is None:
        raise ImportError("jsonschema is not installed")
    jsonschema.validate(instance=parameters, schema=request_schema)


def _process_response_pipeline(
    conn: Any,
    transaction_id: str,
    source: str,
    target: str,
    operation: str,
    canonical_version: str,
    target_contract: dict[str, Any] | None,
    canonical_contract: dict[str, Any] | None,
    target_response: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    """
    Full response transform pipeline:
    1) Validate target_response is valid JSON (dict, no raw)
    2) Transform target_response -> canonical_response via TO_CANONICAL_RESPONSE mapping
    3) Validate canonical_response against canonical_contract.response_schema
    4) Transform canonical_response -> source_response via FROM_CANONICAL_RESPONSE mapping (optional)
       - If mapping found: apply transform; on path-missing -> MAPPING_FAILED
       - If no mapping: source_response = canonical_response (pass-through)
    Returns (canonical_response, source_response, error_info). error_info is None on success.
    Canonical request and canonical response are always validated against canonical schemas.
    """
    # 1) Guard: target_response must be valid dict (caller typically ensures this)
    if not isinstance(target_response, dict) or "raw" in target_response:
        err_t = downstream_invalid_response(raw=str(target_response.get("raw", ""))[:500] if isinstance(target_response, dict) else "")
        write_audit_event(conn, transaction_id, source, "DOWNSTREAM_INVALID_RESPONSE", {"code": err_t["code"], "reason": "invalid_json"})
        return ({}, {}, err_t)

    # 2) Transform target_response -> canonical_response (or passthrough if target returns canonical)
    target_mapping = load_vendor_mapping(conn, target, operation, canonical_version, "TO_CANONICAL_RESPONSE")
    if target_mapping is not None:
        canonical_response, mapping_violations = apply_mapping(target_response, target_mapping)
        if mapping_violations:
            err_t = mapping_failed("Target response mapping violations", mapping_violations)
            write_audit_event(conn, transaction_id, source, "MAPPING_FAILED", {"code": err_t["code"], "violations": mapping_violations})
            return ({}, {}, err_t)
        write_audit_event(conn, transaction_id, source, "RESPONSE_TO_CANONICAL_SUCCESS", {})
    else:
        # No TO_CANONICAL_RESPONSE: treat canonical_response = target_response. Validate against canonical schema.
        canonical_response = dict(target_response) if isinstance(target_response, dict) else target_response
        canonical_schema = canonical_contract.get("response_schema") if canonical_contract else None
        if canonical_schema:
            try:
                validate_request_schema(canonical_response, canonical_schema)
            except Exception as schema_err:
                violations = (
                    _format_jsonschema_violations(schema_err)
                    if (jsonschema and isinstance(schema_err, jsonschema.ValidationError))
                    else [str(schema_err)]
                )
                err_t = mapping_not_found(
                    "Missing active mapping TO_CANONICAL_RESPONSE for target vendor; target response does not conform to canonical response schema",
                    direction="TO_CANONICAL_RESPONSE",
                    violations=violations,
                )
                write_audit_event(conn, transaction_id, source, "MAPPING_NOT_FOUND", {"code": err_t["code"], "direction": "TO_CANONICAL_RESPONSE", "violations": violations})
                return ({}, {}, err_t)

    # 3) Validate canonical_response against canonical_contract.response_schema
    canonical_schema = canonical_contract.get("response_schema") if canonical_contract else None
    if canonical_schema:
        try:
            validate_request_schema(canonical_response, canonical_schema)
        except Exception as schema_err:
            violations = (
                _format_jsonschema_violations(schema_err)
                if (jsonschema and isinstance(schema_err, jsonschema.ValidationError))
                else [str(schema_err)]
            )
            err_t = schema_validation_failed("Canonical response schema validation failed", violations, stage="canonical_response")
            write_audit_event(conn, transaction_id, source, "SCHEMA_VALIDATION_FAILED", {"code": err_t["code"], "violations": violations})
            return (canonical_response, {}, err_t)
        write_audit_event(conn, transaction_id, source, "RESPONSE_VALIDATE_CANONICAL_OK", {})

    # 4) Transform canonical_response -> source_response via FROM_CANONICAL_RESPONSE (optional)
    source_mapping = load_vendor_mapping(conn, source, operation, canonical_version, FROM_CANONICAL_RESPONSE)
    if source_mapping is None:
        # No source response mapping: return canonical as response_body (pass-through)
        source_response = dict(canonical_response) if isinstance(canonical_response, dict) else canonical_response
        write_audit_event(conn, transaction_id, source, "RESPONSE_NO_SOURCE_MAPPING_PASSTHROUGH", {})
        return (canonical_response, source_response, None)
    source_response, from_violations = apply_mapping(canonical_response, source_mapping)
    if from_violations:
        err_t = mapping_failed("Source response mapping violations", from_violations, direction=FROM_CANONICAL_RESPONSE)
        write_audit_event(conn, transaction_id, source, "MAPPING_FAILED", {"code": err_t["code"], "direction": FROM_CANONICAL_RESPONSE, "violations": from_violations})
        return (canonical_response, {}, err_t)
    write_audit_event(conn, transaction_id, source, "RESPONSE_FROM_CANONICAL_SUCCESS", {})

    return (canonical_response, source_response, None)


# --- Auth: resolve sourceVendor (JWT only; vendor_identity used elsewhere) ---

def resolve_vendor_from_api_key(conn: Any, api_key_value: str) -> str | None:
    """
    Look up vendor_code by API key. Uses vendor_identity.resolve_vendor_code.
    Returns vendor_code if valid, None if missing/invalid (caller handles 401/403).
    """
    try:
        return resolve_vendor_code(conn, api_key_value)
    except (VendorAuthError, VendorForbiddenError):
        return None


def _canonical_request_body(body: Any, source_vendor: str | None) -> Any:
    """Build request body for storage, including derived sourceVendor for traceability."""
    if not source_vendor:
        return body
    if isinstance(body, dict):
        return {**body, "sourceVendor": source_vendor}
    return body


# --- Idempotency / Replay ---

# Status for first-time execution (insert before downstream)
STARTED_STATUS = "started"


def idempotency_lookup(
    conn: Any,
    source_vendor_code: str,
    idempotency_key: str | None,
) -> dict[str, Any] | None:
    """
    If (source_vendor_code, idempotency_key) exists: return stored response (replay).
    Uses idempotency_claims (v37) for fast lookup, then transactions for full row.
    Falls back to direct transactions query if idempotency_claims unavailable.
    """
    if not idempotency_key:
        return None
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        tx_id = None
        try:
            cur.execute(
                """
                SELECT transaction_id FROM data_plane.idempotency_claims
                WHERE source_vendor = %s AND idempotency_key = %s
                """,
                (source_vendor_code, idempotency_key),
            )
            claim = cur.fetchone()
            if claim:
                tx_id = claim["transaction_id"]
        except Exception:
            pass
        if not tx_id:
            cur.execute(
                """
                SELECT transaction_id, correlation_id, status, response_body
                FROM data_plane.transactions
                WHERE source_vendor = %s AND idempotency_key = %s
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (source_vendor_code, idempotency_key),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "action": "replay",
                "transaction_id": row["transaction_id"],
                "correlation_id": row["correlation_id"],
                "status": row["status"],
                "response_body": row.get("response_body"),
            }
        cur.execute(
            """
            SELECT transaction_id, correlation_id, status, response_body
            FROM data_plane.transactions
            WHERE transaction_id = %s AND source_vendor = %s
            LIMIT 1
            """,
            (tx_id, source_vendor_code),
        )
        row = cur.fetchone()
        if not row:
            return {"action": "replay", "transaction_id": tx_id, "correlation_id": tx_id, "status": "received", "response_body": None}
        return {
            "action": "replay",
            "transaction_id": row["transaction_id"],
            "correlation_id": row["correlation_id"],
            "status": row["status"],
            "response_body": row.get("response_body"),
        }


# --- Audit ---

AUDIT_PAYLOAD_MAX_BYTES = 4096  # 4 KB; truncate beyond this for PII safety


def _audit_safe_payload(obj: Any) -> dict[str, Any]:
    """
    Produce PII-safe payload for audit details: truncate to N KB, store hash if truncated.
    Returns dict with 'value', and optionally 'truncated', 'hash'.
    """
    if obj is None:
        return {}
    try:
        serialized = json.dumps(obj, default=str)
    except (TypeError, ValueError):
        return {"value": str(obj)[:500], "truncated": True}
    encoded = serialized.encode("utf-8")
    if len(encoded) <= AUDIT_PAYLOAD_MAX_BYTES:
        return {"value": obj}
    hash_val = hashlib.sha256(encoded).hexdigest()[:16]
    truncated = encoded[:AUDIT_PAYLOAD_MAX_BYTES]
    try:
        truncated_str = truncated.decode("utf-8", errors="replace")
        while truncated_str and truncated_str[-1] in ("\uFFFD", "\\"):
            truncated_str = truncated_str[:-1]
        parsed = json.loads(truncated_str) if truncated_str.strip() else None
    except Exception:
        parsed = None
    return {
        "value": parsed if parsed is not None else {"_truncated": True, "_hash": hash_val},
        "truncated": True,
        "hash": hash_val,
    }


def _audit_details(
    *,
    canonical_request: Any = None,
    target_request: Any = None,
    target_status_code: int | None = None,
    target_response: Any = None,
    canonical_response: Any = None,
    error: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build audit details dict with PII-safe payloads."""
    details: dict[str, Any] = dict(extra)
    if canonical_request is not None:
        s = _audit_safe_payload(canonical_request)
        details["canonical_request"] = s.get("value", canonical_request)
        if s.get("truncated"):
            details["canonical_request_truncated"] = True
            details["canonical_request_hash"] = s.get("hash")
    if target_request is not None:
        s = _audit_safe_payload(target_request)
        details["target_request"] = s.get("value", target_request)
        if s.get("truncated"):
            details["target_request_truncated"] = True
            details["target_request_hash"] = s.get("hash")
    if target_status_code is not None:
        details["target_status_code"] = target_status_code
    if target_response is not None:
        s = _audit_safe_payload(target_response)
        details["target_response"] = s.get("value", target_response)
        if s.get("truncated"):
            details["target_response_truncated"] = True
            details["target_response_hash"] = s.get("hash")
    if canonical_response is not None:
        s = _audit_safe_payload(canonical_response)
        details["canonical_response"] = s.get("value", canonical_response)
        if s.get("truncated"):
            details["canonical_response_truncated"] = True
            details["canonical_response_hash"] = s.get("hash")
    if error is not None:
        details["error"] = {
            "code": error.get("code"),
            "message": (str(error.get("message", ""))[:500] if error.get("message") else None),
            "category": error.get("category"),
        }
    return details


def write_audit_event(
    conn: Any,
    transaction_id: str,
    vendor_code: str,
    event_type: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Write audit event to data_plane.audit_events."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO data_plane.audit_events (transaction_id, action, vendor_code, details)
            VALUES (%s, %s, %s, %s)
            """,
            (transaction_id, event_type, vendor_code, Json(details) if details else None),
        )


def _emit_route_failed(
    conn: Any | None,
    transaction_id: str,
    vendor_code: str | None,
    err: dict[str, Any],
    **extras: Any,
) -> None:
    """Emit ROUTE_FAILED audit event with canonical error in details.error."""
    vendor = vendor_code or "system"
    details = _audit_details(error=err, **extras)
    if conn:
        write_audit_event(conn, transaction_id, vendor, "ROUTE_FAILED", details)
    else:
        try:
            with _get_connection() as c:
                write_audit_event(c, transaction_id, vendor, "ROUTE_FAILED", details)
        except Exception:
            pass


# --- Transaction record ---


class IdempotencyConflict(Exception):
    """Raised when idempotency_claims insert conflicts (concurrent request)."""


def _claim_idempotency(conn: Any, source_vendor: str, idempotency_key: str, transaction_id: str) -> bool:
    """Claim idempotency key. Returns True if claimed, False if conflict (already claimed)."""
    if not idempotency_key or not source_vendor:
        return True
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO data_plane.idempotency_claims (source_vendor, idempotency_key, transaction_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (source_vendor, idempotency_key) DO NOTHING
                RETURNING transaction_id
                """,
                (source_vendor, idempotency_key, transaction_id),
            )
            return cur.fetchone() is not None
    except Exception:
        return False


REDRIVEABLE_STATUSES = frozenset({
    "downstream_error",
    "downstream_failed",
    "failed",
    "timeout",
    "validation_failed",
})


def create_transaction_record(
    conn: Any,
    transaction_id: str,
    correlation_id: str,
    source_vendor_code: str | None,
    target_vendor_code: str | None,
    operation_code: str | None,
    idempotency_key: str | None,
    status: str = "pending",
    request_body: dict[str, Any] | None = None,
    response_body: dict[str, Any] | None = None,
    parent_transaction_id: Any | None = None,
    redrive_count: int = 0,
) -> None:
    """Create transaction record. Claims idempotency first (v37); raises IdempotencyConflict if race."""
    if idempotency_key and source_vendor_code:
        if not _claim_idempotency(conn, source_vendor_code, idempotency_key, transaction_id):
            raise IdempotencyConflict("idempotency key already claimed")
    columns = [
        "transaction_id", "correlation_id", "source_vendor", "target_vendor", "operation",
        "idempotency_key", "status", "request_body", "response_body",
    ]
    values = [
        transaction_id, correlation_id, source_vendor_code, target_vendor_code, operation_code,
        idempotency_key, status,
        Json(request_body) if request_body else None,
        Json(response_body) if response_body else None,
    ]
    if parent_transaction_id is not None:
        columns.append("parent_transaction_id")
        values.append(parent_transaction_id)
    if redrive_count != 0:
        columns.append("redrive_count")
        values.append(redrive_count)
    placeholders = ", ".join("%s" for _ in values)
    col_str = ", ".join(columns)
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO data_plane.transactions ({col_str}) VALUES ({placeholders})",
            values,
        )


def update_transaction_success(
    conn: Any,
    transaction_id: str,
    response_body: dict[str, Any],
    canonical_request: dict[str, Any] | None = None,
    target_request: dict[str, Any] | None = None,
    target_response_body: dict[str, Any] | None = None,
    canonical_response_body: dict[str, Any] | None = None,
    http_status: int = 200,
) -> None:
    """Update transaction with success response for idempotency reuse. Sets debug tier fields."""
    with conn.cursor() as cur:
        updates = ["status = 'completed'", "response_body = %s", "http_status = %s", "error_code = NULL", "retryable = NULL", "failure_stage = NULL"]
        vals: list[Any] = [Json(response_body), http_status]
        if canonical_request is not None:
            updates.append("canonical_request_body = %s")
            vals.append(Json(canonical_request))
        if target_request is not None:
            updates.append("target_request_body = %s")
            vals.append(Json(target_request))
        if target_response_body is not None:
            updates.append("target_response_body = %s")
            vals.append(Json(target_response_body))
        if canonical_response_body is not None:
            updates.append("canonical_response_body = %s")
            vals.append(Json(canonical_response_body))
        vals.append(transaction_id)
        cur.execute(
            f"UPDATE data_plane.transactions SET {', '.join(updates)} WHERE transaction_id = %s",
            vals,
        )


def update_transaction_status(
    conn: Any,
    transaction_id: str,
    status: str,
    response_body: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    canonical_request: dict[str, Any] | None = None,
    target_request: dict[str, Any] | None = None,
) -> None:
    """Update transaction status. Optionally set response_body, idempotency_key, canonical_request, target_request."""
    with conn.cursor() as cur:
        updates = ["status = %s"]
        vals: list[Any] = [status]
        if response_body is not None:
            updates.append("response_body = %s")
            vals.append(Json(response_body))
        if idempotency_key is not None:
            updates.append("idempotency_key = %s")
            vals.append(idempotency_key)
        if canonical_request is not None:
            updates.append("canonical_request_body = %s")
            vals.append(Json(canonical_request))
        if target_request is not None:
            updates.append("target_request_body = %s")
            vals.append(Json(target_request))
        vals.append(transaction_id)
        cur.execute(
            f"UPDATE data_plane.transactions SET {', '.join(updates)} WHERE transaction_id = %s",
            vals,
        )


def _infer_failure_stage(
    status: str, taxonomy_err: dict[str, Any] | None
) -> str | None:
    """Infer failure_stage: details.stage if present, else DOWNSTREAM, MAPPING, or CONFIG."""
    if not taxonomy_err:
        return None
    stage = (taxonomy_err.get("details") or {}).get("stage")
    if stage:
        return stage  # schema_validation_failed includes details.stage
    if status in ("downstream_error", "downstream_failed"):
        return "DOWNSTREAM"
    if status == "mapping_failed":
        direction = (taxonomy_err.get("details") or {}).get("direction")
        if direction == FROM_CANONICAL_RESPONSE:
            return "CANONICAL_RESPONSE_MAPPING"
        return "MAPPING"
    code = taxonomy_err.get("code", "")
    if code in (
        "CONTRACT_NOT_FOUND",
        "OPERATION_NOT_FOUND",
        "ALLOWLIST_DENIED",
        "ENDPOINT_NOT_VERIFIED",
        "VENDOR_NOT_FOUND",
        "NOT_FOUND",
    ):
        return "CONFIG"
    if status == "validation_failed":
        return "CANONICAL_REQUEST"  # Input schema validation (no stage)
    return None


def update_transaction_failure(
    conn: Any,
    transaction_id: str,
    status: str = "failed",
    response_body: dict[str, Any] | None = None,
    *,
    error_code: str | None = None,
    http_status: int | None = None,
    retryable: bool | None = None,
    failure_stage: str | None = None,
    canonical_request_body: dict[str, Any] | None = None,
    target_request_body: dict[str, Any] | None = None,
    target_response_body: dict[str, Any] | None = None,
    canonical_response_body: dict[str, Any] | None = None,
    taxonomy_err: dict[str, Any] | None = None,
) -> None:
    """Update transaction with failure status. Persists error metadata: error_code, http_status, retryable, failure_stage."""
    if taxonomy_err is not None:
        error_code = error_code or taxonomy_err.get("code")
        http_status = http_status if http_status is not None else taxonomy_err.get("http_status")
        retryable = retryable if retryable is not None else taxonomy_err.get("retryable")
        if failure_stage is None:
            failure_stage = _infer_failure_stage(status, taxonomy_err)
    updates = ["status = %s"]
    vals: list[Any] = [status]
    if response_body is not None:
        updates.append("response_body = %s")
        vals.append(Json(response_body))
    if error_code is not None:
        updates.append("error_code = %s")
        vals.append(error_code)
    if http_status is not None:
        updates.append("http_status = %s")
        vals.append(http_status)
    if retryable is not None:
        updates.append("retryable = %s")
        vals.append(retryable)
    if failure_stage is not None:
        updates.append("failure_stage = %s")
        vals.append(failure_stage)
    if canonical_request_body is not None:
        updates.append("canonical_request_body = %s")
        vals.append(Json(canonical_request_body))
    if target_request_body is not None:
        updates.append("target_request_body = %s")
        vals.append(Json(target_request_body))
    if target_response_body is not None:
        updates.append("target_response_body = %s")
        vals.append(Json(target_response_body))
    if canonical_response_body is not None:
        updates.append("canonical_response_body = %s")
        vals.append(Json(canonical_response_body))
    vals.append(transaction_id)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE data_plane.transactions SET {', '.join(updates)} WHERE transaction_id = %s",
            vals,
        )


# --- Downstream call ---


def _resolve_secret(secret_ref: str | None) -> str:
    """Resolve secret value from Secrets Manager. secret_ref: secret name or ARN."""
    if not secret_ref or not str(secret_ref).strip():
        raise ValueError("secretRef is required")
    import boto3
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=secret_ref.strip())
    value = resp.get("SecretString")
    if value is None:
        raise ValueError(f"Secret {secret_ref!r} has no SecretString")
    return value


# In-memory cache for OAuth2 access tokens. Key: auth_profile.id. Value: {access_token, expires_at}
_oauth_token_cache: dict[str, dict[str, Any]] = {}

OAUTH2_TOKEN_SAFETY_MARGIN_SEC = 60
OAUTH2_DEFAULT_EXPIRES_IN_SEC = 600


def fetch_oauth2_token(auth_profile: dict[str, Any]) -> tuple[str, datetime]:
    """
    Fetch OAuth2 access token via client credentials flow.
    Resolves client_id and client_secret from Secrets Manager.
    Returns (access_token, expires_at). Raises OAuthTokenFetchError on failure.
    Never logs token, clientId, or clientSecret.
    """
    config = auth_profile.get("config") or {}
    if not isinstance(config, dict):
        config = {}

    token_url = (config.get("tokenUrl") or "").strip()
    if not token_url:
        err = build_error(
            ErrorCode.AUTH_ERROR,
            "OAuth token fetch failed: config.tokenUrl is required",
            http_status=401,
            details={"statusCode": None, "body": None},
        )
        raise OAuthTokenFetchError(err)

    auth_style = (config.get("authStyle") or "BASIC").strip().upper()
    if auth_style not in ("BASIC", "BODY"):
        auth_style = "BASIC"

    client_id_ref = config.get("clientIdSecretRef")
    client_secret_ref = config.get("clientSecretSecretRef")
    try:
        client_id = _resolve_secret(client_id_ref)
        client_secret = _resolve_secret(client_secret_ref)
    except ValueError as e:
        err = build_error(
            ErrorCode.AUTH_ERROR,
            "OAuth token fetch failed: " + str(e),
            http_status=401,
            details={"statusCode": None, "body": None},
        )
        raise OAuthTokenFetchError(err)

    form_data: dict[str, str] = {"grant_type": "client_credentials"}
    scope = (config.get("scope") or "").strip()
    if scope:
        form_data["scope"] = scope
    audience = (config.get("audience") or "").strip()
    if audience:
        form_data["audience"] = audience
    if auth_style == "BODY":
        form_data["client_id"] = client_id
        form_data["client_secret"] = client_secret

    headers: dict[str, str] = {"Content-Type": "application/x-www-form-urlencoded"}
    if auth_style == "BASIC":
        creds = f"{client_id}:{client_secret}"
        encoded = base64.b64encode(creds.encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"

    body = urllib.parse.urlencode(form_data)
    try:
        resp = requests.post(
            token_url,
            data=body,
            headers=headers,
            timeout=15,
            allow_redirects=False,
        )
    except requests.RequestException as e:
        err = build_error(
            ErrorCode.AUTH_ERROR,
            "OAuth token fetch failed: " + str(e),
            http_status=401,
            details={"statusCode": None, "body": None},
        )
        raise OAuthTokenFetchError(err)

    status_code = resp.status_code
    body_snippet = (resp.text or "")[:500] if hasattr(resp, "text") else ""

    if status_code not in (200, 201):
        err = build_error(
            ErrorCode.AUTH_ERROR,
            "OAuth token fetch failed",
            http_status=401,
            details={"statusCode": status_code, "body": body_snippet},
        )
        raise OAuthTokenFetchError(err)

    try:
        data = resp.json()
    except (ValueError, TypeError):
        err = build_error(
            ErrorCode.AUTH_ERROR,
            "OAuth token fetch failed: token response is not valid JSON",
            http_status=401,
            details={"statusCode": status_code, "body": body_snippet},
        )
        raise OAuthTokenFetchError(err)

    access_token = data.get("access_token")
    if not access_token or not isinstance(access_token, str):
        err = build_error(
            ErrorCode.AUTH_ERROR,
            "OAuth token fetch failed: token response missing access_token",
            http_status=401,
            details={"statusCode": status_code, "body": body_snippet},
        )
        raise OAuthTokenFetchError(err)

    expires_in = data.get("expires_in")
    if expires_in is not None and isinstance(expires_in, (int, float)):
        expires_in_sec = max(0, int(expires_in))
    else:
        expires_in_sec = OAUTH2_DEFAULT_EXPIRES_IN_SEC

    safety = min(OAUTH2_TOKEN_SAFETY_MARGIN_SEC, max(0, expires_in_sec - 1))
    expires_at = datetime.now(timezone.utc).timestamp() + expires_in_sec - safety
    expires_at_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)

    return access_token.strip(), expires_at_dt


def get_oauth2_access_token(auth_profile: dict[str, Any]) -> str:
    """
    Get OAuth2 access token, using in-memory cache if valid and unexpired.
    Cache key: auth_profile.id. Returns access_token string.
    Raises OAuthTokenFetchError on fetch failure.
    """
    profile_id = auth_profile.get("id") or ""
    if not profile_id:
        profile_id = hashlib.sha256(
            json.dumps(auth_profile.get("config") or {}, sort_keys=True).encode()
        ).hexdigest()[:32]

    now = datetime.now(timezone.utc)
    cached = _oauth_token_cache.get(profile_id)
    if cached:
        expires_at = cached.get("expires_at")
        if isinstance(expires_at, datetime) and expires_at > now:
            return cached["access_token"]
        if isinstance(expires_at, (int, float)) and expires_at > now.timestamp():
            return cached["access_token"]

    access_token, expires_at = fetch_oauth2_token(auth_profile)
    _oauth_token_cache[profile_id] = {"access_token": access_token, "expires_at": expires_at}
    return access_token


def build_downstream_headers(
    transaction_id: str | None,
    correlation_id: str | None,
    auth_profile: dict[str, Any] | None,
    *,
    vendor_code: str = "",
    operation: str = "",
) -> tuple[dict[str, str], dict[str, str], dict[str, Any]]:
    """
    Build headers and params for downstream vendor call. Base: x-transaction-id, x-correlation-id.
    Tier-1 auth: API_KEY_HEADER, API_KEY_QUERY, STATIC_BEARER use inline config.value/config.token.
    Returns (headers_dict, params_dict, audit_details_dict with no secrets).
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}
    params: dict[str, str] = {}
    if transaction_id:
        headers["x-transaction-id"] = transaction_id
    if correlation_id:
        headers["x-correlation-id"] = correlation_id
    header_names_for_audit: list[str] = list(headers.keys())
    param_names_for_audit: list[str] = []

    if not auth_profile or (auth_profile.get("auth_type") or "").upper() == "NONE":
        audit_none = {"headerNames": header_names_for_audit, "authType": "NONE"}
        if vendor_code:
            audit_none["vendorCode"] = vendor_code
        if operation:
            audit_none["operation"] = operation
        return headers, params, audit_none

    auth_type = (auth_profile.get("auth_type") or "").upper()
    config = auth_profile.get("config") or {}
    if not isinstance(config, dict):
        config = {}

    try:
        if auth_type == "API_KEY_HEADER":
            header_name = (config.get("headerName") or "Api-Key").strip()
            val = config.get("value")
            if val is not None and isinstance(val, str) and val.strip():
                headers[header_name] = val.strip()
            elif config.get("secretRef"):
                headers[header_name] = _resolve_secret(config.get("secretRef"))
            else:
                raise ValueError("config.value or config.secretRef required for API_KEY_HEADER")
            header_names_for_audit.append(header_name)
        elif auth_type == "API_KEY_QUERY":
            param_name = (config.get("paramName") or "api_key").strip()
            val = config.get("value")
            if val is not None and isinstance(val, str) and val.strip():
                params[param_name] = val.strip()
            else:
                raise ValueError("config.value required for API_KEY_QUERY")
            param_names_for_audit.append(param_name)
        elif auth_type == "STATIC_BEARER":
            header_name = (config.get("headerName") or "Authorization").strip()
            prefix = (config.get("prefix") or "Bearer ").strip()
            if prefix and not prefix.endswith(" "):
                prefix = prefix + " "
            token = config.get("token")
            if token is not None and isinstance(token, str) and token.strip():
                headers[header_name] = prefix + token.strip()
            elif config.get("secretRef"):
                headers[header_name] = prefix + _resolve_secret(config.get("secretRef"))
            else:
                raise ValueError("config.token or config.secretRef required for STATIC_BEARER")
            header_names_for_audit.append(header_name)
        elif auth_type == "BASIC":
            header_name = (config.get("headerName") or "Authorization").strip()
            username_ref = config.get("usernameSecretRef")
            password_ref = config.get("passwordSecretRef")
            username = _resolve_secret(username_ref)
            password = _resolve_secret(password_ref)
            creds = f"{username}:{password}"
            encoded = base64.b64encode(creds.encode("utf-8")).decode("ascii")
            headers[header_name] = f"Basic {encoded}"
            header_names_for_audit.append(header_name)
        elif auth_type == "OAUTH2_CLIENT_CREDENTIALS":
            access_token = get_oauth2_access_token(auth_profile)
            header_name = (config.get("headerName") or "Authorization").strip()
            prefix = (config.get("prefix") or "Bearer ").strip()
            if prefix and not prefix.endswith(" "):
                prefix = prefix + " "
            headers[header_name] = prefix + access_token
            header_names_for_audit.append(header_name)
        # else: unknown auth_type, leave base headers only
    except OAuthTokenFetchError:
        raise
    except ValueError as e:
        raise e

    audit_details = {
        "headerNames": header_names_for_audit,
        "authType": auth_type,
    }
    if param_names_for_audit:
        audit_details["paramNames"] = param_names_for_audit
    if vendor_code:
        audit_details["vendorCode"] = vendor_code
    if operation:
        audit_details["operation"] = operation
    if auth_profile and auth_profile.get("name"):
        audit_details["authProfileName"] = str(auth_profile.get("name", "")).strip()
    return headers, params, audit_details


def _build_vendor_body(
    target_request: Any,
    canonical_request: dict[str, Any],
) -> Any:
    """
    Build the exact body to send to the vendor endpoint.
    Invariant: body must be exactly target_request (if mapping produced it) or canonical_request (if no mapping).
    For JSON: dict. For XML: string. For binary: base64 string or bytes.
    NO extra fields (transactionId, correlationId, etc.) may be merged into the body.
    IDs are passed as headers only (X-Transaction-Id, X-Correlation-Id).
    """
    if target_request is not None:
        return target_request
    return dict(canonical_request) if isinstance(canonical_request, dict) else canonical_request


def call_downstream(
    endpoint_url: str,
    timeout_ms: int,
    vendor_body: Any,
    http_method: str | None = "POST",
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    payload_format: str | None = None,
    content_type_override: str | None = None,
) -> tuple[int, dict[str, Any], dict[str, Any] | None]:
    """
    Call downstream vendor endpoint. Body and Content-Type from build_http_request_body_and_headers.
    Headers and params (query string) from build_downstream_headers.
    Returns (status_code, response_body, binary_meta). binary_meta is None for non-binary payloads.
    """
    timeout_sec = min(
        max(MIN_DOWNSTREAM_TIMEOUT_SEC, (timeout_ms or 8000) / 1000),
        MAX_DOWNSTREAM_TIMEOUT_SEC,
    )
    method = (http_method or "POST").upper()
    base_headers = headers if headers is not None else {"Content-Type": "application/json"}
    req_params = params if params is not None else {}

    body_bytes, req_headers, binary_meta = build_http_request_body_and_headers(
        method=method,
        payload_format=payload_format or "json",
        body=vendor_body,
        base_headers=base_headers,
        content_type_override=content_type_override,
        max_binary_bytes=DEFAULT_MAX_BINARY_BYTES,
    )

    resp = requests.request(
        method,
        endpoint_url,
        data=body_bytes,
        timeout=timeout_sec,
        headers=req_headers,
        params=req_params if req_params else None,
    )
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text[:500], "statusCode": resp.status_code}
    return resp.status_code, body, binary_meta


# --- Canonical error ---


def canonical_error(
    code: str,
    message: str,
    transaction_id: str,
    correlation_id: str,
    status_code: int = 500,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build canonical error response."""
    err = {"error": {"code": code, "message": message}}
    if details:
        err["error"]["details"] = details
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "X-Transaction-Id": transaction_id,
            "X-Correlation-Id": correlation_id,
        },
        "body": json.dumps(
            {
                "transactionId": transaction_id,
                "correlationId": correlation_id,
                **err,
            },
            default=str,
        ),
    }


def _err_from(taxonomy_err: dict[str, Any], transaction_id: str, correlation_id: str) -> dict[str, Any]:
    """Build full API response from taxonomy error dict (code, message, http_status, category, retryable, violations?, details?)."""
    status = taxonomy_err.get("http_status", 400)
    err_obj: dict[str, Any] = {
        "code": taxonomy_err["code"],
        "message": taxonomy_err["message"],
        "category": taxonomy_err.get("category", "internal"),
        "retryable": taxonomy_err.get("retryable", False),
    }
    if taxonomy_err.get("violations") is not None:
        err_obj["violations"] = taxonomy_err["violations"]
    if taxonomy_err.get("details"):
        err_obj["details"] = taxonomy_err["details"]
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "X-Transaction-Id": transaction_id,
            "X-Correlation-Id": correlation_id,
        },
        "body": json.dumps(
            {
                "transactionId": transaction_id,
                "correlationId": correlation_id,
                "error": err_obj,
            },
            default=str,
        ),
    }


def canonical_success(
    transaction_id: str,
    correlation_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Build canonical success response with transactionId, correlationId, responseBody."""
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "X-Transaction-Id": transaction_id,
            "X-Correlation-Id": correlation_id,
        },
        "body": json.dumps(
            {
                "transactionId": transaction_id,
                "correlationId": correlation_id,
                "responseBody": body,
            },
            default=str,
        ),
    }


# --- Redrive ---


def _normalize_event(event: dict[str, Any]) -> None:
    """Normalize HTTP API v2 or REST API event to consistent path, pathParameters, httpMethod."""
    if "path" not in event and "rawPath" in event:
        event["path"] = event["rawPath"]
    path = event.get("path") or event.get("rawPath") or ""
    # REST API includes stage in path (e.g. /prod/v1/...); strip for routing
    parts = path.strip("/").split("/")
    if len(parts) >= 2 and parts[1] == "v1":
        event["path"] = "/" + "/".join(parts[1:])
    elif path and not path.startswith("/v1"):
        idx = next((i for i, p in enumerate(parts) if p == "v1"), None)
        if idx is not None:
            event["path"] = "/" + "/".join(parts[idx:])
    if "pathParameters" not in event or not event["pathParameters"]:
        rc = event.get("requestContext") or {}
        params = event.get("pathParameters") or rc.get("pathParameters") or {}
        event["pathParameters"] = params
    if "httpMethod" not in event:
        event["httpMethod"] = (
            event.get("requestContext", {}).get("http", {}).get("method", "")
        ).upper()


def _get_transaction_by_id(conn: Any, transaction_id: str) -> dict[str, Any] | None:
    """Fetch transaction by transaction_id."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, transaction_id, correlation_id, status, request_body,
                   source_vendor, target_vendor, operation, idempotency_key, redrive_count
            FROM data_plane.transactions
            WHERE transaction_id = %s
            """,
            (transaction_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _execute_routing_for_redrive(
    transaction_id: str,
    correlation_id: str,
    source: str,
    target: str,
    operation: str,
    parameters: dict[str, Any],
    original_tx_id: str,
) -> tuple[bool, int, dict[str, Any], dict[str, Any] | None]:
    """
    Execute routing path: contracts, mappings, validate control plane, downstream.
    Returns (success, status_code, response_body, error_dict).
    Same logic as /execute minus idempotency lookup/insert.
    Does not hold DB conn during downstream HTTP call.
    """
    with _get_connection() as conn:
        canonical_version = load_operation_version(conn, operation)
        if canonical_version is None:
            op_err = operation_not_found()
            update_transaction_failure(conn, transaction_id, "validation_failed", response_body=to_response_body(op_err), taxonomy_err=op_err)
            write_audit_event(conn, transaction_id, source, "OPERATION_NOT_FOUND", {"code": op_err["code"]})
            return False, op_err["http_status"], to_response_body(op_err), op_err

        canonical_contract = load_operation_contract(conn, operation, canonical_version)
        source_contract = load_operation_contract(conn, operation, canonical_version, vendor_code=source)
        target_contract = load_operation_contract(conn, operation, canonical_version, vendor_code=target)
        if source_contract is None or canonical_contract is None or target_contract is None:
            msg = "No active contract for this operation/vendor pair" if source_contract is None else "No active canonical contract" if canonical_contract is None else "No active contract for this operation/vendor pair"
            c_err = contract_not_found(msg)
            update_transaction_failure(conn, transaction_id, "validation_failed", response_body=to_response_body(c_err), taxonomy_err=c_err)
            write_audit_event(conn, transaction_id, source, "CONTRACT_NOT_FOUND", {"code": c_err["code"]})
            return False, c_err["http_status"], to_response_body(c_err), c_err

        # Source request mapping (optional): TO_CANONICAL_REQUEST or TO_CANONICAL
        source_request_mapping = load_vendor_mapping(conn, source, operation, canonical_version, TO_CANONICAL_REQUEST)
        if source_request_mapping is None:
            source_request_mapping = load_vendor_mapping(conn, source, operation, canonical_version, "TO_CANONICAL")

        if source_request_mapping is not None:
            if source_contract.get("request_schema"):
                try:
                    validate_request_schema(parameters, source_contract["request_schema"])
                except Exception as schema_err:
                    violations = _format_jsonschema_violations(schema_err) if (jsonschema and isinstance(schema_err, jsonschema.ValidationError)) else [str(schema_err)]
                    s_err = schema_validation_failed("Schema validation failed", violations, stage="source")
                    update_transaction_failure(conn, transaction_id, "validation_failed", response_body=to_response_body(s_err), taxonomy_err=s_err)
                    write_audit_event(conn, transaction_id, source, "SCHEMA_VALIDATION_FAILED", {"code": s_err["code"], "violations": violations})
                    return False, s_err["http_status"], to_response_body(s_err), s_err
            canonical_payload, mapping_violations = apply_mapping(parameters, source_request_mapping)
            if mapping_violations:
                m_err = mapping_failed("Source request mapping violations", mapping_violations)
                update_transaction_failure(conn, transaction_id, "mapping_failed", response_body=to_response_body(m_err), taxonomy_err=m_err, canonical_request_body=canonical_payload)
                write_audit_event(conn, transaction_id, source, "MAPPING_FAILED", {"code": m_err["code"], "direction": TO_CANONICAL_REQUEST, "violations": mapping_violations})
                return False, m_err["http_status"], to_response_body(m_err), m_err
        else:
            canonical_payload = dict(parameters) if isinstance(parameters, dict) else parameters

        target_mapping = load_vendor_mapping(conn, target, operation, canonical_version, "FROM_CANONICAL")

        if canonical_contract.get("request_schema"):
            try:
                validate_request_schema(canonical_payload, canonical_contract["request_schema"])
            except Exception as schema_err:
                violations = _format_jsonschema_violations(schema_err) if (jsonschema and isinstance(schema_err, jsonschema.ValidationError)) else [str(schema_err)]
                s_err = schema_validation_failed("Canonical schema validation failed", violations, stage="canonical")
                update_transaction_failure(conn, transaction_id, "validation_failed", response_body=to_response_body(s_err), taxonomy_err=s_err, canonical_request_body=canonical_payload)
                write_audit_event(conn, transaction_id, source, "SCHEMA_VALIDATION_FAILED", {"code": s_err["code"], "violations": violations})
                return False, s_err["http_status"], to_response_body(s_err), s_err

        if target_mapping is not None:
            target_payload, mapping_violations = apply_mapping(canonical_payload, target_mapping)
            if mapping_violations:
                m_err = mapping_failed("Target mapping violations", mapping_violations)
                update_transaction_failure(conn, transaction_id, "mapping_failed", response_body=to_response_body(m_err), taxonomy_err=m_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
                write_audit_event(conn, transaction_id, source, "MAPPING_FAILED", {"code": m_err["code"], "violations": mapping_violations})
                return False, m_err["http_status"], to_response_body(m_err), m_err
        else:
            target_payload = dict(canonical_payload) if isinstance(canonical_payload, dict) else canonical_payload
            if target_contract.get("request_schema"):
                try:
                    validate_request_schema(target_payload, target_contract["request_schema"])
                except Exception as schema_err:
                    violations = _format_jsonschema_violations(schema_err) if (jsonschema and isinstance(schema_err, jsonschema.ValidationError)) else [str(schema_err)]
                    mn_err = mapping_not_found(
                        "Missing active mapping FROM_CANONICAL for target vendor; canonical payload does not conform to target request schema",
                        direction="FROM_CANONICAL",
                        violations=violations,
                    )
                    update_transaction_failure(conn, transaction_id, "mapping_failed", response_body=to_response_body(mn_err), taxonomy_err=mn_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
                    write_audit_event(conn, transaction_id, source, "MAPPING_NOT_FOUND", {"code": mn_err["code"], "direction": "FROM_CANONICAL", "violations": violations})
                    return False, mn_err["http_status"], to_response_body(mn_err), mn_err

        if target_contract.get("request_schema") and target_mapping is not None:
            try:
                validate_request_schema(target_payload, target_contract["request_schema"])
            except Exception as schema_err:
                violations = _format_jsonschema_violations(schema_err) if (jsonschema and isinstance(schema_err, jsonschema.ValidationError)) else [str(schema_err)]
                s_err = schema_validation_failed("Target schema validation failed", violations, stage="target")
                update_transaction_failure(conn, transaction_id, "validation_failed", response_body=to_response_body(s_err), taxonomy_err=s_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
                write_audit_event(conn, transaction_id, source, "SCHEMA_VALIDATION_FAILED", {"code": s_err["code"], "violations": violations})
                return False, s_err["http_status"], to_response_body(s_err), s_err

        with _xray_subsegment("db_lookup"):
            endpoint = validate_control_plane(conn, source, target, operation)
        with conn.cursor() as cur:
            cur.execute("SET LOCAL app.vendor_code = %s", (source,))
        write_audit_event(
            conn,
            transaction_id,
            source,
            "ROUTE_START",
            {"target": target, "operation": operation, "original_transaction_id": original_tx_id},
        )

    # Invariant: HTTP body = exactly target_request (or canonical when no mapping). IDs in headers only.
    vendor_body = _build_vendor_body(target_payload, canonical_payload)
    auth_profile = endpoint.get("auth_profile")
    try:
        downstream_headers, downstream_params, headers_audit = build_downstream_headers(
            transaction_id, correlation_id, auth_profile,
            vendor_code=target, operation=operation,
        )
    except ValueError as e:
        cfg_err = build_error(
            ErrorCode.INTERNAL_ERROR,
            "Auth profile misconfigured for target endpoint",
            http_status=500,
            details={"targetVendor": target, "operation": operation, "message": str(e)},
        )
        with _get_connection() as conn:
            update_transaction_failure(conn, transaction_id, "downstream_error", response_body=to_response_body(cfg_err), taxonomy_err=cfg_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
        return False, cfg_err["http_status"], to_response_body(cfg_err), cfg_err
    with _get_connection() as conn:
        write_audit_event(
            conn, transaction_id, source, "DOWNSTREAM_HEADERS_BUILT",
            headers_audit,
        )
        if auth_profile and headers_audit.get("authType") not in (None, "NONE"):
            write_audit_event(conn, transaction_id, source, "DOWNSTREAM_AUTH_APPLIED", {"authType": headers_audit.get("authType"), "vendorCode": target, "operation": operation})
    payload_fmt = (endpoint.get("payload_format") or "json").strip().lower()
    with _xray_subsegment("downstream_http"):
        try:
            status_code, downstream_body, binary_request_meta = call_downstream(
                endpoint["url"],
                endpoint.get("timeout_ms") or 8000,
                vendor_body,
                endpoint.get("http_method"),
                headers=downstream_headers,
                params=downstream_params,
                payload_format=endpoint.get("payload_format"),
                content_type_override=endpoint.get("content_type"),
            )
        except requests.exceptions.Timeout:
            emit_metric("DownstreamTimeout", operation=operation or "-", source_vendor=source, target_vendor=target)
            t_err = downstream_timeout()
            with _get_connection() as conn:
                update_transaction_failure(conn, transaction_id, "downstream_error", response_body=to_response_body(t_err), taxonomy_err=t_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
                write_audit_event(conn, transaction_id, source, "DOWNSTREAM_TIMEOUT", {"code": t_err["code"], "original_transaction_id": original_tx_id})
            return False, t_err["http_status"], to_response_body(t_err), t_err
        except PayloadFormatError as e:
            cfg_err = build_error(
                ErrorCode.INTERNAL_ERROR,
                f"Payload format misconfiguration: {e}",
                http_status=400,
                details={"targetVendor": target, "operation": operation, "message": str(e)},
            )
            with _get_connection() as conn:
                update_transaction_failure(conn, transaction_id, "downstream_error", response_body=to_response_body(cfg_err), taxonomy_err=cfg_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
            return False, cfg_err["http_status"], to_response_body(cfg_err), cfg_err

    target_request_to_persist: Any = (
        binary_request_meta
        if (payload_fmt == "binary" and binary_request_meta)
        else target_payload
    )
    with _get_connection() as conn:
        if 200 <= status_code < 300:
            target_response = downstream_body
            if isinstance(target_response, dict) and "raw" in target_response:
                inv_err = downstream_invalid_response(raw=target_response.get("raw", ""))
                update_transaction_failure(conn, transaction_id, "downstream_error", response_body=to_response_body(inv_err), taxonomy_err=inv_err, canonical_request_body=canonical_payload, target_request_body=target_request_to_persist, target_response_body=target_response)
                write_audit_event(conn, transaction_id, source, "DOWNSTREAM_INVALID_RESPONSE", {"code": inv_err["code"], "statusCode": status_code})
                return False, inv_err["http_status"], to_response_body(inv_err), inv_err
            write_audit_event(conn, transaction_id, source, "DOWNSTREAM_RESPONSE_RECEIVED", {"statusCode": status_code})
            if target_contract and target_contract.get("response_schema"):
                try:
                    validate_request_schema(target_response, target_contract["response_schema"])
                except Exception as schema_err:
                    violations = _format_jsonschema_violations(schema_err) if (jsonschema and isinstance(schema_err, jsonschema.ValidationError)) else [str(schema_err)]
                    s_err = schema_validation_failed("Target response schema validation failed", violations, stage="target_response")
                    update_transaction_failure(conn, transaction_id, "validation_failed", response_body=to_response_body(s_err), taxonomy_err=s_err, canonical_request_body=canonical_payload, target_request_body=target_request_to_persist, target_response_body=target_response)
                    write_audit_event(conn, transaction_id, source, "SCHEMA_VALIDATION_FAILED", {"code": s_err["code"], "violations": violations})
                    return False, s_err["http_status"], to_response_body(s_err), s_err
            canonical_response, source_response, pipeline_err = _process_response_pipeline(
                conn, transaction_id, source, target, operation, canonical_version,
                target_contract, canonical_contract, target_response,
            )
            if pipeline_err is not None:
                _status = (
                    "mapping_failed"
                    if pipeline_err.get("code") in ("MAPPING_NOT_FOUND", "MAPPING_FAILED")
                    else "downstream_error"
                    if pipeline_err.get("code") == "DOWNSTREAM_INVALID_RESPONSE"
                    else "validation_failed"
                )
                update_transaction_failure(conn, transaction_id, _status, response_body=to_response_body(pipeline_err), taxonomy_err=pipeline_err, canonical_request_body=canonical_payload, target_request_body=target_request_to_persist, target_response_body=target_response, canonical_response_body=canonical_response)
                return False, pipeline_err["http_status"], to_response_body(pipeline_err), pipeline_err
            api_response_body = {"transactionId": transaction_id, "correlationId": correlation_id, "sourceVendor": source, "targetVendor": target, "operation": operation, "status": "completed", "responseBody": source_response}
            update_transaction_success(
                conn, transaction_id, source_response,
                canonical_request=canonical_payload, target_request=target_request_to_persist,
                target_response_body=target_response, canonical_response_body=canonical_response,
                http_status=status_code,
            )
            write_audit_event(conn, transaction_id, source, "REDRIVE_SUCCESS", {"original_transaction_id": original_tx_id, "statusCode": status_code})
            return True, status_code, api_response_body, None
        else:
            # Downstream >= 400: status=downstream_error, return immediately. DO NOT apply TO_CANONICAL_RESPONSE
            # mapping or response schema validation. Store downstream_http_error_response_body shape.
            http_err = downstream_http_error(status_code, downstream_body)
            target_resp = downstream_body if isinstance(downstream_body, dict) else None
            response_body = downstream_http_error_response_body(status_code, downstream_body, vendor_code=target, operation=operation)
            update_transaction_failure(conn, transaction_id, "downstream_error", response_body=response_body, taxonomy_err=http_err, canonical_request_body=canonical_payload, target_request_body=target_request_to_persist, target_response_body=target_resp)
            write_audit_event(
                conn, transaction_id, source, "ROUTE_DOWNSTREAM_ERROR",
                {"vendorStatusCode": status_code, "targetVendor": target, "operation": operation},
            )
            return False, http_err["http_status"], to_response_body(http_err), http_err


def handle_redrive(event: dict[str, Any]) -> dict[str, Any]:
    """
    POST /v1/admin/redrive/{transactionId}
    Full redrive: load original, validate request_body, rehydrate, create linked row, execute routing.
    Requires JWT (Authorization: Bearer) with admin role.
    """
    auth_err = require_admin_secret(event)
    if auth_err:
        return add_cors_to_response(auth_err)
    path_params = event.get("pathParameters") or {}
    path = event.get("path") or event.get("rawPath", "")
    segments = [s for s in path.strip("/").split("/") if s]
    transaction_id_param = path_params.get("transactionId") or (
        segments[3] if len(segments) >= 4 and segments[:3] == ["v1", "admin", "redrive"] else None
    )
    if not transaction_id_param or not transaction_id_param.strip():
        fallback_id = str(uuid.uuid4())
        return canonical_error(
            "VALIDATION_ERROR",
            "transactionId path parameter is required",
            fallback_id,
            fallback_id,
            status_code=400,
        )

    original_tx_id = transaction_id_param.strip()
    new_transaction_id = str(uuid.uuid4())
    new_correlation_id = str(uuid.uuid4())

    try:
        with _get_connection() as conn:
            orig = _get_transaction_by_id(conn, original_tx_id)
            if not orig:
                write_audit_event(
                    conn,
                    original_tx_id,
                    "system",
                    "REDRIVE_NOT_FOUND",
                    {"requested_transaction_id": original_tx_id},
                )
                return canonical_error(
                    "NOT_FOUND",
                    "Transaction not found",
                    original_tx_id,
                    new_correlation_id,
                    status_code=404,
                )

            request_body = orig.get("request_body")
            if request_body is None or not isinstance(request_body, dict):
                return canonical_error(
                    "REDRIVE_NOT_POSSIBLE",
                    "Cannot redrive: original transaction has no request_body",
                    original_tx_id,
                    orig["correlation_id"],
                    status_code=400,
                )

            source = _normalize_str(request_body.get("sourceVendor")) or orig.get("source_vendor")
            target = _normalize_str(request_body.get("targetVendor")) or orig.get("target_vendor")
            operation = _normalize_str(request_body.get("operation")) or orig.get("operation")
            parameters = request_body.get("parameters") if isinstance(request_body.get("parameters"), dict) else {}
            if source is None or target is None or operation is None:
                return canonical_error(
                    "REDRIVE_NOT_POSSIBLE",
                    "Cannot redrive: request_body missing required fields (sourceVendor, targetVendor, operation)",
                    original_tx_id,
                    orig["correlation_id"],
                    status_code=400,
                )

            orig_redrive_count = orig.get("redrive_count") or 0
            new_redrive_count = orig_redrive_count + 1
            orig_idempotency = orig.get("idempotency_key")
            new_idempotency_key = (
                f"{orig_idempotency}:redrive:{new_redrive_count}"
                if orig_idempotency
                else None
            )

            rehydrated_request = {
                "sourceVendor": source,
                "targetVendor": target,
                "operation": operation,
                "parameters": parameters,
                "idempotencyKey": new_idempotency_key,
                "correlationId": new_correlation_id,
            }

            write_audit_event(
                conn,
                original_tx_id,
                orig.get("source_vendor") or source,
                "REDRIVE_REQUESTED",
                {"new_transaction_id": new_transaction_id},
            )

            redrive_ctx = {
                "transaction_id": new_transaction_id,
                "correlation_id": new_correlation_id,
                "source_vendor": source,
                "target_vendor": target,
                "operation": operation,
            }
            log_json("INFO", "redrive_start", ctx=redrive_ctx, original_transaction_id=original_tx_id)
            emit_metric("RedriveRequested", operation=operation or "-", source_vendor=source, target_vendor=target)

            create_transaction_record(
                conn,
                new_transaction_id,
                new_correlation_id,
                source,
                target,
                operation,
                new_idempotency_key,
                status="received",
                request_body=rehydrated_request,
                response_body=None,
                parent_transaction_id=orig["id"],
                redrive_count=new_redrive_count,
            )
            write_audit_event(
                conn,
                new_transaction_id,
                "system",
                "AUTH_ADMIN_JWT_SUCCEEDED",
                {"redrive_of": original_tx_id},
            )
        # Connection committed/closed here - child row is now visible to _execute_routing_for_redrive

        success, status_code, response_body, error_info = _execute_routing_for_redrive(
            new_transaction_id,
            new_correlation_id,
            source,
            target,
            operation,
            parameters,
            original_tx_id,
        )

        log_json(
            "INFO",
            "redrive_stop",
            ctx={"transaction_id": new_transaction_id, "correlation_id": new_correlation_id},
            original_transaction_id=original_tx_id,
            success=success,
            status_code=status_code,
        )

        if success:
            emit_metric("RedriveSuccess", operation=operation or "-", source_vendor=source, target_vendor=target)
            api_response = {
                "parentTransactionId": original_tx_id,
                "redriveCount": new_redrive_count,
                "status": "completed",
                "response": response_body.get("downstream") if isinstance(response_body, dict) else response_body,
                "error": None,
                "replayed": False,
            }
            return canonical_success(new_transaction_id, new_correlation_id, api_response)
        else:
            emit_metric("RedriveFailed", operation=operation or "-", source_vendor=source, target_vendor=target)
            err = error_info or build_error("INTERNAL_ERROR", "Redrive failed", http_status=502)
            redrive_details = {"parentTransactionId": original_tx_id, "redriveCount": new_redrive_count}
            if isinstance(response_body, dict):
                redrive_details["response"] = response_body
            err_with_meta = {**err, "details": {**(err.get("details") or {}), **redrive_details}}
            return _err_from(err_with_meta, new_transaction_id, new_correlation_id)

    except EndpointNotVerifiedError as e:
        log_json("WARN", "endpoint_not_verified", ctx=get_current_ctx(), error=str(e), original_transaction_id=original_tx_id)
        ep_err = endpoint_not_verified(str(e))
        try:
            with _get_connection() as conn:
                write_audit_event(conn, new_transaction_id, source, "ENDPOINT_NOT_VERIFIED", {"code": ep_err["code"], "target": target, "operation": operation})
        except Exception:
            pass
        return _err_from(ep_err, new_transaction_id, new_correlation_id)
    except OAuthTokenFetchError as e:
        auth_err = e.canonical_error
        log_json("WARN", "oauth_token_fetch_failed", ctx=get_current_ctx(), authType="OAUTH2_CLIENT_CREDENTIALS", vendor_code=target, operation=operation, status="failure")
        try:
            with _get_connection() as conn:
                update_transaction_failure(conn, new_transaction_id, "auth_error", response_body=to_response_body(auth_err), taxonomy_err=auth_err)
                write_audit_event(conn, new_transaction_id, source, "OAUTH_TOKEN_FETCH_FAILED", {"code": auth_err.get("code")})
        except Exception:
            pass
        return _err_from(auth_err, new_transaction_id, new_correlation_id)
    except ValueError as e:
        val_err = allowlist_denied(str(e)) if "Allowlist" in str(e) else build_error("NOT_FOUND", str(e), http_status=400)
        try:
            with _get_connection() as conn:
                write_audit_event(conn, original_tx_id, "system", "REDRIVE_VALIDATION_FAILED", {"code": val_err["code"], "error": str(e)})
        except Exception:
            pass
        return _err_from(val_err, new_transaction_id, new_correlation_id)
    except (psycopg2.Error, ConnectionError) as e:
        db_err = db_error(str(e) if isinstance(e, ConnectionError) else "Database error", exc_type=type(e).__name__)
        try:
            with _get_connection() as conn:
                write_audit_event(conn, new_transaction_id, "system", "REDRIVE_DB_ERROR", {"code": db_err["code"]})
        except Exception:
            pass
        return _err_from(db_err, new_transaction_id, new_correlation_id)
    except Exception as e:
        int_err = internal_error(str(e), exc_type=type(e).__name__)
        try:
            with _get_connection() as conn:
                write_audit_event(conn, new_transaction_id, "system", "REDRIVE_INTERNAL_ERROR", {"code": int_err["code"]})
        except Exception:
            pass
        return _err_from(int_err, new_transaction_id, new_correlation_id)


# --- Handler ---


def _handler_impl(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Routing Lambda entry point."""
    _normalize_event(event)

    # Redrive route: POST /v1/admin/redrive/{transactionId} uses JWT (admin).
    # sourceVendor comes from original transaction's request_body, not from auth.
    method = event.get("httpMethod", event.get("requestContext", {}).get("http", {}).get("method", "")).upper()
    path = event.get("path") or event.get("rawPath", "")
    if method == "POST":
        segments = [s for s in path.strip("/").split("/") if s]
        if len(segments) == 4 and segments[:3] == ["v1", "admin", "redrive"]:
            return handle_redrive(event)

    ctx = get_current_ctx() or get_context(event, context)
    transaction_id = ctx["transaction_id"]
    correlation_id = ctx["correlation_id"]
    ctx.setdefault("source_vendor", None)
    ctx.setdefault("target_vendor", None)
    ctx.setdefault("operation", None)

    def err(status_code: int, code: str, msg: str, details: dict[str, Any] | None = None):
        return canonical_error(code, msg, transaction_id, correlation_id, status_code, details)

    def err_t(taxonomy_err: dict[str, Any]):
        return _err_from(taxonomy_err, transaction_id, correlation_id)

    # -------------------------------------------------------------------------
    # AUTH FLOW (Vendor Execute: POST /v1/integrations/execute) — JWT only
    # -------------------------------------------------------------------------
    # Authorization: Bearer <token> required. Body.sourceVendor is always ignored.
    # -------------------------------------------------------------------------
    headers = event.get("headers") or {}
    h_lower = {k.lower(): v for k, v in (headers or {}).items()}
    auth_header_raw = h_lower.get("authorization")
    auth_header = str(auth_header_raw).strip() if auth_header_raw else ""
    has_bearer = auth_header.lower().startswith("bearer ")

    source: str | None = None

    if has_bearer:
        jwt_config = load_jwt_auth_config_from_env()
        if not jwt_config:
            auth_err = auth_error("JWT auth not configured. Set IDP_JWKS_URL to enable.")
            _emit_route_failed(None, transaction_id, "system", auth_err)
            emit_metric("ExecuteAuthFailed", operation=ctx.get("operation") or "-")
            log_json("WARN", "AUTH_ERROR", ctx=ctx, error="JWT auth not configured")
            return err_t(auth_err)
        try:
            result = validate_jwt_and_map_vendor(auth_header, jwt_config, None)
            vendor_code_from_jwt = result.vendor_code
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT vendor_code, COALESCE(is_active, true) AS is_active
                        FROM control_plane.vendors WHERE vendor_code = %s
                        """,
                        (vendor_code_from_jwt,),
                    )
                    row = cur.fetchone()
            if row is None:
                vnf = vendor_not_found(f"Vendor '{vendor_code_from_jwt}' not provisioned")
                with _get_connection() as conn:
                    write_audit_event(
                        conn, transaction_id, "system", "AUTH_JWT_FAILED",
                        {"reason": "vendor_not_found", "vendor_code": vendor_code_from_jwt},
                    )
                _emit_route_failed(None, transaction_id, "system", vnf)
                emit_metric("ExecuteAuthFailed", operation=ctx.get("operation") or "-")
                return err_t(vnf)
            if not (row[1] if len(row) > 1 else True):
                forb_err = forbidden(f"Vendor '{vendor_code_from_jwt}' is inactive")
                with _get_connection() as conn:
                    write_audit_event(
                        conn, transaction_id, vendor_code_from_jwt, "AUTH_JWT_FAILED",
                        {"reason": "vendor_inactive", "vendor_code": vendor_code_from_jwt},
                    )
                _emit_route_failed(None, transaction_id, vendor_code_from_jwt, forb_err)
                emit_metric("ExecuteAuthFailed", operation=ctx.get("operation") or "-")
                return err_t(forb_err)
            source = vendor_code_from_jwt
            with _get_connection() as conn:
                write_audit_event(
                    conn,
                    transaction_id,
                    source,
                    "AUTH_JWT_SUCCEEDED",
                    {
                        "vendor_code": source,
                        "sub": str(result.claims.get("sub", ""))[:64],
                        "issuer": jwt_config.issuer,
                        "audience": jwt_config.audiences[0] if jwt_config.audiences else None,
                        "vendorClaim": jwt_config.vendor_claim,
                    },
                )
        except JwtValidationError as e:
            reason = e.code.lower() if e.code else "validation_failed"
            auth_err = auth_error(
                "Invalid or expired token" if "token" in reason or "expired" in reason else e.message
            )
            with _get_connection() as conn:
                write_audit_event(
                    conn, transaction_id, "system", "AUTH_JWT_FAILED",
                    {"reason": reason, "code": e.code, "message": e.message},
                )
            _emit_route_failed(None, transaction_id, "system", auth_err)
            emit_metric("ExecuteAuthFailed", operation=ctx.get("operation") or "-")
            log_json("WARN", "AUTH_ERROR", ctx=ctx, error=e.message)
            return err_t(auth_err)
        except Exception:
            raise

    if source is None:
        auth_err = auth_error("Missing Authorization")
        _emit_route_failed(None, transaction_id, "system", auth_err)
        emit_metric("ExecuteAuthFailed", operation=ctx.get("operation") or "-")
        log_json("WARN", "AUTH_ERROR", ctx=ctx, error="Missing Authorization")
        return err_t(auth_err)

    body_raw = event.get("body") or "{}"

    # 1) Parse body: request_body = parsed dict or {_raw}
    parse_error_msg = ""
    try:
        payload = json.loads(body_raw)
        request_body = payload if isinstance(payload, dict) else {}
        json_valid = True
    except json.JSONDecodeError as parse_err:
        payload = {}
        request_body = {"_raw": body_raw}
        json_valid = False
        parse_error_msg = str(parse_err)

    # 2) Extract fields. sourceVendor is from JWT (already set). Body: targetVendor, operation, parameters.
    payload_dict = payload if json_valid and isinstance(payload, dict) else {}
    target = _normalize_str(payload_dict.get("targetVendor"))
    operation = _normalize_str(payload_dict.get("operation"))
    requested_source_vendor_code = _normalize_str(
        payload_dict.get("sourceVendorCode") or payload_dict.get("sourceVendor")
    )
    ctx["source_vendor"] = source
    ctx["target_vendor"] = target
    ctx["operation"] = operation
    idempotency_raw = _normalize_str(payload_dict.get("idempotencyKey"))
    # Compute effective idempotency_key BEFORE any DB insert (required for lookup-before-insert)
    idempotency_key = idempotency_raw if idempotency_raw else str(uuid.uuid4())
    canonical_request_body = _canonical_request_body(request_body, source)

    # Audit: body.sourceVendor is never used for auth; if present, log AUTH_SOURCE_VENDOR_IGNORED.
    if json_valid and isinstance(request_body, dict) and request_body.get("sourceVendor"):
        try:
            with _get_connection() as conn:
                write_audit_event(
                    conn,
                    transaction_id,
                    source,
                    "AUTH_SOURCE_VENDOR_IGNORED",
                    {"message": "sourceVendor from body ignored; derived from JWT"},
                )
        except Exception:
            pass

    # 3) Idempotency lookup: AFTER auth, BEFORE transaction insert. Uses (source_vendor, idempotency_key).
    with _get_connection() as conn:
        with _xray_subsegment("idempotency_lookup"):
            cached = idempotency_lookup(conn, source, idempotency_key)
        if cached:
            tx_id = cached["transaction_id"]
            corr_id = cached["correlation_id"]
            ctx["transaction_id"] = tx_id
            ctx["correlation_id"] = corr_id
            resp_body = cached.get("response_body")
            if resp_body is not None:
                # Replay: return stored response
                emit_metric("Replay", operation=operation or "-", source_vendor=source, target_vendor=target)
                log_json("INFO", "replay", ctx=ctx, idempotency_key=idempotency_key)
                error_obj = None
                if isinstance(resp_body, dict) and "error" in resp_body:
                    error_obj = resp_body["error"]
                body = {
                    "transactionId": tx_id,
                    "correlationId": corr_id,
                    "replayed": True,
                    "status": cached["status"],
                    "response": resp_body if resp_body else None,
                    "error": error_obj,
                }
                write_audit_event(conn, tx_id, source, "REPLAY", {"idempotency_key": idempotency_key, "transaction_id": tx_id})
                return canonical_success(tx_id, corr_id, body)
            # In-flight: status=received (or started) and response_body null -> 409 IN_FLIGHT
            in_flight = in_flight_error(message="Request is still in progress", transaction_id=tx_id, status=cached.get("status", "received"))
            write_audit_event(conn, tx_id, source, "IN_FLIGHT", {"idempotency_key": idempotency_key, "transaction_id": tx_id, "status": cached.get("status", "received")})
            log_json("WARN", "in_flight", ctx=ctx, idempotency_key=idempotency_key, transaction_id=tx_id)
            return _err_from(in_flight, tx_id, corr_id)

    # 4) No cached row: create transaction only when proceeding. Handle validation errors first.
    if not json_valid:
        inv = invalid_json(parse_error_msg, body_raw)
        response_body_err = to_response_body(inv)
        try:
            with _get_connection() as conn:
                create_transaction_record(
                    conn,
                    transaction_id,
                    correlation_id,
                    source,
                    target,
                    operation,
                    idempotency_key,
                    status="validation_failed",
                    request_body=canonical_request_body,
                    response_body=response_body_err,
                )
                update_transaction_failure(
                    conn, transaction_id, "validation_failed",
                    response_body=response_body_err, taxonomy_err=inv,
                )
        except Exception:
            pass
        _emit_route_failed(None, transaction_id, source, inv, canonical_request=canonical_request_body)
        emit_metric("ExecuteValidationFailed", operation=ctx.get("operation") or "-", source_vendor=source, target_vendor=target)
        log_json("WARN", "validation_failed", ctx=ctx, decision="INVALID_JSON", error=parse_error_msg)
        return err_t(inv)

    # Reject deprecated vendor codes (no special-vendor logic)
    if target and str(target).strip().upper() in ("HUB", "LH000"):
        validation_msg = "Deprecated vendor codes are not accepted. Provide the actual target vendor code."
        schema_err = schema_validation_failed(validation_msg, violations=[validation_msg])
        response_body_err = to_response_body(schema_err)
        try:
            with _get_connection() as conn:
                create_transaction_record(
                    conn,
                    transaction_id,
                    correlation_id,
                    source,
                    target,
                    operation,
                    idempotency_key,
                    status="received",
                    request_body=canonical_request_body,
                )
                update_transaction_failure(
                    conn, transaction_id, "validation_failed",
                    response_body=response_body_err, taxonomy_err=schema_err,
                )
                _emit_route_failed(conn, transaction_id, source, schema_err, canonical_request=canonical_request_body)
        except Exception:
            pass
        emit_metric("ExecuteValidationFailed", operation=ctx.get("operation") or "-", source_vendor=source, target_vendor=target)
        log_json("WARN", "validation_failed", ctx=ctx, decision="DEPRECATED_VENDOR_CODE", error=validation_msg)
        return err_t(schema_err)

    if target is None or operation is None:
        missing = [f for f, v in [("targetVendor", target), ("operation", operation)] if v is None]
        validation_msg = f"{', '.join(missing)} is required and must be a non-empty string"
        schema_err = schema_validation_failed(validation_msg, violations=[validation_msg])
        response_body_err = to_response_body(schema_err)
        try:
            with _get_connection() as conn:
                create_transaction_record(
                    conn,
                    transaction_id,
                    correlation_id,
                    source,
                    target,
                    operation,
                    idempotency_key,
                    status="received",
                    request_body=canonical_request_body,
                )
                update_transaction_failure(
                    conn, transaction_id, "validation_failed",
                    response_body=response_body_err, taxonomy_err=schema_err,
                )
                _emit_route_failed(conn, transaction_id, source, schema_err, canonical_request=canonical_request_body)
        except Exception:
            pass
        emit_metric("ExecuteValidationFailed", operation=ctx.get("operation") or "-", source_vendor=source, target_vendor=target)
        log_json("WARN", "validation_failed", ctx=ctx, decision=schema_err["code"], error=validation_msg)
        return err_t(schema_err)

    # 5) Valid path: create transaction status='received' and proceed
    parameters_raw = payload_dict.get("parameters")
    parameters = parameters_raw if isinstance(parameters_raw, dict) else {}

    try:
        with _get_connection() as conn:
            # First-time: insert row (race-safe: UniqueViolation -> lookup and replay/IN_FLIGHT)
            try:
                with _xray_subsegment("db_write"):
                    create_transaction_record(
                        conn,
                        transaction_id,
                        correlation_id,
                        source,
                        target,
                        operation,
                        idempotency_key,
                        status="received",
                        request_body=canonical_request_body,
                    )
            except (psycopg2.errors.UniqueViolation, IdempotencyConflict):
                # Concurrent insert won race (UniqueViolation pre-v37, IdempotencyConflict v37+)
                with _xray_subsegment("idempotency_lookup"):
                    cached = idempotency_lookup(conn, source, idempotency_key)
                if cached:
                    tx_id = cached["transaction_id"]
                    corr_id = cached["correlation_id"]
                    ctx["transaction_id"] = tx_id
                    ctx["correlation_id"] = corr_id
                    resp_body = cached.get("response_body")
                    if resp_body is not None:
                        emit_metric("Replay", operation=operation or "-", source_vendor=source, target_vendor=target)
                        log_json("INFO", "replay", ctx=ctx, idempotency_key=idempotency_key)
                        error_obj = None
                        if isinstance(resp_body, dict) and "error" in resp_body:
                            error_obj = resp_body["error"]
                        body = {
                            "transactionId": tx_id,
                            "correlationId": corr_id,
                            "replayed": True,
                            "status": cached["status"],
                            "response": resp_body if resp_body else None,
                            "error": error_obj,
                        }
                        write_audit_event(conn, tx_id, source, "REPLAY", {"idempotency_key": idempotency_key, "transaction_id": tx_id})
                        return canonical_success(tx_id, corr_id, body)
                    in_flight = in_flight_error(message="Request is still in progress", transaction_id=tx_id, status=cached.get("status", "received"))
                    write_audit_event(conn, tx_id, source, "IN_FLIGHT", {"idempotency_key": idempotency_key, "transaction_id": tx_id, "status": cached.get("status", "received")})
                    log_json("WARN", "in_flight", ctx=ctx, idempotency_key=idempotency_key, transaction_id=tx_id)
                    return _err_from(in_flight, tx_id, corr_id)
                raise  # unexpected: lookup failed after duplicate insert

            with _xray_subsegment("db_write"):
                update_transaction_status(conn, transaction_id, "started", idempotency_key=idempotency_key)

            # 4) Load operation canonical_version
            with _xray_subsegment("db_lookup"):
                canonical_version = load_operation_version(conn, operation)
            if canonical_version is None:
                op_err = operation_not_found()
                response_body = to_response_body(op_err)
                update_transaction_failure(conn, transaction_id, "validation_failed", response_body=response_body, taxonomy_err=op_err)
                write_audit_event(conn, transaction_id, source, "OPERATION_NOT_FOUND", {"code": op_err["code"], "message": op_err["message"]})
                _emit_route_failed(conn, transaction_id, source, op_err)
                emit_metric("ExecuteValidationFailed", operation=operation or "-", source_vendor=source, target_vendor=target)
                return err_t(op_err)

            # 5) Load contracts: canonical, source vendor, target vendor
            with _xray_subsegment("db_lookup"):
                canonical_contract = load_operation_contract(conn, operation, canonical_version)
                source_contract = load_operation_contract(conn, operation, canonical_version, vendor_code=source)
                target_contract = load_operation_contract(conn, operation, canonical_version, vendor_code=target)
            if source_contract is None:
                c_err = contract_not_found("No active contract for this operation/vendor pair")
                response_body = to_response_body(c_err)
                update_transaction_failure(conn, transaction_id, "validation_failed", response_body=response_body, taxonomy_err=c_err)
                write_audit_event(conn, transaction_id, source, "CONTRACT_NOT_FOUND", {"code": c_err["code"], "message": c_err["message"]})
                _emit_route_failed(conn, transaction_id, source, c_err)
                emit_metric("ExecuteValidationFailed", operation=operation or "-", source_vendor=source, target_vendor=target)
                return err_t(c_err)
            if canonical_contract is None:
                c_err = contract_not_found("No active canonical contract")
                response_body = to_response_body(c_err)
                update_transaction_failure(conn, transaction_id, "validation_failed", response_body=response_body, taxonomy_err=c_err)
                write_audit_event(conn, transaction_id, source, "CONTRACT_NOT_FOUND", {"code": c_err["code"], "message": c_err["message"]})
                _emit_route_failed(conn, transaction_id, source, c_err)
                return err_t(c_err)
            if target_contract is None:
                c_err = contract_not_found("No active contract for this operation/vendor pair")
                response_body = to_response_body(c_err)
                update_transaction_failure(conn, transaction_id, "validation_failed", response_body=response_body, taxonomy_err=c_err)
                write_audit_event(conn, transaction_id, source, "CONTRACT_NOT_FOUND", {"code": c_err["code"], "message": c_err["message"]})
                _emit_route_failed(conn, transaction_id, source, c_err)
                return err_t(c_err)

            # --- Request pipeline (source -> canonical -> target) ---
            # 6) SOURCE REQUEST MAPPING (optional, TO_CANONICAL_REQUEST): parameters -> canonical_request
            #    If mapping exists: validate params vs source schema, apply mapping; on path-missing -> MAPPING_FAILED.
            #    If no mapping: parameters = canonical_request (pass-through).
            #    Applied BEFORE canonical schema validation.
            # Canonical request and canonical response are always validated against canonical schemas.
            with _xray_subsegment("db_lookup"):
                source_request_mapping = load_vendor_mapping(conn, source, operation, canonical_version, TO_CANONICAL_REQUEST)
                if source_request_mapping is None:
                    source_request_mapping = load_vendor_mapping(conn, source, operation, canonical_version, "TO_CANONICAL")

            if source_request_mapping is not None:
                # Optional source schema validation when mapping exists (params in source format)
                if source_contract.get("request_schema"):
                    with _xray_subsegment("schema_validate"):
                        try:
                            validate_request_schema(parameters, source_contract["request_schema"])
                        except Exception as schema_err:
                            violations: list[str] = []
                            if jsonschema is not None and isinstance(schema_err, jsonschema.ValidationError):
                                violations = _format_jsonschema_violations(schema_err)
                            else:
                                violations = [str(schema_err)]
                            schema_err_t = schema_validation_failed("Schema validation failed", violations, stage="source")
                            response_body = to_response_body(schema_err_t)
                            update_transaction_failure(conn, transaction_id, "validation_failed", response_body=response_body, taxonomy_err=schema_err_t)
                            write_audit_event(conn, transaction_id, source, "SCHEMA_VALIDATION_FAILED", {"code": schema_err_t["code"], "violations": violations})
                            _emit_route_failed(conn, transaction_id, source, schema_err_t, canonical_request=parameters)
                            emit_metric("ExecuteValidationFailed", operation=operation or "-", source_vendor=source, target_vendor=target)
                            return err_t(schema_err_t)
                # Apply source request mapping
                canonical_payload, mapping_violations = apply_mapping(parameters, source_request_mapping)
                if mapping_violations:
                    m_err = mapping_failed("Source request mapping violations", mapping_violations)
                    response_body = to_response_body(m_err)
                    update_transaction_failure(conn, transaction_id, "mapping_failed", response_body=response_body, taxonomy_err=m_err, canonical_request_body=canonical_payload)
                    write_audit_event(conn, transaction_id, source, "MAPPING_FAILED", {"code": m_err["code"], "direction": TO_CANONICAL_REQUEST, "violations": mapping_violations})
                    _emit_route_failed(conn, transaction_id, source, m_err, canonical_request=canonical_payload)
                    emit_metric("ExecuteValidationFailed", operation=operation or "-", source_vendor=source, target_vendor=target)
                    return err_t(m_err)
                write_audit_event(conn, transaction_id, source, "TRANSFORM_TO_CANONICAL_SUCCESS", {"direction": TO_CANONICAL_REQUEST})
            else:
                # No source request mapping: parameters are already canonical
                canonical_payload = dict(parameters) if isinstance(parameters, dict) else parameters

            # 7) Load target request mapping (FROM_CANONICAL) - unchanged
            with _xray_subsegment("db_lookup"):
                target_mapping = load_vendor_mapping(conn, target, operation, canonical_version, "FROM_CANONICAL")

            # 8) Validate canonical_request against canonical contract schema
            if canonical_contract.get("request_schema"):
                with _xray_subsegment("schema_validate"):
                    try:
                        validate_request_schema(canonical_payload, canonical_contract["request_schema"])
                    except Exception as schema_err:
                        violations = _format_jsonschema_violations(schema_err) if (jsonschema and isinstance(schema_err, jsonschema.ValidationError)) else [str(schema_err)]
                        schema_err_t = schema_validation_failed("Canonical schema validation failed", violations, stage="canonical")
                        response_body = to_response_body(schema_err_t)
                        update_transaction_failure(conn, transaction_id, "validation_failed", response_body=response_body, taxonomy_err=schema_err_t, canonical_request_body=canonical_payload)
                        write_audit_event(conn, transaction_id, source, "SCHEMA_VALIDATION_FAILED", {"code": schema_err_t["code"], "stage": "canonical", "violations": violations})
                        _emit_route_failed(conn, transaction_id, source, schema_err_t, canonical_request=canonical_payload)
                        return err_t(schema_err_t)

            write_audit_event(
                conn, transaction_id, source, "CANONICAL_VALIDATED",
                _audit_details(canonical_request=canonical_payload),
            )
            # 9) Apply FROM_CANONICAL mapping (or passthrough if target accepts canonical)
            if target_mapping is not None:
                target_payload, mapping_violations = apply_mapping(canonical_payload, target_mapping)
                if mapping_violations:
                    m_err = mapping_failed("Target mapping violations", mapping_violations)
                    response_body = to_response_body(m_err)
                    update_transaction_failure(conn, transaction_id, "mapping_failed", response_body=response_body, taxonomy_err=m_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
                    write_audit_event(conn, transaction_id, source, "MAPPING_FAILED", {"code": m_err["code"], "violations": mapping_violations})
                    _emit_route_failed(conn, transaction_id, source, m_err, canonical_request=canonical_payload, target_request=target_payload)
                    emit_metric("ExecuteValidationFailed", operation=operation or "-", source_vendor=source, target_vendor=target)
                    return err_t(m_err)
            else:
                # No FROM_CANONICAL: treat target_request = canonical_request. Validate canonical passes target schema.
                target_payload = dict(canonical_payload) if isinstance(canonical_payload, dict) else canonical_payload
                if target_contract.get("request_schema"):
                    try:
                        validate_request_schema(target_payload, target_contract["request_schema"])
                    except Exception as schema_err:
                        violations = _format_jsonschema_violations(schema_err) if (jsonschema and isinstance(schema_err, jsonschema.ValidationError)) else [str(schema_err)]
                        m_err = mapping_not_found(
                            "Missing active mapping FROM_CANONICAL for target vendor; canonical payload does not conform to target request schema",
                            direction="FROM_CANONICAL",
                            violations=violations,
                        )
                        response_body = to_response_body(m_err)
                        update_transaction_failure(conn, transaction_id, "mapping_failed", response_body=response_body, taxonomy_err=m_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
                        write_audit_event(conn, transaction_id, source, "MAPPING_NOT_FOUND", {"code": m_err["code"], "direction": "FROM_CANONICAL", "violations": violations})
                        _emit_route_failed(conn, transaction_id, source, m_err, canonical_request=canonical_payload, target_request=target_payload)
                        return err_t(m_err)
            write_audit_event(
                conn, transaction_id, source, "TARGET_REQUEST_MAPPED",
                _audit_details(canonical_request=canonical_payload, target_request=target_payload),
            )
            if target_contract.get("request_schema") and target_mapping is not None:
                with _xray_subsegment("schema_validate"):
                    try:
                        validate_request_schema(target_payload, target_contract["request_schema"])
                    except Exception as schema_err:
                        violations = _format_jsonschema_violations(schema_err) if (jsonschema and isinstance(schema_err, jsonschema.ValidationError)) else [str(schema_err)]
                        schema_err_t = schema_validation_failed("Target schema validation failed", violations, stage="target")
                        response_body = to_response_body(schema_err_t)
                        update_transaction_failure(conn, transaction_id, "validation_failed", response_body=response_body, taxonomy_err=schema_err_t, canonical_request_body=canonical_payload, target_request_body=target_payload)
                        write_audit_event(conn, transaction_id, source, "SCHEMA_VALIDATION_FAILED", {"code": schema_err_t["code"], "stage": "target", "violations": violations})
                        _emit_route_failed(conn, transaction_id, source, schema_err_t, canonical_request=canonical_payload, target_request=target_payload)
                        return err_t(schema_err_t)

            # 10) Continue existing checks: vendor_supported_operations, allowlist, endpoint
            policy_decision = evaluate_policy(
                PolicyContext(
                    surface="RUNTIME",
                    action="EXECUTE",
                    vendor_code=source,
                    target_vendor_code=target,
                    operation_code=operation,
                    requested_source_vendor_code=requested_source_vendor_code,
                    is_admin=False,
                    groups=[],
                    query={
                        "enforce_allowlist": False,
                        "transaction_id": transaction_id,
                        "correlation_id": correlation_id,
                    },
                ),
                conn=conn,
            )
            if not policy_decision.allow:
                pol_err = build_error(
                    policy_decision.decision_code,
                    policy_decision.message,
                    http_status=policy_decision.http_status,
                    details={"policy": policy_decision.metadata},
                )
                update_transaction_failure(
                    conn,
                    transaction_id,
                    "validation_failed",
                    response_body=to_response_body(pol_err),
                    taxonomy_err=pol_err,
                    canonical_request_body=canonical_payload,
                    target_request_body=target_payload,
                )
                write_audit_event(
                    conn,
                    transaction_id,
                    source,
                    "POLICY_DENIED",
                    {"code": policy_decision.decision_code},
                )
                _emit_route_failed(
                    conn,
                    transaction_id,
                    source,
                    pol_err,
                    canonical_request=canonical_payload,
                    target_request=target_payload,
                )
                return err_t(pol_err)

            with _xray_subsegment("db_lookup"):
                endpoint = validate_control_plane(conn, source, target, operation)

            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.vendor_code = %s", (source,))

            write_audit_event(
                conn, transaction_id, source, "ROUTE_START",
                _audit_details(canonical_request=canonical_payload, target_request=target_payload, target=target, operation=operation),
            )

        # Downstream call (outside transaction to avoid holding conn during HTTP)
        log_json("INFO", "downstream_call_start", ctx=ctx, url=endpoint.get("url"), operation=operation)
        with _get_connection() as conn:
            write_audit_event(
                conn, transaction_id, source, "DOWNSTREAM_CALLED",
                _audit_details(canonical_request=canonical_payload, target_request=target_payload),
            )
        # Invariant: HTTP body = exactly target_request (or canonical when no mapping). IDs in headers only.
        vendor_body = _build_vendor_body(target_payload, canonical_payload)
        auth_profile = endpoint.get("auth_profile")
        try:
            downstream_headers, downstream_params, headers_audit = build_downstream_headers(
                transaction_id, correlation_id, auth_profile,
                vendor_code=target, operation=operation,
            )
        except ValueError as e:
            cfg_err = build_error(
                ErrorCode.INTERNAL_ERROR,
                "Auth profile misconfigured for target endpoint",
                http_status=500,
                details={"targetVendor": target, "operation": operation, "message": str(e)},
            )
            with _get_connection() as conn:
                update_transaction_failure(conn, transaction_id, "downstream_error", response_body=to_response_body(cfg_err), taxonomy_err=cfg_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
            _emit_route_failed(None, transaction_id, source, cfg_err, canonical_request=canonical_payload, target_request=target_payload)
            return err_t(cfg_err)
        with _get_connection() as conn:
            write_audit_event(
                conn, transaction_id, source, "DOWNSTREAM_HEADERS_BUILT",
                headers_audit,
            )
            if auth_profile and headers_audit.get("authType") not in (None, "NONE"):
                write_audit_event(conn, transaction_id, source, "DOWNSTREAM_AUTH_APPLIED", {"authType": headers_audit.get("authType"), "vendorCode": target, "operation": operation})
        t0 = time.perf_counter()
        payload_fmt = (endpoint.get("payload_format") or "json").strip().lower()
        with _xray_subsegment("downstream_http"):
            try:
                status_code, downstream_body, binary_request_meta = call_downstream(
                    endpoint["url"],
                    endpoint.get("timeout_ms") or 8000,
                    vendor_body,
                    endpoint.get("http_method"),
                    headers=downstream_headers,
                    params=downstream_params,
                    payload_format=endpoint.get("payload_format"),
                    content_type_override=endpoint.get("content_type"),
                )
            except requests.exceptions.Timeout:
                emit_metric("DownstreamTimeout", operation=operation or "-", source_vendor=source, target_vendor=target)
                log_json("WARN", "downstream_timeout", ctx=ctx)
                timeout_err = downstream_timeout()
                with _get_connection() as conn:
                    update_transaction_failure(conn, transaction_id, "downstream_failed", response_body=to_response_body(timeout_err), taxonomy_err=timeout_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
                    write_audit_event(conn, transaction_id, source, "DOWNSTREAM_TIMEOUT", {"code": timeout_err["code"], "statusCode": 504})
                    _emit_route_failed(conn, transaction_id, source, timeout_err, canonical_request=canonical_payload, target_request=target_payload)
                return err_t(timeout_err)
            except PayloadFormatError as e:
                cfg_err = build_error(
                    ErrorCode.INTERNAL_ERROR,
                    f"Payload format misconfiguration: {e}",
                    http_status=400,
                    details={"targetVendor": target, "operation": operation, "message": str(e)},
                )
                with _get_connection() as conn:
                    update_transaction_failure(conn, transaction_id, "downstream_error", response_body=to_response_body(cfg_err), taxonomy_err=cfg_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
                    _emit_route_failed(conn, transaction_id, source, cfg_err, canonical_request=canonical_payload, target_request=target_payload)
                return err_t(cfg_err)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        log_json("INFO", "downstream_call_stop", ctx=ctx, status_code=status_code)

        target_request_to_persist: Any = (
            binary_request_meta
            if (payload_fmt == "binary" and binary_request_meta)
            else target_payload
        )
        with _get_connection() as conn:
            if 200 <= status_code < 300:
                target_response = downstream_body
                if isinstance(target_response, dict) and "raw" in target_response:
                    inv_resp_err = downstream_invalid_response(raw=target_response.get("raw", ""))
                    response_body_err = to_response_body(inv_resp_err)
                    update_transaction_failure(conn, transaction_id, "downstream_failed", response_body=response_body_err, taxonomy_err=inv_resp_err, canonical_request_body=canonical_payload, target_request_body=target_request_to_persist, target_response_body=target_response)
                    write_audit_event(
                        conn, transaction_id, source, "DOWNSTREAM_INVALID_RESPONSE",
                        {"code": inv_resp_err["code"], "statusCode": status_code, "elapsedMs": elapsed_ms},
                    )
                    _emit_route_failed(
                        conn, transaction_id, source, inv_resp_err,
                        canonical_request=canonical_payload, target_request=target_request_to_persist,
                        target_status_code=status_code, target_response=target_response,
                    )
                    emit_metric("DownstreamError", operation=operation or "-", source_vendor=source, target_vendor=target)
                    return err_t(inv_resp_err)

                write_audit_event(
                    conn, transaction_id, source, "TARGET_RESPONSE_RECEIVED",
                    _audit_details(
                        target_status_code=status_code,
                        target_response=target_response,
                        elapsed_ms=elapsed_ms,
                    ),
                )
                if target_contract and target_contract.get("response_schema"):
                    try:
                        validate_request_schema(target_response, target_contract["response_schema"])
                    except Exception as schema_err:
                        violations = (
                            _format_jsonschema_violations(schema_err)
                            if (jsonschema and isinstance(schema_err, jsonschema.ValidationError))
                            else [str(schema_err)]
                        )
                        schema_err_t = schema_validation_failed("Target response schema validation failed", violations, stage="target_response")
                        response_body_err = to_response_body(schema_err_t)
                        update_transaction_failure(conn, transaction_id, "validation_failed", response_body=response_body_err, taxonomy_err=schema_err_t, canonical_request_body=canonical_payload, target_request_body=target_request_to_persist, target_response_body=target_response)
                        write_audit_event(conn, transaction_id, source, "SCHEMA_VALIDATION_FAILED", {"code": schema_err_t["code"], "stage": "target_response", "violations": violations})
                        _emit_route_failed(
                            conn, transaction_id, source, schema_err_t,
                            canonical_request=canonical_payload, target_request=target_request_to_persist,
                            target_status_code=status_code, target_response=target_response,
                        )
                        emit_metric("ExecuteValidationFailed", operation=operation or "-", source_vendor=source, target_vendor=target)
                        return err_t(schema_err_t)

                # Response pipeline: TO_CANONICAL_RESPONSE (target->canonical), validate canonical,
                # then FROM_CANONICAL_RESPONSE (optional): canonical->source. If no source mapping,
                # source_response = canonical_response. On source mapping path-missing -> MAPPING_FAILED.
                canonical_response, source_response, pipeline_err = _process_response_pipeline(
                    conn, transaction_id, source, target, operation, canonical_version,
                    target_contract, canonical_contract, target_response,
                )
                if pipeline_err is None:
                    write_audit_event(
                        conn, transaction_id, source, "CANONICAL_RESPONSE_MAPPED",
                        _audit_details(
                            target_status_code=status_code,
                            target_response=target_response,
                            canonical_response=canonical_response,
                        ),
                    )
                if pipeline_err is not None:
                    response_body_err = to_response_body(pipeline_err)
                    _status = (
                        "mapping_failed"
                        if pipeline_err.get("code") in ("MAPPING_NOT_FOUND", "MAPPING_FAILED")
                        else "downstream_error"
                        if pipeline_err.get("code") == "DOWNSTREAM_INVALID_RESPONSE"
                        else "validation_failed"
                    )
                    update_transaction_failure(conn, transaction_id, _status, response_body=response_body_err, taxonomy_err=pipeline_err, canonical_request_body=canonical_payload, target_request_body=target_request_to_persist, target_response_body=target_response, canonical_response_body=canonical_response)
                    _emit_route_failed(
                        conn, transaction_id, source, pipeline_err,
                        canonical_request=canonical_payload, target_request=target_request_to_persist,
                        target_status_code=status_code, target_response=target_response,
                    )
                    emit_metric("ExecuteValidationFailed", operation=operation or "-", source_vendor=source, target_vendor=target)
                    return err_t(pipeline_err)

                with _xray_subsegment("db_write"):
                    api_response_body = {
                        "transactionId": transaction_id,
                        "correlationId": correlation_id,
                        "replayed": False,
                        "sourceVendor": source,
                        "targetVendor": target,
                        "operation": operation,
                        "status": "completed",
                        "responseBody": source_response,
                    }
                    # TODO(AI_FORMATTER): Read ai_presentation_mode, ai_formatter_prompt from operations.
                    # If != RAW_ONLY: would call Bedrock for human-friendly summary. For now only log.
                    try:
                        with conn.cursor(cursor_factory=RealDictCursor) as cur:
                            cur.execute(
                                "SELECT ai_presentation_mode FROM control_plane.operations WHERE operation_code = %s LIMIT 1",
                                (operation,),
                            )
                            op_row = cur.fetchone()
                        ai_mode = (op_row or {}).get("ai_presentation_mode") or "RAW_ONLY"
                        ai_summary_planned = ai_mode and str(ai_mode).strip().upper() != "RAW_ONLY"
                        log_json("INFO", "ai_formatter_hook", operation=operation, ai_summary_planned=ai_summary_planned)
                    except Exception:
                        pass
                    update_transaction_success(
                        conn,
                        transaction_id,
                        source_response,
                        canonical_request=canonical_payload,
                        target_request=target_request_to_persist,
                        target_response_body=target_response,
                        canonical_response_body=canonical_response,
                        http_status=status_code,
                    )
                    write_audit_event(
                        conn, transaction_id, source, "ROUTE_SUCCESS",
                        _audit_details(
                            target_status_code=status_code,
                            target_response=target_response,
                            canonical_response=canonical_response,
                        ),
                    )
                    emit_metric("ExecuteSuccess", operation=operation or "-", source_vendor=source, target_vendor=target)
                return canonical_success(transaction_id, correlation_id, api_response_body)
            else:
                # Downstream >= 400: status=downstream_error, return immediately. DO NOT apply TO_CANONICAL_RESPONSE
                # mapping or response schema validation. Store downstream_http_error_response_body shape.
                emit_metric("DownstreamError", operation=operation or "-", source_vendor=source, target_vendor=target)
                http_err = downstream_http_error(status_code, downstream_body)
                response_body = downstream_http_error_response_body(status_code, downstream_body, vendor_code=target, operation=operation)
                update_transaction_failure(
                    conn, transaction_id, "downstream_error",
                    response_body=response_body,
                    taxonomy_err=http_err,
                    canonical_request_body=canonical_payload,
                    target_request_body=target_request_to_persist,
                    target_response_body=downstream_body,
                )
                write_audit_event(
                    conn, transaction_id, source, "ROUTE_DOWNSTREAM_ERROR",
                    {"vendorStatusCode": status_code, "targetVendor": target, "operation": operation},
                )
                _emit_route_failed(
                    conn, transaction_id, source, http_err,
                    canonical_request=canonical_payload, target_request=target_request_to_persist,
                    target_status_code=status_code, target_response=downstream_body,
                )
                return err_t(http_err)

    except EndpointNotVerifiedError as e:
        log_json("WARN", "endpoint_not_verified", ctx=get_current_ctx(), error=str(e))
        ep_err = endpoint_not_verified(str(e))
        try:
            with _get_connection() as conn:
                update_transaction_failure(conn, transaction_id, "validation_failed", response_body=to_response_body(ep_err), taxonomy_err=ep_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
                write_audit_event(conn, transaction_id, source, "ENDPOINT_NOT_VERIFIED", {"code": ep_err["code"], "target": target, "operation": operation})
                _emit_route_failed(conn, transaction_id, source, ep_err, canonical_request=canonical_payload, target_request=target_payload)
        except Exception:
            pass
        return err_t(ep_err)

    except OAuthTokenFetchError as e:
        auth_err = e.canonical_error
        ctx = get_current_ctx()
        config = (endpoint.get("auth_profile") or {}).get("config") or {}
        log_json(
            "WARN", "oauth_token_fetch_failed",
            ctx=ctx,
            authType="OAUTH2_CLIENT_CREDENTIALS",
            tokenUrl=(config.get("tokenUrl") or "").strip()[:100] if config.get("tokenUrl") else None,
            headerName=config.get("headerName") or "Authorization",
            vendor_code=ctx.get("target_vendor"),
            operation=ctx.get("operation"),
            status="failure",
        )
        try:
            with _get_connection() as conn:
                update_transaction_failure(
                    conn, transaction_id, "auth_error",
                    response_body=to_response_body(auth_err), taxonomy_err=auth_err,
                    canonical_request_body=canonical_payload, target_request_body=target_payload,
                )
                write_audit_event(conn, transaction_id, source, "OAUTH_TOKEN_FETCH_FAILED", {"code": auth_err.get("code")})
                _emit_route_failed(conn, transaction_id, source, auth_err, canonical_request=canonical_payload, target_request=target_payload)
        except Exception:
            pass
        return err_t(auth_err)

    except ValueError as e:
        ctx = get_current_ctx()
        err_str = str(e)
        if "ALLOWLIST_VENDOR_DENIED" in err_str:
            emit_metric("ExecuteAllowlistVendorDenied", operation=ctx.get("operation") or "-", source_vendor=ctx.get("source_vendor"), target_vendor=ctx.get("target_vendor"))
            den_err = allowlist_vendor_denied(err_str.split(": ", 1)[-1] if ": " in err_str else err_str)
            log_json("WARN", "allowlist_vendor_denied", ctx=ctx, error=err_str)
            try:
                with _get_connection() as conn:
                    update_transaction_failure(conn, transaction_id, "validation_failed", response_body=to_response_body(den_err), taxonomy_err=den_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
                    write_audit_event(conn, transaction_id, source, "ALLOWLIST_VENDOR_DENIED", {"code": den_err["code"]})
                    _emit_route_failed(conn, transaction_id, source, den_err, canonical_request=canonical_payload, target_request=target_payload)
            except Exception:
                pass
            return err_t(den_err)
        if "Allowlist" in err_str:
            emit_metric("ExecuteAllowlistDenied", operation=ctx.get("operation") or "-", source_vendor=ctx.get("source_vendor"), target_vendor=ctx.get("target_vendor"))
            den_err = allowlist_denied(err_str)
            log_json("WARN", "allowlist_denied", ctx=ctx, error=str(e))
            try:
                with _get_connection() as conn:
                    update_transaction_failure(conn, transaction_id, "validation_failed", response_body=to_response_body(den_err), taxonomy_err=den_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
                    write_audit_event(conn, transaction_id, source, "ALLOWLIST_DENIED", {"code": den_err["code"]})
                    _emit_route_failed(conn, transaction_id, source, den_err, canonical_request=canonical_payload, target_request=target_payload)
            except Exception:
                pass
            return err_t(den_err)
        # Other ValueError from validate_control_plane (endpoint not found, vendor/operation not found, etc.)
        err_msg = str(e)
        if "endpoint" in err_msg.lower() and ("not found" in err_msg.lower() or "no active" in err_msg.lower()):
            nf_err = endpoint_not_found(err_msg)
        elif "vendor" in err_msg.lower() and ("not found" in err_msg.lower() or "inactive" in err_msg.lower()):
            nf_err = vendor_not_found(err_msg)
        elif "operation" in err_msg.lower() and ("not found" in err_msg.lower() or "does not support" in err_msg.lower()):
            nf_err = operation_not_found(err_msg)
        else:
            nf_err = build_error("NOT_FOUND", err_msg, http_status=400)
        log_json("WARN", "validation_failed", ctx=ctx, error=str(e))
        try:
            with _get_connection() as conn:
                update_transaction_failure(conn, transaction_id, "validation_failed", response_body=to_response_body(nf_err), taxonomy_err=nf_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
                write_audit_event(conn, transaction_id, source, "VALIDATION_FAILED", {"code": nf_err["code"]})
                _emit_route_failed(conn, transaction_id, source, nf_err, canonical_request=canonical_payload, target_request=target_payload)
        except Exception:
            pass
        return err_t(nf_err)

    except (psycopg2.Error, ConnectionError) as e:
        db_err = db_error(str(e) if isinstance(e, ConnectionError) else "Database error", exc_type=type(e).__name__)
        try:
            with _get_connection() as conn:
                create_transaction_record(
                    conn,
                    transaction_id,
                    correlation_id,
                    source,
                    target,
                    operation,
                    idempotency_key,
                    status="db_error",
                    request_body=canonical_request_body,
                )
                _emit_route_failed(conn, transaction_id, source, db_err, canonical_request=canonical_request_body)
        except Exception:
            pass
        return err_t(db_err)

    except requests.RequestException as e:
        conn_err = downstream_connection_error(str(e), exc_type=type(e).__name__)
        try:
            with _get_connection() as conn:
                update_transaction_failure(conn, transaction_id, "downstream_error", response_body=to_response_body(conn_err), taxonomy_err=conn_err, canonical_request_body=canonical_payload, target_request_body=target_payload)
                write_audit_event(conn, transaction_id, source, "DOWNSTREAM_CONNECTION_ERROR", {"code": conn_err["code"]})
                _emit_route_failed(conn, transaction_id, source, conn_err, canonical_request=canonical_payload, target_request=target_payload)
        except Exception:
            pass
        return err_t(conn_err)

    except Exception as e:
        int_err = internal_error(str(e), exc_type=type(e).__name__)
        try:
            with _get_connection() as conn:
                create_transaction_record(
                    conn,
                    transaction_id,
                    correlation_id,
                    source,
                    target,
                    operation,
                    idempotency_key,
                    status="internal_error",
                    request_body=canonical_request_body,
                )
                _emit_route_failed(conn, transaction_id, source, int_err, canonical_request=canonical_request_body)
        except Exception:
            pass
        return err_t(int_err)


_handler_impl_wrapped = with_observability(_handler_impl, "routing")


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Entry point. Adds CORS headers for REST API (execute) responses. Catches unhandled exceptions."""
    try:
        result = _handler_impl_wrapped(event, context)
        path = (event.get("path") or event.get("rawPath") or "").lower()
        if isinstance(result, dict) and "statusCode" in result:
            add_cors_to_response(result)
        return result
    except Exception as e:
        log_json("ERROR", "routing_unhandled", error=str(e))
        ctx = get_context(event, context)
        int_err = internal_error(str(e), exc_type=type(e).__name__)
        resp = _err_from(int_err, ctx["transaction_id"], ctx["correlation_id"])
        return add_cors_to_response(resp)
