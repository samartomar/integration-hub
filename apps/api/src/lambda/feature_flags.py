"""Feature flag helpers backed by control_plane.feature_gates."""

from __future__ import annotations

from typing import Any

from psycopg2.extras import RealDictCursor


def is_global_feature_enabled(
    conn: Any,
    feature_code: str,
    *,
    default_enabled: bool = True,
) -> bool:
    """Return global feature gate state (vendor_code IS NULL)."""
    if not feature_code or not str(feature_code).strip():
        return default_enabled
    code = str(feature_code).strip()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT is_enabled
            FROM control_plane.feature_gates
            WHERE feature_code = %s AND vendor_code IS NULL
            LIMIT 1
            """,
            (code,),
        )
        row = cur.fetchone()
    if row is None:
        return default_enabled
    return bool(row.get("is_enabled"))


def is_feature_enabled_for_vendor(
    conn: Any,
    feature_code: str,
    vendor_code: str | None,
    *,
    default_enabled: bool = False,
) -> bool:
    """
    Resolve gate with precedence:
      1) (feature_code, vendor_code)
      2) (feature_code, NULL) global
      3) default_enabled
    """
    if not feature_code or not str(feature_code).strip():
        return default_enabled
    code = str(feature_code).strip()
    vendor = str(vendor_code or "").strip().upper() or None
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if vendor:
            cur.execute(
                """
                SELECT is_enabled
                FROM control_plane.feature_gates
                WHERE feature_code = %s AND vendor_code = %s
                LIMIT 1
                """,
                (code, vendor),
            )
            row = cur.fetchone()
            if row is not None:
                return bool(row.get("is_enabled"))
        cur.execute(
            """
            SELECT is_enabled
            FROM control_plane.feature_gates
            WHERE feature_code = %s AND vendor_code IS NULL
            LIMIT 1
            """,
            (code,),
        )
        row = cur.fetchone()
    if row is None:
        return default_enabled
    return bool(row.get("is_enabled"))

