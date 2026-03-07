"""Integration inventory discovery - existing Integration Hub artifacts.

Discovers what exists in the current system from DB/control-plane records.
No persistence. No runtime execution. Read-only. Admin-only.
"""

from __future__ import annotations

from typing import Any

INVENTORY_NOTE = "Inventory is derived from existing control-plane records. No fabrication."


def _enumerate_allowlist_pairs(conn: Any) -> list[tuple[str, str, str, str]]:
    """Enumerate (operation_code, version, source_vendor, target_vendor) from allowlist.

    Only explicit pairs (is_any_source=false, is_any_target=false).
    Version from operations.canonical_version or '1.0'.
    """
    from psycopg2.extras import RealDictCursor

    q = """
    SELECT DISTINCT
        a.operation_code,
        COALESCE(o.canonical_version, 'v1') AS canonical_version,
        a.source_vendor_code,
        a.target_vendor_code
    FROM control_plane.vendor_operation_allowlist a
    LEFT JOIN control_plane.operations o ON o.operation_code = a.operation_code AND o.is_active = true
    WHERE a.is_any_source = false AND a.is_any_target = false
      AND a.source_vendor_code IS NOT NULL AND a.target_vendor_code IS NOT NULL
      AND (a.rule_scope = 'admin' OR a.rule_scope IS NULL)
    ORDER BY a.operation_code, a.source_vendor_code, a.target_vendor_code
    """
    pairs: list[tuple[str, str, str, str]] = []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q)
        for r in cur.fetchall() or []:
            op = (r.get("operation_code") or "").strip().upper()
            ver = (r.get("canonical_version") or "1.0").strip().replace("v", "")
            if "." not in ver:
                ver = f"{ver}.0" if ver.isdigit() else "1.0"
            src = (r.get("source_vendor_code") or "").strip().upper()
            tgt = (r.get("target_vendor_code") or "").strip().upper()
            if op and src and tgt:
                pairs.append((op, ver, src, tgt))
    return list(dict.fromkeys(pairs))


def _check_operation_exists(conn: Any, operation_code: str) -> bool:
    """Check if operation exists in control_plane.operations."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM control_plane.operations WHERE operation_code = %s AND is_active = true",
            (operation_code,),
        )
        return cur.fetchone() is not None


def _check_allowlist_exists(conn: Any, source: str, target: str, operation: str) -> bool:
    """Check if allowlist rule exists for (source, target, operation)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM control_plane.vendor_operation_allowlist
            WHERE source_vendor_code = %s AND target_vendor_code = %s AND operation_code = %s
              AND is_any_source = false AND is_any_target = false
            """,
            (source, target, operation),
        )
        return cur.fetchone() is not None


def _check_operation_contract_exists(conn: Any, operation_code: str, version: str) -> bool:
    """Check if canonical operation contract exists."""
    ver_norm = version.replace("v", "") if version else "1.0"
    if "." not in ver_norm:
        ver_norm = f"{ver_norm}.0" if ver_norm.isdigit() else "1.0"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM control_plane.operation_contracts
            WHERE operation_code = %s AND canonical_version = %s AND is_active = true
            """,
            (operation_code, ver_norm),
        )
        if cur.fetchone():
            return True
        cur.execute(
            """
            SELECT 1 FROM control_plane.operation_contracts
            WHERE operation_code = %s AND canonical_version = %s AND is_active = true
            """,
            (operation_code, f"v{ver_norm}"),
        )
        return cur.fetchone() is not None


