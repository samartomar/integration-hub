-- Local seed (explicit matrix). Run after migrations.

-- 1) Vendors
INSERT INTO control_plane.vendors (vendor_code, vendor_name, is_active)
VALUES
  ('LH001', 'Elevance Health, Inc', true),
  ('LH002', 'Excellus Health Plan', true),
  ('LH023', 'MassHealth', true),
  ('LH030', 'Horizon Blue Cross Blue Shield', true),
  ('LH046', 'CareFirst BlueCross BlueShield', true)
ON CONFLICT (vendor_code) DO UPDATE
SET vendor_name = EXCLUDED.vendor_name,
    is_active = EXCLUDED.is_active;

-- 2) Operations
INSERT INTO control_plane.operations
  (operation_code, description, canonical_version, is_async_capable, is_active, direction_policy, ai_presentation_mode)
VALUES
  ('GET_COB_INQUIRY', 'Coordination of benefits inquiry', 'v1', true, true, 'TWO_WAY', 'RAW_ONLY'),
  ('GET_VERIFY_MEMBER_ELIGIBILITY', 'Verify member eligibility', 'v1', true, true, 'TWO_WAY', 'RAW_ONLY'),
  ('GET_PROVIDER_CONTRACT_STATUS', 'Check provider contract status', 'v1', true, true, 'TWO_WAY', 'RAW_ONLY'),
  ('GET_JOKE_DEMO', 'Demo: get a joke', 'v1', true, true, 'TWO_WAY', 'RAW_ONLY'),
  ('GET_EXCHANGE_RATE_DEMO', 'Demo: get FX rate', 'v1', true, true, 'TWO_WAY', 'RAW_ONLY')
ON CONFLICT (operation_code) DO UPDATE
SET description = EXCLUDED.description,
    canonical_version = EXCLUDED.canonical_version,
    is_async_capable = EXCLUDED.is_async_capable,
    is_active = EXCLUDED.is_active,
    direction_policy = EXCLUDED.direction_policy,
    ai_presentation_mode = EXCLUDED.ai_presentation_mode;

-- 3) Contracts (refresh only these ops)
DELETE FROM control_plane.operation_contracts
WHERE operation_code IN (
  'GET_COB_INQUIRY',
  'GET_VERIFY_MEMBER_ELIGIBILITY',
  'GET_PROVIDER_CONTRACT_STATUS',
  'GET_JOKE_DEMO',
  'GET_EXCHANGE_RATE_DEMO'
);

INSERT INTO control_plane.operation_contracts
  (operation_code, canonical_version, request_schema, response_schema, is_active)
