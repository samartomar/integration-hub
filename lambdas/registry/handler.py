"""Registry Lambda handler - thin routing layer."""

from __future__ import annotations

import json
from typing import Any

from db import ensure_tables, get_connection
from idempotency import check_idempotency, get_idempotency_key_from_event
from response import error, no_content, success
from service import allowlist_service, operation_service, vendor_service
from timeout import ensure_sufficient_time


def _parse_body(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    """Parse request body to dict."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _route(
    path: str,
    method: str,
    path_params: dict[str, str],
    body: dict[str, Any],
    idempotency_key: str | None,
) -> dict[str, Any]:
    """Route to service layer. Returns response dict."""
    path_params = path_params or {}
    segments = [s for s in path.strip("/").split("/") if s]
    base = 1 if segments and segments[0] == "registry" else 0

    # Vendors
    if len(segments) > base and segments[base] == "vendors":
        vendor_id = path_params.get("id") or (segments[base + 1] if len(segments) > base + 1 else None)
        if method == "GET":
            if vendor_id:
                row = vendor_service.get_vendor(vendor_id)
                return success(200, row) if row else error(404, "NOT_FOUND", "Vendor not found")
            return success(200, vendor_service.list_vendors())
        if method == "POST":
            try:
                check_idempotency(idempotency_key)
                row = vendor_service.create_vendor(body.get("name"), body.get("description"))
                return success(201, row)
            except ValueError as e:
                return error(409 if "idempotency" in str(e).lower() else 400, "VALIDATION_ERROR", str(e))
        if method in ("PUT", "PATCH") and vendor_id:
            row = vendor_service.update_vendor(vendor_id, body.get("name"), body.get("description"))
            return success(200, row) if row else error(404, "NOT_FOUND", "Vendor not found")
        if method == "DELETE" and vendor_id:
            ok = vendor_service.delete_vendor(vendor_id)
            return no_content() if ok else error(404, "NOT_FOUND", "Vendor not found")
        return error(405, "METHOD_NOT_ALLOWED", "Method not allowed")

    # Operations
    if len(segments) > base and segments[base] == "operations":
        operation_id = path_params.get("id") or (segments[base + 1] if len(segments) > base + 1 else None)
        if method == "GET":
            if operation_id:
                row = operation_service.get_operation(operation_id)
                return success(200, row) if row else error(404, "NOT_FOUND", "Operation not found")
            return success(200, operation_service.list_operations())
        if method == "POST":
            try:
                check_idempotency(idempotency_key)
                row = operation_service.create_operation(body.get("name"), body.get("description"))
                return success(201, row)
            except ValueError as e:
                return error(409 if "idempotency" in str(e).lower() else 400, "VALIDATION_ERROR", str(e))
        if method in ("PUT", "PATCH") and operation_id:
            row = operation_service.update_operation(
                operation_id, body.get("name"), body.get("description")
            )
            return success(200, row) if row else error(404, "NOT_FOUND", "Operation not found")
        if method == "DELETE" and operation_id:
            ok = operation_service.delete_operation(operation_id)
            return no_content() if ok else error(404, "NOT_FOUND", "Operation not found")
        return error(405, "METHOD_NOT_ALLOWED", "Method not allowed")

    # Vendor operation allowlist
    if len(segments) > base and segments[base] == "vendor_operation_allowlist":
        allowlist_id = path_params.get("id") or (segments[base + 1] if len(segments) > base + 1 else None)
        if method == "GET":
            if allowlist_id:
                row = allowlist_service.get_allowlist(allowlist_id)
                return success(200, row) if row else error(404, "NOT_FOUND", "Allowlist entry not found")
            return success(200, allowlist_service.list_allowlist())
        if method == "POST":
            try:
                check_idempotency(idempotency_key)
                row = allowlist_service.create_allowlist(body.get("vendor_id"), body.get("operation_id"))
                return success(201, row)
            except ValueError as e:
                return error(409 if "idempotency" in str(e).lower() else 400, "VALIDATION_ERROR", str(e))
        if method == "DELETE" and allowlist_id:
            ok = allowlist_service.delete_allowlist(allowlist_id)
            return no_content() if ok else error(404, "NOT_FOUND", "Allowlist entry not found")
        return error(405, "METHOD_NOT_ALLOWED", "Method not allowed")

    return error(404, "NOT_FOUND", "Not found")


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """
    Handle registry CRUD requests.

    Expects API Gateway proxy event with httpMethod, path, pathParameters, body.
    Routes to service layer. Returns consistent JSON: success={data:...}, error={error:{code,message}}.
    """
    try:
        ensure_sufficient_time(context)
        method = event.get("httpMethod", "GET")
        path = event.get("path", "") or event.get("rawPath", "")
        path_params = event.get("pathParameters") or {}
        body = _parse_body(event.get("body"))
        idempotency_key = get_idempotency_key_from_event(event)

        try:
            with get_connection() as conn:
                ensure_tables(conn)
        except Exception:
            pass  # Tables may exist; proceed

        return _route(path, method, path_params, body, idempotency_key)
    except TimeoutError as e:
        return error(504, "TIMEOUT", str(e))
    except Exception as e:
        return error(500, "INTERNAL_ERROR", str(e), details={"type": type(e).__name__})
