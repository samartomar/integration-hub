"""
Effective contract resolution: vendor override or canonical fallback.

Rule: Use vendor_operation_contracts if present; otherwise operation_contracts (canonical).
Only CONTRACT_NOT_FOUND when neither exists.

Single source of truth for vendor->canonical fallback SQL. Import this module everywhere.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class ContractNotFound(Exception):
    """Raised when neither vendor-specific nor canonical contract exists."""


@dataclass
class EffectiveContract:
    """Contract from vendor override or canonical fallback."""

    operation_code: str
    canonical_version: str
    request_schema: dict[str, Any]
    response_schema: dict[str, Any] | None
    vendor_code: str | None = None  # set when from vendor_operation_contracts
    source: str = "canonical"  # "vendor" | "canonical"


def load_effective_contract(
    conn: Any,
    *,
    operation_code: str,
    vendor_code: str,
    canonical_version: str | None = None,
    flow_direction: str | None = None,
) -> EffectiveContract:
    """
    Return the effective contract for a vendor/operation and flow_direction:

    1) Try vendor_operation_contracts (override) for (vendor_code, operation_code, canonical_version, flow_direction).
    2) Fallback to operation_contracts (canonical).
    3) If neither exists, raise ContractNotFound.

    flow_direction: OUTBOUND or INBOUND. When None, defaults to OUTBOUND for backward compatibility.
    """
    ver = (canonical_version or "v1").strip()
    op = (operation_code or "").strip()
    vc = (vendor_code or "").strip()
    fd = (flow_direction or "OUTBOUND").strip().upper()
    if fd not in ("INBOUND", "OUTBOUND"):
        fd = "OUTBOUND"
    if not op or not vc:
        raise ContractNotFound(
            f"No active contract (vendor or canonical) for operation={operation_code}, vendor={vendor_code}"
        )

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 1) Vendor-specific contract (if any) for this flow_direction
        cur.execute(
            """
            SELECT vendor_code, operation_code, canonical_version, request_schema, response_schema
            FROM control_plane.vendor_operation_contracts
            WHERE vendor_code = %s AND operation_code = %s AND canonical_version = %s
              AND flow_direction = %s AND is_active = true
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """,
            (vc, op, ver, fd),
        )
        vrow = cur.fetchone()
        if vrow:
            req = vrow.get("request_schema")
            resp = vrow.get("response_schema")
            logger.info(
                "Contract resolved",
                extra={
                    "operation_code": op,
                    "vendor_code": vc,
                    "contractSource": "vendor",
                },
            )
            return EffectiveContract(
                operation_code=op,
                canonical_version=ver,
                request_schema=req if isinstance(req, dict) else {},
                response_schema=resp if isinstance(resp, dict) else None,
                vendor_code=vc,
                source="vendor",
            )

        # 2) Canonical fallback
        cur.execute(
            """
            SELECT operation_code, canonical_version, request_schema, response_schema
            FROM control_plane.operation_contracts
            WHERE operation_code = %s AND canonical_version = %s AND is_active = true
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """,
            (op, ver),
        )
        crow = cur.fetchone()
        if crow:
            req = crow.get("request_schema")
            resp = crow.get("response_schema")
            logger.info(
                "Contract resolved",
                extra={
                    "operation_code": op,
                    "vendor_code": vc,
                    "contractSource": "canonical",
                },
            )
            return EffectiveContract(
                operation_code=op,
                canonical_version=ver,
                request_schema=req if isinstance(req, dict) else {},
                response_schema=resp if isinstance(resp, dict) else None,
                vendor_code=None,
                source="canonical",
            )

    raise ContractNotFound(
        f"No active contract (vendor or canonical) for operation={operation_code}, vendor={vendor_code}"
    )


def load_effective_contract_optional(
    conn: Any,
    *,
    operation_code: str,
    vendor_code: str,
    canonical_version: str | None = None,
    flow_direction: str | None = None,
) -> EffectiveContract | None:
    """Like load_effective_contract but returns None instead of raising when not found."""
    try:
        return load_effective_contract(
            conn,
            operation_code=operation_code,
            vendor_code=vendor_code,
            canonical_version=canonical_version,
            flow_direction=flow_direction,
        )
    except ContractNotFound:
        return None


def load_canonical_contract(
    conn: Any,
    *,
    operation_code: str,
    canonical_version: str | None = None,
) -> dict[str, Any] | None:
    """
    Load canonical contract only (operation_contracts). No vendor override.
    Returns dict with operation_code, canonical_version, request_schema, response_schema or None.
    """
    ver = (canonical_version or "v1").strip()
    op = (operation_code or "").strip()
    if not op:
        return None

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT operation_code, canonical_version, request_schema, response_schema
            FROM control_plane.operation_contracts
            WHERE operation_code = %s AND canonical_version = %s AND is_active = true
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """,
            (op, ver),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def effective_contract_to_dict(ec: EffectiveContract) -> dict[str, Any]:
    """Convert EffectiveContract to dict compatible with routing's contract row shape."""
    return {
        "operation_code": ec.operation_code,
        "canonical_version": ec.canonical_version,
        "request_schema": ec.request_schema,
        "response_schema": ec.response_schema,
    }
