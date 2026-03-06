"""Admin approval gate for vendor config changes.

Vendor mutations create PENDING change_requests; admins approve/apply or reject.
Feature gates control per-feature whether vendor changes go through change_requests or apply immediately.
"""

from __future__ import annotations

import json
import re
from typing import Any

from psycopg2.extras import RealDictCursor

GATE_BY_REQUEST_TYPE = {
    "ALLOWLIST_RULE": "GATE_ALLOWLIST_RULE",
    "MAPPING_CONFIG": "GATE_MAPPING_CONFIG",
    "VENDOR_CONTRACT_CHANGE": "GATE_VENDOR_CONTRACT_CHANGE",
    "ENDPOINT_CONFIG": "GATE_ENDPOINT_CONFIG",
}

DEFAULT_GATE_ENABLED = {
    "ALLOWLIST_RULE": True,
    "MAPPING_CONFIG": True,
    "VENDOR_CONTRACT_CHANGE": True,
    "ENDPOINT_CONFIG": False,
}

VENDOR_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


def is_feature_gated(conn: Any, request_type: str) -> bool:
    """
    Check if the given request_type is gated (requires admin approval).
    Returns True if vendor changes should create a change_request; False to apply immediately.
    Uses global gate (vendor_code IS NULL). Vendor-specific overrides can be added later.
    """
    feature_code = GATE_BY_REQUEST_TYPE.get(request_type)
    if not feature_code:
        # safety: unknown types stay gated
        return True

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT is_enabled
            FROM control_plane.feature_gates
            WHERE feature_code = %s AND vendor_code IS NULL
            """,
            (feature_code,),
        )
        row = cur.fetchone()

    if row is None:
        # fall back to current behavior if row missing
        return DEFAULT_GATE_ENABLED.get(request_type, True)

    return bool(row[0])


def apply_payload_directly(conn: Any, request_type: str, payload: dict, vendor_code: str) -> None:
    """
    Apply a payload directly to the target tables (skip change_request).
    Used when feature gate is disabled for the request_type.
    Reuses the same apply logic as apply_vendor_change_request.
    """
    if request_type == "ALLOWLIST_RULE":
        _apply_allowlist_payload(conn, payload, vendor_code)
    elif request_type == "ENDPOINT_CONFIG":
        _apply_endpoint_payload(conn, payload, vendor_code)
    elif request_type == "MAPPING_CONFIG":
        _apply_mapping_payload(conn, payload, vendor_code)
    elif request_type == "VENDOR_CONTRACT_CHANGE":
        _apply_vendor_contract_payload(conn, payload, vendor_code)
    else:
        raise ValueError(f"Unknown request_type: {request_type}")


def create_change_request(
    conn: Any,
    *,
    request_type: str,
    vendor_code: str,
    operation_code: str | None,
    payload: dict,
    requested_by: str | None,
    requested_via: str,
) -> dict[str, Any]:
    """
    Insert a PENDING row into control_plane.change_requests and return
    minimal info (id, status, created_at).
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO control_plane.change_requests
            (request_type, vendor_code, operation_code, payload, status, requested_by, requested_via, updated_at)
            VALUES (%s, %s, %s, %s::jsonb, 'PENDING', %s, %s, now())
            RETURNING id, status, created_at
            """,
            (
                request_type,
                vendor_code,
                operation_code,
                json.dumps(payload),
                requested_by,
                requested_via,
            ),
        )
        row = cur.fetchone()
    return dict(row) if row else {"id": None, "status": "PENDING", "created_at": None}


def apply_change_request(
    conn: Any,
    change_request_row: dict,
    approver: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """
    Given a PENDING change_request row:
    - Apply its payload to the correct tables (allowlist, endpoints, mappings)
    - Update status to APPLIED
    - Set approved_by, approved_at, applied_at
    """
    request_type = change_request_row.get("request_type")
    payload = change_request_row.get("payload")
    if not isinstance(payload, dict):
        payload = json.loads(payload) if isinstance(payload, str) else {}
    vendor_code = (change_request_row.get("vendor_code") or change_request_row.get("target_vendor_code") or "").strip()
    change_request_row.get("operation_code")
    str(change_request_row.get("id", ""))

    if request_type == "ALLOWLIST_RULE":
        _apply_allowlist_payload(conn, payload, vendor_code)
    elif request_type == "ENDPOINT_CONFIG":
        _apply_endpoint_payload(conn, payload, vendor_code)
    elif request_type == "MAPPING_CONFIG":
        _apply_mapping_payload(conn, payload, vendor_code)
    elif request_type == "VENDOR_CONTRACT_CHANGE":
        _apply_vendor_contract_payload(conn, payload, vendor_code)
    else:
        raise ValueError(f"Unknown request_type: {request_type}")

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            UPDATE control_plane.change_requests
            SET status = 'APPLIED', approved_by = %s, approved_at = now(), applied_at = now(),
                rejected_reason = NULL, updated_at = now()
            WHERE id = %s
            RETURNING id, status, applied_at
            """,
            (approver, change_request_row.get("id")),
        )
        row = cur.fetchone()
    return dict(row) if row else change_request_row


