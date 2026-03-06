"""
Effective mapping resolution: vendor mapping if present, else canonical pass-through.

Used by routing_lambda and vendor_registry_lambda for consistent request/response
transformation and for returning source metadata (vendor_mapping vs canonical_pass_through).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


@dataclass
class EffectiveMappingInfo:
    """Describes whether vendor mappings exist for request/response."""

    request_source: str  # "canonical_pass_through" | "vendor_mapping" | "none"
    response_source: str  # same
    has_vendor_request_mapping: bool
    has_vendor_response_mapping: bool
    request_mapping: dict[str, Any] | None
    response_mapping: dict[str, Any] | None


def _load_mapping(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    canonical_version: str,
    direction: str,
    flow_direction: str = "OUTBOUND",
) -> dict[str, Any] | None:
    """Load active mapping for (vendor, op, version, direction). Returns None if none or empty."""
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
        if len(m) == 0 or (len(m) == 1 and m.get("type") == "identity"):
            return None
        return m


def resolve_effective_mapping(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    canonical_version: str,
    flow_direction: str = "OUTBOUND",
    role: str = "target",
) -> EffectiveMappingInfo:
    """
    Resolve effective mapping for vendor/op/version.

    role="target" (outbound): vendor receives request, returns response.
      - Request: FROM_CANONICAL (canonical -> vendor request)
      - Response: TO_CANONICAL_RESPONSE (vendor response -> canonical)
    role="source" (outbound): vendor sends request, receives response.
      - Request: TO_CANONICAL_REQUEST or TO_CANONICAL (vendor -> canonical)
      - Response: FROM_CANONICAL_RESPONSE (canonical -> vendor response)

    Returns EffectiveMappingInfo with request_source, response_source.
    """
    ver = (canonical_version or "v1").strip()
    op = (operation_code or "").strip()
    vc = (vendor_code or "").strip()
    fd = (flow_direction or "OUTBOUND").strip().upper()
    if fd not in ("INBOUND", "OUTBOUND"):
        fd = "OUTBOUND"

    if role == "source":
        req_mapping = _load_mapping(conn, vc, op, ver, "TO_CANONICAL_REQUEST", fd)
        if req_mapping is None:
            req_mapping = _load_mapping(conn, vc, op, ver, "TO_CANONICAL", fd)
        resp_mapping = _load_mapping(conn, vc, op, ver, "FROM_CANONICAL_RESPONSE", fd)
    else:
        req_mapping = _load_mapping(conn, vc, op, ver, "FROM_CANONICAL", fd)
        resp_mapping = _load_mapping(conn, vc, op, ver, "TO_CANONICAL_RESPONSE", fd)

    has_req = req_mapping is not None
    has_resp = resp_mapping is not None

    req_src = "vendor_mapping" if has_req else "canonical_pass_through"
    resp_src = "vendor_mapping" if has_resp else "canonical_pass_through"

    logger.info(
        "Effective mapping resolved",
        extra={
            "operation_code": op,
            "vendor_code": vc,
            "mappingRequestSource": req_src,
            "mappingResponseSource": resp_src,
        },
    )

    return EffectiveMappingInfo(
        request_source=req_src,
        response_source=resp_src,
        has_vendor_request_mapping=has_req,
        has_vendor_response_mapping=has_resp,
        request_mapping=req_mapping,
        response_mapping=resp_mapping,
    )
