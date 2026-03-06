#!/usr/bin/env python3
"""Generate Postman collection and environment with all Integration Hub endpoints."""

from __future__ import annotations

import json
from pathlib import Path

# Script lives in tooling/scripts/; repo root is parent.parent.parent
_SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = _SCRIPT_DIR.parent.parent
POSTMAN_DIR = ROOT / "postman"
IDEM_SCRIPT = (
    "if (!pm.variables.get('idempotencyKey') || pm.variables.get('idempotencyKey') === '') { "
    "pm.variables.set('idempotencyKey', 'pm-' + Date.now() + '-' + Math.random().toString(36).slice(2, 11)); }"
)


def req(
    name: str,
    method: str,
    url: str,
    headers: list[dict],
    body: str | None = None,
    event: dict | None = None,
) -> dict:
    r: dict = {"name": name, "request": {"method": method, "header": headers, "url": url}}
    if body:
        r["request"]["body"] = {"mode": "raw", "raw": body}
    if event:
        r["event"] = [event]
    return r


def main() -> None:
    POSTMAN_DIR.mkdir(exist_ok=True)

    admin_hdr = [{"key": "Authorization", "value": "Bearer {{adminJwt}}"}]
    json_hdr = [{"key": "Content-Type", "value": "application/json"}]
    vendor_key_hdr = [{"key": "Authorization", "value": "Bearer {{vendorJwt}}"}]
    runtime_hdr = [
        {"key": "Content-Type", "value": "application/json"},
        {"key": "Authorization", "value": "Bearer {{runtimeJwt}}"},
    ]
    prerequest = {"listen": "prerequest", "script": {"exec": [IDEM_SCRIPT], "type": "text/javascript"}}

    collection = {
        "info": {
            "name": "Integration Hub - POC",
            "description": "Three APIs: Vendor (vendorJwt), Admin (adminJwt), Runtime (runtimeJwt). Run .\\tooling\\scripts\\get-postman-urls.ps1 -Update to fetch base URLs.",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [
            {"key": "baseUrlVendorApi", "value": "https://YOUR_REST_API_ID.execute-api.us-east-1.amazonaws.com/prod", "description": "Vendor API base URL (REST): execute, onboarding, vendor registry"},
            {"key": "baseUrlAdminApi", "value": "https://YOUR_HTTP_API_ID.execute-api.us-east-1.amazonaws.com", "description": "Admin API base URL (HTTP): registry, audit, redrive, AI execute"},
            {"key": "baseUrlRuntimeApi", "value": "https://YOUR_RUNTIME_API_ID.execute-api.us-east-1.amazonaws.com", "description": "Runtime API base URL (HTTP): /v1/execute, /v1/ai/execute"},
            {"key": "vendorJwt", "value": "", "description": "Vendor JWT for /v1/integrations/execute (Authorization: Bearer)."},
            {"key": "adminJwt", "value": "", "description": "Admin JWT for registry, audit, redrive (Authorization: Bearer)."},
            {"key": "runtimeJwt", "value": "", "description": "Runtime JWT for /v1/execute, /v1/ai/execute (Authorization: Bearer)."},
            {"key": "vendorMockUrl", "value": "http://localhost:8000", "description": "Vendor mock server URL for integration tests"},
            {"key": "xVendorCode", "value": "", "description": "Vendor code when calling api-keys self without a key yet"},
            {"key": "sourceVendor", "value": "LH001", "description": "Source vendor code (caller) for execute and allowlist"},
            {"key": "targetVendor", "value": "LH002", "description": "Target vendor code for execute"},
            {"key": "vendorName", "value": "Vendor A"},
            {"key": "operation", "value": "GET_RECEIPT"},
            {"key": "operationCode", "value": "GET_RECEIPT"},
            {"key": "canonicalVersion", "value": "v1"},
            {"key": "idempotencyKey", "value": "poc-test-001"},
            {"key": "vendorCode", "value": "LH001"},
            {"key": "transactionId", "value": ""},
            {"key": "transactionIdForRedrive", "value": ""},
            {"key": "authProfileId", "value": ""},
            {"key": "allowlistId", "value": ""},
            {"key": "exportJobId", "value": ""},
            {"key": "dateFrom", "value": ""},
            {"key": "dateTo", "value": ""},
            {"key": "direction", "value": "all"},
            {"key": "getWeatherLatitude", "value": "39.7392"},
            {"key": "getWeatherLongitude", "value": "-104.9903"},
            {"key": "changeRequestId", "value": ""},
        ],
        "item": [
            {
                "name": "Runtime API",
                "item": [
                    req(
                        "Runtime Execute",
                        "POST",
                        "{{baseUrlRuntimeApi}}/v1/execute",
                        json_hdr + runtime_hdr,
                        '{"sourceVendor":"{{sourceVendor}}","targetVendor":"{{targetVendor}}","operation":"{{operation}}","idempotencyKey":"{{idempotencyKey}}","parameters":{"transactionId":"tx-123"},"includeActuals":true}',
                        prerequest,
                    ),
                    req(
                        "Runtime AI Execute DATA",
                        "POST",
                        "{{baseUrlRuntimeApi}}/v1/ai/execute",
                        json_hdr + runtime_hdr,
                        '{"requestType":"DATA","operationCode":"GET_WEATHER","targetVendorCode":"{{targetVendor}}","sourceVendorCode":"{{sourceVendor}}","payload":{"latitude":{{getWeatherLatitude}},"longitude":{{getWeatherLongitude}},"timezone":"America/Chicago","hoursAhead":0},"aiFormatter":false}',
                    ),
                ],
            },
            {
                "name": "Integrations",
                "item": [
                    req(
                        "Execute Integration",
                        "POST",
                        "{{baseUrlVendorApi}}/v1/integrations/execute",
                        json_hdr + vendor_key_hdr,
                        '{"targetVendor":"{{targetVendor}}","operation":"{{operation}}","idempotencyKey":"{{idempotencyKey}}","parameters":{"transactionId":"tx-123"}}',
                        prerequest,
                    ),
                    req(
                        "Execute GET_WEATHER",
                        "POST",
                        "{{baseUrlVendorApi}}/v1/integrations/execute",
                        json_hdr + vendor_key_hdr,
                        '{"targetVendor":"{{targetVendor}}","operation":"GET_WEATHER","idempotencyKey":"{{idempotencyKey}}","parameters":{"latitude":39.7392,"longitude":-104.9903,"timezone":"America/Chicago","hoursAhead":0}}',
                        prerequest,
                    ),
                ],
            },
            {
                "name": "AI Endpoint",
                "item": [
                    req(
                        "AI Execute DATA (GET_WEATHER)",
                        "POST",
                        "{{baseUrlAdminApi}}/v1/ai/execute",
                        json_hdr + admin_hdr,
                        '{"requestType":"DATA","operationCode":"GET_WEATHER","targetVendorCode":"{{targetVendor}}","payload":{"latitude":{{getWeatherLatitude}},"longitude":{{getWeatherLongitude}},"timezone":"America/Chicago","hoursAhead":0},"aiFormatter":false}',
                    ),
                    req(
                        "AI Execute DATA (GET_WEATHER) with Formatter",
                        "POST",
                        "{{baseUrlAdminApi}}/v1/ai/execute",
                        json_hdr + admin_hdr,
                        '{"requestType":"DATA","operationCode":"GET_WEATHER","targetVendorCode":"{{targetVendor}}","payload":{"latitude":{{getWeatherLatitude}},"longitude":{{getWeatherLongitude}}},"aiFormatter":true}',
                    ),
                    req(
                        "AI Execute DATA (GET_RECEIPT)",
                        "POST",
                        "{{baseUrlAdminApi}}/v1/ai/execute",
                        json_hdr + admin_hdr,
                        '{"requestType":"DATA","operationCode":"GET_RECEIPT","targetVendorCode":"{{targetVendor}}","payload":{"txnId":"123"},"aiFormatter":true}',
                    ),
                    req(
                        "AI Execute PROMPT",
                        "POST",
                        "{{baseUrlAdminApi}}/v1/ai/execute",
                        json_hdr + admin_hdr,
                        '{"requestType":"PROMPT","prompt":"What is the weather in Denver?"}',
                    ),
                ],
            },
            {
                "name": "Onboarding",
                "item": [
                    req(
                        "Register Vendor",
                        "POST",
                        "{{baseUrlVendorApi}}/v1/onboarding/register",
                        json_hdr,
                        '{"vendorCode":"{{vendorCode}}","vendorName":"{{vendorName}}","forceRotate":false}',
                    ),
                ],
            },
            {
                "name": "Admin",
                "item": [
                    req(
                        "Redrive Failed Transaction",
                        "POST",
                        "{{baseUrlAdminApi}}/v1/admin/redrive/{{transactionIdForRedrive}}",
                        json_hdr + admin_hdr,
                        "{}",
                    ),
                ],
            },
            {
                "name": "Audit",
                "item": [
                    req(
                        "List Transactions",
                        "GET",
                        "{{baseUrlAdminApi}}/v1/audit/transactions?vendorCode={{vendorCode}}&from={{dateFrom}}&to={{dateTo}}&limit=20&includeDebugPayload=false",
                        admin_hdr,
                    ),
                    req(
                        "Get Transaction by ID",
                        "GET",
                        "{{baseUrlAdminApi}}/v1/audit/transactions/{{transactionId}}?vendorCode={{vendorCode}}",
                        admin_hdr,
                    ),
                    req(
                        "Get Audit Events",
                        "GET",
                        "{{baseUrlAdminApi}}/v1/audit/events?transactionId={{transactionId}}&limit=200",
                        admin_hdr,
                    ),
                ],
            },
            {
                "name": "Registry (Admin)",
                "item": [
                    req("Get Contract", "GET", "{{baseUrlAdminApi}}/v1/registry/contracts?operationCode={{operationCode}}&canonicalVersion={{canonicalVersion}}", admin_hdr),
                    req(
                        "Upsert Contract",
                        "POST",
                        "{{baseUrlAdminApi}}/v1/registry/contracts",
                        json_hdr + admin_hdr,
                        '{"operationCode":"{{operationCode}}","canonicalVersion":"{{canonicalVersion}}","requestSchema":{"type":"object","required":["transactionId"],"properties":{"transactionId":{"type":"string","minLength":1}}},"responseSchema":null}',
                    ),
                    req("List Vendors", "GET", "{{baseUrlAdminApi}}/v1/registry/vendors?limit=50", admin_hdr),
                    req("Upsert Vendor", "POST", "{{baseUrlAdminApi}}/v1/registry/vendors", json_hdr + admin_hdr, '{"vendor_code":"LH003","vendor_name":"Vendor C","is_active":true}'),
                    req("List Operations", "GET", "{{baseUrlAdminApi}}/v1/registry/operations?isActive=true", admin_hdr),
                    req("Upsert Operation", "POST", "{{baseUrlAdminApi}}/v1/registry/operations", json_hdr + admin_hdr, '{"operation_code":"SEND_RECEIPT","description":"Send receipt","canonical_version":"v1","is_async_capable":true,"is_active":true}'),
                    req("Set Operation Canonical Version", "POST", "{{baseUrlAdminApi}}/v1/registry/operations/{{operationCode}}/canonical-version", json_hdr + admin_hdr, '{"canonical_version":"{{canonicalVersion}}"}'),
                    req("List Allowlist", "GET", "{{baseUrlAdminApi}}/v1/registry/allowlist?limit=50", admin_hdr),
                    req("Upsert Allowlist", "POST", "{{baseUrlAdminApi}}/v1/registry/allowlist", json_hdr + admin_hdr, '{"source_vendor_code":"LH001","target_vendor_code":"LH002","operation_code":"GET_RECEIPT"}'),
                    req("Delete Allowlist", "DELETE", "{{baseUrlAdminApi}}/v1/registry/allowlist/{{allowlistId}}", admin_hdr),
                    req("List Change Requests", "GET", "{{baseUrlAdminApi}}/v1/registry/change-requests?status=PENDING&source=allowlist&limit=50", admin_hdr),
                    req("Approve Change Request", "POST", "{{baseUrlAdminApi}}/v1/registry/change-requests/{{changeRequestId}}/decision", json_hdr + admin_hdr, '{"action":"APPROVE"}'),
                    req("Reject Change Request", "POST", "{{baseUrlAdminApi}}/v1/registry/change-requests/{{changeRequestId}}/decision", json_hdr + admin_hdr, '{"action":"REJECT","reason":"Optional reason"}'),
                    req("List Endpoints", "GET", "{{baseUrlAdminApi}}/v1/registry/endpoints?limit=50", admin_hdr),
                    req("Upsert Endpoint", "POST", "{{baseUrlAdminApi}}/v1/registry/endpoints", json_hdr + admin_hdr, '{"vendor_code":"LH002","operation_code":"GET_RECEIPT","url":"{{vendorMockUrl}}/receipt","http_method":"POST","payload_format":"JSON","timeout_ms":8000,"is_active":true}'),
                    req("Get Readiness", "GET", "{{baseUrlAdminApi}}/v1/registry/readiness?vendorCode={{targetVendor}}&operationCode={{operation}}", admin_hdr),
                    req("Readiness Batch", "POST", "{{baseUrlAdminApi}}/v1/registry/readiness/batch", json_hdr + admin_hdr, '{"vendorCodes":["LH001","LH002"],"operationCode":"{{operation}}"}'),
                    req("Get Usage", "GET", "{{baseUrlAdminApi}}/v1/registry/usage?from={{dateFrom}}&to={{dateTo}}&limit=50", admin_hdr),
                    req("List Auth Profiles", "GET", "{{baseUrlAdminApi}}/v1/registry/auth-profiles?vendorCode={{vendorCode}}&limit=50", admin_hdr),
                    req("Upsert Auth Profile", "POST", "{{baseUrlAdminApi}}/v1/registry/auth-profiles", json_hdr + admin_hdr, '{"vendor_code":"{{vendorCode}}","name":"Outbound API Key","auth_type":"API_KEY_HEADER","config":{"header_name":"Api-Key","value":"secret"},"is_active":true}'),
                    req("Patch Auth Profile", "PATCH", "{{baseUrlAdminApi}}/v1/registry/auth-profiles/{{authProfileId}}", json_hdr + admin_hdr, '{"isActive":true}'),
                    req("Delete Auth Profile", "DELETE", "{{baseUrlAdminApi}}/v1/registry/auth-profiles/{{authProfileId}}", admin_hdr),
                ],
            },
            {
                "name": "Vendor Registry",
                "item": [
                    req("Get Config Bundle", "GET", "{{baseUrlVendorApi}}/v1/vendor/config-bundle", vendor_key_hdr),
                    req("Get API Keys Self-Summary", "GET", "{{baseUrlVendorApi}}/v1/vendor/api-keys/self-summary", vendor_key_hdr + [{"key": "x-vendor-code", "value": "{{xVendorCode}}", "description": "When no key"}]),
                    req("Post API Key Self", "POST", "{{baseUrlVendorApi}}/v1/vendor/api-keys/self", json_hdr + [{"key": "x-vendor-code", "value": "{{xVendorCode}}"}], "{}"),
                    req("Get Supported Operations", "GET", "{{baseUrlVendorApi}}/v1/vendor/supported-operations", vendor_key_hdr),
                    req("Post Supported Operation", "POST", "{{baseUrlVendorApi}}/v1/vendor/supported-operations", json_hdr + vendor_key_hdr, '{"operationCode":"{{operation}}"}'),
                    req("Delete Supported Operation", "DELETE", "{{baseUrlVendorApi}}/v1/vendor/supported-operations/{{operationCode}}", vendor_key_hdr),
                    req("Get Endpoints", "GET", "{{baseUrlVendorApi}}/v1/vendor/endpoints", vendor_key_hdr),
                    req("Post Endpoint", "POST", "{{baseUrlVendorApi}}/v1/vendor/endpoints", json_hdr + vendor_key_hdr, '{"operationCode":"{{operation}}","url":"{{vendorMockUrl}}/receipt","httpMethod":"POST","payloadFormat":"JSON","timeoutMs":8000,"isActive":true}'),
                    req("Verify Endpoint", "POST", "{{baseUrlVendorApi}}/v1/vendor/endpoints/verify", json_hdr + vendor_key_hdr, '{"operationCode":"{{operation}}"}'),
                    req("Get Contracts", "GET", "{{baseUrlVendorApi}}/v1/vendor/contracts?operationCode={{operation}}&canonicalVersion={{canonicalVersion}}", vendor_key_hdr),
                    req("Post Contract", "POST", "{{baseUrlVendorApi}}/v1/vendor/contracts", json_hdr + vendor_key_hdr, '{"operationCode":"{{operation}}","canonicalVersion":"{{canonicalVersion}}","requestSchema":{"type":"object"},"responseSchema":null}'),
                    req("Get Operations Catalog", "GET", "{{baseUrlVendorApi}}/v1/vendor/operations-catalog", vendor_key_hdr),
                    req("Get Operations Mapping Status", "GET", "{{baseUrlVendorApi}}/v1/vendor/operations-mapping-status", vendor_key_hdr),
                    req("Get Canonical Operations", "GET", "{{baseUrlVendorApi}}/v1/vendor/canonical/operations", vendor_key_hdr),
                    req("Get Canonical Contracts", "GET", "{{baseUrlVendorApi}}/v1/vendor/canonical/contracts?operationCode={{operation}}", vendor_key_hdr),
                    req("Get Canonical Vendors", "GET", "{{baseUrlVendorApi}}/v1/vendor/canonical/vendors", vendor_key_hdr),
                    req("Get Auth Profiles", "GET", "{{baseUrlVendorApi}}/v1/vendor/auth-profiles", vendor_key_hdr),
                    req("Post Auth Profile", "POST", "{{baseUrlVendorApi}}/v1/vendor/auth-profiles", json_hdr + vendor_key_hdr, '{"name":"Outbound API Key","authType":"API_KEY_HEADER","config":{"header_name":"Api-Key","value":"secret"},"isActive":true}'),
                    req("Patch Auth Profile", "PATCH", "{{baseUrlVendorApi}}/v1/vendor/auth-profiles/{{authProfileId}}", json_hdr + vendor_key_hdr, '{"isActive":true}'),
                    req("Delete Auth Profile", "DELETE", "{{baseUrlVendorApi}}/v1/vendor/auth-profiles/{{authProfileId}}", vendor_key_hdr),
                    req("Get My Allowlist", "GET", "{{baseUrlVendorApi}}/v1/vendor/my-allowlist", vendor_key_hdr),
                    req("Post Allowlist", "POST", "{{baseUrlVendorApi}}/v1/vendor/allowlist", json_hdr + vendor_key_hdr, '{"sourceVendorCode":"LH001","targetVendorCode":"LH002","operationCode":"{{operation}}"}'),
                    req("Delete Allowlist", "DELETE", "{{baseUrlVendorApi}}/v1/vendor/allowlist/{{allowlistId}}", vendor_key_hdr),
                    req("Post Allowlist Change Request", "POST", "{{baseUrlVendorApi}}/v1/vendor/allowlist-change-requests", json_hdr + vendor_key_hdr, '{"rules":[{"sourceVendorCode":"LH001","targetVendorCode":"LH002","operationCode":"{{operation}}"}]}'),
                    req("Get My Change Requests", "GET", "{{baseUrlVendorApi}}/v1/vendor/my-change-requests?status=PENDING&limit=50", vendor_key_hdr),
                    req("Get Eligible Access", "GET", "{{baseUrlVendorApi}}/v1/vendor/eligible-access?operationCode={{operation}}&direction=outbound", vendor_key_hdr),
                    req("Get My Operations", "GET", "{{baseUrlVendorApi}}/v1/vendor/my-operations", vendor_key_hdr),
                    req("Get Metrics Overview", "GET", "{{baseUrlVendorApi}}/v1/vendor/metrics/overview?from={{dateFrom}}&to={{dateTo}}", vendor_key_hdr),
                    req("Post Export Job", "POST", "{{baseUrlVendorApi}}/v1/vendor/export-jobs", json_hdr + vendor_key_hdr, '{"exportType":"TXN_7D","from":"{{dateFrom}}","to":"{{dateTo}}"}'),
                    req("Get Export Job", "GET", "{{baseUrlVendorApi}}/v1/vendor/export-jobs/{{exportJobId}}", vendor_key_hdr),
                    req("List Transactions", "GET", "{{baseUrlVendorApi}}/v1/vendor/transactions?from={{dateFrom}}&to={{dateTo}}&direction={{direction}}&limit=50", vendor_key_hdr),
                    req("Get Transaction by ID", "GET", "{{baseUrlVendorApi}}/v1/vendor/transactions/{{transactionId}}", vendor_key_hdr),
                    req("Redrive Transaction", "POST", "{{baseUrlVendorApi}}/v1/vendor/transactions/{{transactionIdForRedrive}}/redrive", json_hdr + vendor_key_hdr, "{}"),
                    req("Patch Operation", "PATCH", "{{baseUrlVendorApi}}/v1/vendor/operations/{{operationCode}}", json_hdr + vendor_key_hdr, '{"isActive":true}'),
                    req("Delete Operation", "DELETE", "{{baseUrlVendorApi}}/v1/vendor/operations/{{operationCode}}", vendor_key_hdr),
                    req("Get Operation Mappings", "GET", "{{baseUrlVendorApi}}/v1/vendor/operations/{{operationCode}}/{{canonicalVersion}}/mappings", vendor_key_hdr),
                    req("Put Operation Mappings", "PUT", "{{baseUrlVendorApi}}/v1/vendor/operations/{{operationCode}}/{{canonicalVersion}}/mappings", json_hdr + vendor_key_hdr, '{"requestMapping":{"transactionId":"$.transactionId"},"responseMapping":{"receiptId":"$.receiptId"}}'),
                    req("Get Mappings", "GET", "{{baseUrlVendorApi}}/v1/vendor/mappings?operationCode={{operation}}&canonicalVersion={{canonicalVersion}}", vendor_key_hdr),
                    req("Post Mapping", "POST", "{{baseUrlVendorApi}}/v1/vendor/mappings", json_hdr + vendor_key_hdr, '{"operationCode":"{{operation}}","canonicalVersion":"{{canonicalVersion}}","direction":"TO_CANONICAL","mapping":{"transactionId":"$.transactionId"}}'),
                    req("Get Flow", "GET", "{{baseUrlVendorApi}}/v1/vendor/flows/{{operationCode}}/{{canonicalVersion}}", vendor_key_hdr),
                    req("Put Flow", "PUT", "{{baseUrlVendorApi}}/v1/vendor/flows/{{operationCode}}/{{canonicalVersion}}", json_hdr + vendor_key_hdr, '{"visualModel":{},"requestMapping":{"transactionId":"$.transactionId"},"responseMapping":{"receiptId":"$.receiptId"}}'),
                    req("Test Flow", "POST", "{{baseUrlVendorApi}}/v1/vendor/flows/{{operationCode}}/{{canonicalVersion}}/test", json_hdr + vendor_key_hdr, '{"parameters":{"transactionId":"tx-test-123"}}'),
                ],
            },
        ],
    }

    env_values = [
        {"key": "baseUrlVendorApi", "value": "https://YOUR_REST_API_ID.execute-api.us-east-1.amazonaws.com/prod", "type": "default", "enabled": True},
        {"key": "baseUrlAdminApi", "value": "https://YOUR_HTTP_API_ID.execute-api.us-east-1.amazonaws.com", "type": "default", "enabled": True},
        {"key": "baseUrlRuntimeApi", "value": "https://YOUR_RUNTIME_API_ID.execute-api.us-east-1.amazonaws.com", "type": "default", "enabled": True},
        {"key": "vendorJwt", "value": "", "type": "secret", "enabled": True},
        {"key": "adminJwt", "value": "", "type": "secret", "enabled": True},
        {"key": "runtimeJwt", "value": "", "type": "secret", "enabled": True},
        {"key": "xVendorCode", "value": "", "type": "default", "enabled": True},
        {"key": "vendorMockUrl", "value": "http://localhost:8000", "type": "default", "enabled": True},
        {"key": "sourceVendor", "value": "LH001", "type": "default", "enabled": True},
        {"key": "targetVendor", "value": "LH002", "type": "default", "enabled": True},
        {"key": "vendorName", "value": "Vendor A", "type": "default", "enabled": True},
        {"key": "operation", "value": "GET_RECEIPT", "type": "default", "enabled": True},
        {"key": "operationCode", "value": "GET_RECEIPT", "type": "default", "enabled": True},
        {"key": "canonicalVersion", "value": "v1", "type": "default", "enabled": True},
        {"key": "idempotencyKey", "value": "poc-test-001", "type": "default", "enabled": True},
        {"key": "vendorCode", "value": "LH001", "type": "default", "enabled": True},
        {"key": "transactionId", "value": "", "type": "default", "enabled": True},
        {"key": "transactionIdForRedrive", "value": "", "type": "default", "enabled": True},
        {"key": "authProfileId", "value": "", "type": "default", "enabled": True},
        {"key": "allowlistId", "value": "", "type": "default", "enabled": True},
        {"key": "exportJobId", "value": "", "type": "default", "enabled": True},
        {"key": "dateFrom", "value": "", "type": "default", "enabled": True},
        {"key": "dateTo", "value": "", "type": "default", "enabled": True},
        {"key": "direction", "value": "all", "type": "default", "enabled": True},
        {"key": "getWeatherLatitude", "value": "39.7392", "type": "default", "enabled": True},
        {"key": "getWeatherLongitude", "value": "-104.9903", "type": "default", "enabled": True},
        {"key": "changeRequestId", "value": "", "type": "default", "enabled": True},
    ]

    env_obj = {
        "id": "poc-env-001",
        "name": "Integration Hub - POC",
        "_postman_variable_scope": "environment",
        "values": env_values,
    }

    # Local env: localhost:8080, local-dev keys
    local_values = [
        {"key": "baseUrlVendorApi", "value": "http://localhost:8080", "type": "default", "enabled": True},
        {"key": "baseUrlAdminApi", "value": "http://localhost:8080", "type": "default", "enabled": True},
        {"key": "baseUrlRuntimeApi", "value": "http://localhost:8080", "type": "default", "enabled": True},
        {"key": "vendorJwt", "value": "", "type": "secret", "enabled": True},
        {"key": "adminJwt", "value": "", "type": "secret", "enabled": True},
        {"key": "runtimeJwt", "value": "", "type": "secret", "enabled": True},
        {"key": "xVendorCode", "value": "LH001", "type": "default", "enabled": True},
        {"key": "sourceVendor", "value": "LH001", "type": "default", "enabled": True},
        {"key": "targetVendor", "value": "LH002", "type": "default", "enabled": True},
        {"key": "vendorName", "value": "Vendor A", "type": "default", "enabled": True},
        {"key": "operation", "value": "GET_RECEIPT", "type": "default", "enabled": True},
        {"key": "operationCode", "value": "GET_RECEIPT", "type": "default", "enabled": True},
        {"key": "canonicalVersion", "value": "v1", "type": "default", "enabled": True},
        {"key": "idempotencyKey", "value": "poc-local-001", "type": "default", "enabled": True},
        {"key": "vendorCode", "value": "LH001", "type": "default", "enabled": True},
        {"key": "transactionId", "value": "", "type": "default", "enabled": True},
        {"key": "transactionIdForRedrive", "value": "", "type": "default", "enabled": True},
        {"key": "authProfileId", "value": "", "type": "default", "enabled": True},
        {"key": "allowlistId", "value": "", "type": "default", "enabled": True},
        {"key": "exportJobId", "value": "", "type": "default", "enabled": True},
        {"key": "dateFrom", "value": "", "type": "default", "enabled": True},
        {"key": "dateTo", "value": "", "type": "default", "enabled": True},
        {"key": "direction", "value": "all", "type": "default", "enabled": True},
        {"key": "getWeatherLatitude", "value": "39.7392", "type": "default", "enabled": True},
        {"key": "getWeatherLongitude", "value": "-104.9903", "type": "default", "enabled": True},
        {"key": "changeRequestId", "value": "", "type": "default", "enabled": True},
    ]
    local_env_obj = {
        "id": "poc-env-local",
        "name": "Integration Hub - Local",
        "_postman_variable_scope": "environment",
        "values": local_values,
    }

    coll_path = POSTMAN_DIR / "Integration-Hub-POC.postman_collection.json"
    with open(coll_path, "w") as f:
        json.dump(collection, f, indent=2)
    print(f"Created {coll_path}")

    env_path = POSTMAN_DIR / "Integration-Hub-POC.postman_environment.json"
    with open(env_path, "w") as f:
        json.dump(env_obj, f, indent=2)
    print(f"Created {env_path}")

    local_env_path = POSTMAN_DIR / "Integration-Hub-POC-Local.postman_environment.json"
    with open(local_env_path, "w") as f:
        json.dump(local_env_obj, f, indent=2)
    print(f"Created {local_env_path}")

    print("\nRun .\\tooling\\scripts\\get-postman-urls.ps1 -Update to fetch live API URLs.")


if __name__ == "__main__":
    main()