def apply_vendor_change_request(conn: Any, request_row: dict, decided_by: str, reason: str | None = None) -> None:
    """
    Apply a PENDING vendor_change_requests row. Updates vendor_change_requests on success.
    Raises on apply failure.
    """
    request_type = request_row.get("request_type")
    payload = request_row.get("payload")
    if not isinstance(payload, dict):
        payload = json.loads(payload) if isinstance(payload, str) else {}
    vendor_code = (request_row.get("target_vendor_code") or request_row.get("requesting_vendor_code") or "").strip()
    request_id = request_row.get("id")

    if request_type == "ALLOWLIST_RULE":
        _apply_allowlist_payload(conn, payload, vendor_code)
    elif request_type == "ENDPOINT_CONFIG":
        _apply_endpoint_payload(conn, payload, vendor_code)
    elif request_type == "MAPPING_CONFIG":
        _apply_mapping_payload(conn, payload, vendor_code)
    elif request_type == "VENDOR_CONTRACT_CHANGE":
        _apply_vendor_contract_payload(conn, payload, vendor_code)
    else:
        raise ValueError(f"Unknown request_type: {request_type}")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE control_plane.vendor_change_requests
            SET status = 'APPROVED', decision_reason = %s, decided_by = %s, decided_at = now(), updated_at = now()
            WHERE id = %s
            """,
            (reason, decided_by, request_id),
        )


def _apply_vendor_contract_payload(conn: Any, payload: dict, vendor_code: str) -> None:
    """Apply VENDOR_CONTRACT_CHANGE payload to vendor_operation_contracts."""
    op = (payload.get("operationCode") or payload.get("operation_code") or "").strip().upper()
    canon_ver = payload.get("canonicalVersion") or payload.get("canonical_version") or "v1"
    req_schema = payload.get("requestSchema") or payload.get("request_schema")
    resp_schema = payload.get("responseSchema") or payload.get("response_schema")
    is_active = payload.get("isActive", payload.get("is_active", True))
    if isinstance(is_active, str):
        is_active = is_active.lower() in ("true", "1", "yes")
    if not op or not isinstance(req_schema, dict):
        raise ValueError("operationCode and requestSchema required in contract payload")
    vc = (payload.get("vendor_code") or payload.get("vendorCode") or vendor_code).strip().upper()
    fd = (payload.get("flowDirection") or payload.get("flow_direction") or "OUTBOUND").strip().upper()
    if fd not in ("INBOUND", "OUTBOUND"):
        fd = "OUTBOUND"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control_plane.vendor_operation_contracts
            (vendor_code, operation_code, canonical_version, flow_direction, request_schema, response_schema, is_active)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (vendor_code, operation_code, canonical_version, flow_direction) WHERE is_active = true
            DO UPDATE SET
                request_schema = EXCLUDED.request_schema,
                response_schema = EXCLUDED.response_schema,
                is_active = EXCLUDED.is_active,
                updated_at = now()
            """,
            (vc, op, canon_ver, fd, json.dumps(req_schema), json.dumps(resp_schema) if resp_schema else None, is_active),
        )


