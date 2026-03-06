#!/usr/bin/env python3
"""
Seed minimal-but-rich data for local dev:

- Vendors:
    LH001 - Elevance Health, Inc
    LH002 - Excellus Health Plan
    LH023 - MassHealth
    LH030 - Horizon Blue Cross Blue Shield
    LH046 - CareFirst BlueCross BlueShield

- Operations:
    GET_COB_INQUIRY
    GET_VERIFY_MEMBER_ELIGIBILITY
    GET_PROVIDER_CONTRACT_STATUS
    GET_EXCHANGE_RATE_DEMO     (public, API-key header)
    GET_JOKE_DEMO              (public, bearer token)

- Contracts: canonical-only, vendor falls back to canonical
- Allowlist:
    Explicit vendor-to-vendor pairs only (no wildcard rows):
      - full ordered source->target matrix for all seeded ops
- Vendor supported operations:
    all 5 vendors: OUTBOUND for all seeded ops
- Endpoints:
    all 5 vendors OUTBOUND endpoints for the 3 health operations (Render mock)
- Feature gates: global flags seeded with upsert

Safe to run multiple times.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

import psycopg2
from psycopg2.extras import Json, RealDictCursor


# ---------------------------------------------------------------------------
# DB connection helpers
# ---------------------------------------------------------------------------

def _build_db_url() -> str:
    """
    Build a DATABASE_URL from env or fall back to local dev defaults.
    Priority:
    1. DATABASE_URL
    2. DB_URL
    3. PG* pieces → postgresql://user:pass@host:port/db
    4. Default: postgresql://hub:hub@localhost:5434/hub
    """
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if os.getenv("DB_URL"):
        return os.environ["DB_URL"]

    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5434")
    user = os.getenv("PGUSER", "hub")
    password = os.getenv("PGPASSWORD", "hub")
    db = os.getenv("PGDATABASE", "hub")

    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def get_conn():
    url = _build_db_url()
    print(f"[seed_local] Connecting to DB: {url}")
    return psycopg2.connect(url)


# ---------------------------------------------------------------------------
# Clear control_plane and validate
# ---------------------------------------------------------------------------

SEEDED_OPS = [
    "GET_COB_INQUIRY",
    "GET_VERIFY_MEMBER_ELIGIBILITY",
    "GET_PROVIDER_CONTRACT_STATUS",
    "GET_JOKE_DEMO",
    "GET_EXCHANGE_RATE_DEMO",
]

DEMO_LICS = ["LH001", "LH002", "LH023", "LH030", "LH046"]

CONTROL_PLANE_TABLES = [
    "platform_phase_features",
    "platform_settings",
    "platform_phases",
    "platform_features",
    "vendor_endpoints",
    "vendor_operation_allowlist",
    "vendor_supported_operations",
    "vendor_operation_contracts",
    "vendor_operation_mappings",
    "vendor_flow_layouts",
    "vendor_auth_profiles",
    "allowlist_change_requests",
    "vendor_change_requests",
    "change_requests",
    "auth_profiles",
    "operation_contracts",
    "feature_gates",
    "operations",
    "vendors",
]

PLATFORM_FEATURE_CODES = [
    "home_welcome",
    "registry_basic",
    "execute_test",
    "audit_view",
    "flow_builder",
    "mappings_ui",
    "governance_allowlist",
    "approvals",
    "replay_console",
    "ai_formatter_ui",
    "usage_billing_ui",
]

PLATFORM_PHASES = [
    ("PHASE_0", "Foundation", "Initial demo foundation"),
    ("PHASE_1", "Build", "Enable build-focused capabilities"),
    ("PHASE_2", "Govern", "Add governance and approvals"),
    ("PHASE_3", "Operate", "Enable runtime operations tooling"),
    ("PHASE_4", "Optimize", "Enable optimization capabilities"),
]

PHASE_FEATURES = {
    "PHASE_0": {"home_welcome", "registry_basic", "execute_test", "audit_view"},
    "PHASE_1": {"home_welcome", "registry_basic", "execute_test", "audit_view", "flow_builder", "mappings_ui"},
    "PHASE_2": {
        "home_welcome",
        "registry_basic",
        "execute_test",
        "audit_view",
        "flow_builder",
        "mappings_ui",
        "governance_allowlist",
        "approvals",
    },
    "PHASE_3": {
        "home_welcome",
        "registry_basic",
        "execute_test",
        "audit_view",
        "flow_builder",
        "mappings_ui",
        "governance_allowlist",
        "approvals",
        "replay_console",
    },
    "PHASE_4": {
        "home_welcome",
        "registry_basic",
        "execute_test",
        "audit_view",
        "flow_builder",
        "mappings_ui",
        "governance_allowlist",
        "approvals",
        "replay_console",
        "ai_formatter_ui",
        "usage_billing_ui",
    },
}


def clear_control_plane(cur) -> None:
    """DELETE from all control_plane tables (FK-safe order)."""
    for table in CONTROL_PLANE_TABLES:
        try:
            cur.execute(f"DELETE FROM control_plane.{table}")
            n = cur.rowcount
            if n > 0:
                print(f"[seed_local] Deleted {n} rows from control_plane.{table}")
        except Exception as e:
            # Table may not exist in this migration state
            print(f"[seed_local] Warning: control_plane.{table}: {e}")


def validate_control_plane_empty(cur) -> bool:
    """Return True if all control_plane tables are empty."""
    all_empty = True
    for table in CONTROL_PLANE_TABLES:
        try:
            cur.execute(f"SELECT COUNT(*) AS n FROM control_plane.{table}")
            row = cur.fetchone()
            n = row["n"] if isinstance(row, dict) else row[0]
            if n > 0:
                print(f"[seed_local] ERROR: control_plane.{table} has {n} rows (expected 0)")
                all_empty = False
        except Exception as e:
            print(f"[seed_local] Warning: control_plane.{table}: {e}")
    return all_empty


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def upsert_vendor(cur, vendor_code: str, vendor_name: str) -> None:
    cur.execute(
        """
        INSERT INTO control_plane.vendors (vendor_code, vendor_name, is_active)
        VALUES (%s, %s, true)
        ON CONFLICT (vendor_code)
        DO UPDATE SET
            vendor_name = EXCLUDED.vendor_name,
            is_active   = true,
            updated_at  = now()
        """,
        (vendor_code, vendor_name),
    )


def upsert_operation(
    cur,
    operation_code: str,
    description: str,
    canonical_version: str = "v1",
    direction_policy: str = "TWO_WAY",
    is_async_capable: bool = True,
    ai_presentation_mode: str = "RAW_ONLY",
) -> None:
    cur.execute(
        """
        INSERT INTO control_plane.operations (
            operation_code,
            description,
            canonical_version,
            is_async_capable,
            is_active,
            direction_policy,
            ai_presentation_mode
        )
        VALUES (%s, %s, %s, %s, true, %s, %s)
        ON CONFLICT (operation_code)
        DO UPDATE SET
            description        = EXCLUDED.description,
            canonical_version  = EXCLUDED.canonical_version,
            is_async_capable   = EXCLUDED.is_async_capable,
            direction_policy   = EXCLUDED.direction_policy,
            ai_presentation_mode = EXCLUDED.ai_presentation_mode,
            updated_at         = now()
        """,
        (
            operation_code,
            description,
            canonical_version,
            is_async_capable,
            direction_policy,
            ai_presentation_mode,
        ),
    )


def upsert_operation_contract(
    cur,
    operation_code: str,
    canonical_version: str,
    request_schema: Dict[str, Any],
    response_schema: Optional[Dict[str, Any]] = None,
) -> None:
    cur.execute(
        """
        INSERT INTO control_plane.operation_contracts (
            operation_code,
            canonical_version,
            request_schema,
            response_schema,
            is_active
        )
        VALUES (%s, %s, %s, %s, true)
        ON CONFLICT (operation_code, canonical_version)
        DO UPDATE SET
            request_schema  = EXCLUDED.request_schema,
            response_schema = EXCLUDED.response_schema,
            is_active       = true,
            updated_at      = now()
        """,
        (
            operation_code,
            canonical_version,
            Json(request_schema),
            Json(response_schema) if response_schema is not None else None,
        ),
    )


def upsert_auth_profile(
    cur,
    vendor_code: str,
    name: str,
    auth_type: str,
    config: Dict[str, Any],
) -> str:
    """
    Insert or update a vendor auth profile and return its id.
    Unique key is (vendor_code, profile_name).
    """
    cur.execute(
        """
        INSERT INTO control_plane.vendor_auth_profiles (
            vendor_code, profile_name, auth_type, config, is_default, is_active
        )
        VALUES (%s, %s, %s, %s, false, true)
        ON CONFLICT (vendor_code, profile_name)
        DO UPDATE SET
            auth_type = EXCLUDED.auth_type,
            config    = EXCLUDED.config,
            is_default = EXCLUDED.is_default,
            is_active = true,
            updated_at = now()
        RETURNING id
        """,
        (vendor_code, name, auth_type, Json(config)),
    )
    row = cur.fetchone()
    return str(row["id"])


def upsert_vendor_supported_operation(
    cur,
    vendor_code: str,
    operation_code: str,
    canonical_version: str,
    flow_direction: str,
) -> None:
    """
    Keyed by (vendor_code, operation_code, canonical_version, flow_direction).
    """
    cur.execute(
        """
        INSERT INTO control_plane.vendor_supported_operations (
            vendor_code,
            operation_code,
            canonical_version,
            flow_direction,
            supports_outbound,
            supports_inbound,
            is_active
        )
        VALUES (
            %s, %s, %s, %s,
            CASE WHEN %s = 'OUTBOUND' THEN true ELSE false END,
            CASE WHEN %s = 'INBOUND' THEN true ELSE false END,
            true
        )
        ON CONFLICT (vendor_code, operation_code, canonical_version, flow_direction) WHERE (is_active = true)
        DO UPDATE SET
            canonical_version = EXCLUDED.canonical_version,
            supports_outbound = EXCLUDED.supports_outbound,
            supports_inbound  = EXCLUDED.supports_inbound,
            is_active         = true,
            updated_at        = now()
        """,
        (
            vendor_code,
            operation_code,
            canonical_version,
            flow_direction,
            flow_direction,
            flow_direction,
        ),
    )


def replace_allowlist_rule(
    cur,
    *,
    source_vendor_code: Optional[str],
    target_vendor_code: Optional[str],
    is_any_source: bool,
    is_any_target: bool,
    operation_code: str,
    flow_direction: str,
    rule_scope: str = "admin",
) -> None:
    """
    Enforce a single admin rule for (source, target, op, direction).
    Delete ALL existing rows for (source, target, op, rule_scope), then insert.
    """
    cur.execute(
        """
        DELETE FROM control_plane.vendor_operation_allowlist
        WHERE (source_vendor_code IS NOT DISTINCT FROM %s)
          AND (target_vendor_code IS NOT DISTINCT FROM %s)
          AND operation_code = %s
          AND rule_scope = %s
        """,
        (source_vendor_code, target_vendor_code, operation_code, rule_scope),
    )
    cur.execute(
        """
        INSERT INTO control_plane.vendor_operation_allowlist (
            source_vendor_code,
            target_vendor_code,
            is_any_source,
            is_any_target,
            operation_code,
            rule_scope,
            flow_direction
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            source_vendor_code,
            target_vendor_code,
            is_any_source,
            is_any_target,
            operation_code,
            rule_scope,
            flow_direction,
        ),
    )


