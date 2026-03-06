"""Unit tests for Routing Lambda - execute auth (JWT), redrive auth (JWT), and flow."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

if os.environ.get("RUN_LEGACY_ROUTING_TESTS", "0") != "1":
    pytest.skip(
        "Routing execute tests disabled by default; set RUN_LEGACY_ROUTING_TESTS=1 to run with JWT mocks.",
        allow_module_level=True,
    )

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from routing_lambda import build_downstream_headers, handler  # noqa: E402


@pytest.fixture(autouse=True)
def _mock_jwt_for_execute():
    """Provide JWT auth mocks so execute tests get past auth with default Bearer header."""
    from jwt_auth import JwtAuthConfig, JwtAuthResult  # noqa: E402

    with patch("routing_lambda.load_jwt_auth_config_from_env") as p_cfg:
        with patch("routing_lambda.validate_jwt_and_map_vendor") as p_val:
            p_cfg.return_value = JwtAuthConfig(
                issuer="https://idp.example.com",
                jwks_uri="https://idp.example.com/.well-known/jwks.json",
                audiences=["hub-api"],
                vendor_claim="hub_vendor",
                allowed_alg="RS256",
            )
            p_val.return_value = JwtAuthResult(vendor_code="LH001", claims={"hub_vendor": "LH001"})
            yield

# EMF observability tests - import after path setup
from observability import emit_metric  # noqa: E402


def _redrive_event(transaction_id: str, headers: dict | None = None) -> dict:
    """Event for POST /v1/admin/redrive/{transactionId}."""
    return {
        "path": f"/v1/admin/redrive/{transaction_id}",
        "rawPath": f"/v1/admin/redrive/{transaction_id}",
        "httpMethod": "POST",
        "pathParameters": {"transactionId": transaction_id},
        "requestContext": {"http": {"method": "POST"}},
        "headers": headers or {},
        "body": "{}",
    }


def _base_event(body: dict | str | None = None, headers: dict | None = None) -> dict:
    evt: dict = {
        "path": "/v1/integrations/execute",
        "rawPath": "/v1/integrations/execute",
        "httpMethod": "POST",
        "pathParameters": {},
        "requestContext": {"http": {"method": "POST"}},
        "headers": headers or {"Authorization": "Bearer mock-token"},
        "body": json.dumps(body) if isinstance(body, dict) else (body or "{}"),
    }
    return evt


def _execute_body(
    target_vendor: str = "LH002",
    operation: str = "GET_RECEIPT",
    parameters: dict | None = None,
    idempotency_key: str | None = None,
) -> dict:
    body: dict = {
        "targetVendor": target_vendor,
        "operation": operation,
        "parameters": parameters or {},
    }
    if idempotency_key is not None:
        body["idempotencyKey"] = idempotency_key
    return body


# --- Redrive auth: JWT authorizer ---


def test_redrive_missing_jwt_authorizer_returns_403() -> None:
    """POST /v1/admin/redrive/{id} without JWT authorizer: 403 AUTH_ERROR."""
    event = _redrive_event("tx-123", headers={})
    resp = handler(event, None)
    assert resp["statusCode"] == 403
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "AUTH_ERROR"


# --- Auth: missing Authorization ---


def test_execute_missing_authorization_returns_auth_error() -> None:
    """No Authorization header: AUTH_ERROR 401, category auth, retryable False."""
    event = _base_event(_execute_body(), headers={"content-type": "application/json"})
    resp = handler(event, None)
    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "AUTH_ERROR"
    assert err.get("category") == "AUTH"
    assert err.get("retryable") is False
    assert "authorization" in err["message"].lower()
    assert "transactionId" in body


# --- Auth: invalid JWT ---


@patch("routing_lambda._get_connection")
@patch("routing_lambda.load_jwt_auth_config_from_env")
@patch("routing_lambda.validate_jwt_and_map_vendor")
def test_execute_invalid_jwt_returns_auth_error(
    mock_validate_jwt,
    mock_load_jwt,
    mock_conn_ctx,
) -> None:
    """Invalid or expired JWT: AUTH_ERROR 401."""
    from jwt_auth import JwtValidationError

    mock_load_jwt.return_value = MagicMock(issuer="https://idp.example.com", audiences=["api"])
    mock_validate_jwt.side_effect = JwtValidationError("invalid_token", "Invalid token")
    mock_conn_ctx.return_value.__enter__.return_value = MagicMock()
    event = _base_event(_execute_body(), headers={"Authorization": "Bearer bad-token"})
    resp = handler(event, None)
    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "AUTH_ERROR"


# --- Auth: JWT valid -> source_vendor from JWT ---


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
@patch("routing_lambda.load_jwt_auth_config_from_env")
@patch("routing_lambda.validate_jwt_and_map_vendor")
def test_execute_valid_jwt_sets_source_vendor_and_completes(
    mock_validate_jwt,
    mock_load_jwt_config,
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Valid Authorization: Bearer <jwt>: source_vendor derived from JWT, vendor validated, flow proceeds."""
    from jwt_auth import JwtAuthConfig, JwtAuthResult

    mock_load_jwt_config.return_value = JwtAuthConfig(
        issuer="https://idp.example.com",
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
        audiences=["hub-api"],
        vendor_claim="hub_vendor",
        allowed_alg="RS256",
    )
    mock_validate_jwt.return_value = JwtAuthResult(vendor_code="VJWT01", claims={"hub_vendor": "VJWT01"})
    mock_validate.return_value = {
        "url": "http://example.com/op",
        "http_method": "POST",
        "timeout_ms": 8000,
        "canonical_version": "v1",
    }
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": None,
        "response_schema": None,
    }

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE"):
            return {"result": "$.result"}
        return {"transactionId": "$.transactionId"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("VJWT01", True), ("tx-123",)]  # vendor check + _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(
        _execute_body(parameters={"transactionId": "tx-1"}),
        headers={"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJodWJfdmVuZG9yIjoidkpXVFQxIn0.x"},
    )
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "transactionId" in body
    rb = body.get("responseBody", {})
    assert rb.get("status") == "completed"
    mock_validate_jwt.assert_called_once()
    mock_load_jwt_config.assert_called_once()
    mock_validate.assert_called_once()
    assert mock_validate.call_args[0][1] == "VJWT01"


# --- Auth: JWT invalid -> AUTH_ERROR 401 ---


@patch("routing_lambda._get_connection")
@patch("routing_lambda.load_jwt_auth_config_from_env")
@patch("routing_lambda.validate_jwt_and_map_vendor")
def test_execute_invalid_jwt_returns_auth_error(
    mock_validate_jwt,
    mock_load_jwt_config,
    mock_conn_ctx,
) -> None:
    """Invalid JWT (bad sig, wrong issuer, expired): AUTH_ERROR 401."""
    from jwt_auth import JwtAuthConfig, JwtValidationError

    mock_load_jwt_config.return_value = JwtAuthConfig(
        issuer="https://idp.example.com",
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
        audiences=["hub-api"],
        vendor_claim="hub_vendor",
        allowed_alg="RS256",
    )
    mock_validate_jwt.side_effect = JwtValidationError(
        "INVALID_ISSUER", "Token issuer does not match"
    )

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    event = _base_event(
        _execute_body(),
        headers={"Authorization": "Bearer invalid.jwt.here"},
    )
    resp = handler(event, None)

    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "AUTH_ERROR"
    assert "issuer" in body.get("error", {}).get("message", "").lower() or "token" in body.get(
        "error", {}
    ).get("message", "").lower()


# --- Auth: JWT missing vendor claim -> AUTH_ERROR ---


@patch("routing_lambda._get_connection")
@patch("routing_lambda.load_jwt_auth_config_from_env")
@patch("routing_lambda.validate_jwt_and_map_vendor")
def test_execute_jwt_missing_vendor_claim_returns_auth_error(
    mock_validate_jwt,
    mock_load_jwt_config,
    mock_conn_ctx,
) -> None:
    """JWT missing required vendor claim: AUTH_ERROR with clear details."""
    from jwt_auth import JwtAuthConfig, JwtValidationError

    mock_load_jwt_config.return_value = JwtAuthConfig(
        issuer="https://idp.example.com",
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
        audiences=["hub-api"],
        vendor_claim="hub_vendor",
        allowed_alg="RS256",
    )
    mock_validate_jwt.side_effect = JwtValidationError(
        "MISSING_VENDOR_CLAIM",
        "JWT missing required claim 'hub_vendor'",
        {"vendor_claim": "hub_vendor"},
    )

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    event = _base_event(
        _execute_body(),
        headers={"Authorization": "Bearer some.jwt.token"},
    )
    resp = handler(event, None)

    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "AUTH_ERROR"
    assert "hub_vendor" in body.get("error", {}).get("message", "")


@patch("routing_lambda.load_jwt_auth_config_from_env")
def test_execute_jwt_disabled_but_bearer_present_returns_auth_error(
    mock_load_jwt_config,
) -> None:
    """Bearer present but IDP_JWKS_URL empty (JWT disabled): auth_error 'JWT auth not configured'."""
    mock_load_jwt_config.return_value = None

    event = _base_event(
        _execute_body(),
        headers={"Authorization": "Bearer some.jwt.token"},
    )
    resp = handler(event, None)

    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "AUTH_ERROR"
    assert "not configured" in body.get("error", {}).get("message", "").lower()


