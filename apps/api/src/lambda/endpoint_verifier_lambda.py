"""Endpoint Verifier Lambda - triggered by EventBridge endpoint.upserted events."""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import psycopg2
from contract_utils import (
    effective_contract_to_dict,
    load_canonical_contract,
    load_effective_contract_optional,
)
from endpoint_utils import EndpointNotFound, load_effective_endpoint
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# Schema type -> default example value
SCHEMA_DEFAULTS: dict[str, Any] = {
    "string": "test",
    "number": 1,
    "integer": 1,
    "boolean": True,
    "object": {},
    "array": [],
}


def _resolve_db_creds() -> str:
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
    pw = raw["password"]
    pw_enc = urllib.parse.quote(str(pw), safe="")
    return (
        f"postgresql://{raw.get('username') or raw.get('user')}:{pw_enc}"
        f"@{raw['host']}:{raw.get('port', 5432)}"
        f"/{raw.get('dbname', raw.get('database', 'integrationhub'))}"
    )


@contextmanager
def _get_connection() -> Generator[Any, None, None]:
    creds = _resolve_db_creds()
    conn = psycopg2.connect(creds, connect_timeout=10, options="-c client_encoding=UTF8")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _load_operation_contract(
    conn: Any,
    operation_code: str,
    canonical_version: str,
    vendor_code: str | None = None,
    flow_direction: str | None = None,
) -> dict[str, Any] | None:
    """
    Load effective contract (vendor override or canonical fallback).
    When vendor_code provided: uses contract_utils effective resolution.
    When vendor_code None: canonical only (legacy).
    flow_direction: OUTBOUND or INBOUND for vendor contract lookup.
    """
    if vendor_code:
        ec = load_effective_contract_optional(
            conn,
            operation_code=operation_code,
            vendor_code=vendor_code,
            canonical_version=canonical_version,
            flow_direction=flow_direction,
        )
        if ec:
            return effective_contract_to_dict(ec)
        return None
    # Canonical-only fallback when no vendor (e.g. admin-triggered verify)
    return load_canonical_contract(
        conn,
        operation_code=operation_code,
        canonical_version=canonical_version,
    )


def _get_canonical_version(conn: Any, operation_code: str) -> str:
    """Get canonical_version from operations table. Default 'v1'."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT canonical_version FROM control_plane.operations
            WHERE operation_code = %s AND COALESCE(is_active, true)
            """,
            (operation_code,),
        )
        row = cur.fetchone()
        return (row.get("canonical_version") or "v1") if row else "v1"


def _generate_example_from_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Generate minimal valid example payload from JSON schema.
    required string -> "test", number -> 1, boolean -> true, object -> {}
    """
    result: dict[str, Any] = {}
    required = schema.get("required") or []
    properties = schema.get("properties") or {}

    for prop_name in required:
        prop_schema = properties.get(prop_name, {})
        if isinstance(prop_schema, dict):
            prop_type = prop_schema.get("type", "string")
            result[prop_name] = SCHEMA_DEFAULTS.get(
                prop_type, SCHEMA_DEFAULTS["string"]
            )
        else:
            result[prop_name] = "test"

    return result


def _make_verification_request(
    url: str,
    method: str,
    payload: dict[str, Any],
    timeout_ms: int,
) -> tuple[int, str | dict[str, Any], str | None]:
    """
    Make HTTP request to endpoint.
    Returns (status_code, body_parsed_or_raw, error_message_if_failed).
    """
    import requests

    method = (method or "POST").upper()
    timeout_sec = max(5, min(30, (timeout_ms or 8000) / 1000))
    try:
        resp = requests.request(
            method,
            url,
            json=payload,
            timeout=timeout_sec,
            headers={"Content-Type": "application/json"},
        )
        body: str | dict[str, Any]
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:2000] if resp.text else ""

        if 200 <= resp.status_code < 300:
            return resp.status_code, body, None
        return resp.status_code, body, f"HTTP {resp.status_code}: {str(body)[:500]}"
    except requests.exceptions.Timeout:
        return -1, "", f"Timeout after {timeout_sec}s"
    except requests.exceptions.RequestException as e:
        return -1, "", str(e)[:500]


def _update_verification_status(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    status: str,
    error: str | None,
    endpoint_id: str | None = None,
) -> None:
    """Update vendor_endpoints.verification_status, last_verified_at, last_verification_error.
    When endpoint_id provided, update that row only; else update all active rows for (vendor_code, operation_code).
    """
    now = datetime.now(UTC).isoformat()
    with conn.cursor() as cur:
        if endpoint_id:
            cur.execute(
                """
                UPDATE control_plane.vendor_endpoints
                SET verification_status = %s,
                    last_verified_at = %s,
                    last_verification_error = %s,
                    updated_at = now()
                WHERE id = %s AND is_active = true
                """,
                (status, now, error, endpoint_id),
            )
        else:
            cur.execute(
                """
                UPDATE control_plane.vendor_endpoints
                SET verification_status = %s,
                    last_verified_at = %s,
                    last_verification_error = %s,
                    updated_at = now()
                WHERE vendor_code = %s AND operation_code = %s AND is_active = true
                """,
                (status, now, error, vendor_code, operation_code),
            )


def _write_audit_event(
    conn: Any,
    vendor_code: str,
    action: str,
    details: dict[str, Any],
) -> None:
    """Insert into data_plane.audit_events."""
    tx_id = f"verify-{vendor_code}-{details.get('operationCode', '')}-{id(details)}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO data_plane.audit_events (transaction_id, action, vendor_code, details)
            VALUES (%s, %s, %s, %s::jsonb)
            """,
            (tx_id, action, vendor_code, json.dumps(details)),
        )