def upsert_endpoint(
    cur,
    *,
    vendor_code: str,
    operation_code: str,
    flow_direction: str,
    url: str,
    http_method: str = "POST",
    payload_format: str = "JSON",
    timeout_ms: int = 3000,
    auth_profile_id: Optional[str] = None,
) -> None:
    """
    UPSERT endpoint keyed by (vendor_code, operation_code, flow_direction).
    """
    cur.execute(
        """
        INSERT INTO control_plane.vendor_endpoints (
            vendor_code,
            operation_code,
            url,
            http_method,
            payload_format,
            timeout_ms,
            is_active,
            flow_direction,
            vendor_auth_profile_id,
            verification_status
        )
        VALUES (%s, %s, %s, %s, %s, %s, true, %s, %s, 'PENDING')
        ON CONFLICT (vendor_code, operation_code, flow_direction) WHERE (is_active = true)
        DO UPDATE SET
            url              = EXCLUDED.url,
            http_method      = EXCLUDED.http_method,
            payload_format   = EXCLUDED.payload_format,
            timeout_ms       = EXCLUDED.timeout_ms,
            is_active        = true,
            vendor_auth_profile_id  = EXCLUDED.vendor_auth_profile_id,
            updated_at       = now()
        """,
        (
            vendor_code,
            operation_code,
            url,
            http_method,
            payload_format,
            timeout_ms,
            flow_direction,
            auth_profile_id,
        ),
    )


