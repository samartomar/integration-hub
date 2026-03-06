#!/usr/bin/env python3
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

import requests

try:
    import psycopg2
except ImportError:
    print("Missing dependency: psycopg2-binary. Install with: pip install psycopg2-binary")
    sys.exit(2)


# --------------------------
# Configuration + Utilities
# --------------------------

@dataclass
class Config:
    database_url: str
    vendor_api_base_url: str
    admin_api_base_url: str
    reset_sql_path: str
    execute_path: str = "/v1/execute"
    vendor_api_key: str | None = None
    vendor_jwt: str | None = None
    ai_tool_url: str | None = None
    ai_tool_api_key: str | None = None
    timeout_s: int = 20


def require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def load_config() -> Config:
    return Config(
        database_url=require_env("DATABASE_URL"),
        vendor_api_base_url=require_env("VENDOR_API_BASE_URL").rstrip("/"),
        admin_api_base_url=require_env("ADMIN_API_BASE_URL").rstrip("/"),
        reset_sql_path=require_env("RESET_SQL_PATH"),
        execute_path=(os.getenv("EXECUTE_PATH") or "/v1/execute").strip() or "/v1/execute",
        vendor_api_key=os.getenv("VENDOR_API_KEY"),
        vendor_jwt=os.getenv("VENDOR_JWT"),
        ai_tool_url=os.getenv("AI_TOOL_URL"),
        ai_tool_api_key=os.getenv("AI_TOOL_API_KEY"),
        timeout_s=int(os.getenv("HTTP_TIMEOUT_S", "20")),
    )