def apply_allowlist_change_request(
    conn: Any,
    request_row: dict,
    decided_by: str,
    reason: str | None = None,
) -> None:
    """
    Apply a PENDING allowlist_change_requests row. Materializes vendor rules into
    vendor_operation_allowlist and updates the request status to APPROVED.
    Raises on apply failure.
    """
    source = (request_row.get("source_vendor_code") or "").strip().upper()
    targets_raw = request_row.get("target_vendor_codes") or []
    use_wildcard = request_row.get("use_wildcard_target") or False
    operation_code = (request_row.get("operation_code") or "").strip().upper()
    direction = (request_row.get("direction") or "OUTBOUND").strip().upper()
    request_id = request_row.get("id")

    if not source or not operation_code:
        raise ValueError("source_vendor_code and operation_code required")
    if use_wildcard:
        raise ValueError("Wildcard targets are not supported; explicit target vendor codes are required")
    if direction not in ("INBOUND", "OUTBOUND"):
        direction = "OUTBOUND"

    targets = [str(t).strip().upper() for t in targets_raw if str(t).strip()] if isinstance(targets_raw, list) else []

    with conn.cursor() as cur:
        if use_wildcard:
            cur.execute(
                """
                INSERT INTO control_plane.vendor_operation_allowlist
                (source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, rule_scope, flow_direction)
                VALUES (%s, NULL, FALSE, TRUE, %s, 'vendor', %s)
                ON CONFLICT (COALESCE(source_vendor_code, '*'), is_any_source, COALESCE(target_vendor_code, '*'), is_any_target, operation_code, rule_scope, flow_direction) DO NOTHING
                """,
                (source, operation_code, direction),
            )
        elif direction == "INBOUND":
            # CALLER_NARROWING: source_vendor_code = receiver, target_vendor_codes = callers.
            # Allowlist: caller sends to receiver. Delete existing vendor inbound rules, then insert selected callers.
            # Same schema as putProviderNarrowing: (source=caller, target=receiver, flow_direction=OUTBOUND).
            cur.execute(
                """
                DELETE FROM control_plane.vendor_operation_allowlist
                WHERE rule_scope = 'vendor'
                  AND target_vendor_code = %s
                  AND operation_code = %s
                  AND flow_direction = 'OUTBOUND'
                """,
                (source, operation_code),
            )
            for caller in targets:
                if not caller:
                    continue
                cur.execute(
                    """
                    INSERT INTO control_plane.vendor_operation_allowlist
                    (source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, rule_scope, flow_direction)
                    VALUES (%s, %s, FALSE, FALSE, %s, 'vendor', 'OUTBOUND')
                    ON CONFLICT (COALESCE(source_vendor_code, '*'), is_any_source, COALESCE(target_vendor_code, '*'), is_any_target, operation_code, rule_scope, flow_direction) DO NOTHING
                    """,
                    (caller, source, operation_code),
                )
        else:
            # OUTBOUND (PROVIDER_NARROWING): source=caller, target=provider.
            for tgt in targets:
                if not tgt:
                    continue
                cur.execute(
                    """
                    INSERT INTO control_plane.vendor_operation_allowlist
                    (source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, rule_scope, flow_direction)
                    VALUES (%s, %s, FALSE, FALSE, %s, 'vendor', 'OUTBOUND')
                    ON CONFLICT (COALESCE(source_vendor_code, '*'), is_any_source, COALESCE(target_vendor_code, '*'), is_any_target, operation_code, rule_scope, flow_direction) DO NOTHING
                    """,
                    (source, tgt, operation_code),
                )

        cur.execute(
            """
            UPDATE control_plane.allowlist_change_requests
            SET status = 'APPROVED', reviewed_by = %s, decision_reason = %s, updated_at = now()
            WHERE id = %s
            """,
            (decided_by, reason, request_id),
        )


