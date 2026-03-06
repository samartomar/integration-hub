"""Audit Lambda handler - read-only access to transactions with filtering and pagination."""

from __future__ import annotations

from typing import Any

from response import error_response, success
from timeout import ensure_sufficient_time
from transactions import get_by_id, query_transactions
from validation import validate_query_params


def _normalize_event(event: dict[str, Any]) -> None:
    """Normalize HTTP API v2 payload to REST API format for compatibility."""
    if "httpMethod" not in event and "requestContext" in event:
        http = event.get("requestContext", {}).get("http", {})
        event["httpMethod"] = http.get("method", "").upper()
    if "path" not in event and "rawPath" in event:
        event["path"] = event["rawPath"]
    if "queryStringParameters" not in event and "rawQueryString" in event:
        from urllib.parse import parse_qs

        qs = event.get("rawQueryString") or ""
        event["queryStringParameters"] = (
            {k: v[0] if len(v) == 1 else v for k, v in parse_qs(qs).items()}
            if qs
            else {}
        )


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """
    Handle audit read requests for transactions.

    Expects API Gateway proxy event with:
    - httpMethod: GET (or requestContext.http.method for HTTP API v2)
    - path: /audit, /audit/transactions or /audit/transactions/{id}
    - pathParameters: {id: "transaction_id"} or proxy path segments
    - queryStringParameters: filter and pagination params
      - dateFrom, dateTo (ISO 8601)
      - operation, status
      - limit (default 20, max 100), offset (default 0)
    """
    _normalize_event(event)
    if event.get("httpMethod") != "GET":
        return error_response(405, "METHOD_NOT_ALLOWED", "Method not allowed")

    path = event.get("path", "") or event.get("rawPath", "")
    path_params = event.get("pathParameters") or {}
    segments = [s for s in path.strip("/").split("/") if s]
    base = 1 if segments and segments[0] == "audit" else 0
    # Treat /audit as /audit/transactions (list)
    if segments == ["audit"]:
        segments = ["audit", "transactions"]

    # GET /transactions/{id} - single transaction
    if len(segments) > base + 1 and segments[base] == "transactions":
        tx_id = path_params.get("id") or segments[base + 1]
        if not tx_id or not tx_id.strip():
            return error_response(400, "VALIDATION_ERROR", "transaction_id is required")
        tx_id = tx_id.strip()
        try:
            ensure_sufficient_time(context)
            row = get_by_id(tx_id)
            return success(row) if row else error_response(404, "NOT_FOUND", "Transaction not found")
        except TimeoutError as e:
            return error_response(504, "TIMEOUT", str(e))
        except Exception as e:
            return error_response(500, "INTERNAL_ERROR", str(e), details={"type": type(e).__name__})

    # GET /transactions - list with filtering and pagination
    if len(segments) <= base or segments[base] != "transactions":
        return error_response(404, "NOT_FOUND", "Not found")

    try:
        filters = validate_query_params(event.get("queryStringParameters"))
    except ValueError as e:
        return error_response(400, "VALIDATION_ERROR", str(e))

    try:
        ensure_sufficient_time(context)
        rows, total_count = query_transactions(
            transaction_id=filters["transaction_id"],
            correlation_id=filters["correlation_id"],
            source_vendor=filters["source_vendor"],
            target_vendor=filters["target_vendor"],
            operation=filters["operation"],
            status=filters["status"],
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            limit=filters["limit"],
            offset=filters["offset"],
        )

        return success({
            "total_count": total_count,
            "results": rows,
            "pagination": {
                "limit": filters["limit"],
                "offset": filters["offset"],
                "has_more": filters["offset"] + len(rows) < total_count,
            },
        })
    except TimeoutError as e:
        return error_response(504, "TIMEOUT", str(e))
    except Exception as e:
        return error_response(500, "INTERNAL_ERROR", str(e), details={"type": type(e).__name__})