def _verify_endpoint(detail: dict[str, Any]) -> None:
    """Main verification logic.
    Uses load_effective_endpoint (same as execute) so verification matches what routing will use.
    """
    vendor_code = detail.get("vendorCode") or detail.get("vendor_code")
    operation_code = detail.get("operationCode") or detail.get("operation_code")

    if not vendor_code or not operation_code:
        logger.warning("Missing required fields: vendorCode=%s operationCode=%s", vendor_code, operation_code)
        return

    with _get_connection() as conn:
        # Resolve effective endpoint (INBOUND preferred, fallback any direction) - same as execute
        try:
            resolved = load_effective_endpoint(
                conn,
                vendor_code,
                operation_code,
                expected_direction="INBOUND",
            )
        except EndpointNotFound as e:
            logger.warning("Endpoint not found for verification: %s", e)
            _write_audit_event(
                conn,
                vendor_code,
                "ENDPOINT_VERIFY_FAILED",
                {"operationCode": operation_code, "error": str(e)},
            )
            return

        url = resolved.url
        method = resolved.method
        timeout_ms = resolved.timeout_ms

        canonical_version = _get_canonical_version(conn, operation_code)
        contract = _load_operation_contract(
            conn, operation_code, canonical_version,
            vendor_code=vendor_code,
            flow_direction=resolved.flow_direction or resolved.matched_direction,
        )
        if not contract or not contract.get("request_schema"):
            _update_verification_status(
                conn, vendor_code, operation_code, "FAILED", "No active contract",
                endpoint_id=resolved.row_id,
            )
            _write_audit_event(
                conn,
                vendor_code,
                "ENDPOINT_VERIFY_FAILED",
                {
                    "operationCode": operation_code,
                    "error": "No active contract",
                },
            )
            return

        request_schema = contract["request_schema"]
        payload = _generate_example_from_schema(request_schema)
        verify_payload = {"operation": operation_code, **payload}

        status_code, body, error_msg = _make_verification_request(
            url, method, verify_payload, timeout_ms
        )
        endpoint_id = resolved.row_id

        if 200 <= status_code < 300:
            is_parseable = isinstance(body, dict) or (
                isinstance(body, str) and body.strip().startswith(("{", "["))
            )
            if is_parseable:
                _update_verification_status(
                    conn, vendor_code, operation_code, "VERIFIED", None,
                    endpoint_id=endpoint_id,
                )
                _write_audit_event(
                    conn,
                    vendor_code,
                    "ENDPOINT_VERIFY_SUCCESS",
                    {
                        "operationCode": operation_code,
                        "statusCode": status_code,
                        "url": url,
                    },
                )
            else:
                _update_verification_status(
                    conn,
                    vendor_code,
                    operation_code,
                    "FAILED",
                    "Response not parseable as JSON",
                    endpoint_id=endpoint_id,
                )
                _write_audit_event(
                    conn,
                    vendor_code,
                    "ENDPOINT_VERIFY_FAILED",
                    {
                        "operationCode": operation_code,
                        "statusCode": status_code,
                        "error": "Response not parseable as JSON",
                    },
                )
        else:
            _update_verification_status(
                conn, vendor_code, operation_code, "FAILED", error_msg,
                endpoint_id=endpoint_id,
            )
            _write_audit_event(
                conn,
                vendor_code,
                "ENDPOINT_VERIFY_FAILED",
                {
                    "operationCode": operation_code,
                    "statusCode": status_code,
                    "error": error_msg,
                },
            )


def handler(event: dict[str, Any], context: object) -> None:
    """
    Handle endpoint.upserted EventBridge events.
    Detail: { vendorCode, operationCode, url, method, format, timeout_ms }
    """
    detail = event.get("detail", event)
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except json.JSONDecodeError:
            detail = {}
    logger.info(
        "endpoint.upserted: vendorCode=%s operationCode=%s url=%s",
        detail.get("vendorCode"),
        detail.get("operationCode"),
        detail.get("url"),
    )
    try:
        _verify_endpoint(detail)
    except Exception as e:
        logger.exception("Verification failed: %s", e)
        vendor_code = detail.get("vendorCode") or detail.get("vendor_code", "unknown")
        operation_code = detail.get("operationCode") or detail.get("operation_code", "unknown")
        try:
            with _get_connection() as conn:
                _update_verification_status(
                    conn, vendor_code, operation_code, "FAILED", str(e)[:500]
                )
                _write_audit_event(
                    conn,
                    vendor_code,
                    "ENDPOINT_VERIFY_FAILED",
                    {"operationCode": operation_code, "error": str(e)},
                )
        except Exception:
            pass