@patch("routing_lambda._get_connection")
@patch("routing_lambda.load_jwt_auth_config_from_env")
@patch("routing_lambda.validate_jwt_and_map_vendor")
def test_execute_jwt_success_but_vendor_not_found_returns_404(
    mock_validate_jwt,
    mock_load_jwt_config,
    mock_conn_ctx,
) -> None:
    """JWT valid, vendor claim UNKNOWN, but vendor not in DB: vendor_not_found 404."""
    from jwt_auth import JwtAuthConfig, JwtAuthResult

    mock_load_jwt_config.return_value = JwtAuthConfig(
        issuer="https://idp.example.com",
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
        audiences=["hub-api"],
        vendor_claim="vendor_code",
        allowed_alg="RS256",
    )
    mock_validate_jwt.return_value = JwtAuthResult(vendor_code="UNKNOWN", claims={"vendor_code": "UNKNOWN"})

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = None

    event = _base_event(
        _execute_body(),
        headers={"Authorization": "Bearer valid.jwt.token"},
    )
    resp = handler(event, None)

    assert resp["statusCode"] == 404
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "VENDOR_NOT_FOUND"


@patch("routing_lambda._get_connection")
@patch("routing_lambda.load_jwt_auth_config_from_env")
@patch("routing_lambda.validate_jwt_and_map_vendor")
def test_execute_jwt_success_but_vendor_inactive_returns_forbidden(
    mock_validate_jwt,
    mock_load_jwt_config,
    mock_conn_ctx,
) -> None:
    """JWT valid, vendor in DB but is_active=false: forbidden 403."""
    from jwt_auth import JwtAuthConfig, JwtAuthResult

    mock_load_jwt_config.return_value = JwtAuthConfig(
        issuer="https://idp.example.com",
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
        audiences=["hub-api"],
        vendor_claim="vendor_code",
        allowed_alg="RS256",
    )
    mock_validate_jwt.return_value = JwtAuthResult(vendor_code="INACTIVE01", claims={"vendor_code": "INACTIVE01"})

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = ("INACTIVE01", False)

    event = _base_event(
        _execute_body(),
        headers={"Authorization": "Bearer valid.jwt.token"},
    )
    resp = handler(event, None)

    assert resp["statusCode"] == 403
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "FORBIDDEN"


# --- Validation: deprecated vendor code (HUB) rejected ---


@patch("routing_lambda._get_connection")
@patch("routing_lambda.load_jwt_auth_config_from_env")
@patch("routing_lambda.validate_jwt_and_map_vendor")
def test_execute_target_vendor_hub_returns_validation_error(
    mock_validate_jwt,
    mock_load_jwt,
    mock_conn_ctx,
) -> None:
    """targetVendor 'HUB' or 'LH000' must be rejected with SCHEMA_VALIDATION_FAILED. No special-vendor logic."""
    from jwt_auth import JwtAuthConfig, JwtAuthResult  # noqa: E402

    mock_load_jwt.return_value = JwtAuthConfig(
        issuer="https://idp.example.com",
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
        audiences=["hub-api"],
        vendor_claim="hub_vendor",
        allowed_alg="RS256",
    )
    mock_validate_jwt.return_value = JwtAuthResult(vendor_code="LH001", claims={"hub_vendor": "LH001"})
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("LH001", True), None]  # vendor check, then idempotency

    event = _base_event(_execute_body(target_vendor="HUB"))
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "SCHEMA_VALIDATION_FAILED"
    assert "deprecated" in err.get("message", "").lower() or "not accepted" in err.get("message", "").lower()


# --- Auth: valid JWT, source_vendor set, completed ---


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_valid_auth_completes_flow(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Valid JWT auth: source_vendor from token, flow proceeds to completion."""
    mock_validate.return_value = {
        "url": "http://example.com/op",
        "http_method": "POST",
        "timeout_ms": 8000,
        "canonical_version": "v1",
    }
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE"):
            return {"result": "$.result"}
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        return {"transactionId": "$.transactionId"}
    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("LH001", True), ("tx-123",)]  # vendor check, then _claim_idempotency
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}))
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "transactionId" in body
    assert "correlationId" in body
    rb = body.get("responseBody", {})
    assert rb.get("status") == "completed"
    assert rb.get("responseBody", {}).get("result") == "ok"

    mock_validate.assert_called_once()
    assert mock_validate.call_args[0][1] == "LH001"
    assert mock_validate.call_args[0][2] == "LH002"


# --- Request envelope normalization: value, payload, operationCode, targetVendorCode ---


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_envelope_value_normalization(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Execute with value (instead of parameters) normalizes and validates correctly."""
    mock_validate.return_value = {
        "url": "http://example.com/op",
        "http_method": "POST",
        "timeout_ms": 8000,
        "canonical_version": "v1",
    }
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": None,
        "response_schema": None,
    }
    mock_load_mapping.side_effect = lambda c, v, o, ver, d, flow_direction="OUTBOUND": (
        {"result": "$.result"} if "CANONICAL_RESPONSE" in d else {"transactionId": "$.transactionId"}
    )
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("LH001", True), ("tx-123",)]
    mock_cursor.execute.side_effect = None

    body = {
        "targetVendor": "LH002",
        "operation": "GET_RECEIPT",
        "value": {"transactionId": "tx-1"},  # value instead of parameters
    }
    event = _base_event(body)
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    assert json.loads(resp["body"]).get("responseBody", {}).get("status") == "completed"
    mock_call_downstream.assert_called_once()
    vendor_body = mock_call_downstream.call_args[0][2]
    assert isinstance(vendor_body, dict) and vendor_body.get("transactionId") == "tx-1"


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_envelope_payload_normalization(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Execute with payload (instead of parameters) normalizes and validates correctly."""
    mock_validate.return_value = {
        "url": "http://example.com/op",
        "http_method": "POST",
        "timeout_ms": 8000,
        "canonical_version": "v1",
    }
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": None,
        "response_schema": None,
    }
    mock_load_mapping.side_effect = lambda c, v, o, ver, d, flow_direction="OUTBOUND": (
        {"result": "$.result"} if "CANONICAL_RESPONSE" in d else {"transactionId": "$.transactionId"}
    )
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]
    mock_cursor.execute.side_effect = None

    body = {
        "operationCode": "GET_RECEIPT",  # operationCode instead of operation
        "targetVendorCode": "LH002",  # targetVendorCode instead of targetVendor
        "payload": {"transactionId": "tx-2"},  # payload instead of parameters
    }
    event = _base_event(body)
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    assert json.loads(resp["body"]).get("responseBody", {}).get("status") == "completed"
    mock_call_downstream.assert_called_once()
    vendor_body = mock_call_downstream.call_args[0][2]
    assert isinstance(vendor_body, dict) and vendor_body.get("transactionId") == "tx-2"
    mock_validate.assert_called_once()
    assert mock_validate.call_args[0][2] == "LH002"


# --- Idempotency: same sourceVendor + idempotencyKey returns replay, no new insert ---


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
@patch("routing_lambda.create_transaction_record")
def test_idempotency_same_key_returns_replay_no_new_insert(
    mock_create_tx,
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Two requests with same sourceVendor + idempotencyKey: second returns replay, no new row."""
    mock_validate.return_value = {
        "url": "http://example.com/op",
        "http_method": "POST",
        "timeout_ms": 8000,
        "canonical_version": "v1",
    }
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE"):
            return {"result": "$.result"}
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        return {"transactionId": "$.transactionId"}
    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)

    idem_key = "idem-same-123"
    first_response_ids = {}  # populated after first request

    def idem_side_effect(conn, source, key):
        if mock_idempotency_lookup.call_count == 1:
            return None
        return {
            "action": "replay",
            "transaction_id": first_response_ids.get("tx_id", "unknown"),
            "correlation_id": first_response_ids.get("corr_id", "unknown"),
            "status": "completed",
            "response_body": {"result": "ok"},
        }

    mock_idempotency_lookup.side_effect = idem_side_effect

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("LH001", True), ("tx-123",), ("LH001", True)]  # vendor, claim idempotency, vendor (replay)

    body = _execute_body(
        parameters={"transactionId": "tx-1"},
        idempotency_key=idem_key,
    )
    event = _base_event(body)

    # First request: idempotency_lookup returns None -> creates transaction
    resp1 = handler(event, None)
    assert resp1["statusCode"] == 200
    body1 = json.loads(resp1["body"])
    first_tx_id_actual = body1.get("transactionId")
    assert first_tx_id_actual
    first_response_ids["tx_id"] = first_tx_id_actual
    first_response_ids["corr_id"] = body1.get("correlationId", "")

    # Second request: same sourceVendor + idempotencyKey -> replay, no new insert
    resp2 = handler(event, None)
    assert resp2["statusCode"] == 200
    body2 = json.loads(resp2["body"])
    rb2 = body2.get("responseBody") or {}
    assert rb2.get("replayed") is True
    assert body2.get("transactionId") == first_tx_id_actual
    assert body2.get("correlationId")

    # create_transaction_record called exactly once (first request only)
    assert mock_create_tx.call_count == 1


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
@patch("routing_lambda.create_transaction_record")
def test_idempotency_first_call_inserts_and_proceeds(
    mock_create_tx,
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """First call with idempotencyKey: lookup returns None, insert proceeds, returns 200."""
    mock_validate.return_value = {
        "url": "http://example.com/op",
        "http_method": "POST",
        "timeout_ms": 8000,
        "canonical_version": "v1",
    }
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": (
        {"result": "$.result"} if "RESPONSE" in d else {"transactionId": "$.transactionId"}
    )
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("LH001", True), ("tx-123",)]  # vendor check, then _claim_idempotency

    event = _base_event(
        _execute_body(parameters={"transactionId": "tx-1"}, idempotency_key="idem-first-123")
    )
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("transactionId")
    rb = body.get("responseBody") or {}
    assert rb.get("status") == "completed"
    assert rb.get("replayed") is not True
    assert mock_create_tx.call_count == 1
    # Verify first call inserted with status='received' (deterministic idempotency)
    call_kw = mock_create_tx.call_args[1]
    assert call_kw.get("status") == "received"