def _apply_allowlist_payload(conn: Any, payload: dict, vendor_code: str) -> None:
    """Apply ALLOWLIST_RULE payload to vendor_operation_allowlist.
    Supports two formats:
    1. payload.rules (array) - from my-allowlist/change-request
    2. payload.allowlist (object) - legacy single-rule format
    """
    rules = payload.get("rules")
    if isinstance(rules, list) and len(rules) > 0:
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            src = rule.get("source_vendor_code") or rule.get("sourceVendorCode")
            tgt = rule.get("target_vendor_code") or rule.get("targetVendorCode")
            is_any_src = rule.get("is_any_source", rule.get("isAnySource", False))
            is_any_tgt = rule.get("is_any_target", rule.get("isAnyTarget", False))
            op = rule.get("operation_code") or rule.get("operationCode")
            scope = rule.get("rule_scope", "vendor")
            flow_dir = rule.get("flow_direction", rule.get("flowDirection", "BOTH"))
            if not op:
                raise ValueError("operation_code required in each rule")
            if is_any_src or is_any_tgt:
                raise ValueError("Wildcard allowlist rules are not supported")
            src_val = _validate_vendor_code(src, "source_vendor_code")
            tgt_val = _validate_vendor_code(tgt, "target_vendor_code")
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO control_plane.vendor_operation_allowlist
                    (source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, rule_scope, flow_direction)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (COALESCE(source_vendor_code, '*'), is_any_source, COALESCE(target_vendor_code, '*'), is_any_target, operation_code, rule_scope, flow_direction) DO NOTHING
                    """,
                    (src_val, tgt_val, is_any_src, is_any_tgt, op.strip().upper(), scope, flow_dir),
                )
        return

    allowlist = payload.get("allowlist")
    if isinstance(allowlist, dict):
        src = allowlist.get("source_vendor_code") or allowlist.get("sourceVendorCode")
        tgt = allowlist.get("target_vendor_code") or allowlist.get("targetVendorCode")
        is_any_src = allowlist.get("is_any_source", allowlist.get("isAnySource", False))
        is_any_tgt = allowlist.get("is_any_target", allowlist.get("isAnyTarget", False))
        op = allowlist.get("operation_code") or allowlist.get("operationCode")
        scope = allowlist.get("rule_scope", "vendor")
        flow_dir = allowlist.get("flow_direction", allowlist.get("flowDirection", "BOTH"))
        if not op:
            raise ValueError("operation_code required in allowlist payload")
        if is_any_src or is_any_tgt:
            raise ValueError("Wildcard allowlist rules are not supported")
        src_val = _validate_vendor_code(src, "source_vendor_code")
        tgt_val = _validate_vendor_code(tgt, "target_vendor_code")
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO control_plane.vendor_operation_allowlist
                (source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, rule_scope, flow_direction)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (COALESCE(source_vendor_code, '*'), is_any_source, COALESCE(target_vendor_code, '*'), is_any_target, operation_code, rule_scope, flow_direction) DO NOTHING
                """,
                (src_val, tgt_val, is_any_src, is_any_tgt, op.strip().upper(), scope, flow_dir),
            )
        return

    if "sourceVendorCode" in payload or "source_vendor_code" in payload:
        src = payload.get("source_vendor_code") or payload.get("sourceVendorCode")
        tgt = payload.get("target_vendor_code") or payload.get("targetVendorCode")
        op = payload.get("operation_code") or payload.get("operationCode")
        flow_dir = payload.get("flow_direction", payload.get("flowDirection", "BOTH"))
        if not op:
            raise ValueError("operation_code required in payload")
        src_val = _validate_vendor_code(src, "source_vendor_code")
        tgt_val = _validate_vendor_code(tgt, "target_vendor_code")
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO control_plane.vendor_operation_allowlist
                (source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, rule_scope, flow_direction)
                VALUES (%s, %s, FALSE, FALSE, %s, 'vendor', %s)
                ON CONFLICT (COALESCE(source_vendor_code, '*'), is_any_source, COALESCE(target_vendor_code, '*'), is_any_target, operation_code, rule_scope, flow_direction) DO NOTHING
                """,
                (src_val, tgt_val, op.strip().upper(), flow_dir),
            )
        return

    raise ValueError("payload must have rules array, allowlist object, or sourceVendorCode/targetVendorCode/operationCode")


def _validate_vendor_code(value: Any, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required")
    s = str(value).strip().upper()
    if not s:
        raise ValueError(f"{field_name} cannot be empty")
    if s == "*":
        raise ValueError(f"{field_name} wildcard '*' is not supported")
    if len(s) > 64 or not VENDOR_CODE_PATTERN.match(s):
        raise ValueError(f"{field_name} must match [A-Z][A-Z0-9_]{{1,63}}")
    return s


def _apply_endpoint_payload(conn: Any, payload: dict, vendor_code: str) -> None:
    """Apply ENDPOINT_CONFIG payload to vendor_endpoints."""
    ep = payload.get("endpoint")
    if not isinstance(ep, dict):
        raise ValueError("payload.endpoint must be a JSON object")
    vc = (ep.get("vendor_code") or ep.get("vendorCode") or vendor_code).strip().upper()
    op = (ep.get("operation_code") or ep.get("operationCode") or "").strip().upper()
    fd = (ep.get("flow_direction") or ep.get("flowDirection") or "OUTBOUND").strip().upper()
    if fd not in ("INBOUND", "OUTBOUND"):
        fd = "OUTBOUND"
    url = (ep.get("url") or "").strip()
    method = ep.get("http_method") or ep.get("httpMethod") or "POST"
    payload_fmt = ep.get("payload_format") or ep.get("payloadFormat") or "JSON"
    timeout = ep.get("timeout_ms") or ep.get("timeoutMs") or 8000
    auth_id = (
        ep.get("vendor_auth_profile_id")
        or ep.get("vendorAuthProfileId")
        or ep.get("auth_profile_id")
        or ep.get("authProfileId")
    )
    if not op or not url:
        raise ValueError("operation_code and url required in endpoint payload")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE control_plane.vendor_endpoints
            SET is_active = false, updated_at = now()
            WHERE vendor_code = %s AND operation_code = %s AND flow_direction = %s AND is_active = true
            """,
            (vc, op, fd),
        )
        cur.execute(
            """
            INSERT INTO control_plane.vendor_endpoints
            (vendor_code, operation_code, flow_direction, url, http_method, payload_format, timeout_ms, vendor_auth_profile_id, verification_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING')
            """,
            (vc, op, fd, url, method, payload_fmt, timeout, auth_id),
        )


