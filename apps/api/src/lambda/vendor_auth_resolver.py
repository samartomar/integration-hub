"""Resolve endpoint outbound auth from control_plane.vendor_auth_profiles."""

from __future__ import annotations

from typing import Any

from psycopg2 import sql
from psycopg2.extras import RealDictCursor


def resolve_vendor_auth(
    conn: Any, vendor_code: str, vendor_auth_profile_id: str | None
) -> dict[str, Any]:
    """
    Resolve vendor-scoped outbound auth profile for endpoint execution.

    Returns empty dict when no vendor_auth_profile_id is set.
    Raises ValueError when the profile is missing/inactive or belongs to a different vendor.
    """
    if not vendor_auth_profile_id:
        return {}

    q = sql.SQL(
        """
        SELECT id, vendor_code, profile_name, auth_type, config, is_default, is_active
        FROM control_plane.vendor_auth_profiles
        WHERE id = %s::uuid AND COALESCE(is_active, true)
        LIMIT 1
        """
    )
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, (str(vendor_auth_profile_id).strip(),))
        row = cur.fetchone()

    if not row:
        raise ValueError(
            f"Vendor auth profile {vendor_auth_profile_id} is missing or inactive for endpoint"
        )

    row_vendor = str(row.get("vendor_code") or "").strip().upper()
    expected_vendor = str(vendor_code or "").strip().upper()
    if not expected_vendor or row_vendor != expected_vendor:
        raise ValueError(
            f"Vendor auth profile {vendor_auth_profile_id} does not belong to vendor {vendor_code}"
        )

    return {
        "id": str(row["id"]),
        "vendor_code": row.get("vendor_code"),
        "name": row.get("profile_name"),
        "auth_type": row.get("auth_type"),
        "config": row.get("config") if isinstance(row.get("config"), dict) else {},
        "is_default": bool(row.get("is_default", False)),
        "is_active": bool(row.get("is_active", True)),
    }
