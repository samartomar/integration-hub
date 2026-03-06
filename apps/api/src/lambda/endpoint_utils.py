"""
Effective endpoint resolution: prefer exact flow_direction match and enforce strict
direction when expected_direction is provided by the caller.

Used by routing_lambda (execute) and endpoint_verifier_lambda for consistent endpoint lookup.
Aligns execute behavior with vendor configuration UI (Verified = usable).

Manual verification checklist:
1. Save endpoint for GET_RECEIPT as LH001 in vendor portal, verify it shows Verified.
2. Execute GET_RECEIPT targeting LH001 (/v1/integrations/execute or playground).
3. Confirm no ENDPOINT_NOT_FOUND.
4. If includeActuals enabled, confirm response.actuals shows endpointSource and endpointUrl.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class EndpointNotFound(Exception):
    """Raised when no active endpoint found for (vendor_code, operation_code)."""


@dataclass
class ResolvedEndpoint:
    """Resolved endpoint with source metadata."""

    vendor_code: str
    operation_code: str
    url: str
    method: str
    timeout_ms: int
    vendor_auth_profile_id: str | None
    payload_format: str | None
    verification_status: str
    flow_direction: str | None  # flow_direction value when matched
    source: str  # "exact_match" | "fallback_any" | "not_found"
    matched_direction: str | None  # alias for flow_direction
    row_id: str | None  # UUID for updates


def load_effective_endpoint(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    expected_direction: str | None = None,
) -> ResolvedEndpoint:
    """
    Resolve effective endpoint for (vendor_code, operation_code).

    Resolution order:
      a) Exact: if expected_direction provided, match flow_direction.
      b) If expected_direction was provided and no row exists, raise EndpointNotFound.
      c) If expected_direction omitted, resolve any active endpoint for
         (vendor_code, operation_code).

    UI "Verified" = verification_status='VERIFIED'. Resolver returns any active row;
    caller (routing) enforces VERIFIED for execute.
    """
    vc = (vendor_code or "").strip()
    op = (operation_code or "").strip()
    if not vc or not op:
        raise EndpointNotFound("vendor_code and operation_code required")

    exp = (expected_direction or "").strip().upper()
    if exp not in ("INBOUND", "OUTBOUND"):
        exp = None

    row: dict[str, Any] | None = None
    source = "fallback_any"
    matched_direction: str | None = None

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if exp:
            cur.execute(
                """
                SELECT id, vendor_code, operation_code, flow_direction, url, http_method,
                       payload_format, timeout_ms, vendor_auth_profile_id, verification_status
                FROM control_plane.vendor_endpoints
                WHERE vendor_code = %s AND operation_code = %s
                  AND flow_direction = %s AND COALESCE(is_active, true)
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
                """,
                (vc, op, exp),
            )
            row = cur.fetchone()
            if row is not None:
                source = "exact_match"
                matched_direction = row.get("flow_direction")

        if row is None and exp:
            raise EndpointNotFound(
                f"No active endpoint for {vc} + {op} with flow_direction={exp}"
            )

        if row is None:
            cur.execute(
                """
                SELECT id, vendor_code, operation_code, flow_direction, url, http_method,
                       payload_format, timeout_ms, vendor_auth_profile_id, verification_status
                FROM control_plane.vendor_endpoints
                WHERE vendor_code = %s AND operation_code = %s
                  AND COALESCE(is_active, true)
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
                """,
                (vc, op),
            )
            row = cur.fetchone()
            if row is not None:
                matched_direction = row.get("flow_direction")

    if row is None:
        raise EndpointNotFound(
            f"No active endpoint for {vc} + {op}"
        )

    logger.info(
        "endpoint_resolved",
        extra={
            "vendor_code": vc,
            "operation_code": op,
            "expected_direction": exp,
            "source": source,
        },
    )

    fd = row.get("flow_direction")
    return ResolvedEndpoint(
        vendor_code=row["vendor_code"],
        operation_code=row["operation_code"],
        url=row["url"] or "",
        method=(row.get("http_method") or "POST").strip().upper() or "POST",
        timeout_ms=int(row.get("timeout_ms") or 8000),
        vendor_auth_profile_id=str(row["vendor_auth_profile_id"]) if row.get("vendor_auth_profile_id") else None,
        payload_format=row.get("payload_format"),
        verification_status=(row.get("verification_status") or "PENDING").strip(),
        flow_direction=fd,
        source=source,
        matched_direction=matched_direction or fd,
        row_id=str(row["id"]) if row.get("id") else None,
    )