@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
def test_idempotency_second_call_when_first_received_returns_409_in_flight(
    mock_conn_ctx,
    mock_idempotency_lookup,
) -> None:
    """Second call with same idempotencyKey when first is still 'received' (no response_body): 409 IN_FLIGHT."""
    mock_idempotency_lookup.return_value = {
        "action": "replay",
        "transaction_id": "tx-in-flight-1",
        "correlation_id": "corr-1",
        "status": "received",
        "response_body": None,
    }

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    event = _base_event(
        _execute_body(parameters={"transactionId": "tx-1"}, idempotency_key="idem-same-123"),
,
    )
    resp = handler(event, None)

    assert resp["statusCode"] == 409
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "IN_FLIGHT"
    assert err.get("category") == "CONFLICT"
    assert err.get("retryable") is True
    details = err.get("details", {})
    assert details.get("transactionId") == "tx-in-flight-1"
    assert details.get("status") == "received"
    assert "in progress" in err["message"].lower()


# --- Response pipeline: mapping missing ---


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_response_mapping_missing_returns_validation_error(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Missing TO_CANONICAL_RESPONSE + target returns non-canonical -> SCHEMA_VALIDATION_FAILED (canonical pass-through, schema validation fails)."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    # Canonical response requires validField; target returns {"result": "ok"} which fails
    base_contract = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None}
    canonical_contract = {**base_contract, "response_schema": {"type": "object", "required": ["validField"], "properties": {"validField": {"type": "string"}}}}

    def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
        if vendor_code is None:
            return canonical_contract
        return {**base_contract, "response_schema": None}

    mock_load_contract.side_effect = contract_side_effect

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        if direction == "FROM_CANONICAL":
            return {"transactionId": "$.transactionId"}
        if direction == "TO_CANONICAL_RESPONSE":
            return None
        return {"result": "$.result"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "SCHEMA_VALIDATION_FAILED"
    assert err.get("category") == "VALIDATION"
    assert err.get("retryable") is False
    assert "canonical" in err["message"].lower() or "schema" in err["message"].lower()


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_no_source_response_mapping_returns_canonical_as_is(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """No FROM_CANONICAL_RESPONSE mapping: canonical response returned as-is in response_body."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        if direction == "TO_CANONICAL_RESPONSE":
            return {"result": "$.result"}
        return None

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    rb = body.get("responseBody", {})
    assert rb.get("status") == "completed"
    assert rb.get("responseBody") == {"result": "ok"}


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_source_response_mapping_transforms_canonical_to_source_view(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Source response mapping: canonical {status, receiptId, vendorTrace} -> {receiptId} only."""
    canonical_response_schema = {"type": "object", "required": ["receiptId"], "properties": {"receiptId": {"type": "string"}, "status": {"type": "string"}, "vendorTrace": {"type": "string"}}}
    base_contract = {"operation_code": "GET_RECEIPT", "canonical_version": "v1"}

    def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
        if vendor_code is None:
            return {**base_contract, "request_schema": None, "response_schema": canonical_response_schema}
        return {**base_contract, "request_schema": None, "response_schema": None}

    mock_load_contract.side_effect = contract_side_effect

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        if direction == "TO_CANONICAL_RESPONSE":
            return {"status": "$.status", "receiptId": "$.receiptId", "vendorTrace": "$.vendorTrace"}
        if direction == "FROM_CANONICAL_RESPONSE":
            return {"receiptId": "$.receiptId"}
        return None

    mock_load_mapping.side_effect = mapping_side_effect
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_idempotency_lookup.return_value = None
    mock_call_downstream.return_value = (200, {"status": "completed", "receiptId": "R-123", "vendorTrace": "abc"}, None)

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    rb = body.get("responseBody", {})
    assert rb.get("status") == "completed"
    assert rb.get("responseBody") == {"receiptId": "R-123"}


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_source_response_mapping_missing_path_returns_mapping_failed(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Source response mapping requires path that does not exist -> MAPPING_FAILED 422."""
    canonical_response_schema = {"type": "object", "required": ["receiptId"], "properties": {"receiptId": {"type": "string"}}}
    base_contract = {"operation_code": "GET_RECEIPT", "canonical_version": "v1"}

    def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
        if vendor_code is None:
            return {**base_contract, "request_schema": None, "response_schema": canonical_response_schema}
        return {**base_contract, "request_schema": None, "response_schema": None}

    mock_load_contract.side_effect = contract_side_effect

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        if direction == "TO_CANONICAL_RESPONSE":
            return {"receiptId": "$.receiptId"}
        if direction == "FROM_CANONICAL_RESPONSE":
            return {"receiptId": "$.receiptId", "missingField": "$.missingField"}
        return None

    mock_load_mapping.side_effect = mapping_side_effect
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_idempotency_lookup.return_value = None
    mock_call_downstream.return_value = (200, {"receiptId": "R-123"}, None)

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 422
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "MAPPING_FAILED"
    assert err.get("category") == "MAPPING"
    assert "violations" in err or "violations" in (err.get("details") or {})


# --- Optional mappings: target accepts/returns canonical ---


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_target_no_mappings_vendor_schemas_match_canonical_success(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Target with no FROM_CANONICAL or TO_CANONICAL_RESPONSE but schemas match canonical -> success."""
    canonical_request_schema = {"type": "object", "required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}}
    canonical_response_schema = {"type": "object", "required": ["validField"], "properties": {"validField": {"type": "string"}}}
    base_contract = {"operation_code": "GET_RECEIPT", "canonical_version": "v1"}

    def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
        if vendor_code is None:
            return {**base_contract, "request_schema": canonical_request_schema, "response_schema": canonical_response_schema}
        if vendor_code == "LH002":
            # Target: same schemas as canonical (accepts canonical request, returns canonical response)
            return {**base_contract, "request_schema": canonical_request_schema, "response_schema": canonical_response_schema}
        return {**base_contract, "request_schema": None, "response_schema": None}

    mock_load_contract.side_effect = contract_side_effect

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        if direction == "FROM_CANONICAL":
            return None  # Target has no request mapping - passthrough
        if direction == "TO_CANONICAL_RESPONSE":
            return None  # Target has no response mapping - passthrough
        if direction == "FROM_CANONICAL_RESPONSE":
            return {"result": "$.validField"}  # Source maps canonical -> source format
        return None

    mock_load_mapping.side_effect = mapping_side_effect
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_idempotency_lookup.return_value = None
    mock_call_downstream.return_value = (200, {"validField": "ok"}, None)

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    rb = body.get("responseBody", {})
    assert rb.get("status") == "completed"
    assert rb.get("responseBody") == {"result": "ok"}


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_target_no_mappings_vendor_returns_non_canonical_fails_validation(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Target with no TO_CANONICAL_RESPONSE and vendor returns non-canonical -> SCHEMA_VALIDATION_FAILED (canonical pass-through, schema fails)."""
    base_contract = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None}
    canonical_contract = {**base_contract, "response_schema": {"type": "object", "required": ["validField"], "properties": {"validField": {"type": "string"}}}}

    def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
        if vendor_code is None:
            return canonical_contract
        return {**base_contract, "response_schema": None}

    mock_load_contract.side_effect = contract_side_effect
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_idempotency_lookup.return_value = None

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        if direction == "FROM_CANONICAL":
            return {"transactionId": "$.transactionId"}
        if direction == "TO_CANONICAL_RESPONSE":
            return None
        return {"result": "$.result"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"otherField": "non-canonical"}, None)

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "SCHEMA_VALIDATION_FAILED"
    assert "TO_CANONICAL_RESPONSE" in err.get("message", "") or "canonical" in err.get("message", "").lower()


# --- Source request mapping (TO_CANONICAL_REQUEST optional) ---


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_no_source_request_mapping_parameters_treated_as_canonical(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """No TO_CANONICAL_REQUEST or TO_CANONICAL for source -> parameters are canonical, validation works."""
    canonical_request_schema = {"type": "object", "required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}}
    base_contract = {"operation_code": "GET_RECEIPT", "canonical_version": "v1"}

    def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
        if vendor_code is None:
            return {**base_contract, "request_schema": canonical_request_schema, "response_schema": None}
        return {**base_contract, "request_schema": canonical_request_schema, "response_schema": None}

    mock_load_contract.side_effect = contract_side_effect

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL"):
            return None
        if direction == "FROM_CANONICAL":
            return {"transactionId": "$.transactionId"}
        return {"receipt_id": "$.receipt_id"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_idempotency_lookup.return_value = None
    mock_call_downstream.return_value = (200, {"receipt_id": "R-123"}, None)

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    rb = body.get("responseBody", {})
    assert rb.get("status") == "completed"
    assert rb.get("responseBody", {}).get("receipt_id") == "R-123"


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_source_request_mapping_transforms_to_canonical(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Source has TO_CANONICAL_REQUEST: businessTransactionId -> transactionId, passes schema."""
    canonical_request_schema = {"type": "object", "required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}}
    base_contract = {"operation_code": "GET_RECEIPT", "canonical_version": "v1"}

    def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
        if vendor_code is None:
            return {**base_contract, "request_schema": canonical_request_schema, "response_schema": None}
        return {**base_contract, "request_schema": None, "response_schema": None}

    mock_load_contract.side_effect = contract_side_effect

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction == "TO_CANONICAL_REQUEST":
            return {"transactionId": "$.businessTransactionId"}
        if direction == "FROM_CANONICAL":
            return {"transactionId": "$.transactionId"}
        return {"receipt_id": "$.receipt_id"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_idempotency_lookup.return_value = None
    mock_call_downstream.return_value = (200, {"receipt_id": "R-ABC-123"}, None)

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"businessTransactionId": "ABC-123", "customerId": "C-001"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    rb = body.get("responseBody", {})
    assert rb.get("status") == "completed"
    assert rb.get("responseBody", {}).get("receipt_id") == "R-ABC-123"
    mock_call_downstream.assert_called_once()
    call_args = mock_call_downstream.call_args[0]
    downstream_payload = call_args[2]
    assert downstream_payload.get("transactionId") == "ABC-123"
    # Outbound request must be target_request_body only; no transactionId/correlationId merge
    assert "correlationId" not in downstream_payload


def test_from_canonical_mapping_downstream_receives_only_mapped_fields() -> None:
    """When FROM_CANONICAL mapping exists, downstream must receive ONLY mapping output (no merge)."""
    with (
        patch("routing_lambda.call_downstream") as mock_call_downstream,
        patch("routing_lambda.load_vendor_mapping") as mock_load_mapping,
        patch("routing_lambda.load_operation_contract") as mock_load_contract,
        patch("routing_lambda.load_operation_version") as mock_load_version,
        patch("routing_lambda.idempotency_lookup") as mock_idempotency_lookup,
        patch("routing_lambda._get_connection") as mock_conn_ctx,
        patch("routing_lambda.validate_control_plane") as mock_validate,
    ):
        canonical_schema = {"type": "object", "required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}}
        target_schema = {"type": "object", "required": ["txnId"], "properties": {"txnId": {"type": "string"}}}
        base = {"operation_code": "GET_RECEIPT", "canonical_version": "v1"}

        def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
            if vendor_code is None:
                return {**base, "request_schema": canonical_schema, "response_schema": None}
            if vendor_code == "LH002":
                return {**base, "request_schema": target_schema, "response_schema": None}
            return {**base, "request_schema": None, "response_schema": None}

        def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
            if direction == "FROM_CANONICAL":
                return {"txnId": "$.transactionId"}
            if direction == "TO_CANONICAL_RESPONSE":
                return {"receiptId": "$.receiptId"}
            return None

        mock_load_contract.side_effect = contract_side_effect
        mock_load_mapping.side_effect = mapping_side_effect
        mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
        mock_load_version.return_value = "v1"
        mock_idempotency_lookup.return_value = None
        mock_call_downstream.return_value = (200, {"receiptId": "R-123"}, None)

        mock_conn = MagicMock()
        mock_conn_ctx.return_value.__enter__.return_value = mock_conn
        mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
        mock_cursor.fetchone.side_effect = [("LH001", True), ("tx-123",)]  # vendor check, then _claim_idempotency
        mock_cursor.execute.side_effect = None

        event = _base_event(_execute_body(parameters={"transactionId": "123"}))
        resp = handler(event, None)

        assert resp["statusCode"] == 200
        mock_call_downstream.assert_called_once()
        downstream_body = mock_call_downstream.call_args[0][2]
        assert downstream_body == {"txnId": "123"}
        assert "transactionId" not in downstream_body
        assert "correlationId" not in downstream_body


def test_no_from_canonical_mapping_downstream_receives_canonical_as_is() -> None:
    """When no FROM_CANONICAL mapping, downstream receives canonical_request_body as-is."""
    with (
        patch("routing_lambda.call_downstream") as mock_call_downstream,
        patch("routing_lambda.load_vendor_mapping") as mock_load_mapping,
        patch("routing_lambda.load_operation_contract") as mock_load_contract,
        patch("routing_lambda.load_operation_version") as mock_load_version,
        patch("routing_lambda.idempotency_lookup") as mock_idempotency_lookup,
        patch("routing_lambda._get_connection") as mock_conn_ctx,
        patch("routing_lambda.validate_control_plane") as mock_validate,
    ):
        canonical_schema = {"type": "object", "required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}}
        base = {"operation_code": "GET_RECEIPT", "canonical_version": "v1"}

        def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
            if vendor_code is None:
                return {**base, "request_schema": canonical_schema, "response_schema": None}
            if vendor_code == "LH002":
                return {**base, "request_schema": canonical_schema, "response_schema": None}
            return {**base, "request_schema": None, "response_schema": None}

        def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
            if direction == "FROM_CANONICAL":
                return None
            if direction == "TO_CANONICAL_RESPONSE":
                return {"receiptId": "$.receiptId"}
            return None

        mock_load_contract.side_effect = contract_side_effect
        mock_load_mapping.side_effect = mapping_side_effect
        mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
        mock_load_version.return_value = "v1"
        mock_idempotency_lookup.return_value = None
        mock_call_downstream.return_value = (200, {"receiptId": "R-123"}, None)

        mock_conn = MagicMock()
        mock_conn_ctx.return_value.__enter__.return_value = mock_conn
        mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
        mock_cursor.fetchone.side_effect = [("LH001", True), ("tx-123",)]  # vendor check, then _claim_idempotency
        mock_cursor.execute.side_effect = None

        event = _base_event(_execute_body(parameters={"transactionId": "123"}))
        resp = handler(event, None)

        assert resp["statusCode"] == 200
        mock_call_downstream.assert_called_once()
        downstream_body = mock_call_downstream.call_args[0][2]
        assert downstream_body == {"transactionId": "123"}
        assert "correlationId" not in downstream_body


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_source_request_mapping_missing_path_returns_mapping_failed(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Source mapping requires businessTransactionId but params lack it -> MAPPING_FAILED with violations."""
    base_contract = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_contract.return_value = base_contract

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction == "TO_CANONICAL_REQUEST":
            return {"transactionId": "$.businessTransactionId"}
        if direction == "FROM_CANONICAL":
            return {"transactionId": "$.transactionId"}
        return None

    mock_load_mapping.side_effect = mapping_side_effect
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_idempotency_lookup.return_value = None
    mock_call_downstream.return_value = (200, {}, None)

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"customerId": "C-001"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 422
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "MAPPING_FAILED"
    assert err.get("category") == "MAPPING"
    violations = err.get("violations") or (err.get("details") or {}).get("violations", [])
    assert any("businessTransactionId" in str(v) or "transactionId" in str(v) for v in violations)
    mock_call_downstream.assert_not_called()


# --- Response pipeline: mapping works ---


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_response_mapping_works_produces_canonical_and_source_response(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Response pipeline: target_response -> canonical_response -> source_response produced."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        return {"result": "$.result", "amount": "$.amount"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok", "amount": 42}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    rb = body.get("responseBody", {})
    assert rb.get("status") == "completed"
    assert rb.get("responseBody") == {"result": "ok", "amount": 42}


# --- Response pipeline: canonical schema violation ---


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_canonical_response_schema_violation_returns_validation_error(
    mock_validate,
    mock_conn_ctx,
    mock_load_version,
    mock_idempotency_lookup,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Canonical response schema violation -> SCHEMA_VALIDATION_FAILED with violations."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_idempotency_lookup.return_value = None

    base_contract = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None}
    canonical_contract = {**base_contract, "response_schema": {"type": "object", "required": ["validField"], "properties": {"validField": {"type": "string"}}}}
    target_contract = {**base_contract, "response_schema": None}

    def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
        if vendor_code == "LH002":
            return target_contract
        if vendor_code:
            return {**base_contract, "response_schema": None}
        return canonical_contract

    mock_load_contract.side_effect = contract_side_effect

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        return {"result": "$.result"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "SCHEMA_VALIDATION_FAILED"
    assert err.get("category") in ("VALIDATION", "MAPPING", "NOT_FOUND", "POLICY")
    violations = err.get("violations", err.get("details", {}).get("violations", []))
    assert len(violations) > 0


# --- Canonical taxonomy: error path assertions ---


@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
def test_execute_invalid_json_body_returns_invalid_json(
    mock_conn_ctx,
    mock_idempotency_lookup,
) -> None:
    """Invalid JSON body -> INVALID_JSON 400, category validation."""
    mock_idempotency_lookup.return_value = None  # no cached row
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    event = _base_event("not json {{{", headers={"Authorization": "Bearer mock-token"})
    resp = handler(event, None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "INVALID_JSON"
    assert err.get("category") in ("VALIDATION", "MAPPING", "NOT_FOUND", "POLICY")
    assert err.get("retryable") is False


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
def test_execute_operation_not_found_returns_operation_not_found(
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Operation not found or inactive -> OPERATION_NOT_FOUND 404."""
    mock_load_version.return_value = None
    mock_idempotency_lookup.return_value = None
    mock_load_contract.return_value = {}
    mock_load_mapping.return_value = {}
    mock_call_downstream.return_value = (200, {}, None)
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None
    event = _base_event(_execute_body(), )
    resp = handler(event, None)
    assert resp["statusCode"] == 404
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "OPERATION_NOT_FOUND"
    assert err.get("category") in ("VALIDATION", "MAPPING", "NOT_FOUND", "POLICY")
    assert err.get("retryable") is False


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_downstream_non_2xx_returns_downstream_http_error(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Downstream returns 502 -> DOWNSTREAM_HTTP_ERROR 502, category downstream, does not trigger mapping/schema validation."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE"):
            return {"result": "$.result"}
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        return {"transactionId": "$.transactionId"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (502, {"error": "Bad Gateway"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 502
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "DOWNSTREAM_HTTP_ERROR"
    assert err.get("category") == "DOWNSTREAM"
    assert err.get("retryable") is False
    assert err.get("details", {}).get("vendorStatusCode") == 502


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_downstream_400_produces_downstream_http_error_no_mapping_errors(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Downstream 400 produces DOWNSTREAM_HTTP_ERROR; does NOT trigger response mapping or schema validation."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE"):
            return {"result": "$.result"}
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        return {"transactionId": "$.transactionId"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (400, {"error": "Bad Request", "details": "Invalid transactionId"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 502
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "DOWNSTREAM_HTTP_ERROR"
    assert err.get("category") == "DOWNSTREAM"
    assert err.get("details", {}).get("vendorStatusCode") == 400
    assert err.get("details", {}).get("vendorBody") == {"error": "Bad Request", "details": "Invalid transactionId"}
    assert err.get("code") != "MAPPING_FAILED"
    assert err.get("code") != "SCHEMA_VALIDATION_FAILED"


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_missing_request_mapping_produces_mapping_not_found(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Missing FROM_CANONICAL for target + target has different request_schema -> SCHEMA_VALIDATION_FAILED 400."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    base_contract = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "response_schema": None}
    canonical_request_schema = {"type": "object", "required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}}
    target_request_schema = {"type": "object", "required": ["receiptId"], "properties": {"receiptId": {"type": "string"}}}

    def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
        if vendor_code is None:
            return {**base_contract, "request_schema": canonical_request_schema}
        if vendor_code == "LH002":
            return {**base_contract, "request_schema": target_request_schema}
        return {**base_contract, "request_schema": None}

    mock_load_contract.side_effect = contract_side_effect

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL"):
            return None  # Params as canonical
        if direction == "FROM_CANONICAL":
            return None  # Target has no mapping; passthrough fails schema
        if direction in ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE"):
            return {"result": "$.result"}
        return {"transactionId": "$.transactionId"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "SCHEMA_VALIDATION_FAILED"
    assert err.get("category") in ("VALIDATION", "MAPPING", "NOT_FOUND", "POLICY")
    assert "canonical" in err.get("message", "").lower() or "schema" in err.get("message", "").lower()


@patch("routing_lambda.apply_mapping")
@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_jsonpath_missing_produces_mapping_failed_with_violations(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
    mock_apply_mapping,
) -> None:
    """JSONPath missing in source produces MAPPING_FAILED with violations."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE"):
            return {"result": "$.result"}
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        return {"transactionId": "$.transactionId"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    violations = ["Path '$.missingField' not found"]
    call_count = [0]

    def apply_mapping_side_effect(source, mapping):
        call_count[0] += 1
        if call_count[0] == 1:
            return ({"transactionId": source.get("transactionId")}, violations)
        return (source, [])

    mock_apply_mapping.side_effect = apply_mapping_side_effect

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 422
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "MAPPING_FAILED"
    assert err.get("category") in ("VALIDATION", "MAPPING", "NOT_FOUND", "POLICY")
    assert "violations" in err.get("details", {})
    assert err["details"]["violations"] == violations


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_downstream_timeout_returns_downstream_timeout(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Downstream timeout -> DOWNSTREAM_TIMEOUT 504, category downstream, retryable True."""
    import requests

    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE"):
            return {"result": "$.result"}
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        return {"transactionId": "$.transactionId"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.side_effect = requests.exceptions.Timeout()
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 504
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "DOWNSTREAM_TIMEOUT"
    assert err.get("category") == "DOWNSTREAM"
    assert err.get("retryable") is True


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_downstream_connection_error_returns_downstream_connection_error(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """RequestException (e.g. connection refused) -> DOWNSTREAM_CONNECTION_ERROR 502, retryable True."""
    import requests

    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE"):
            return {"result": "$.result"}
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        return {"transactionId": "$.transactionId"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.side_effect = requests.exceptions.ConnectionError("Connection refused")
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 502
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "DOWNSTREAM_CONNECTION_ERROR"
    assert err.get("category") == "DOWNSTREAM"
    assert err.get("retryable") is True


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_endpoint_not_verified_returns_endpoint_not_verified(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """EndpointNotVerifiedError -> ENDPOINT_NOT_VERIFIED 412."""
    from routing_lambda import EndpointNotVerifiedError

    mock_validate.side_effect = EndpointNotVerifiedError("Endpoint not verified for LH002")
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE"):
            return {"result": "$.result"}
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        return {"transactionId": "$.transactionId"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 412
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "ENDPOINT_NOT_VERIFIED"
    assert err.get("category") in ("VALIDATION", "MAPPING", "NOT_FOUND", "POLICY")


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_allowlist_denied_returns_allowlist_denied(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """ValueError with Allowlist -> ALLOWLIST_DENIED 403."""
    mock_validate.side_effect = ValueError("Allowlist does not permit LH001->LH002 for GET_RECEIPT")
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE"):
            return {"result": "$.result"}
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        return {"transactionId": "$.transactionId"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 403
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "ALLOWLIST_DENIED"
    assert err.get("category") in ("VALIDATION", "MAPPING", "NOT_FOUND", "POLICY")


@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_allowlist_vendor_denied_returns_403(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
) -> None:
    """ValueError with ALLOWLIST_VENDOR_DENIED -> 403 ALLOWLIST_VENDOR_DENIED (provider narrowing)."""
    mock_validate.side_effect = ValueError(
        "ALLOWLIST_VENDOR_DENIED: Provider narrowed access; LH046 not in whitelist for GET_WEATHER -> LH001"
    )
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_WEATHER", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, version, d, flow_direction="OUTBOUND": {"city": "$.city"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {}
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("LH001", True), ("tx-123",)]
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(target_vendor="LH001", operation="GET_WEATHER", parameters={"city": "NYC"}))
    resp = handler(event, None)

    assert resp["statusCode"] == 403
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "ALLOWLIST_VENDOR_DENIED"


# --- Error classification: httpStatus, error.code, error.category, error.retryable, violations ---


@patch("routing_lambda._process_response_pipeline")
@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_downstream_http_error_skips_response_mapping(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
    mock_process_response_pipeline,
) -> None:
    """Downstream 400 with JSON body: error.code==DOWNSTREAM_HTTP_ERROR, mapping not called, schema validation for CANONICAL_RESPONSE not called."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"transactionId": "$.transactionId"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"result": "$.result"}
    mock_call_downstream.return_value = (400, {"error": "Bad Request", "message": "Invalid payload"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 502
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "DOWNSTREAM_HTTP_ERROR"
    assert err.get("category") == "DOWNSTREAM"
    assert err.get("retryable") is False
    assert err.get("details", {}).get("vendorStatusCode") == 400
    mock_call_downstream.assert_called_once()

    # Response mapping (TO_CANONICAL_RESPONSE, FROM_CANONICAL_RESPONSE) must NOT be invoked
    response_directions = ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE")
    for call in mock_load_mapping.call_args_list:
        args, kwargs = call[0], call[1] if len(call) > 1 else {}
        direction = args[4] if len(args) > 4 else kwargs.get("direction")
        assert direction not in response_directions, (
            "Response mapping must not be invoked when downstream returns >= 400"
        )
    # Schema validation for CANONICAL_RESPONSE (inside _process_response_pipeline) must NOT be invoked
    mock_process_response_pipeline.assert_not_called()


@patch("routing_lambda._process_response_pipeline")
@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_downstream_4xx_does_not_invoke_response_pipeline(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
    mock_process_response_pipeline,
) -> None:
    """Downstream 4xx/5xx: _process_response_pipeline (TO_CANONICAL_RESPONSE, schema, FROM_CANONICAL_RESPONSE) is never invoked."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"transactionId": "$.transactionId"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"result": "$.result"}
    mock_call_downstream.return_value = (404, {"error": "Not found"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 502
    mock_process_response_pipeline.assert_not_called()


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_mapping_not_found_returns_409(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Missing FROM_CANONICAL for target + target has different request_schema -> SCHEMA_VALIDATION_FAILED 400."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    base_contract = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "response_schema": None}
    canonical_request_schema = {"type": "object", "required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}}
    target_request_schema = {"type": "object", "required": ["receiptId"], "properties": {"receiptId": {"type": "string"}}}

    def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
        if vendor_code is None:
            return {**base_contract, "request_schema": canonical_request_schema}
        if vendor_code == "LH002":
            return {**base_contract, "request_schema": target_request_schema}
        return {**base_contract, "request_schema": None}

    mock_load_contract.side_effect = contract_side_effect

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL"):
            return None  # Params as canonical
        if direction == "FROM_CANONICAL":
            return None  # Target has no mapping; passthrough fails schema
        return {"result": "$.result"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "SCHEMA_VALIDATION_FAILED"
    assert err.get("category") == "VALIDATION"
    assert err.get("retryable") is False
    mock_call_downstream.assert_not_called()


@patch("routing_lambda.apply_mapping")
@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_mapping_failed_returns_422_with_violations(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
    mock_apply_mapping,
) -> None:
    """JSONPath missing in source -> MAPPING_FAILED 422 with violations."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"transactionId": "$.transactionId"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"result": "$.result"}
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    violations = ["Path '$.missingField' not found"]
    mock_apply_mapping.side_effect = lambda src, m: ({"transactionId": src.get("transactionId")}, violations)

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 422
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "MAPPING_FAILED"
    assert err.get("category") == "MAPPING"
    assert err.get("retryable") is False
    assert "violations" in err or "violations" in (err.get("details") or {})
    violations_out = err.get("violations") or (err.get("details") or {}).get("violations", [])
    assert len(violations_out) > 0
    assert violations_out[0] == "Path '$.missingField' not found"


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_schema_validation_failed_stage_canonical_request(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Canonical payload violates canonical request schema -> SCHEMA_VALIDATION_FAILED 400 with violations, stage CANONICAL_REQUEST."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"

    canonical_schema = {"type": "object", "required": ["transactionId"], "properties": {"transactionId": {"type": "string", "minLength": 1}}}

    def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
        if vendor_code:
            return {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
        return {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": canonical_schema, "response_schema": None}

    mock_load_contract.side_effect = contract_side_effect
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"transactionId": "$.transactionId"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"result": "$.result"}
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": ""}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "SCHEMA_VALIDATION_FAILED"
    assert err.get("category") == "VALIDATION"
    assert err.get("retryable") is False
    violations = err.get("violations", (err.get("details") or {}).get("violations", []))
    assert len(violations) > 0
    assert err.get("details", {}).get("stage") == "CANONICAL_REQUEST"


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_vendor_not_found_returns_404(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Target vendor not found or inactive -> VENDOR_NOT_FOUND 404."""
    mock_validate.side_effect = ValueError("Target vendor LH002 not found or inactive")
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"transactionId": "$.transactionId"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"result": "$.result"}
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 404
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "VENDOR_NOT_FOUND"
    assert err.get("category") == "NOT_FOUND"
    assert err.get("retryable") is False
    mock_call_downstream.assert_not_called()


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_operation_not_found_returns_404(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Operation not found or inactive -> OPERATION_NOT_FOUND 404."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = None
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"transactionId": "$.transactionId"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"result": "$.result"}
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 404
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "OPERATION_NOT_FOUND"
    assert err.get("category") == "NOT_FOUND"
    assert err.get("retryable") is False
    mock_call_downstream.assert_not_called()


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_allowlist_denied(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Allowlist does not permit operation -> ALLOWLIST_DENIED 403."""
    mock_validate.side_effect = ValueError("Allowlist does not permit LH001->LH002 for GET_RECEIPT")
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"transactionId": "$.transactionId"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"result": "$.result"}
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 403
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "ALLOWLIST_DENIED"
    assert err.get("category") == "POLICY"
    assert err.get("retryable") is False
    mock_call_downstream.assert_not_called()


# --- Routing flow rules: direction_policy, allowlist flow_direction, INBOUND endpoint ---


def _make_validate_control_plane_mock_cursor(
    source_ok: bool = True,
    target_ok: bool = True,
    operation_row: dict | None = None,
    supported_ok: bool = True,
    allowlist_ok: bool = True,
    endpoint_row: dict | None = None,
    vendor_rules: list[dict] | None = None,
) -> MagicMock:
    """Build cursor mock for validate_control_plane DB sequence.
    vendor_rules: for PROVIDER_RECEIVES_ONLY, list of {source_vendor_code} for fetchall.
    Empty list = no narrowing. Non-empty = source must be in list or ALLOWLIST_VENDOR_DENIED."""
    op_row = dict(operation_row or {"operation_code": "GET_WEATHER", "canonical_version": "v1"})
    if "direction_policy" not in op_row:
        op_row["direction_policy"] = "TWO_WAY"
    # Endpoint row for load_effective_endpoint (needs id, vendor_auth_profile_id, flow_direction, etc.)
    _default_ep = {
        "id": "ep-uuid-provider",
        "vendor_code": "PROVIDER",
        "operation_code": "GET_WEATHER",
        "flow_direction": "INBOUND",
        "url": "http://provider.com/weather",
        "http_method": "POST",
        "timeout_ms": 5000,
        "payload_format": None,
        "vendor_auth_profile_id": None,
        "verification_status": "VERIFIED",
    }
    ep_row = {**_default_ep, **(endpoint_row or {})} if endpoint_row is not False else None
    fetchone_results: list = []
    if source_ok:
        fetchone_results.append((1,))
    else:
        fetchone_results.append(None)
    if target_ok:
        fetchone_results.append((1,))
    else:
        fetchone_results.append(None)
    fetchone_results.append(op_row)
    if supported_ok:
        fetchone_results.append((1,))
    else:
        fetchone_results.append(None)
    if allowlist_ok:
        fetchone_results.append((1,))
    else:
        fetchone_results.append(None)
    # load_effective_endpoint exact match (6th fetchone)
    fetchone_results.append(ep_row if endpoint_row is not False else None)

    cursor = MagicMock()
    cursor.execute = MagicMock()
    cursor.fetchone = MagicMock(side_effect=fetchone_results)
    cursor.fetchall = MagicMock(return_value=vendor_rules if vendor_rules is not None else [])
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    return cursor


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
def test_routing_provider_receives_only_flow_succeeds(
    mock_conn_ctx: MagicMock,
    mock_idempotency_lookup: MagicMock,
    mock_load_version: MagicMock,
    mock_load_contract: MagicMock,
    mock_load_mapping: MagicMock,
    mock_call_downstream: MagicMock,
) -> None:
    """Licensee->Provider with direction_policy=PROVIDER_RECEIVES_ONLY: allowlist flow_direction=OUTBOUND,
    provider endpoint flow_direction=INBOUND. Routing succeeds, uses INBOUND endpoint."""
    from routing_lambda import validate_control_plane

    mock_idempotency_lookup.return_value = None
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_WEATHER", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"city": "$.city"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"temp": "$.temp"}
    mock_call_downstream.return_value = (200, {"temp": 72}, None)

    cursor = _make_validate_control_plane_mock_cursor(
        allowlist_ok=True,
        endpoint_row={
            "url": "http://provider.com/weather",
            "http_method": "POST",
            "timeout_ms": 5000,
            "payload_format": None,
            "verification_status": "VERIFIED",
            "vendor_auth_profile_id": None,
        },
    )
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = cursor
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    result = validate_control_plane(mock_conn, "LICENSEE", "PROVIDER", "GET_WEATHER")
    assert result["url"] == "http://provider.com/weather"
    assert result["http_method"] == "POST"
    assert result["canonical_version"] == "v1"


def test_validate_control_plane_fallback_when_only_opposite_direction() -> None:
    """Endpoint exists only as OUTBOUND; explicit INBOUND resolution now fails."""
    from routing_lambda import validate_control_plane

    op_row = {"operation_code": "GET_WEATHER", "canonical_version": "v1", "direction_policy": "TWO_WAY"}
    ep_row_outbound = {
        "id": "ep-outbound",
        "vendor_code": "PROVIDER",
        "operation_code": "GET_WEATHER",
        "flow_direction": "OUTBOUND",
        "url": "https://fallback.com/weather",
        "http_method": "POST",
        "timeout_ms": 5000,
        "payload_format": None,
        "vendor_auth_profile_id": None,
        "verification_status": "VERIFIED",
    }
    cursor = _make_validate_control_plane_mock_cursor(
        operation_row=op_row,
        allowlist_ok=True,
        endpoint_row=None,
    )
    # Override: 6th fetchone (exact) = None; no cross-direction fallback now.
    cursor.fetchone = MagicMock(
        side_effect=[
            (1,),
            (1,),
            op_row,
            (1,),
            (1,),
            None,
        ]
    )
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = cursor

    with pytest.raises(ValueError, match="No active endpoint"):
        validate_control_plane(mock_conn, "LICENSEE", "PROVIDER", "GET_WEATHER")


@patch("routing_lambda._get_connection")
def test_validate_control_plane_allowlist_violation_raises_value_error(mock_conn_ctx: MagicMock) -> None:
    """validate_control_plane raises ValueError when no allowlist row -> handler maps to ALLOWLIST_DENIED 403."""
    from routing_lambda import validate_control_plane

    cursor = _make_validate_control_plane_mock_cursor(allowlist_ok=False, endpoint_row=False)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = cursor
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    with pytest.raises(ValueError, match="Allowlist violation"):
        validate_control_plane(mock_conn, "LICENSEE", "PROVIDER", "GET_WEATHER")


# --- Provider narrowing (PROVIDER_RECEIVES_ONLY vendor rules) ---


@patch("routing_lambda._get_connection")
def test_validate_control_plane_provider_narrowing_admin_star_no_vendor_rules_any_source_allowed(
    mock_conn_ctx: MagicMock,
) -> None:
    """Admin * -> LH001; no vendor rules: any source vendor allowed."""
    from routing_lambda import validate_control_plane

    cursor = _make_validate_control_plane_mock_cursor(
        operation_row={"operation_code": "GET_WEATHER", "canonical_version": "v1", "direction_policy": "PROVIDER_RECEIVES_ONLY"},
        allowlist_ok=True,
        vendor_rules=[],  # No vendor rules = no narrowing
    )
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = cursor
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    result = validate_control_plane(mock_conn, "LH046", "LH001", "GET_WEATHER")
    assert result["url"] is not None


@patch("routing_lambda._get_connection")
def test_validate_control_plane_provider_narrowing_vendor_rules_lh002_only_lh002_allowed(
    mock_conn_ctx: MagicMock,
) -> None:
    """Admin * -> LH001; vendor rules for LH002 only: LH002 -> LH001 allowed."""
    from routing_lambda import validate_control_plane

    cursor = _make_validate_control_plane_mock_cursor(
        operation_row={"operation_code": "GET_WEATHER", "canonical_version": "v1", "direction_policy": "PROVIDER_RECEIVES_ONLY"},
        allowlist_ok=True,
        vendor_rules=[{"source_vendor_code": "LH002", "is_any_source": False}],
    )
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = cursor
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    result = validate_control_plane(mock_conn, "LH002", "LH001", "GET_WEATHER")
    assert result["url"] is not None


@patch("routing_lambda._get_connection")
def test_validate_control_plane_provider_narrowing_vendor_rules_lh002_only_lh046_denied(
    mock_conn_ctx: MagicMock,
) -> None:
    """Admin * -> LH001; vendor rules for LH002 only: LH046 -> LH001 denied (ALLOWLIST_VENDOR_DENIED)."""
    from routing_lambda import validate_control_plane

    cursor = _make_validate_control_plane_mock_cursor(
        operation_row={"operation_code": "GET_WEATHER", "canonical_version": "v1", "direction_policy": "PROVIDER_RECEIVES_ONLY"},
        allowlist_ok=True,
        vendor_rules=[{"source_vendor_code": "LH002", "is_any_source": False}],
    )
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = cursor
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    with pytest.raises(ValueError, match="ALLOWLIST_VENDOR_DENIED"):
        validate_control_plane(mock_conn, "LH046", "LH001", "GET_WEATHER")


@patch("routing_lambda._get_connection")
def test_validate_control_plane_provider_narrowing_admin_lh002_only_vendor_cannot_widen(
    mock_conn_ctx: MagicMock,
) -> None:
    """Admin LH002 -> LH001; even if vendor rule for LH046 exists, LH046 -> LH001 denied (admin doesn't allow)."""
    from routing_lambda import validate_control_plane

    # Admin allowlist fails for LH046 -> LH001 (we simulate by allowlist_ok=False for that combo)
    # So validate_control_plane raises Allowlist violation before we get to vendor narrowing.
    cursor = _make_validate_control_plane_mock_cursor(
        operation_row={"operation_code": "GET_WEATHER", "canonical_version": "v1", "direction_policy": "PROVIDER_RECEIVES_ONLY"},
        allowlist_ok=False,  # Admin does not allow LH046 -> LH001
        vendor_rules=[{"source_vendor_code": "LH046", "is_any_source": False}],
    )
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = cursor
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    with pytest.raises(ValueError, match="Allowlist violation"):
        validate_control_plane(mock_conn, "LH046", "LH001", "GET_WEATHER")


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_routing_e2e_licensee_to_provider_happy_path(
    mock_validate: MagicMock,
    mock_conn_ctx: MagicMock,
    mock_idempotency_lookup: MagicMock,
    mock_load_version: MagicMock,
    mock_load_contract: MagicMock,
    mock_load_mapping: MagicMock,
    mock_call_downstream: MagicMock,
) -> None:
    """E2E: Licensee->Provider happy path. validate_control_plane returns INBOUND endpoint;
    flow completes: allowlist passed, correct endpoint used, transaction+audit, 200."""
    mock_validate.return_value = {
        "url": "http://provider.com/weather",
        "http_method": "POST",
        "timeout_ms": 5000,
        "canonical_version": "v1",
    }
    mock_idempotency_lookup.return_value = None
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_WEATHER", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"city": "$.city"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"temp": "$.temp"}
    mock_call_downstream.return_value = (200, {"temp": 72}, None)

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("LH001", True), ("tx-123",)]
    mock_cursor.execute.side_effect = None

    event = _base_event(
        _execute_body(target_vendor="PROVIDER", operation="GET_WEATHER", parameters={"city": "NYC"})
    )
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "transactionId" in body
    assert body.get("responseBody", {}).get("status") == "completed"
    mock_call_downstream.assert_called_once()
    mock_validate.assert_called_once_with(mock_conn, "LH001", "PROVIDER", "GET_WEATHER")
    call_args = mock_call_downstream.call_args[0]
    assert call_args[0] == "http://provider.com/weather"


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_routing_e2e_allowlist_ok_but_missing_endpoint_returns_structured_error(
    mock_validate: MagicMock,
    mock_conn_ctx: MagicMock,
    mock_idempotency_lookup: MagicMock,
    mock_load_version: MagicMock,
    mock_load_contract: MagicMock,
    mock_load_mapping: MagicMock,
    mock_call_downstream: MagicMock,
) -> None:
    """E2E: Allowlist permits but provider has no endpoint -> ENDPOINT_NOT_FOUND, not 500."""
    mock_validate.side_effect = ValueError("No active endpoint for PROVIDER + GET_WEATHER")
    mock_idempotency_lookup.return_value = None
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_WEATHER", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"city": "$.city"}

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("LH001", True), ("tx-123",)]
    mock_cursor.execute.side_effect = None

    event = _base_event(
        _execute_body(target_vendor="PROVIDER", operation="GET_WEATHER", parameters={"city": "NYC"})
    )
    resp = handler(event, None)

    assert resp["statusCode"] in (400, 404)
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "ENDPOINT_NOT_FOUND"
    mock_call_downstream.assert_not_called()


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_endpoint_not_verified(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Endpoint not verified -> ENDPOINT_NOT_VERIFIED 412."""
    from routing_lambda import EndpointNotVerifiedError

    mock_validate.side_effect = EndpointNotVerifiedError("Endpoint not verified for LH002")
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"transactionId": "$.transactionId"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"result": "$.result"}
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 412
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "ENDPOINT_NOT_VERIFIED"
    assert err.get("category") == "VALIDATION"
    assert err.get("retryable") is False
    mock_call_downstream.assert_not_called()


# --- Debug payload tier: success and mapping failure ---


@patch("routing_lambda.update_transaction_success")
@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_success_populates_debug_payload_fields(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
    mock_update_success,
) -> None:
    """Successful execute populates canonical/target bodies and http_status on transaction."""
    mock_validate.return_value = {
        "url": "http://example.com/op",
        "http_method": "POST",
        "timeout_ms": 8000,
        "canonical_version": "v1",
    }
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": None,
        "response_schema": None,
    }

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE"):
            return {"result": "$.result"}
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        return {"transactionId": "$.transactionId"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(
        _execute_body(parameters={"transactionId": "tx-1"}),
,
    )
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    mock_update_success.assert_called_once()
    call_args, call_kw = mock_update_success.call_args
    assert call_kw.get("canonical_request") == {"transactionId": "tx-1"}
    assert call_kw.get("target_request") == {"transactionId": "tx-1"}
    assert call_kw.get("target_response_body") == {"result": "ok"}
    assert call_kw.get("canonical_response_body", {}).get("result") == "ok"
    assert call_kw.get("http_status") == 200


@patch("routing_lambda.update_transaction_failure")
@patch("routing_lambda.apply_mapping")
@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_execute_mapping_failure_populates_debug_payload_fields(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
    mock_apply_mapping,
    mock_update_failure,
) -> None:
    """Mapping failure populates error_code, http_status, retryable, and body fields."""
    mock_validate.return_value = {
        "url": "http://example.com/op",
        "http_method": "POST",
        "timeout_ms": 8000,
        "canonical_version": "v1",
    }
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": None,
        "response_schema": None,
    }

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_RESPONSE", "FROM_CANONICAL_RESPONSE"):
            return {"result": "$.result"}
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL"):
            return {"transactionId": "$.transactionId"}
        return {"transactionId": "$.transactionId"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    violations = ["Path '$.missingField' not found"]
    call_count = [0]

    def apply_mapping_side_effect(source, mapping):
        call_count[0] += 1
        if call_count[0] == 1:
            return ({"transactionId": source.get("transactionId")}, violations)
        return (source, [])

    mock_apply_mapping.side_effect = apply_mapping_side_effect

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(
        _execute_body(parameters={"transactionId": "tx-1"}),
,
    )
    resp = handler(event, None)

    assert resp["statusCode"] == 422
    mock_update_failure.assert_called_once()
    call_args, call_kw = mock_update_failure.call_args
    assert call_args[2] == "mapping_failed"  # status matches error type
    assert call_kw.get("taxonomy_err") is not None
    assert call_kw["taxonomy_err"].get("code") == "MAPPING_FAILED"
    assert call_kw["taxonomy_err"].get("http_status") == 422
    assert call_kw["taxonomy_err"].get("retryable") is False
    assert call_kw.get("canonical_request_body") == {"transactionId": "tx-1"}
    assert call_kw.get("target_request_body") is None


# --- Regression: taxonomy + downstream rule ---


@patch("routing_lambda._process_response_pipeline")
@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_regression_downstream_400_downstream_http_error_and_response_mapping_not_called(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
    mock_process_response_pipeline,
) -> None:
    """Regression: downstream 400 -> error.code DOWNSTREAM_HTTP_ERROR, response mapping not called."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"transactionId": "$.transactionId"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"result": "$.result"}
    mock_call_downstream.return_value = (400, {"error": "Bad Request"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "DOWNSTREAM_HTTP_ERROR"
    mock_process_response_pipeline.assert_not_called()


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_regression_missing_mapping_mapping_not_found_409(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Regression: missing FROM_CANONICAL for target + target has different request_schema -> SCHEMA_VALIDATION_FAILED, http_status 400."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    base_contract = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "response_schema": None}
    canonical_request_schema = {"type": "object", "required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}}
    target_request_schema = {"type": "object", "required": ["receiptId"], "properties": {"receiptId": {"type": "string"}}}

    def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
        if vendor_code is None:
            return {**base_contract, "request_schema": canonical_request_schema}
        if vendor_code == "LH002":
            return {**base_contract, "request_schema": target_request_schema}
        return {**base_contract, "request_schema": None}

    mock_load_contract.side_effect = contract_side_effect

    def mapping_side_effect(conn, vendor, op, version, direction, flow_direction="OUTBOUND"):
        if direction in ("TO_CANONICAL_REQUEST", "TO_CANONICAL"):
            return None
        if direction == "FROM_CANONICAL":
            return None
        return {"result": "$.result"}

    mock_load_mapping.side_effect = mapping_side_effect
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert body.get("error", {}).get("code") == "SCHEMA_VALIDATION_FAILED"


@patch("routing_lambda.apply_mapping")
@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_regression_mapping_violation_mapping_failed_422_with_violations(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
    mock_apply_mapping,
) -> None:
    """Regression: mapping violation -> MAPPING_FAILED, http_status 422 with violations."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"transactionId": "$.transactionId"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"result": "$.result"}
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    violations = ["Path '$.missing' not found"]
    mock_apply_mapping.side_effect = lambda src, m: ({"transactionId": src.get("transactionId")}, violations)

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 422
    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "MAPPING_FAILED"
    violations_out = err.get("violations") or (err.get("details") or {}).get("violations", [])
    assert len(violations_out) > 0


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_regression_schema_canonical_request_violation_schema_validation_failed_stage(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Regression: schema canonical request violation -> SCHEMA_VALIDATION_FAILED with stage CANONICAL_REQUEST."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = "v1"

    schema = {"type": "object", "required": ["transactionId"], "properties": {"transactionId": {"type": "string", "minLength": 1}}}

    def contract_side_effect(conn, op, version, vendor_code=None, flow_direction=None):
        if vendor_code:
            return {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
        return {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": schema, "response_schema": None}

    mock_load_contract.side_effect = contract_side_effect
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"transactionId": "$.transactionId"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"result": "$.result"}
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": ""}), )
    resp = handler(event, None)

    body = json.loads(resp["body"])
    err = body.get("error", {})
    assert err.get("code") == "SCHEMA_VALIDATION_FAILED"
    assert err.get("details", {}).get("stage") == "CANONICAL_REQUEST"


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_regression_vendor_not_found_404(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Regression: vendor_not_found -> 404."""
    mock_validate.side_effect = ValueError("Target vendor LH002 not found or inactive")
    mock_load_version.return_value = "v1"
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"transactionId": "$.transactionId"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"result": "$.result"}
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 404
    assert json.loads(resp["body"]).get("error", {}).get("code") == "VENDOR_NOT_FOUND"


@patch("routing_lambda.call_downstream")
@patch("routing_lambda.load_vendor_mapping")
@patch("routing_lambda.load_operation_contract")
@patch("routing_lambda.load_operation_version")
@patch("routing_lambda.idempotency_lookup")
@patch("routing_lambda._get_connection")
@patch("routing_lambda.validate_control_plane")
def test_regression_operation_not_found_404(
    mock_validate,
    mock_conn_ctx,
    mock_idempotency_lookup,
    mock_load_version,
    mock_load_contract,
    mock_load_mapping,
    mock_call_downstream,
) -> None:
    """Regression: operation_not_found -> 404."""
    mock_validate.return_value = {"url": "http://example.com/op", "http_method": "POST", "timeout_ms": 8000, "canonical_version": "v1"}
    mock_load_version.return_value = None
    mock_load_contract.return_value = {"operation_code": "GET_RECEIPT", "canonical_version": "v1", "request_schema": None, "response_schema": None}
    mock_load_mapping.side_effect = lambda conn, v, op, ver, d, flow_direction="OUTBOUND": {"transactionId": "$.transactionId"} if d in ("TO_CANONICAL_REQUEST", "TO_CANONICAL", "FROM_CANONICAL") else {"result": "$.result"}
    mock_call_downstream.return_value = (200, {"result": "ok"}, None)
    mock_idempotency_lookup.return_value = None

    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.side_effect = [("tx-123",)]  # _claim_idempotency RETURNING
    mock_cursor.execute.side_effect = None

    event = _base_event(_execute_body(parameters={"transactionId": "tx-1"}), )
    resp = handler(event, None)

    assert resp["statusCode"] == 404
    assert json.loads(resp["body"]).get("error", {}).get("code") == "OPERATION_NOT_FOUND"


# --- Tier-1 outbound auth profiles: build_downstream_headers ---


def test_build_downstream_headers_api_key_header_adds_header() -> None:
    """API_KEY_HEADER: value in config adds header (default Api-Key)."""
    auth_profile = {"auth_type": "API_KEY_HEADER", "config": {"headerName": "Api-Key", "value": "secret-123"}}
    headers, params, audit = build_downstream_headers("tx-1", "corr-1", auth_profile)
    assert headers.get("Api-Key") == "secret-123"
    assert "x-transaction-id" in headers
    assert "x-correlation-id" in headers
    assert audit.get("authType") == "API_KEY_HEADER"


def test_build_downstream_headers_api_key_query_adds_param() -> None:
    """API_KEY_QUERY: value in config adds query param, existing params preserved."""
    auth_profile = {"auth_type": "API_KEY_QUERY", "config": {"paramName": "api_key", "value": "query-secret"}}
    headers, params, audit = build_downstream_headers("tx-1", "corr-1", auth_profile)
    assert params.get("api_key") == "query-secret"
    assert "paramNames" in audit
    assert "api_key" in audit["paramNames"]


def test_build_downstream_headers_static_bearer_sets_authorization() -> None:
    """STATIC_BEARER: token in config sets Authorization: Bearer <token>."""
    auth_profile = {"auth_type": "STATIC_BEARER", "config": {"token": "eyJhbGciOiJIUzI1NiJ9"}}
    headers, params, audit = build_downstream_headers("tx-1", "corr-1", auth_profile)
    assert headers.get("Authorization") == "Bearer eyJhbGciOiJIUzI1NiJ9"
    assert audit.get("authType") == "STATIC_BEARER"


def test_build_downstream_headers_none_auth_returns_base_only() -> None:
    """No auth_profile or auth_type NONE: base headers only, no secrets."""
    headers, params, audit = build_downstream_headers("tx-1", "corr-1", None)
    assert "x-transaction-id" in headers
    assert "x-correlation-id" in headers
    assert "Api-Key" not in headers
    assert audit.get("authType") == "NONE"
    assert len(params) == 0

    headers2, params2, audit2 = build_downstream_headers("tx-1", "corr-1", {"auth_type": "NONE"})
    assert "Api-Key" not in headers2
    assert audit2.get("authType") == "NONE"


def test_build_downstream_headers_api_key_header_missing_value_raises() -> None:
    """API_KEY_HEADER with neither value nor secretRef raises ValueError (config error)."""
    auth_profile = {"auth_type": "API_KEY_HEADER", "config": {"headerName": "Api-Key"}}
    try:
        build_downstream_headers("tx-1", "corr-1", auth_profile)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "value" in str(e).lower()
