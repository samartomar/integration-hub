"""Mission Control service - read-only canonical/runtime transaction visibility.

Reuses existing data_plane.transactions and data_plane.audit_events.
No runtime execution changes. No second transaction store.
"""

from __future__ import annotations

from typing import Any

from psycopg2 import sql
from psycopg2.extras import RealDictCursor

DEFAULT_LOOKBACK_MINUTES = 60
MAX_LIMIT = 200
MIN_LIMIT = 1


def _derive_mode(row: dict[str, Any]) -> str:
    """Derive mode from request bodies when safe. Default EXECUTE."""
    for key in ("request_body", "canonical_request_body", "canonical_request"):
        body = row.get(key)
        if not isinstance(body, dict):
            continue
        dry = body.get("dryRun") or body.get("dry_run")
        if dry is True:
            return "DRY_RUN"
    return "EXECUTE"


def _derive_canonical_version(row: dict[str, Any]) -> str | None:
    """Derive canonicalVersion from envelope when safe."""
    for key in ("request_body", "canonical_request_body", "canonical_request"):
        body = row.get(key)
        if not isinstance(body, dict):
            continue
        v = body.get("version") or body.get("canonicalVersion") or body.get("canonical_version")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _build_summary(row: dict[str, Any], operation: str | None) -> str:
    """Build human-readable summary from transaction metadata."""
    op = operation or row.get("operation") or "unknown"
    status = row.get("status") or "unknown"
    src = row.get("source_vendor") or "-"
    tgt = row.get("target_vendor") or "-"
    return f"{op} ({src} → {tgt}) {status}."


def _safe_request_metadata(body: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract safe metadata only from request body. No payload content."""
    if not isinstance(body, dict):
        return None
    safe: dict[str, Any] = {}
    for key in ("operationCode", "operation", "targetVendor", "target_vendor", "version", "canonicalVersion", "dryRun", "dry_run"):
        if key in body and body[key] is not None:
            safe[key] = body[key]
    return safe if safe else None


def _safe_response_metadata(
    target_resp: Any,
    canonical_resp: Any,
    error_code: str | None,
    http_status: int | None,
    failure_stage: str | None,
) -> dict[str, Any]:
    """Build response summary with safe metadata only. No payload bodies."""
    out: dict[str, Any] = {
        "errorCode": error_code,
        "httpStatus": http_status,
        "failureStage": failure_stage,
    }
    if isinstance(target_resp, dict):
        out["targetHasBody"] = True
        out["targetKeys"] = list(target_resp.keys())[:10]  # key names only, no values
    if isinstance(canonical_resp, dict):
        out["canonicalHasBody"] = True
        out["canonicalKeys"] = list(canonical_resp.keys())[:10]
    return out


def _derive_event_type(row: dict[str, Any]) -> str:
    """Derive eventType for canonical bridge activity."""
    status = (row.get("status") or "").lower()
    if status in ("success", "succeeded", "completed", "ok"):
        return "CANONICAL_BRIDGE_EXECUTE"
    if status in ("pending", "started", "in_progress", "queued", "running"):
        return "CANONICAL_BRIDGE_START"
    return "CANONICAL_BRIDGE_EXECUTE"


def _row_to_list_item(row: dict[str, Any]) -> dict[str, Any]:
    """Convert DB row to Mission Control list item."""
    created_at = row.get("created_at")
    created_iso = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at) if created_at else None
    operation = row.get("operation")
    mode = _derive_mode(row)
    canonical_version = _derive_canonical_version(row)
    return {
        "transactionId": row.get("transaction_id"),
        "parentTransactionId": row.get("parent_transaction_id"),  # resolved to tx_id string if join used
        "sourceVendor": row.get("source_vendor"),
        "targetVendor": row.get("target_vendor"),
        "operationCode": operation,
        "canonicalVersion": canonical_version,
        "correlationId": row.get("correlation_id"),
        "mode": mode,
        "status": row.get("status"),
        "eventType": _derive_event_type(row),
        "createdAt": created_iso,
        "updatedAt": created_iso,  # transactions table has no updated_at; use created_at
        "summary": _build_summary(row, operation),
    }


def list_mission_control_transactions(
    conn: Any,
    *,
    filters: dict[str, Any] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List recent transactions relevant to canonical bridge/runtime flows.

    Reuses data_plane.transactions. Time-bounded via lookback to avoid unbounded scans.
    Supports filters: operationCode, sourceVendor, targetVendor, status, mode, correlationId.
    Derives missing fields conservatively; does not fabricate values.
    """
    filters = filters or {}
    limit = max(MIN_LIMIT, min(MAX_LIMIT, limit))
    lookback_minutes = filters.get("lookbackMinutes") or DEFAULT_LOOKBACK_MINUTES
    lookback_minutes = max(1, min(1440, int(lookback_minutes) if lookback_minutes else DEFAULT_LOOKBACK_MINUTES))

    conditions: list[sql.Composable] = [
        sql.SQL("t.created_at >= (now() - (%s || ' minutes')::interval)"),
    ]
    params: list[Any] = [lookback_minutes]

    if filters.get("operationCode"):
        conditions.append(sql.SQL("t.operation = %s"))
        params.append(filters["operationCode"])
    if filters.get("sourceVendor"):
        conditions.append(sql.SQL("t.source_vendor = %s"))
        params.append(filters["sourceVendor"])
    if filters.get("targetVendor"):
        conditions.append(sql.SQL("t.target_vendor = %s"))
        params.append(filters["targetVendor"])
    if filters.get("status"):
        conditions.append(sql.SQL("t.status = %s"))
        params.append(filters["status"])
    if filters.get("correlationId"):
        conditions.append(sql.SQL("t.correlation_id = %s"))
        params.append(filters["correlationId"])

    # mode is derived, not stored; filter in Python if requested
    filter_mode = filters.get("mode")

    where = sql.SQL(" AND ").join(conditions)
    params.append(limit + 50)  # fetch extra to allow post-filter by mode

    q = sql.SQL(
        """
        SELECT
            t.transaction_id,
            t.correlation_id,
            t.source_vendor,
            t.target_vendor,
            t.operation,
            t.status,
            t.created_at,
            t.request_body,
            COALESCE(t.canonical_request_body, t.canonical_request) AS canonical_request_body,
            p.transaction_id AS parent_transaction_id
        FROM data_plane.transactions t
        LEFT JOIN data_plane.transactions p ON t.parent_transaction_id = p.id
        WHERE {}
        ORDER BY t.created_at DESC
        LIMIT %s
        """
    ).format(where)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, tuple(params))
        rows = [dict(r) for r in (cur.fetchall() or [])]

    items: list[dict[str, Any]] = []
    for row in rows:
        item = _row_to_list_item(row)
        if filter_mode and item.get("mode") != filter_mode:
            continue
        items.append(item)
        if len(items) >= limit:
            break

    return items


