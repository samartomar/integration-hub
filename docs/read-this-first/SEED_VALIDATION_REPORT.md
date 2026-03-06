# Seed File Validation Report

Validation of the proposed `seed_local.py` against schema, backend expectations, and design alignment.

> Note: endpoint outbound auth has since moved to `control_plane.vendor_auth_profiles` + `vendor_endpoints.vendor_auth_profile_id`.
> References to `auth_profiles` in this historical report are legacy context.

---

## Critical bugs (must fix)

### 1. **upsert_vendor calls missing `cur` argument**
```python
# WRONG
upsert_vendor("LH001", "Elevance Health, Inc")

# CORRECT
upsert_vendor(cur, "LH001", "Elevance Health, Inc")
```
All five `upsert_vendor` calls in `seed_all` are missing the cursor.

---

### 2. **vendor_supported_operations ON CONFLICT wrong**
Schema unique index: `(vendor_code, operation_code, canonical_version, flow_direction)` WHERE is_active = true.

Proposed:
```sql
ON CONFLICT (vendor_code, operation_code, flow_direction)
```
This will fail: no unique index on those three columns alone.

**Fix:** Include `canonical_version`:
```sql
ON CONFLICT (vendor_code, operation_code, canonical_version, flow_direction)
DO UPDATE SET canonical_version = EXCLUDED.canonical_version, is_active = true, updated_at = now()
```
Note: PostgreSQL partial unique indexes require the conflict target to match the index columns. The index includes all four columns.

---

### 3. **auth_type: BEARER_TOKEN invalid**
Backend expects: `API_KEY_HEADER`, `API_KEY_QUERY`, `STATIC_BEARER`, `BASIC`, `OAUTH2_CLIENT_CREDENTIALS`, `NONE`.

**Fix:** Use `STATIC_BEARER` instead of `BEARER_TOKEN`.

Config for STATIC_BEARER (from routing_lambda):
- `headerName` (optional, default `Authorization`)
- `token` or `secretRef`
- `prefix` (optional, default `Bearer `)

Proposed config uses `tokenPrefix` + `token` — change to `prefix` + `token` for consistency.

---

### 4. **Feature gate codes don't match backend**
Backend (`approval_utils`, `registry_lambda`) expects:
- `GATE_ALLOWLIST_RULE`
- `GATE_ENDPOINT_CONFIG`
- `GATE_MAPPING_CONFIG`
- `GATE_VENDOR_CONTRACT_CHANGE`

Proposed uses: `vendor_endpoint_gating`, `canonical_mapping_approval`, `ai_formatter_enabled`, `local_demo_mode`.

**Fix:** Use the backend gate codes, e.g.:
```python
upsert_feature_gate_global(cur, "GATE_ALLOWLIST_RULE", False)
upsert_feature_gate_global(cur, "GATE_ENDPOINT_CONFIG", False)
upsert_feature_gate_global(cur, "GATE_MAPPING_CONFIG", False)
upsert_feature_gate_global(cur, "GATE_VENDOR_CONTRACT_CHANGE", False)
```

---

### 5. **replace_allowlist_rule delete too narrow**
Proposed delete includes `flow_direction` in the WHERE clause. That leaves rules with other flow_directions (e.g. BOTH) when reseeding, leading to duplicate or conflicting rules.

**Fix:** Delete all admin rules for `(source, target, op)` regardless of flow_direction:
```python
cur.execute("""
    DELETE FROM control_plane.vendor_operation_allowlist
    WHERE (source_vendor_code IS NOT DISTINCT FROM %s)
      AND (target_vendor_code IS NOT DISTINCT FROM %s)
      AND operation_code = %s
      AND rule_scope = %s
""", (source_vendor_code, target_vendor_code, operation_code, rule_scope))
```
Then INSERT the desired row.

---

### 6. **feature_gates ON CONFLICT syntax**
v51 has partial unique index: `(feature_code) WHERE vendor_code IS NULL`.

PostgreSQL 15+ supports:
```sql
ON CONFLICT (feature_code) WHERE (vendor_code IS NULL) DO UPDATE SET ...
```
Use parentheses around the predicate: `WHERE (vendor_code IS NULL)`.

---

## Schema checks

| Table / Operation | Schema / Expectation | Proposed | Status |
|-------------------|---------------------|----------|--------|
| vendors | ON CONFLICT (vendor_code) | ✓ | OK |
| operations | ON CONFLICT (operation_code) | ✓ | OK |
| operation_contracts | ON CONFLICT (operation_code, canonical_version) | ✓ | OK |
| auth_profiles | UNIQUE (vendor_code, name) | ✓ | OK |
| vendor_supported_operations | (vendor_code, operation_code, canonical_version, flow_direction) | ✗ Missing canonical_version | Fix |
| vendor_endpoints | (vendor_code, operation_code, flow_direction) WHERE is_active | ✓ | OK |
| feature_gates | (feature_code) WHERE vendor_code IS NULL | Need WHERE (vendor_code IS NULL) | Fix |
| allowlist | DELETE by (src, tgt, op, scope) not flow_direction | ✗ Includes flow_direction | Fix |

---

## Logic and semantics

- **GET_RECEIPT direction_policy:** `PROVIDER_RECEIVES_ONLY` ✓
- **Allowlist:** LH001 OUTBOUND → LH002 for GET_RECEIPT ✓
- **Vendor supported ops:** LH001 OUTBOUND for all; LH002 INBOUND for GET_RECEIPT ✓
- **Endpoints:** LH002 INBOUND GET_RECEIPT; LH001 OUTBOUND for all ✓
- **Auth profiles:** NONE, API_KEY_HEADER, STATIC_BEARER usage is fine once auth_type fixed

---

## Minor / optional

1. **operations.ai_presentation_mode** — Baseline includes this column; proposed passes it. ✓
2. **conn.autocommit** — Proposed uses `with conn:` (transaction) + `cur`; current seed uses `conn.autocommit = True`. Either is fine; proposed pattern is clearer for transactional seed.
3. **auth_profile for NONE** — Using an explicit "NoAuth" profile with `auth_type="NONE"` is optional; `auth_profile_id=None` on the endpoint is equivalent.

---

## Summary

| Category | Count |
|----------|-------|
| Critical bugs | 6 |
| Schema OK | Most tables |
| Logic OK | Yes (after fixes) |

Apply the listed fixes before using this seed in production or shared environments.
