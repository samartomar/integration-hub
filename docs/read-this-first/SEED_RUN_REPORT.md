# Seed Run Report (Clear + Validate + Original Proposed Seed)

## What was done

1. **DELETE** from all `control_plane.*` tables in FK-safe order (16 tables).
2. **Validate** that all tables were empty before seeding.
3. **Seed** using the proposed seed file (as sent, with one needed fix to run it).

## Failures

### 1. `upsert_vendor` calls missing `cur` (blocks all seeding)
- **Error:** `TypeError: upsert_vendor() missing 1 required positional argument: 'vendor_name'`
- **Cause:** Calls were `upsert_vendor("LH001", "Elevance Health, Inc")` but the function expects `upsert_vendor(cur, vendor_code, vendor_name)`. Without `cur`, execution fails.
- **Workaround used for testing:** Restored `cur` in the 5 `upsert_vendor` calls so the rest of the seed could run.

### 2. ON CONFLICT constraint mismatch
- **Error:** `InvalidColumnReference('there is no unique or exclusion constraint matching the ON CONFLICT specification')`
- **Likely causes (one or more of):**
  - **vendor_supported_operations:** Uses `ON CONFLICT (vendor_code, operation_code, flow_direction)`, but the unique index is `(vendor_code, operation_code, canonical_version, flow_direction)` so `canonical_version` is missing.
  - **vendor_endpoints:** Uses `ON CONFLICT (vendor_code, operation_code, flow_direction)` without `WHERE (is_active = true)`; the unique index is partial.
  - **feature_gates:** Uses `ON CONFLICT (feature_code) WHERE vendor_code IS NULL`; the predicate syntax may not match the partial unique index.
- **Outcome:** Seed stops at the first failing upsert.

## Summary

| Step          | Result                              |
|---------------|-------------------------------------|
| Clear tables  | Passed (tables emptied)             |
| Validate empty| Passed (all empty)                  |
| Seed          | Failed (ON CONFLICT specification)  |

The proposed seed file cannot complete until:

1. `vendor_supported_operations` `ON CONFLICT` is updated to match the unique index (include `canonical_version`, and `WHERE (is_active = true)` for the partial index).
2. `vendor_endpoints` `ON CONFLICT` is updated to include `WHERE (is_active = true)` for the partial unique index.
3. `feature_gates` `ON CONFLICT` is checked for correct partial index syntax.
