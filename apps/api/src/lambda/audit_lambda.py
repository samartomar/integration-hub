"""Audit Lambda - read-only transactions with vendorCode filter and cursor pagination."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.parse
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import psycopg2
from admin_guard import validate_admin_claims
from bcp_auth import AuthError
from canonical_response import canonical_error, canonical_ok, policy_denied_response
from cors import add_cors_to_response
from observability import get_context, log_json, with_observability
from policy_engine import PolicyContext, evaluate_policy
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

SCHEMA = "data_plane"
TABLE = "transactions"
DEFAULT_LIMIT = 20
MAX_LIMIT = 200
MAX_STRING_LENGTH = 128

_ISO_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)


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
    conn = psycopg2.connect(
        creds["connection_string"],
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    )
    try:
        yield conn
    finally:
        conn.close()


def _execute_query(
    conn: Any,
    query: sql.Composed,
    params: tuple[Any, ...] | None = None,
) -> list[dict[str, Any]]:
    """Execute query and return rows as dicts."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params or ())
        return [dict(row) for row in cur.fetchall()]


def _execute_one(
    conn: Any,
    query: sql.Composed,
    params: tuple[Any, ...] | None = None,
) -> dict[str, Any] | None:
    """Execute and return first row or None."""
    rows = _execute_query(conn, query, params)
    return rows[0] if rows else None


def _get_by_id(conn: Any, transaction_id: str, vendor_code: str | None) -> dict[str, Any] | None:
    """Get single transaction by id, optionally filtered by source vendor."""
    q = sql.SQL(
        """
        SELECT id, transaction_id, correlation_id, source_vendor, target_vendor,
               operation, idempotency_key, status, created_at,
               request_body, response_body,
               COALESCE(canonical_request_body, canonical_request) AS canonical_request_body,
               COALESCE(target_request_body, target_request) AS target_request_body,
               target_response_body, canonical_response_body,
               error_code, http_status, retryable, failure_stage
        FROM {}.{}
        WHERE transaction_id = %s
          AND (%s IS NULL OR source_vendor = %s)
        """
    ).format(sql.Identifier(SCHEMA), sql.Identifier(TABLE))
    return _execute_one(conn, q, (transaction_id, vendor_code, vendor_code))


def _to_transaction_detail_response(row: dict[str, Any]) -> dict[str, Any]:
    """
    Build JSON response for single transaction detail with camelCase debug fields.
    Keeps existing fields unchanged; maps debug columns to camelCase.
    """
    out: dict[str, Any] = {k: v for k, v in row.items()}
    # Map debug fields to camelCase (drop snake_case keys for these to avoid duplication)
    for sn, ca in [
        ("canonical_request_body", "canonicalRequestBody"),
        ("target_request_body", "targetRequestBody"),
        ("target_response_body", "targetResponseBody"),
        ("canonical_response_body", "canonicalResponseBody"),
        ("error_code", "errorCode"),
        ("http_status", "httpStatus"),
        ("failure_stage", "failureStage"),
    ]:
        if sn in out:
            out[ca] = out.pop(sn)
    return out


def _decode_cursor(cursor_b64: str) -> tuple[str, str] | None:
    """Decode cursor to (created_at_iso, transaction_id). Returns None if invalid."""
    try:
        raw = base64.urlsafe_b64decode(cursor_b64.encode()).decode()
        parts = raw.split("|", 1)
        if len(parts) != 2:
            return None
        return (parts[0], parts[1])
    except Exception:
        return None


def _encode_cursor(created_at_iso: str, transaction_id: str) -> str:
    """Encode cursor for next page."""
    return base64.urlsafe_b64encode(f"{created_at_iso}|{transaction_id}".encode()).decode()