VALUES
  (
    'GET_COB_INQUIRY','v1',
    '{"type":"object","additionalProperties":false,"properties":{"memberIdWithPrefix":{"type":"string","minLength":20,"maxLength":20}},"required":["memberIdWithPrefix"]}'::jsonb,
    '{"type":"object","additionalProperties":false,"properties":{"memberIdWithPrefix":{"type":"string"},"name":{"type":"string"},"dob":{"type":"string","format":"date"},"claimNumber":{"type":"string"},"dateOfService":{"type":"string","format":"date"},"status":{"type":"string"}},"required":["memberIdWithPrefix","name","dob","status"],"oneOf":[{"required":["claimNumber"]},{"required":["dateOfService"]}]}'::jsonb,
    true
  ),
  (
    'GET_VERIFY_MEMBER_ELIGIBILITY','v1',
    '{"type":"object","additionalProperties":false,"properties":{"memberIdWithPrefix":{"type":"string"},"date":{"type":"string","format":"date"}},"required":["memberIdWithPrefix","date"]}'::jsonb,
    '{"type":"object","additionalProperties":false,"properties":{"memberIdWithPrefix":{"type":"string"},"name":{"type":"string"},"dob":{"type":"string","format":"date"},"claimNumber":{"type":"string"},"dateOfService":{"type":"string","format":"date"},"status":{"type":"string"}},"required":["memberIdWithPrefix","name","dob","status"],"oneOf":[{"required":["claimNumber"]},{"required":["dateOfService"]}]}'::jsonb,
    true
  ),
  (
    'GET_PROVIDER_CONTRACT_STATUS','v1',
    '{"type":"object","additionalProperties":false,"properties":{"memberIdWithPrefix":{"type":"string"}},"required":["memberIdWithPrefix"]}'::jsonb,
    '{"type":"object","additionalProperties":false,"properties":{"memberIdWithPrefix":{"type":"string"},"name":{"type":"string"},"dob":{"type":"string","format":"date"},"kpi":{"type":"string"},"taxId":{"type":"string"},"deliveryMethod":{"type":"string"},"claimNumber":{"type":"string"},"dateOfService":{"type":"string","format":"date"},"status":{"type":"string"}},"required":["memberIdWithPrefix","name","dob","kpi","taxId","deliveryMethod","status"],"oneOf":[{"required":["claimNumber"]},{"required":["dateOfService"]}]}'::jsonb,
    true
  ),
  (
    'GET_JOKE_DEMO','v1',
    '{"type":"object","additionalProperties":false,"properties":{"category":{"type":"string"}}}'::jsonb,
    '{"type":"object","additionalProperties":false,"properties":{"id":{"type":"string"},"joke":{"type":"string"},"source":{"type":"string"}},"required":["id","joke"]}'::jsonb,
    true
  ),
  (
    'GET_EXCHANGE_RATE_DEMO','v1',
    '{"type":"object","additionalProperties":false,"properties":{"baseCurrency":{"type":"string","minLength":3,"maxLength":3},"targetCurrency":{"type":"string","minLength":3,"maxLength":3},"date":{"type":"string","format":"date"}},"required":["baseCurrency","targetCurrency"]}'::jsonb,
    '{"type":"object","additionalProperties":false,"properties":{"baseCurrency":{"type":"string"},"targetCurrency":{"type":"string"},"date":{"type":"string","format":"date"},"rate":{"type":"number"}},"required":["baseCurrency","targetCurrency","rate"]}'::jsonb,
    true
  );

-- 4) Vendor supported operations (all 5 vendors OUTBOUND for all 5 ops)
DELETE FROM control_plane.vendor_supported_operations
WHERE vendor_code IN ('LH001','LH002','LH023','LH030','LH046')
  AND operation_code IN (
    'GET_COB_INQUIRY',
    'GET_VERIFY_MEMBER_ELIGIBILITY',
    'GET_PROVIDER_CONTRACT_STATUS',
    'GET_JOKE_DEMO',
    'GET_EXCHANGE_RATE_DEMO'
  );

WITH vendors(vendor_code) AS (
  VALUES ('LH001'), ('LH002'), ('LH023'), ('LH030'), ('LH046')
),
ops(operation_code) AS (
  VALUES ('GET_COB_INQUIRY'),
         ('GET_VERIFY_MEMBER_ELIGIBILITY'),
         ('GET_PROVIDER_CONTRACT_STATUS'),
         ('GET_JOKE_DEMO'),
         ('GET_EXCHANGE_RATE_DEMO')
)
INSERT INTO control_plane.vendor_supported_operations
  (vendor_code, operation_code, canonical_version, flow_direction, supports_outbound, supports_inbound)
SELECT v.vendor_code, o.operation_code, 'v1', 'OUTBOUND', true, false
FROM vendors v
CROSS JOIN ops o;

-- 5) Allowlist explicit matrix (source != target) for all 5 ops, OUTBOUND
DELETE FROM control_plane.vendor_operation_allowlist
WHERE operation_code IN (
  'GET_COB_INQUIRY',
  'GET_VERIFY_MEMBER_ELIGIBILITY',
  'GET_PROVIDER_CONTRACT_STATUS',
  'GET_JOKE_DEMO',
  'GET_EXCHANGE_RATE_DEMO'
)
AND (
  source_vendor_code IN ('LH001','LH002','LH023','LH030','LH046')
  OR target_vendor_code IN ('LH001','LH002','LH023','LH030','LH046')
);

WITH vendors(vendor_code) AS (
  VALUES ('LH001'), ('LH002'), ('LH023'), ('LH030'), ('LH046')
),
ops(operation_code) AS (
  VALUES ('GET_COB_INQUIRY'),
         ('GET_VERIFY_MEMBER_ELIGIBILITY'),
         ('GET_PROVIDER_CONTRACT_STATUS'),
         ('GET_JOKE_DEMO'),
         ('GET_EXCHANGE_RATE_DEMO')
)
INSERT INTO control_plane.vendor_operation_allowlist
  (source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, rule_scope, flow_direction)
