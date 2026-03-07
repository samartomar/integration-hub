"""Mapping readiness - deterministic coverage and readiness dashboard.

Derives readiness from existing code-first artifacts. No persistence. No runtime execution.
Read-only. Admin-only in this phase.
"""

from __future__ import annotations

from typing import Any

from schema.canonical_mapping_engine import get_mapping_definition, list_mapping_operations
from schema.mapping_certification import run_mapping_certification
from schema.mapping_fixtures import list_mapping_fixtures

READINESS_NOTE = "Readiness is derived from existing code-first artifacts. No persistence."


def _enumerate_pairs() -> list[tuple[str, str, str, str]]:
    """Enumerate all known operation/vendor pairs from mapping engine."""
    ops = list_mapping_operations()
    pairs: list[tuple[str, str, str, str]] = []
    for item in ops:
        op_code = (item.get("operationCode") or "").strip().upper()
        version = (item.get("version") or "1.0").strip()
        for pair in item.get("vendorPairs") or []:
            src = (pair.get("sourceVendor") or "").strip().upper()
            tgt = (pair.get("targetVendor") or "").strip().upper()
            if op_code and src and tgt:
                pairs.append((op_code, version, src, tgt))
    return pairs


def _check_certification_passes(
    operation_code: str,
    version: str,
    source_vendor: str,
    target_vendor: str,
) -> tuple[bool, list[str]]:
    """Run certification for both directions. Returns (all_pass, notes)."""
    notes: list[str] = []
    for direction in ("CANONICAL_TO_VENDOR", "VENDOR_TO_CANONICAL"):
        payload = {
            "operationCode": operation_code,
            "version": version,
            "sourceVendor": source_vendor,
            "targetVendor": target_vendor,
            "direction": direction,
        }
        result = run_mapping_certification(payload)
        summary = result.get("summary") or {}
        if not result.get("valid") or summary.get("failed", 0) > 0:
            status = summary.get("status", "FAIL")
            notes.append(f"{direction}: {status}")
    return len(notes) == 0, notes


def get_mapping_readiness(
    operation_code: str,
    version: str,
    source_vendor: str,
    target_vendor: str,
) -> dict[str, Any]:
    """Get readiness for a single operation/vendor pair.

    Returns:
        {
            operationCode, version, sourceVendor, targetVendor,
            mappingDefinition, fixtures, certification, runtimeReady,
            status, notes
        }
    """
    op = (operation_code or "").strip().upper()
    ver = (version or "1.0").strip()
    src = (source_vendor or "").strip().upper()
    tgt = (target_vendor or "").strip().upper()

    has_defn = get_mapping_definition(op, ver, src, tgt) is not None
    fixture_list = list_mapping_fixtures(op, ver, src, tgt)
    has_fixtures = len(fixture_list) > 0
    cert_pass, cert_notes = _check_certification_passes(op, ver, src, tgt) if has_defn and has_fixtures else (False, [])
    runtime_ready = has_defn

    notes: list[str] = []
    if not has_defn:
        notes.append("No mapping definition.")
    if not has_fixtures:
        notes.append("No fixtures.")
    if has_defn and has_fixtures and not cert_pass:
        notes.extend(cert_notes)

    if has_defn and has_fixtures and cert_pass and runtime_ready:
        status = "READY"
    elif not has_defn:
        status = "MISSING"
    elif has_defn and has_fixtures and not cert_pass:
        status = "WARN"
    elif has_defn or has_fixtures:
        status = "IN_PROGRESS"
    else:
        status = "MISSING"

    return {
        "operationCode": op,
        "version": ver,
        "sourceVendor": src,
        "targetVendor": tgt,
        "mappingDefinition": has_defn,
        "fixtures": has_fixtures,
        "certification": has_fixtures and has_defn,
        "runtimeReady": runtime_ready,
        "status": status,
        "notes": notes,
    }


def list_mapping_readiness(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """List readiness for all known operation/vendor pairs, optionally filtered.

    Filters: operationCode, sourceVendor, targetVendor, status
    """
    filters = filters or {}
    op_filter = (filters.get("operationCode") or filters.get("operation_code") or "").strip().upper()
    src_filter = (filters.get("sourceVendor") or filters.get("source_vendor") or "").strip().upper()
    tgt_filter = (filters.get("targetVendor") or filters.get("target_vendor") or "").strip().upper()
    status_filter = (filters.get("status") or "").strip().upper()

    pairs = _enumerate_pairs()
    items: list[dict[str, Any]] = []
    for (op, ver, src, tgt) in pairs:
        if op_filter and op != op_filter:
            continue
        if src_filter and src != src_filter:
            continue
        if tgt_filter and tgt != tgt_filter:
            continue
        item = get_mapping_readiness(op, ver, src, tgt)
        if status_filter and item.get("status", "").upper() != status_filter:
            continue
        items.append(item)

    summary = summarize_mapping_readiness(items)
    return {
        "items": items,
        "summary": summary,
        "notes": [READINESS_NOTE],
    }


def summarize_mapping_readiness(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Build summary counts from readiness items."""
    counts: dict[str, int] = {
        "READY": 0,
        "IN_PROGRESS": 0,
        "MISSING": 0,
        "WARN": 0,
    }
    for item in items:
        status = (item.get("status") or "").strip().upper()
        if status in counts:
            counts[status] += 1
        else:
            counts["IN_PROGRESS"] = counts.get("IN_PROGRESS", 0) + 1
    return {
        "total": len(items),
        "ready": counts["READY"],
        "inProgress": counts["IN_PROGRESS"],
        "missing": counts["MISSING"],
        "warn": counts["WARN"],
    }