def _query_transactions(
    conn: Any,
    *,
    vendor_code: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
    status: str | None = None,
    operation: str | None = None,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
    include_debug_payload: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Query transactions. from_ts/to_ts required (caller validates).
    When vendor_code set: WHERE source_vendor=? AND created_at BETWEEN from AND to [status] [operation] [cursor].
    When vendor_code None: WHERE created_at BETWEEN [etc]. ORDER BY created_at DESC, transaction_id DESC. LIMIT capped.

    Index: idx_transactions_audit_vendor_created (source_vendor, created_at DESC, transaction_id) when vendor_code set;
           idx_transactions_created_at when vendor_code omitted. Partition pruning via created_at range.
    EXPLAIN (ANALYZE, BUFFERS) sample (vendor_code=LH001, from=2025-02-01, to=2025-02-22):
      Limit  (cost=0.42..X rows=21)
        ->  Index Scan using idx_transactions_audit_vendor_created on transactions
              Index Cond: ((source_vendor = 'LH001') AND (created_at >= ...) AND (created_at <= ...))
      Append  (subplans: pruned) -- partitions outside range pruned; no full-table scan across all partitions.
    """
    limit = min(max(1, limit), MAX_LIMIT)
    conditions: list[sql.Composable] = []
    params: list[Any] = []

    if vendor_code is not None and vendor_code:
        conditions.append(sql.SQL("source_vendor = %s"))
        params.append(vendor_code)

    if from_ts:
        conditions.append(sql.SQL("created_at >= %s::timestamptz"))
        params.append(from_ts)
    if to_ts:
        conditions.append(sql.SQL("created_at <= %s::timestamptz"))
        params.append(to_ts)
    if status:
        conditions.append(sql.SQL("status = %s"))
        params.append(status)
    if operation:
        conditions.append(sql.SQL("operation = %s"))
        params.append(operation)

    decoded = _decode_cursor(cursor) if cursor else None
    if decoded:
        conditions.append(
            sql.SQL("(created_at, transaction_id) < (%s::timestamptz, %s)")
        )
        params.extend(decoded)

    where = sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("true")
    params.append(limit + 1)

    cols = sql.SQL(
        "id, transaction_id, correlation_id, source_vendor, target_vendor, "
        "operation, idempotency_key, status, created_at"
    )
    if include_debug_payload:
        cols = sql.SQL(
            "{}, request_body, response_body, "
            "COALESCE(canonical_request_body, canonical_request) AS canonical_request_body, "
            "COALESCE(target_request_body, target_request) AS target_request_body, "
            "target_response_body, canonical_response_body, error_code, http_status, retryable, failure_stage"
        ).format(cols)

    # List view: only needed columns (no SELECT *). Time-bounded, indexed, cursor paginated.
    q = sql.SQL(
        """
        SELECT {}
        FROM {}.{}
        WHERE {}
        ORDER BY created_at DESC, transaction_id DESC
        LIMIT %s
        """
    ).format(cols, sql.Identifier(SCHEMA), sql.Identifier(TABLE), where)
    rows = _execute_query(conn, q, tuple(params))

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = _encode_cursor(
            last["created_at"].isoformat() if last.get("created_at") else "",
            last["transaction_id"],
        )
    return rows, next_cursor


def _validate_query_params(params: dict[str, str] | None) -> dict[str, Any]:
    """Validate query params. vendorCode optional; from/to required to avoid unbounded scans."""
    params = params or {}
    vendor_code_raw = params.get("vendorCode") or params.get("vendor_code")
    vendor_code: str | None = None
    if vendor_code_raw and isinstance(vendor_code_raw, str):
        vendor_code = vendor_code_raw.strip()
        if vendor_code:
            if len(vendor_code) > MAX_STRING_LENGTH:
                raise ValueError("vendorCode must be at most 128 characters")
        else:
            vendor_code = None

    def _parse_int(val: str | None, default: int, lo: int, hi: int, name: str) -> int:
        if val is None or (isinstance(val, str) and not val.strip()):
            return default
        try:
            n = int(str(val).strip())
        except ValueError:
            raise ValueError(f"{name} must be a valid integer")
        if n < lo:
            raise ValueError(f"{name} must be at least {lo}")
        return min(n, hi)

    def _iso(val: str | None) -> str | None:
        if val is None or not isinstance(val, str) or not val.strip():
            return None
        s = val.strip()
        if not _ISO_PATTERN.match(s):
            raise ValueError("from and to must be ISO 8601 (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)")
        try:
            datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(f"invalid date: {e}") from e
        return s

    from_ts = _iso(params.get("from"))
    to_ts = _iso(params.get("to"))
    if from_ts and to_ts and from_ts > to_ts:
        raise ValueError("from must be before or equal to to")

    status_val = (params.get("status") or "").strip() or None
    operation_val = (params.get("operation") or "").strip() or None
    cursor_val = (params.get("cursor") or "").strip() or None
    include_debug = (
        (params.get("includeDebugPayload") or params.get("include_debug_payload") or "").strip().lower() in ("true", "1", "yes")
    )
    expand_sensitive = (
        (params.get("expandSensitive") or params.get("expand_sensitive") or "").strip().lower() in ("true", "1", "yes")
    )

    return {
        "vendor_code": vendor_code,
        "from_ts": from_ts,
        "to_ts": to_ts,
        "status": status_val,
        "operation": operation_val,
        "limit": _parse_int(params.get("limit"), DEFAULT_LIMIT, 1, MAX_LIMIT, "limit"),
        "cursor": cursor_val,
        "include_debug_payload": include_debug or expand_sensitive,
        "expand_sensitive": expand_sensitive,
    }


def _derive_auth_summary(
    txn: dict[str, Any], events: list[dict[str, Any]], conn: Any
) -> dict[str, Any]:
    """Derive authSummary from transaction, audit events, and DB (auth_profiles)."""
    mode = "UNKNOWN"
    for ev in events:
        action = ev.get("action")
        if action == "AUTH_JWT_SUCCEEDED":
            mode = "JWT"
            break
        if action == "AUTH_API_KEY_SUCCEEDED":
            mode = "API_KEY"
            break
        if action == "AUTH_ADMIN_JWT_SUCCEEDED":
            mode = "JWT"

    source_vendor = txn.get("source_vendor")
    idp_issuer = None
    idp_audience = None
    vendor_claim = None
    for ev in events:
        if ev.get("action") == "AUTH_JWT_SUCCEEDED":
            details = ev.get("details") or {}
            idp_issuer = details.get("issuer")
            idp_audience = details.get("audience")
            vendor_claim = details.get("vendorClaim")
            break

    auth_profile: dict[str, Any] | None = None
    target_vendor = txn.get("target_vendor")
    operation = txn.get("operation")
    if target_vendor and operation:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ve.auth_profile_id, ap.name, ap.auth_type
                FROM control_plane.vendor_endpoints ve
                LEFT JOIN control_plane.auth_profiles ap ON ve.auth_profile_id = ap.id
                WHERE ve.vendor_code = %s AND ve.operation_code = %s
                  AND COALESCE(ve.is_active, true)
                LIMIT 1
                """,
                (target_vendor, operation),
            )
            row = cur.fetchone()
        if row and row[0] is not None:
            auth_profile = {
                "id": str(row[0]),
                "name": row[1] if row[1] else None,
                "authType": row[2] if row[2] else None,
            }

    return {
        "mode": mode,
        "sourceVendor": source_vendor,
        "idpIssuer": idp_issuer,
        "idpAudience": idp_audience,
        "jwtVendorClaim": vendor_claim,
        "authProfile": auth_profile,
    }