def _is_empty_mapping(m: dict | None) -> bool:
    """True if mapping is empty or identity (canonical pass-through)."""
    if not m or not isinstance(m, dict):
        return True
    return len(m) == 0 or (len(m) == 1 and m.get("type") == "identity")


def _apply_mapping_payload(conn: Any, payload: dict, vendor_code: str) -> None:
    """Apply MAPPING_CONFIG payload to vendor_operation_mappings."""
    m = payload.get("mapping")
    if not isinstance(m, dict):
        raise ValueError("payload.mapping must be a JSON object")
    vc = (m.get("vendor_code") or m.get("vendorCode") or vendor_code).strip().upper()
    op = (m.get("operation_code") or m.get("operationCode") or "").strip().upper()
    canon_ver = m.get("canonical_version") or m.get("canonicalVersion") or "v1"
    fd = (m.get("flow_direction") or m.get("flowDirection") or "OUTBOUND").strip().upper()
    if fd not in ("INBOUND", "OUTBOUND"):
        fd = "OUTBOUND"
    mode = (m.get("mode") or "CUSTOM").strip().upper()
    req_map = m.get("requestMapping") or m.get("request_mapping")
    resp_map = m.get("responseMapping") or m.get("response_mapping")
    use_canon_req = mode == "CANONICAL"
    use_canon_resp = mode == "CANONICAL"
    if mode == "CUSTOM":
        use_canon_req = req_map is None or _is_empty_mapping(req_map if isinstance(req_map, dict) else None)
        use_canon_resp = resp_map is None or _is_empty_mapping(resp_map if isinstance(resp_map, dict) else None)
    if not op:
        raise ValueError("operation_code required in mapping payload")
    req_dir, resp_dir = "FROM_CANONICAL", "TO_CANONICAL_RESPONSE"
    with conn.cursor() as cur:
        for direction, use_canon, mapping_val in [
            (req_dir, use_canon_req, req_map),
            (resp_dir, use_canon_resp, resp_map),
        ]:
            cur.execute(
                """
                UPDATE control_plane.vendor_operation_mappings
                SET is_active = false, updated_at = now()
                WHERE vendor_code = %s AND operation_code = %s AND canonical_version = %s
                  AND direction = %s AND flow_direction = %s AND is_active = true
                """,
                (vc, op, canon_ver, direction, fd),
            )
            if not use_canon and mapping_val is not None and isinstance(mapping_val, dict) and not _is_empty_mapping(mapping_val):
                cur.execute(
                    """
                    INSERT INTO control_plane.vendor_operation_mappings
                    (vendor_code, operation_code, canonical_version, direction, flow_direction, mapping, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, true)
                    """,
                    (vc, op, canon_ver, direction, fd, json.dumps(mapping_val)),
                )