SELECT s.vendor_code, t.vendor_code, false, false, o.operation_code, 'admin', 'OUTBOUND'
FROM vendors s
CROSS JOIN vendors t
CROSS JOIN ops o
WHERE s.vendor_code <> t.vendor_code;

-- 6) Auth profiles for demo outbound auth (LH001)
DELETE FROM control_plane.vendor_auth_profiles
WHERE vendor_code = 'LH001'
  AND profile_name IN ('DemoApiKeyHeader', 'DemoBearerToken');

INSERT INTO control_plane.vendor_auth_profiles
  (vendor_code, profile_name, auth_type, config, is_default, is_active)
VALUES
  (
    'LH001',
    'DemoApiKeyHeader',
    'API_KEY_HEADER',
    '{"headerName":"Api-Key","apiKey":"demo-exchange-key"}'::jsonb,
    false,
    true
  ),
  (
    'LH001',
    'DemoBearerToken',
    'STATIC_BEARER',
    '{"headerName":"Authorization","prefix":"Bearer ","token":"demo-joke-token"}'::jsonb,
    false,
    true
  )
ON CONFLICT (vendor_code, profile_name) DO UPDATE
SET auth_type = EXCLUDED.auth_type,
    config = EXCLUDED.config,
    is_default = EXCLUDED.is_default,
    is_active = EXCLUDED.is_active,
    updated_at = now();

-- 7) Endpoints for health + demo ops (all 5 vendors, OUTBOUND)
DELETE FROM control_plane.vendor_endpoints
WHERE vendor_code IN ('LH001','LH002','LH023','LH030','LH046')
  AND operation_code IN (
    'GET_COB_INQUIRY',
    'GET_VERIFY_MEMBER_ELIGIBILITY',
    'GET_PROVIDER_CONTRACT_STATUS',
    'GET_JOKE_DEMO',
    'GET_EXCHANGE_RATE_DEMO'
  );

WITH vendors(vendor_code) AS (
  VALUES ('LH001'), ('LH002'), ('LH023'), ('LH030'), ('LH046')
),
endpoint_map(operation_code, endpoint_url, http_method) AS (
  VALUES
    ('GET_COB_INQUIRY', 'https://partners-mock-payers.onrender.com/api/get-cob-inquiry', 'POST'),
    ('GET_VERIFY_MEMBER_ELIGIBILITY', 'https://partners-mock-payers.onrender.com/api/get-verify-member-eligibility', 'POST'),
    ('GET_PROVIDER_CONTRACT_STATUS', 'https://partners-mock-payers.onrender.com/api/get-provider-contract-status', 'POST'),
    ('GET_JOKE_DEMO', 'https://official-joke-api.appspot.com/jokes/random', 'GET'),
    ('GET_EXCHANGE_RATE_DEMO', 'https://api.exchangerate.host/latest', 'GET')
)
INSERT INTO control_plane.vendor_endpoints
  (vendor_code, operation_code, url, http_method, payload_format, timeout_ms, flow_direction, vendor_auth_profile_id, verification_status, is_active)
SELECT
  v.vendor_code,
  e.operation_code,
  e.endpoint_url,
  e.http_method,
  'JSON',
  5000,
  'OUTBOUND',
  CASE
    WHEN v.vendor_code = 'LH001' AND e.operation_code = 'GET_EXCHANGE_RATE_DEMO' THEN (
      SELECT id FROM control_plane.vendor_auth_profiles
      WHERE vendor_code = 'LH001' AND profile_name = 'DemoApiKeyHeader' AND is_active = true
      LIMIT 1
    )
    WHEN v.vendor_code = 'LH001' AND e.operation_code = 'GET_JOKE_DEMO' THEN (
      SELECT id FROM control_plane.vendor_auth_profiles
      WHERE vendor_code = 'LH001' AND profile_name = 'DemoBearerToken' AND is_active = true
      LIMIT 1
    )
    ELSE NULL
  END,
  'PENDING',
  true
FROM vendors v
CROSS JOIN endpoint_map e;