def _derive_contract_mapping_summary(txn: dict[str, Any], conn: Any) -> dict[str, Any]:
    """Derive contractMappingSummary from transaction and control_plane tables."""
    source_vendor = txn.get("source_vendor")
    target_vendor = txn.get("target_vendor")
    operation = txn.get("operation")

    canonical_version: str | None = None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT canonical_version FROM control_plane.operations
            WHERE operation_code = %s AND COALESCE(is_active, true)
            LIMIT 1
            """,
            (operation,),
        )
        row = cur.fetchone()
        if row and row[0]:
            canonical_version = str(row[0])

    summary: dict[str, Any] = {
        "operationCode": operation,
        "canonicalVersion": canonical_version,
        "canonical": {"hasRequestSchema": False, "hasResponseSchema": False},
        "sourceVendor": {
            "vendorCode": source_vendor,
            "hasVendorContract": False,
            "hasRequestSchema": False,
            "hasResponseSchema": False,
            "hasFromCanonicalRequestMapping": False,
            "hasToCanonicalResponseMapping": False,
        },
        "targetVendor": {
            "vendorCode": target_vendor,
            "hasVendorContract": False,
            "hasRequestSchema": False,
            "hasResponseSchema": False,
            "hasFromCanonicalRequestMapping": False,
            "hasToCanonicalResponseMapping": False,
        },
    }

    if not canonical_version:
        return summary

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT request_schema, response_schema FROM control_plane.operation_contracts
            WHERE operation_code = %s AND canonical_version = %s AND COALESCE(is_active, true)
            LIMIT 1
            """,
            (operation, canonical_version),
        )
        row = cur.fetchone()
        if row:
            summary["canonical"]["hasRequestSchema"] = row[0] is not None
            summary["canonical"]["hasResponseSchema"] = row[1] is not None

    def _fill_vendor_side(vendor_code: str | None, key: str) -> None:
        if not vendor_code:
            return
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT request_schema, response_schema
                FROM control_plane.vendor_operation_contracts
                WHERE vendor_code = %s AND operation_code = %s
                  AND canonical_version = %s AND COALESCE(is_active, true)
                LIMIT 1
                """,
                (vendor_code, operation, canonical_version),
            )
            row = cur.fetchone()
        if row:
            summary[key]["hasVendorContract"] = True
            summary[key]["hasRequestSchema"] = row[0] is not None
            summary[key]["hasResponseSchema"] = row[1] is not None

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT direction FROM control_plane.vendor_operation_mappings
                WHERE vendor_code = %s AND operation_code = %s
                  AND canonical_version = %s AND COALESCE(is_active, true)
                """,
                (vendor_code, operation, canonical_version),
            )
            directions = {r[0] for r in cur.fetchall()}
        if "FROM_CANONICAL" in directions or "FROM_CANONICAL_REQUEST" in directions:
            summary[key]["hasFromCanonicalRequestMapping"] = True
        if "TO_CANONICAL" in directions or "TO_CANONICAL_RESPONSE" in directions:
            summary[key]["hasToCanonicalResponseMapping"] = True

    _fill_vendor_side(source_vendor, "sourceVendor")
    _fill_vendor_side(target_vendor, "targetVendor")
    return summary