def upsert_feature_gate_global(
    cur,
    feature_code: str,
    is_enabled: bool,
) -> None:
    """
    Global gate = vendor_code NULL.
    We treat seed as authoritative: ON CONFLICT DO UPDATE is_enabled.
    """
    cur.execute(
        """
        INSERT INTO control_plane.feature_gates (
            feature_code,
            vendor_code,
            is_enabled
        )
        VALUES (%s, NULL, %s)
        ON CONFLICT (feature_code) WHERE (vendor_code IS NULL)
        DO UPDATE SET
            is_enabled = EXCLUDED.is_enabled,
            updated_at = now()
        """,
        (feature_code, is_enabled),
    )


def upsert_platform_feature(
    cur,
    feature_code: str,
    is_enabled: Optional[bool] = None,
    description: Optional[str] = None,
) -> None:
    cur.execute(
        """
        INSERT INTO control_plane.platform_features (
            feature_code, is_enabled, description
        )
        VALUES (%s, %s, %s)
        ON CONFLICT (feature_code)
        DO UPDATE SET
            is_enabled = EXCLUDED.is_enabled,
            description = EXCLUDED.description,
            updated_at = now()
        """,
        (feature_code, is_enabled, description),
    )


def upsert_platform_phase(
    cur,
    phase_code: str,
    phase_name: str,
    description: Optional[str] = None,
) -> None:
    cur.execute(
        """
        INSERT INTO control_plane.platform_phases (
            phase_code, phase_name, description
        )
        VALUES (%s, %s, %s)
        ON CONFLICT (phase_code)
        DO UPDATE SET
            phase_name = EXCLUDED.phase_name,
            description = EXCLUDED.description,
            updated_at = now()
        """,
        (phase_code, phase_name, description),
    )