def _check_vendor_mapping_exists(conn: Any, vendor_code: str, operation_code: str, version: str) -> bool:
    """Check if vendor has mapping for operation (target vendor = provider)."""
    ver_norm = version.replace("v", "") if version else "1.0"
    if "." not in ver_norm:
        ver_norm = f"{ver_norm}.0" if ver_norm.isdigit() else "1.0"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM control_plane.vendor_operation_mappings
            WHERE vendor_code = %s AND operation_code = %s
              AND (canonical_version = %s OR canonical_version = %s)
              AND is_active = true
            """,
            (vendor_code, operation_code, ver_norm, f"v{ver_norm}"),
        )
        return cur.fetchone() is not None


def _check_endpoint_exists(conn: Any, vendor_code: str, operation_code: str) -> bool:
    """Check if vendor has endpoint for operation (target vendor = provider)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM control_plane.vendor_endpoints
            WHERE vendor_code = %s AND operation_code = %s AND is_active = true
            """,
            (vendor_code, operation_code),
        )
        return cur.fetchone() is not None


def _build_inventory_item(
    conn: Any,
    operation_code: str,
    version: str,
    source_vendor: str,
    target_vendor: str,
) -> dict[str, Any]:
    """Build single inventory item with evidence."""
    op_exists = _check_operation_exists(conn, operation_code)
    allowlist_exists = _check_allowlist_exists(conn, source_vendor, target_vendor, operation_code)
    contract_exists = _check_operation_contract_exists(conn, operation_code, version)
    mapping_exists = _check_vendor_mapping_exists(conn, target_vendor, operation_code, version)
    endpoint_exists = _check_endpoint_exists(conn, target_vendor, operation_code)

    notes: list[str] = []
    if not op_exists:
        notes.append("Operation not found in control_plane.operations.")
    if not contract_exists and op_exists:
        notes.append("Canonical operation contract not found; version may differ.")
    if allowlist_exists and not mapping_exists:
        notes.append("Allowlist permits access but no vendor mapping for target.")

    return {
        "operationCode": operation_code,
        "version": version,
        "sourceVendor": source_vendor,
        "targetVendor": target_vendor,
        "inventoryEvidence": {
            "operationExists": op_exists,
            "allowlistExists": allowlist_exists,
            "operationContractExists": contract_exists,
            "vendorMappingExists": mapping_exists,
            "endpointConfigExists": endpoint_exists,
        },
        "notes": notes,
    }


def _apply_inventory_filters(
    item: dict[str, Any],
    filters: dict[str, Any],
) -> bool:
    """Return True if item passes all filters."""
    op_f = (filters.get("operationCode") or filters.get("operation_code") or "").strip().upper()
    src_f = (filters.get("sourceVendor") or filters.get("source_vendor") or "").strip().upper()
    tgt_f = (filters.get("targetVendor") or filters.get("target_vendor") or "").strip().upper()
    has_allow = filters.get("hasAllowlist")
    has_contract = filters.get("hasOperationContract")
    has_mapping = filters.get("hasVendorMapping")
    has_endpoint = filters.get("hasEndpointConfig")

    if op_f and (item.get("operationCode") or "").strip().upper() != op_f:
        return False
    if src_f and (item.get("sourceVendor") or "").strip().upper() != src_f:
        return False
    if tgt_f and (item.get("targetVendor") or "").strip().upper() != tgt_f:
        return False
    ev = item.get("inventoryEvidence") or {}
    if has_allow is not None and ev.get("allowlistExists") != bool(has_allow):
        return False
    if has_contract is not None and ev.get("operationContractExists") != bool(has_contract):
        return False
    if has_mapping is not None and ev.get("vendorMappingExists") != bool(has_mapping):
        return False
    if has_endpoint is not None and ev.get("endpointConfigExists") != bool(has_endpoint):
        return False
    return True


def list_integration_inventory(conn: Any, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """List discovered inventory from existing system.

    Args:
        conn: DB connection (from lambda _get_connection).
        filters: operationCode, sourceVendor, targetVendor, hasAllowlist,
                 hasOperationContract, hasVendorMapping, hasEndpointConfig.

    Returns:
        { items, summary, notes }
    """
    filters = filters or {}
    pairs = _enumerate_allowlist_pairs(conn)
    items: list[dict[str, Any]] = []
    for (op, ver, src, tgt) in pairs:
        item = _build_inventory_item(conn, op, ver, src, tgt)
        if _apply_inventory_filters(item, filters):
            items.append(item)

    summary = summarize_integration_inventory(items)
    return {
        "items": items,
        "summary": summary,
        "notes": [INVENTORY_NOTE],
    }


def get_integration_inventory_item(
    conn: Any,
    operation_code: str,
    source_vendor: str,
    target_vendor: str,
    version: str | None = None,
) -> dict[str, Any] | None:
    """Get inventory item for a specific operation/vendor pair.

    Returns None if pair not in allowlist.
    """
    op = (operation_code or "").strip().upper()
    src = (source_vendor or "").strip().upper()
    tgt = (target_vendor or "").strip().upper()
    if not op or not src or not tgt:
        return None

    pairs = _enumerate_allowlist_pairs(conn)
    ver = (version or "").strip()
    for (p_op, p_ver, p_src, p_tgt) in pairs:
        if p_op == op and p_src == src and p_tgt == tgt:
            ver = ver or p_ver
            return _build_inventory_item(conn, op, ver, src, tgt)
    return None


def summarize_integration_inventory(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Build summary counts from inventory items."""
    total = len(items)
    with_all = sum(1 for i in items if _evidence_complete(i.get("inventoryEvidence") or {}))
    return {
        "total": total,
        "withFullEvidence": with_all,
        "partial": total - with_all,
    }


def _evidence_complete(ev: dict[str, Any]) -> bool:
    return bool(
        ev.get("operationExists")
        and ev.get("allowlistExists")
        and ev.get("operationContractExists")
        and ev.get("vendorMappingExists")
        and ev.get("endpointConfigExists")
    )
