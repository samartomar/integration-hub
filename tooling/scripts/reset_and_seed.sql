-- Repeatable clean test: TRUNCATE + seed baseline.
-- Run: psql $DATABASE_URL -f scripts/reset_and_seed.sql
-- Or: ./tooling/scripts/aws_reset_and_seed.sh

BEGIN;

-- 1) TRUNCATE in dependency order (children first)
-- data_plane: audit_events references transactions conceptually
TRUNCATE TABLE data_plane.audit_events RESTART IDENTITY CASCADE;
TRUNCATE TABLE data_plane.transactions RESTART IDENTITY CASCADE;

-- control_plane: vendor_endpoints, allowlist, operation_contracts (vendor_api_keys table removed)
TRUNCATE TABLE control_plane.vendor_endpoints RESTART IDENTITY CASCADE;
TRUNCATE TABLE control_plane.allowlist_change_requests RESTART IDENTITY CASCADE;
TRUNCATE TABLE control_plane.vendor_change_requests RESTART IDENTITY CASCADE;
TRUNCATE TABLE control_plane.vendor_operation_allowlist RESTART IDENTITY CASCADE;
TRUNCATE TABLE control_plane.operation_contracts RESTART IDENTITY CASCADE;
TRUNCATE TABLE control_plane.operations RESTART IDENTITY CASCADE;
TRUNCATE TABLE control_plane.vendors RESTART IDENTITY CASCADE;

-- 2) Seed baseline
INSERT INTO control_plane.vendors (vendor_code, vendor_name)
VALUES ('LH001', 'Vendor A'), ('LH002', 'Vendor B')
ON CONFLICT (vendor_code) DO UPDATE SET vendor_name = EXCLUDED.vendor_name;

INSERT INTO control_plane.operations (operation_code, description, canonical_version, is_async_capable, is_active)
VALUES ('GET_RECEIPT', 'Get receipt by transactionId', 'v1', true, true)
ON CONFLICT (operation_code) DO UPDATE SET
  description = EXCLUDED.description,
  canonical_version = EXCLUDED.canonical_version,
  is_async_capable = EXCLUDED.is_async_capable,
  is_active = EXCLUDED.is_active;

INSERT INTO control_plane.operation_contracts (operation_code, canonical_version, request_schema, response_schema, is_active)
VALUES (
  'GET_RECEIPT',
  'v1',
  '{"type":"object","required":["transactionId"],"properties":{"transactionId":{"type":"string","minLength":1}}}'::jsonb,
  NULL,
  true
)
ON CONFLICT (operation_code, canonical_version) DO UPDATE SET
  request_schema = EXCLUDED.request_schema,
  response_schema = EXCLUDED.response_schema,
  is_active = EXCLUDED.is_active,
  updated_at = now();

-- Baseline: use is_any_source/is_any_target (FALSE for exact); flow_direction default BOTH
INSERT INTO control_plane.vendor_operation_allowlist (source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, rule_scope, flow_direction)
VALUES ('LH001', 'LH002', FALSE, FALSE, 'GET_RECEIPT', 'admin', 'BOTH')
ON CONFLICT (COALESCE(source_vendor_code, '*'), is_any_source, COALESCE(target_vendor_code, '*'), is_any_target, operation_code, rule_scope, flow_direction) DO NOTHING;

-- Endpoint: postman-echo (echoes request for easy verification)
INSERT INTO control_plane.vendor_endpoints (vendor_code, operation_code, url, http_method, payload_format, timeout_ms, is_active)
VALUES ('LH002', 'GET_RECEIPT', 'https://postman-echo.com/post', 'POST', 'JSON', 8000, true)
ON CONFLICT (vendor_code, operation_code) DO UPDATE SET
  url = EXCLUDED.url,
  http_method = EXCLUDED.http_method,
  payload_format = EXCLUDED.payload_format,
  timeout_ms = EXCLUDED.timeout_ms,
  is_active = EXCLUDED.is_active;

COMMIT;