def get_mission_control_transaction(conn: Any, transaction_id: str) -> dict[str, Any] | None:
    """Return detailed read-only view for a transaction.

    Includes summary metadata, canonical request context, runtime request preview,
    response summary, audit event timeline. Adds notes for missing canonical context.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                t.transaction_id,
                t.correlation_id,
                t.source_vendor,
                t.target_vendor,
                t.operation,
                t.status,
                t.created_at,
                t.request_body,
                t.response_body,
                COALESCE(t.canonical_request_body, t.canonical_request) AS canonical_request_body,
                COALESCE(t.target_request_body, t.target_request) AS target_request_body,
                t.target_response_body,
                t.canonical_response_body,
                t.error_code,
                t.http_status,
                t.failure_stage,
                p.transaction_id AS parent_transaction_id
            FROM data_plane.transactions t
            LEFT JOIN data_plane.transactions p ON t.parent_transaction_id = p.id
            WHERE t.transaction_id = %s
            """,
            (transaction_id,),
        )
        row = cur.fetchone()

    if not row:
        return None

    row = dict(row)
    created_at = row.get("created_at")
    created_iso = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at) if created_at else None

    canonical_req = row.get("canonical_request_body")
    target_req = row.get("target_request_body")
    target_resp = row.get("target_response_body")
    canonical_resp = row.get("canonical_response_body")

    # Build timeline from audit_events
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT created_at, action, vendor_code, details
            FROM data_plane.audit_events
            WHERE transaction_id = %s
            ORDER BY created_at ASC
            """,
            (transaction_id,),
        )
        audit_rows = [dict(r) for r in (cur.fetchall() or [])]

    timeline: list[dict[str, Any]] = []
    for ar in audit_rows:
        ts = ar.get("created_at")
        ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts) if ts else None
        details = ar.get("details") or {}
        msg = details.get("message") or details.get("stage") or ar.get("action") or "EVENT"
        timeline.append({
            "timestamp": ts_iso,
            "eventType": ar.get("action") or "AUDIT",
            "status": "INFO",
            "message": str(msg) if msg else "",
        })

    notes: list[str] = [
        "Mission Control is metadata-only.",
        "Sensitive payloads remain redacted.",
    ]
    if not _derive_canonical_version(row):
        notes.append("canonicalVersion not stored in request; shown as null.")

    # preflightStatus: derive from audit/timeline when available; not stored in transactions
    preflight_status: str | None = None
    for ar in audit_rows:
        details = ar.get("details") or {}
        if isinstance(details, dict) and details.get("preflight") is True:
            preflight_status = details.get("preflightStatus") or "READY"
            break

    return {
        "transactionId": row.get("transaction_id"),
        "parentTransactionId": row.get("parent_transaction_id"),
        "sourceVendor": row.get("source_vendor"),
        "targetVendor": row.get("target_vendor"),
        "operationCode": row.get("operation"),
        "canonicalVersion": _derive_canonical_version(row),
        "correlationId": row.get("correlation_id"),
        "mode": _derive_mode(row),
        "status": row.get("status"),
        "preflightStatus": preflight_status,
        "createdAt": created_iso,
        "updatedAt": created_iso,
        "runtimeRequestPreview": _safe_request_metadata(target_req) or _safe_request_metadata(canonical_req),
        "responseSummary": _safe_response_metadata(
            target_resp, canonical_resp,
            row.get("error_code"), row.get("http_status"), row.get("failure_stage"),
        ),
        "timeline": timeline,
        "notes": notes,
    }
