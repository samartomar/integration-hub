"""Platform rollout helpers for Journey Mode feature/phase resolution."""

from __future__ import annotations

import re
from typing import Any

from psycopg2.extras import RealDictCursor

CURRENT_PHASE_SETTINGS_KEY = "CURRENT_PHASE"
FEATURE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
PHASE_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


def normalize_feature_code(feature_code: str | None) -> str:
    code = (feature_code or "").strip().lower()
    if not code or not FEATURE_CODE_PATTERN.match(code):
        raise ValueError("featureCode must be lowercase snake_case (2-64 chars)")
    return code


def normalize_phase_code(phase_code: str | None) -> str:
    code = (phase_code or "").strip().upper()
    if not code or not PHASE_CODE_PATTERN.match(code):
        raise ValueError("phaseCode must be uppercase snake_case (2-64 chars)")
    return code


def evaluate_effective_enabled(
    override_is_enabled: bool | None,
    phase_enabled: bool,
) -> bool:
    if override_is_enabled is True:
        return True
    if override_is_enabled is False:
        return False
    return bool(phase_enabled)


def get_platform_rollout_state(conn: Any) -> dict[str, Any]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT settings_value
            FROM control_plane.platform_settings
            WHERE settings_key = %s
            LIMIT 1
            """,
            (CURRENT_PHASE_SETTINGS_KEY,),
        )
        row = cur.fetchone() or {}
        current_phase = row.get("settings_value")

        cur.execute(
            """
            SELECT
                pf.feature_code,
                pf.description,
                pf.is_enabled,
                COALESCE(ppf.is_enabled, false) AS phase_enabled
            FROM control_plane.platform_features pf
            LEFT JOIN control_plane.platform_phase_features ppf
                ON ppf.feature_code = pf.feature_code
               AND ppf.phase_code = %s
            ORDER BY pf.feature_code
            """,
            (current_phase,),
        )
        rows = cur.fetchall() or []

    features: list[dict[str, Any]] = []
    effective_features: dict[str, bool] = {}
    for r in rows:
        d = dict(r)
        feature_code = str(d.get("feature_code") or "").strip()
        override = d.get("is_enabled")
        phase_enabled = bool(d.get("phase_enabled", False))
        effective_enabled = evaluate_effective_enabled(override, phase_enabled)
        override_state = "INHERIT"
        if override is True:
            override_state = "ENABLED"
        elif override is False:
            override_state = "DISABLED"

        features.append(
            {
                "featureCode": feature_code,
                "description": d.get("description"),
                "isEnabled": override,
                "overrideState": override_state,
                "phaseEnabled": phase_enabled,
                "effectiveEnabled": effective_enabled,
            }
        )
        effective_features[feature_code] = effective_enabled

    return {
        "currentPhase": current_phase,
        "features": features,
        "effectiveFeatures": effective_features,
    }


def list_platform_phases(conn: Any) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT phase_code, phase_name, description
            FROM control_plane.platform_phases
            ORDER BY phase_code
            """
        )
        phase_rows = cur.fetchall() or []

        cur.execute(
            """
            SELECT phase_code, feature_code, is_enabled
            FROM control_plane.platform_phase_features
            ORDER BY phase_code, feature_code
            """
        )
        mapping_rows = cur.fetchall() or []

    by_phase: dict[str, list[dict[str, Any]]] = {}
    for r in mapping_rows:
        d = dict(r)
        phase_code = str(d.get("phase_code") or "")
        by_phase.setdefault(phase_code, []).append(
            {
                "featureCode": d.get("feature_code"),
                "isEnabled": bool(d.get("is_enabled", True)),
            }
        )

    out: list[dict[str, Any]] = []
    for row in phase_rows:
        d = dict(row)
        phase_code = str(d.get("phase_code") or "")
        out.append(
            {
                "phaseCode": phase_code,
                "phaseName": d.get("phase_name"),
                "description": d.get("description"),
                "features": by_phase.get(phase_code, []),
            }
        )
    return out


def set_current_phase(conn: Any, phase_code: str) -> dict[str, Any]:
    normalized = normalize_phase_code(phase_code)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT phase_code
            FROM control_plane.platform_phases
            WHERE phase_code = %s
            LIMIT 1
            """,
            (normalized,),
        )
        exists = cur.fetchone()
        if exists is None:
            raise ValueError(f"Unknown phaseCode '{normalized}'")

        cur.execute(
            """
            INSERT INTO control_plane.platform_settings (
                settings_key, settings_value
            )
            VALUES (%s, %s)
            ON CONFLICT (settings_key)
            DO UPDATE SET
                settings_value = EXCLUDED.settings_value,
                updated_at = now()
            RETURNING settings_key, settings_value, updated_at
            """,
            (CURRENT_PHASE_SETTINGS_KEY, normalized),
        )
        row = cur.fetchone() or {}
    return {
        "settingsKey": row.get("settings_key"),
        "settingsValue": row.get("settings_value"),
        "updatedAt": row.get("updated_at").isoformat() if row.get("updated_at") else None,
    }


def update_platform_feature(
    conn: Any,
    feature_code: str,
    is_enabled: bool | None,
    *,
    description_is_present: bool,
    description: str | None,
) -> dict[str, Any]:
    normalized = normalize_feature_code(feature_code)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if description_is_present:
            cur.execute(
                """
                UPDATE control_plane.platform_features
                SET
                    is_enabled = %s,
                    description = %s,
                    updated_at = now()
                WHERE feature_code = %s
                RETURNING feature_code, is_enabled, description, updated_at
                """,
                (is_enabled, description, normalized),
            )
        else:
            cur.execute(
                """
                UPDATE control_plane.platform_features
                SET
                    is_enabled = %s,
                    updated_at = now()
                WHERE feature_code = %s
                RETURNING feature_code, is_enabled, description, updated_at
                """,
                (is_enabled, normalized),
            )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Unknown featureCode '{normalized}'")

    d = dict(row)
    return {
        "featureCode": d.get("feature_code"),
        "isEnabled": d.get("is_enabled"),
        "description": d.get("description"),
        "updatedAt": d.get("updated_at").isoformat() if d.get("updated_at") else None,
    }
