-- Seed control_plane with sample vendors, operations, allowlist, and endpoints.
-- Run after: alembic upgrade head
-- Replace <VENDOR_B_MOCK> with your actual mock URL (e.g. https://httpbin.org/post or local mock).

INSERT INTO control_plane.vendors (vendor_code, vendor_name)
VALUES ('LH001','Vendor A'), ('LH002','Vendor B')
ON CONFLICT (vendor_code) DO NOTHING;

INSERT INTO control_plane.operations (operation_code, description, canonical_version, is_async_capable, is_active)
VALUES ('GET_RECEIPT','Get receipt by transactionId','v1',true,true)
ON CONFLICT (operation_code) DO NOTHING;

-- Baseline: use is_any_source/is_any_target (FALSE for exact); flow_direction default BOTH
INSERT INTO control_plane.vendor_operation_allowlist (source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, rule_scope, flow_direction)
VALUES ('LH001','LH002',FALSE,FALSE,'GET_RECEIPT','admin','BOTH')
ON CONFLICT (COALESCE(source_vendor_code, '*'), is_any_source, COALESCE(target_vendor_code, '*'), is_any_target, operation_code, rule_scope, flow_direction) DO NOTHING;

INSERT INTO control_plane.vendor_endpoints (vendor_code, operation_code, url, http_method, payload_format, timeout_ms, is_active)
VALUES ('LH002','GET_RECEIPT','https://<VENDOR_B_MOCK>/receipt','POST','JSON',8000,true)
ON CONFLICT (vendor_code, operation_code) DO UPDATE SET
    url = EXCLUDED.url,
    http_method = EXCLUDED.http_method,
    payload_format = EXCLUDED.payload_format,
    timeout_ms = EXCLUDED.timeout_ms,
    is_active = EXCLUDED.is_active;

-- Operation contracts (v9): GET_RECEIPT v1 - request_schema requires transactionId (string minLength 1)
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