def _success(data: dict[str, Any], status_code: int = 200) -> dict[str, Any]:
    """Build canonical success response with CORS and Content-Type."""
    return add_cors_to_response(canonical_ok(data, status_code))


def _error(status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build canonical error response with CORS and Content-Type."""
    return add_cors_to_response(canonical_error(code, message, status_code, details))


def _normalize_event(event: dict[str, Any]) -> None:
    """Normalize HTTP API v2 payload."""
    if "httpMethod" not in event and "requestContext" in event:
        http = event.get("requestContext", {}).get("http", {})
        event["httpMethod"] = http.get("method", "").upper()
    if "path" not in event and "rawPath" in event:
        event["path"] = event["rawPath"]
    if "queryStringParameters" not in event:
        qs = event.get("rawQueryString") or ""
        event["queryStringParameters"] = (
            {k: v[0] if len(v) == 1 else v for k, v in urllib.parse.parse_qs(qs).items()}
            if qs
            else {}
        )


AUDIT_EVENTS_DEFAULT_LIMIT = 200
AUDIT_EVENTS_MAX_LIMIT = 500


def _query_audit_events(
    conn: Any,
    transaction_id: str,
    limit: int = AUDIT_EVENTS_DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """
    List audit events for a transaction. SELECT ... WHERE transaction_id = $1 ORDER BY created_at ASC LIMIT $2.

    Index: idx_audit_events_transaction_id_created (transaction_id, created_at).
    Note: transaction_id does not partition-prune; planner may scan relevant partitions.
    EXPLAIN (ANALYZE, BUFFERS) sample:
      Limit  ->  Index Scan using idx_audit_events_transaction_id_created on audit_events
                  Index Cond: (transaction_id = '...')
      Append  (subplans: 1 of N) -- only partitions with matching rows scanned.
    """
    limit = min(max(1, limit), AUDIT_EVENTS_MAX_LIMIT)
    q = sql.SQL(
        """
        SELECT id, transaction_id, action, vendor_code, details, created_at
        FROM data_plane.audit_events
        WHERE transaction_id = %s
        ORDER BY created_at ASC
        LIMIT %s
        """
    )
    rows = _execute_query(conn, q, (transaction_id.strip(), limit))
    items = []
    for r in rows:
        items.append({
            "id": str(r["id"]) if r.get("id") else None,
            "transactionId": r["transaction_id"],
            "action": r["action"],
            "vendorCode": r.get("vendor_code") or "",
            "details": r.get("details"),
            "createdAt": str(r["created_at"]) if r.get("created_at") else None,
        })
    return items


def _handler_impl(event: dict[str, Any], context: object) -> dict[str, Any]:
    """
    Handle audit requests. All audit routes require admin JWT.

    GET /v1/audit/transactions?vendorCode=<filter>&from=&to=&status=&operation=&limit=&cursor=
    GET /v1/audit/transactions/{transactionId}?vendorCode=<optional filter>
    GET /v1/audit/events?transactionId=X&limit=Y
    """
    _normalize_event(event)
    if event.get("httpMethod") != "GET":
        return _error(405, "METHOD_NOT_ALLOWED", "Method not allowed")

    path = event.get("path", "") or event.get("rawPath", "")
    path_params = event.get("pathParameters") or {}
    segments = [s for s in path.strip("/").split("/") if s]
    params = event.get("queryStringParameters") or {}
    try:
        admin_claims = validate_admin_claims(event)
    except AuthError as e:
        return add_cors_to_response(canonical_error("AUTH_ERROR", e.message, status_code=e.status_code))

    # GET /v1/audit/events?transactionId=<id>&limit=<n>
    # Requires JWT (admin role). limit default 200, max 500. Returns { items, nextCursor: null }.
    if segments == ["v1", "audit", "events"]:
        decision = evaluate_policy(
            PolicyContext(
                surface="ADMIN",
                action="AUDIT_READ",
                vendor_code="ADMIN",
                target_vendor_code=None,
                operation_code=None,
                requested_source_vendor_code=None,
                is_admin=True,
                groups=admin_claims.roles,
                query={},
            )
        )
        if not decision.allow:
            return add_cors_to_response(policy_denied_response(decision))
        transaction_id = (params.get("transactionId") or params.get("transactionid") or "").strip()
        if not transaction_id:
            return _error(400, "VALIDATION_ERROR", "transactionId query param is required")
        limit_raw = (params.get("limit") or "").strip()
        limit = AUDIT_EVENTS_DEFAULT_LIMIT
        if limit_raw:
            try:
                limit = int(limit_raw)
                limit = min(max(1, limit), AUDIT_EVENTS_MAX_LIMIT)
            except ValueError:
                return _error(400, "VALIDATION_ERROR", "limit must be a valid integer")
        try:
            with _get_connection() as conn:
                items = _query_audit_events(conn, transaction_id, limit)
            return _success({"items": items, "nextCursor": None})
        except ConnectionError as e:
            return _error(503, "DB_ERROR", str(e))
        except Exception as e:
            return _error(500, "INTERNAL_ERROR", str(e))

    # GET /v1/audit/transactions/{transactionId}
    if len(segments) == 4 and segments[:3] == ["v1", "audit", "transactions"]:
        transaction_id = path_params.get("transactionId") or segments[3]
        if not transaction_id:
            return _error(400, "VALIDATION_ERROR", "transactionId path param required")
        try:
            filters = _validate_query_params(params)
        except ValueError as e:
            ctx = get_context(event, context)
            log_json("WARN", "validation_failed", ctx=ctx, error=str(e))
            return _error(400, "VALIDATION_ERROR", str(e))
        decision = evaluate_policy(
            PolicyContext(
                surface="ADMIN",
                action="AUDIT_EXPAND_SENSITIVE" if filters["expand_sensitive"] else "AUDIT_READ",
                vendor_code="ADMIN",
                target_vendor_code=None,
                operation_code=None,
                requested_source_vendor_code=None,
                is_admin=True,
                groups=admin_claims.roles,
                query={"expandSensitive": filters["expand_sensitive"]},
            )
        )
        if not decision.allow:
            return add_cors_to_response(policy_denied_response(decision))

        try:
            with _get_connection() as conn:
                row = _get_by_id(conn, transaction_id.strip(), filters["vendor_code"])
            if not row:
                return _error(404, "NOT_FOUND", "Transaction not found")
            txn_resp = _to_transaction_detail_response(row)
            with _get_connection() as conn:
                audit_items = _query_audit_events(conn, transaction_id.strip())
                auth_summary = _derive_auth_summary(row, audit_items, conn)
                contract_mapping_summary = _derive_contract_mapping_summary(row, conn)
            return _success({
                "transaction": txn_resp,
                "auditEvents": audit_items,
                "authSummary": auth_summary,
                "contractMappingSummary": contract_mapping_summary,
            })
        except ConnectionError as e:
            return _error(503, "DB_ERROR", str(e))
        except Exception as e:
            return _error(500, "INTERNAL_ERROR", str(e))

    # GET /v1/audit/transactions - list with from/to (required), vendorCode, status, operation, limit, cursor
    if segments != ["v1", "audit", "transactions"]:
        return _error(404, "NOT_FOUND", "Not found")

    if not (params.get("from") or "").strip() or not (params.get("to") or "").strip():
        return _error(400, "VALIDATION_ERROR", "from and to (ISO 8601) are required to bound the query")

    try:
        filters = _validate_query_params(params)
    except ValueError as e:
        ctx = get_context(event, context)
        log_json("WARN", "validation_failed", ctx=ctx, error=str(e))
        return _error(400, "VALIDATION_ERROR", str(e))

    decision = evaluate_policy(
        PolicyContext(
            surface="ADMIN",
            action="AUDIT_EXPAND_SENSITIVE" if filters["expand_sensitive"] else "AUDIT_LIST",
            vendor_code="ADMIN",
            target_vendor_code=None,
            operation_code=None,
            requested_source_vendor_code=None,
            is_admin=True,
            groups=admin_claims.roles,
            query={"expandSensitive": filters["expand_sensitive"]},
        )
    )
    if not decision.allow:
        return add_cors_to_response(policy_denied_response(decision))

    try:
        with _get_connection() as conn:
            rows, next_cursor = _query_transactions(
                conn,
                vendor_code=filters["vendor_code"],
                from_ts=filters["from_ts"],
                to_ts=filters["to_ts"],
                status=filters["status"],
                operation=filters["operation"],
                limit=filters["limit"],
                cursor=filters["cursor"],
                include_debug_payload=filters["include_debug_payload"],
            )
        body: dict[str, Any] = {
            "transactions": rows,
            "count": len(rows),
        }
        if next_cursor:
            body["nextCursor"] = next_cursor
        return _success(body)
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _safe_handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Catch unhandled exceptions to return structured 500 instead of generic API Gateway error."""
    try:
        return with_observability(_handler_impl, "audit")(event, context)
    except Exception as e:
        log_json("ERROR", "audit_unhandled", error=str(e))
        return _error(
            500,
            "INTERNAL_ERROR",
            str(e),
            details={"type": type(e).__name__},
        )


handler = _safe_handler