def upsert_platform_phase_feature(
    cur,
    phase_code: str,
    feature_code: str,
    is_enabled: bool = True,
) -> None:
    cur.execute(
        """
        INSERT INTO control_plane.platform_phase_features (
            phase_code, feature_code, is_enabled
        )
        VALUES (%s, %s, %s)
        ON CONFLICT (phase_code, feature_code)
        DO UPDATE SET
            is_enabled = EXCLUDED.is_enabled
        """,
        (phase_code, feature_code, is_enabled),
    )


def upsert_platform_setting(cur, settings_key: str, settings_value: str) -> None:
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
        """,
        (settings_key, settings_value),
    )


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

def seed_allowlist(cur) -> None:
    """
    Admin/global rules:

    - Explicit vendor-to-vendor pairs for all seeded operations (OUTBOUND)
    """
    # Clean out old admin rules for these ops so re-runs are deterministic
    cur.execute(
        """
        DELETE FROM control_plane.vendor_operation_allowlist
        WHERE rule_scope = 'admin'
          AND operation_code = ANY(%s)
        """
        ,
        (SEEDED_OPS,)
    )

    # Explicit pair rules for all seeded operations (no wildcard semantics)
    for op in SEEDED_OPS:
        for source_vendor in DEMO_LICS:
            for target_vendor in DEMO_LICS:
                if source_vendor == target_vendor:
                    continue
                cur.execute(
                    """
                    INSERT INTO control_plane.vendor_operation_allowlist (
                        source_vendor_code,
                        target_vendor_code,
                        is_any_source,
                        is_any_target,
                        operation_code,
                        rule_scope,
                        flow_direction
                    ) VALUES (
                        %s,
                        %s,
                        FALSE,
                        FALSE,
                        %s,
                        'admin',
                        'OUTBOUND'
                    )
                    """,
                    (source_vendor, target_vendor, op),
                )


def seed_all(cur) -> None:
    # -----------------------------
    # Vendors
    # -----------------------------
    upsert_vendor(cur, "LH001", "Elevance Health, Inc")
    upsert_vendor(cur, "LH002", "Excellus Health Plan")
    upsert_vendor(cur, "LH023", "MassHealth")
    upsert_vendor(cur, "LH030", "Horizon Blue Cross Blue Shield")
    upsert_vendor(cur, "LH046", "CareFirst BlueCross BlueShield")
    # -----------------------------
    # Operations
    # -----------------------------
    upsert_operation(
        cur,
        operation_code="GET_COB_INQUIRY",
        description="Coordination of benefits inquiry",
        canonical_version="v1",
        direction_policy="TWO_WAY",
        is_async_capable=True,
        ai_presentation_mode="RAW_AND_FORMATTED",
    )
    upsert_operation(
        cur,
        operation_code="GET_VERIFY_MEMBER_ELIGIBILITY",
        description="Verify member eligibility",
        canonical_version="v1",
        direction_policy="TWO_WAY",
        is_async_capable=True,
        ai_presentation_mode="RAW_AND_FORMATTED",
    )
    upsert_operation(
        cur,
        operation_code="GET_PROVIDER_CONTRACT_STATUS",
        description="Check provider contract status",
        canonical_version="v1",
        direction_policy="TWO_WAY",
        is_async_capable=True,
        ai_presentation_mode="RAW_AND_FORMATTED",
    )
    upsert_operation(
        cur,
        operation_code="GET_EXCHANGE_RATE_DEMO",
        description="Demo: get FX rate",
        canonical_version="v1",
        direction_policy="TWO_WAY",
        is_async_capable=True,
        ai_presentation_mode="RAW_AND_FORMATTED",
    )
    upsert_operation(
        cur,
        operation_code="GET_JOKE_DEMO",
        description="Demo: get a joke",
        canonical_version="v1",
        direction_policy="TWO_WAY",
        is_async_capable=True,
        ai_presentation_mode="RAW_AND_FORMATTED",
    )

    # -----------------------------
    # Canonical contracts
    # -----------------------------
    upsert_operation_contract(
        cur,
        "GET_COB_INQUIRY",
        "v1",
        request_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "memberIdWithPrefix": {
                    "type": "string",
                    "minLength": 20,
                    "maxLength": 20,
                    "description": "Required, exact length 20",
                }
            },
            "required": ["memberIdWithPrefix"],
        },
        response_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "memberIdWithPrefix": {"type": "string"},
                "name": {"type": "string"},
                "dob": {"type": "string", "format": "date"},
                "claimNumber": {"type": "string"},
                "dateOfService": {"type": "string", "format": "date"},
                "status": {"type": "string"},
            },
            "required": ["memberIdWithPrefix", "name", "dob", "status"],
            "oneOf": [
                {"required": ["claimNumber"]},
                {"required": ["dateOfService"]},
            ],
        },
    )
    upsert_operation_contract(
        cur,
        "GET_VERIFY_MEMBER_ELIGIBILITY",
        "v1",
        request_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "memberIdWithPrefix": {"type": "string"},
                "date": {"type": "string", "format": "date"},
            },
            "required": ["memberIdWithPrefix", "date"],
        },
        response_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "memberIdWithPrefix": {"type": "string"},
                "name": {"type": "string"},
                "dob": {"type": "string", "format": "date"},
                "claimNumber": {"type": "string"},
                "dateOfService": {"type": "string", "format": "date"},
                "status": {"type": "string"},
            },
            "required": ["memberIdWithPrefix", "name", "dob", "status"],
            "oneOf": [
                {"required": ["claimNumber"]},
                {"required": ["dateOfService"]},
            ],
        },
    )
    upsert_operation_contract(
        cur,
        "GET_PROVIDER_CONTRACT_STATUS",
        "v1",
        request_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "memberIdWithPrefix": {"type": "string"},
            },
            "required": ["memberIdWithPrefix"],
        },
        response_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "memberIdWithPrefix": {"type": "string"},
                "name": {"type": "string"},
                "dob": {"type": "string", "format": "date"},
                "kpi": {"type": "string"},
                "taxId": {"type": "string"},
                "deliveryMethod": {"type": "string"},
                "claimNumber": {"type": "string"},
                "dateOfService": {"type": "string", "format": "date"},
                "status": {"type": "string"},
            },
            "required": [
                "memberIdWithPrefix",
                "name",
                "dob",
                "kpi",
                "taxId",
                "deliveryMethod",
                "status",
            ],
            "oneOf": [
                {"required": ["claimNumber"]},
                {"required": ["dateOfService"]},
            ],
        },
    )
    upsert_operation_contract(
        cur,
        "GET_EXCHANGE_RATE_DEMO",
        "v1",
        request_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "baseCurrency": {"type": "string", "minLength": 3, "maxLength": 3},
                "targetCurrency": {"type": "string", "minLength": 3, "maxLength": 3},
                "date": {"type": "string", "format": "date"},
            },
            "required": ["baseCurrency", "targetCurrency"],
        },
        response_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "baseCurrency": {"type": "string"},
                "targetCurrency": {"type": "string"},
                "date": {"type": "string", "format": "date"},
                "rate": {"type": "number"},
            },
            "required": ["baseCurrency", "targetCurrency", "rate"],
        },
    )
    upsert_operation_contract(
        cur,
        "GET_JOKE_DEMO",
        "v1",
        request_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "category": {"type": "string"},
            },
        },
        response_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "id": {"type": "string"},
                "joke": {"type": "string"},
                "source": {"type": "string"},
            },
            "required": ["id", "joke"],
        },
    )

    # -----------------------------
    # Auth profiles (for demo outbound calls)
    # -----------------------------
    lh001_api_key_id = upsert_auth_profile(
        cur,
        vendor_code="LH001",
        name="DemoApiKeyHeader",
        auth_type="API_KEY_HEADER",
        config={
            "headerName": "Api-Key",
            "apiKey": os.getenv("DEMO_EXCHANGE_API_KEY", "demo-exchange-key"),
        },
    )
    lh001_bearer_id = upsert_auth_profile(
        cur,
        vendor_code="LH001",
        name="DemoBearerToken",
        auth_type="STATIC_BEARER",
        config={
            "headerName": "Authorization",
            "prefix": "Bearer ",
            "token": os.getenv("DEMO_JOKE_API_TOKEN", "demo-joke-token"),
        },
    )

    # -----------------------------
    # Vendor supported operations
    # -----------------------------
    for vendor_code in DEMO_LICS:
        for op_code in SEEDED_OPS:
            upsert_vendor_supported_operation(
                cur,
                vendor_code=vendor_code,
                operation_code=op_code,
                canonical_version="v1",
                flow_direction="OUTBOUND",
            )

    # -----------------------------
    # Allowlist – access control
    # -----------------------------
    seed_allowlist(cur)

    # -----------------------------
    # Endpoints
    # -----------------------------
    cob_url = os.getenv("LH002_COB_URL") or "https://partners-mock-payers.onrender.com/api/get-cob-inquiry"
    eligibility_url = os.getenv("LH002_ELIGIBILITY_URL") or "https://partners-mock-payers.onrender.com/api/get-verify-member-eligibility"
    contract_status_url = os.getenv("LH002_CONTRACT_STATUS_URL") or "https://partners-mock-payers.onrender.com/api/get-provider-contract-status"
    fx_url = os.getenv("DEMO_EXCHANGE_URL") or "https://api.exchangerate.host/latest"
    joke_url = os.getenv("DEMO_JOKE_URL") or "https://official-joke-api.appspot.com/jokes/random"

    # Health ops — OUTBOUND for all five vendors
    for vendor_code in DEMO_LICS:
        for op_code, endpoint_url in [
            ("GET_COB_INQUIRY", cob_url),
            ("GET_VERIFY_MEMBER_ELIGIBILITY", eligibility_url),
            ("GET_PROVIDER_CONTRACT_STATUS", contract_status_url),
        ]:
            upsert_endpoint(
                cur,
                vendor_code=vendor_code,
                operation_code=op_code,
                flow_direction="OUTBOUND",
                url=endpoint_url,
                http_method="POST",
                payload_format="JSON",
                timeout_ms=5000,
                auth_profile_id=None,
            )

    # Demo ops — OUTBOUND for all five vendors
    for vendor_code in DEMO_LICS:
        for op_code, endpoint_url in [
            ("GET_JOKE_DEMO", joke_url),
            ("GET_EXCHANGE_RATE_DEMO", fx_url),
        ]:
            demo_auth_profile_id: Optional[str] = None
            if vendor_code == "LH001":
                if op_code == "GET_EXCHANGE_RATE_DEMO":
                    demo_auth_profile_id = lh001_api_key_id
                elif op_code == "GET_JOKE_DEMO":
                    demo_auth_profile_id = lh001_bearer_id
            upsert_endpoint(
                cur,
                vendor_code=vendor_code,
                operation_code=op_code,
                flow_direction="OUTBOUND",
                url=endpoint_url,
                http_method="GET",
                payload_format="JSON",
                timeout_ms=5000,
                auth_profile_id=demo_auth_profile_id,
            )

    # -----------------------------
    # Feature gates (global) – use backend gate codes
    # -----------------------------
    upsert_feature_gate_global(cur, "GATE_ALLOWLIST_RULE", False)
    upsert_feature_gate_global(cur, "GATE_ENDPOINT_CONFIG", False)
    upsert_feature_gate_global(cur, "GATE_MAPPING_CONFIG", False)
    upsert_feature_gate_global(cur, "GATE_VENDOR_CONTRACT_CHANGE", False)
    upsert_feature_gate_global(cur, "ai_formatter_enabled", True)
    upsert_feature_gate_global(cur, "mission_control", True)

    # -----------------------------
    # Platform rollout (Journey Mode)
    # -----------------------------
    for code in PLATFORM_FEATURE_CODES:
        upsert_platform_feature(cur, code, None, None)

    for phase_code, phase_name, description in PLATFORM_PHASES:
        upsert_platform_phase(cur, phase_code, phase_name, description)

    for phase_code, feature_codes in PHASE_FEATURES.items():
        for feature_code in sorted(feature_codes):
            upsert_platform_phase_feature(cur, phase_code, feature_code, True)

    upsert_platform_setting(cur, "CURRENT_PHASE", "PHASE_0")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    conn = get_conn()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. Clear all control_plane tables
                print("[seed_local] Clearing control_plane...")
                clear_control_plane(cur)

                # 2. Validate empty
                if not validate_control_plane_empty(cur):
                    print("[seed_local] ERROR: Some control_plane tables are not empty. Aborting.")
                    sys.exit(1)
                print("[seed_local] All control_plane tables empty. Proceeding to seed.")

                # 3. Seed
                seed_all(cur)
        print("[seed_local] Seed completed successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[seed_local] ERROR: {exc!r}", file=sys.stderr)
        sys.exit(1)