def http_headers(cfg: Config, include_vendor_auth: bool = False, extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if include_vendor_auth and cfg.vendor_jwt:
        h["Authorization"] = f"Bearer {cfg.vendor_jwt}"
    if extra:
        h.update(extra)
    return h


def die(msg: str) -> None:
    print(f"\n❌ FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"✅ {msg}")


def warn(msg: str) -> None:
    print(f"⚠️  {msg}")


def pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, default=str)


# --------------------------
# DB Helpers
# --------------------------

def run_sql_file(cfg: Config) -> None:
    if not os.path.exists(cfg.reset_sql_path):
        die(f"RESET_SQL_PATH not found: {cfg.reset_sql_path}")

    sql = open(cfg.reset_sql_path, encoding="utf-8").read()

    # psycopg2: execute multi-statement script (split by semicolon for safety)
    with psycopg2.connect(cfg.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def db_one(cfg: Config, sql: str, params: tuple[Any, ...] | None = None) -> tuple[Any, ...]:
    with psycopg2.connect(cfg.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            if not row:
                raise RuntimeError("DB query returned no rows")
            return row


def db_all(cfg: Config, sql: str, params: tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
    with psycopg2.connect(cfg.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


# --------------------------
# API Helpers
# --------------------------

def post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout_s: int) -> tuple[int, dict[str, Any]]:
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout_s)
    try:
        body = r.json()
    except Exception:
        body = {"_raw": r.text}
    return r.status_code, body


def get_json(url: str, headers: dict[str, str], timeout_s: int) -> tuple[int, dict[str, Any]]:
    r = requests.get(url, headers=headers, timeout=timeout_s)
    try:
        body = r.json()
    except Exception:
        body = {"_raw": r.text}
    return r.status_code, body


# --------------------------
# Smoke Tests
# --------------------------

def assert_counts_zero(cfg: Config) -> None:
    tx = db_one(cfg, "SELECT COUNT(*) FROM data_plane.transactions;")[0]
    au = db_one(cfg, "SELECT COUNT(*) FROM data_plane.audit_events;")[0]
    if tx != 0 or au != 0:
        die(f"Expected empty data_plane after reset. transactions={tx}, audit_events={au}")
    ok("DB reset verified: data_plane empty")


def execute_happy(cfg: Config, test_run: str) -> str:
    url = f"{cfg.vendor_api_base_url}{cfg.execute_path}"
    idem = f"{test_run}-happy-001"
    payload = {
        "targetVendor": "LH002",
        "operation": "GET_RECEIPT",
        "idempotencyKey": idem,
        "parameters": {"transactionId": "123"},
    }

    status, body = post_json(url, payload, http_headers(cfg, include_vendor_auth=True), cfg.timeout_s)
    if status not in (200, 201):
        die(f"Happy execute failed HTTP {status}: {pretty(body)}")

    tx_id = body.get("transactionId") or body.get("responseBody", {}).get("transactionId")
    if not tx_id:
        die(f"Happy execute response missing transactionId: {pretty(body)}")

    # DB validation
    row = db_one(cfg, """
        SELECT status, idempotency_key
        FROM data_plane.transactions
        WHERE transaction_id=%s;
    """, (tx_id,))
    if row[0] != "completed":
        die(f"Expected completed for happy tx. got status={row[0]} tx={tx_id}")

    ok(f"Happy path execute ok: transaction_id={tx_id}")
    return idem


def execute_replay(cfg: Config, test_run: str, idem: str) -> None:
    url = f"{cfg.vendor_api_base_url}{cfg.execute_path}"
    payload = {
        "targetVendor": "LH002",
        "operation": "GET_RECEIPT",
        "idempotencyKey": idem,
        "parameters": {"transactionId": "123"},
    }

    status, body = post_json(url, payload, http_headers(cfg, include_vendor_auth=True), cfg.timeout_s)
    if status not in (200, 201):
        die(f"Replay execute failed HTTP {status}: {pretty(body)}")

    # Ensure only one row exists for that idempotency key
    cnt = db_one(cfg, """
        SELECT COUNT(*)
        FROM data_plane.transactions
        WHERE source_vendor='LH001' AND idempotency_key=%s;
    """, (idem,))[0]
    if cnt != 1:
        die(f"Replay should not create new rows. expected 1 got {cnt} for idem={idem}")

    ok("Replay verified: no new transaction row created")


def execute_validation_fail(cfg: Config, test_run: str) -> str:
    url = f"{cfg.vendor_api_base_url}{cfg.execute_path}"
    idem = f"{test_run}-validate-001"
    payload = {
        "targetVendor": "LH002",
        "operation": "GET_RECEIPT",
        "idempotencyKey": idem,
        "parameters": {"transactionId": ""},  # should fail schema
    }

    status, body = post_json(url, payload, http_headers(cfg, include_vendor_auth=True), cfg.timeout_s)
    # your API might return 400 or 200 with an error envelope; accept both but validate DB
    if status not in (200, 400):
        die(f"Validation test unexpected HTTP {status}: {pretty(body)}")

    # find tx by idempotency key
    rows = db_all(cfg, """
        SELECT transaction_id, status, response_body
        FROM data_plane.transactions
        WHERE source_vendor='LH001' AND idempotency_key=%s
        ORDER BY created_at DESC
        LIMIT 1;
    """, (idem,))
    if not rows:
        die(f"No transaction row created for validation fail idem={idem}")

    tx_id, st, resp = rows[0]
    if st != "validation_failed":
        die(f"Expected validation_failed status. got {st}. tx={tx_id} resp={resp}")

    ok(f"Validation failure recorded correctly: transaction_id={tx_id}")
    return tx_id


def redrive(cfg: Config, parent_transaction_id: str) -> str:
    url = f"{cfg.admin_api_base_url}/v1/admin/redrive/{parent_transaction_id}"
    status, body = post_json(url, {}, http_headers(cfg, include_vendor_auth=False), cfg.timeout_s)
    if status not in (200, 400):
        die(f"Redrive unexpected HTTP {status}: {pretty(body)}")

    child_tx = body.get("transactionId")
    if not child_tx:
        # some implementations only return error envelope; still check DB
        warn(f"Redrive response missing transactionId, will detect from DB. Response: {pretty(body)}")
        child_tx = ""

    # detect latest child tx that points to parent (by parent_transaction_id PK is harder; here parent is external transaction_id)
    # We'll find by audit REDRIVE_START if available or by created_at around now; simplest: query last 5 and pick newest with redrive_count>0
    rows = db_all(cfg, """
        SELECT transaction_id, status, redrive_count, parent_transaction_id
        FROM data_plane.transactions
        ORDER BY created_at DESC
        LIMIT 10;
    """)
    child = next((r for r in rows if (r[2] or 0) > 0), None)
    if not child:
        die("Could not find redriven child transaction in DB (redrive_count>0)")

    tx_id, st, rc, parent_pk = child
    if rc < 1 or parent_pk is None:
        die(f"Redrive child row missing linkage. tx={tx_id}, redrive_count={rc}, parent_transaction_id={parent_pk}")

    ok(f"Redrive created child tx: {tx_id} (status={st}, redrive_count={rc})")
    return tx_id


def ai_tool_tests(cfg: Config) -> None:
    if not cfg.ai_tool_url:
        warn("AI_TOOL_URL not set; skipping AI tool tests")
        return

    # Missing param -> NEEDS_INPUT
    payload_missing = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "operation": "GET_RECEIPT",
        "parameters": {},
    }
    headers = {"Content-Type": "application/json"}
    if cfg.ai_tool_api_key:
        headers["Authorization"] = f"Bearer {cfg.ai_tool_api_key}"

    s1, b1 = post_json(cfg.ai_tool_url, payload_missing, headers, cfg.timeout_s)
    if s1 not in (200, 400):
        die(f"AI tool missing-params unexpected HTTP {s1}: {pretty(b1)}")
    if (b1.get("status") or "").upper() != "NEEDS_INPUT":
        die(f"AI tool should return NEEDS_INPUT for missing params. got: {pretty(b1)}")
    ok("AI Tool NEEDS_INPUT behavior verified")

    # Valid -> OK
    payload_ok = {
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "operation": "GET_RECEIPT",
        "parameters": {"transactionId": "123"},
        "idempotencyKey": f"ai-tool-{int(time.time())}",
    }
    s2, b2 = post_json(cfg.ai_tool_url, payload_ok, headers, cfg.timeout_s)
    if s2 not in (200, 201):
        die(f"AI tool OK unexpected HTTP {s2}: {pretty(b2)}")
    if (b2.get("status") or "").upper() not in ("OK", "SUCCESS"):
        die(f"AI tool should return OK/SUCCESS. got: {pretty(b2)}")
    ok("AI Tool OK execution verified")


def main() -> None:
    cfg = load_config()
    test_run = f"t{int(time.time())}"

    print("=== Integration Hub Smoke Test ===")
    print(f"Vendor API: {cfg.vendor_api_base_url}")
    print(f"Admin  API: {cfg.admin_api_base_url}")
    print(f"Reset SQL:  {cfg.reset_sql_path}")
    if cfg.vendor_jwt:
        print("Vendor JWT: (set)")
    elif cfg.vendor_api_key:
        print("Vendor API Key: (set, fallback mode)")
    else:
        warn("No vendor auth found. Set VENDOR_JWT (preferred) or VENDOR_API_KEY (fallback).")

    # 1) Reset + seed
    print("\n[1/5] Reset + seed DB...")
    run_sql_file(cfg)
    ok("Reset + seed SQL executed")

    # 2) Verify empty dataplane
    print("\n[2/5] Verify DB clean state...")
    assert_counts_zero(cfg)

    # 3) Execute happy + replay
    print("\n[3/5] Execute happy path + replay...")
    idem = execute_happy(cfg, test_run)
    execute_replay(cfg, test_run, idem)

    # 4) Validation failure + redrive
    print("\n[4/5] Validation fail + redrive...")
    parent_tx = execute_validation_fail(cfg, test_run)
    _child_tx = redrive(cfg, parent_tx)

    # 5) AI Tool tests (optional)
    print("\n[5/5] AI tool tests (optional)...")
    ai_tool_tests(cfg)

    print("\n🎉 ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
