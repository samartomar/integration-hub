"""Unit tests for Endpoint Verifier Lambda - endpoint.upserted EventBridge handler."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from endpoint_utils import ResolvedEndpoint  # noqa: E402
from endpoint_verifier_lambda import (  # noqa: E402
    _generate_example_from_schema,
    _verify_endpoint,
    handler,
)


def _endpoint_upserted_event(
    vendor_code: str = "LH001",
    operation_code: str = "GET_RECEIPT",
    url: str = "https://example.com/receipt",
    method: str = "POST",
    format: str = "JSON",
    timeout_ms: int = 8000,
) -> dict:
    """Build EventBridge endpoint.upserted event detail."""
    return {
        "detail": {
            "vendorCode": vendor_code,
            "operationCode": operation_code,
            "url": url,
            "http_method": method,
            "payload_format": format,
            "timeout_ms": timeout_ms,
        }
    }


# --- Schema generator ---


def test_generate_example_from_schema_string() -> None:
    """required string -> 'test'."""
    schema = {
        "type": "object",
        "required": ["transactionId"],
        "properties": {"transactionId": {"type": "string"}},
    }
    assert _generate_example_from_schema(schema) == {"transactionId": "test"}


def test_generate_example_from_schema_number() -> None:
    """required number -> 1."""
    schema = {"required": ["count"], "properties": {"count": {"type": "number"}}}
    assert _generate_example_from_schema(schema) == {"count": 1}


def test_generate_example_from_schema_boolean() -> None:
    """required boolean -> True."""
    schema = {"required": ["active"], "properties": {"active": {"type": "boolean"}}}
    assert _generate_example_from_schema(schema) == {"active": True}


def test_generate_example_from_schema_object() -> None:
    """required object -> {}."""
    schema = {"required": ["meta"], "properties": {"meta": {"type": "object"}}}
    assert _generate_example_from_schema(schema) == {"meta": {}}


def test_generate_example_from_schema_get_receipt() -> None:
    """GET_RECEIPT schema produces transactionId: 'test'."""
    schema = {
        "type": "object",
        "required": ["transactionId"],
        "properties": {"transactionId": {"type": "string", "minLength": 1}},
    }
    assert _generate_example_from_schema(schema) == {"transactionId": "test"}


# --- Handler: 2xx VERIFIED ---


@patch("endpoint_verifier_lambda._make_verification_request")
@patch("endpoint_verifier_lambda._load_operation_contract")
@patch("endpoint_verifier_lambda._get_canonical_version")
@patch("endpoint_verifier_lambda.load_effective_endpoint")
@patch("endpoint_verifier_lambda._get_connection")
def test_verify_2xx_json_marks_verified(
    mock_conn_ctx: MagicMock,
    mock_load_endpoint: MagicMock,
    mock_canonical: MagicMock,
    mock_load_contract: MagicMock,
    mock_http: MagicMock,
) -> None:
    """2xx + parseable JSON -> VERIFIED, audit ENDPOINT_VERIFY_SUCCESS."""
    mock_conn_ctx.return_value.__enter__.return_value = MagicMock()
    mock_load_endpoint.return_value = ResolvedEndpoint(
        vendor_code="LH001",
        operation_code="GET_RECEIPT",
        url="https://example.com/receipt",
        method="POST",
        timeout_ms=8000,
        vendor_auth_profile_id=None,
        payload_format="JSON",
        verification_status="VERIFIED",
        flow_direction="INBOUND",
        source="exact_match",
        matched_direction="INBOUND",
        row_id="ep-uuid-123",
    )
    mock_canonical.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": {
            "required": ["transactionId"],
            "properties": {"transactionId": {"type": "string"}},
        },
    }
    mock_http.return_value = (200, {"result": "ok"}, None)

    event = _endpoint_upserted_event()
    handler(event, None)

    mock_load_endpoint.assert_called_once()
    assert mock_load_endpoint.call_args[0][1] == "LH001"
    assert mock_load_endpoint.call_args[0][2] == "GET_RECEIPT"
    mock_http.assert_called_once()
    assert mock_http.call_args[0][0] == "https://example.com/receipt"
    assert mock_http.call_args[0][1] == "POST"
    assert mock_http.call_args[0][2]["transactionId"] == "test"
    assert mock_http.call_args[0][2]["operation"] == "GET_RECEIPT"
    conn = mock_conn_ctx.return_value.__enter__.return_value
    mock_load_contract.assert_called_once_with(
        conn, "GET_RECEIPT", "v1", vendor_code="LH001", flow_direction="INBOUND"
    )
    cur = conn.cursor.return_value.__enter__.return_value
    update_calls = [c for c in cur.execute.call_args_list if "UPDATE control_plane.vendor_endpoints" in str(c)]
    audit_calls = [c for c in cur.execute.call_args_list if "INSERT INTO data_plane.audit_events" in str(c)]
    assert len(update_calls) == 1
    params = update_calls[0][0][1]
    assert params[0] == "VERIFIED"  # status
    assert len(audit_calls) == 1
    assert "ENDPOINT_VERIFY_SUCCESS" in str(audit_calls[0])


# --- Handler: 4xx/5xx FAILED ---


@patch("endpoint_verifier_lambda._make_verification_request")
@patch("endpoint_verifier_lambda._load_operation_contract")
@patch("endpoint_verifier_lambda._get_canonical_version")
@patch("endpoint_verifier_lambda.load_effective_endpoint")
@patch("endpoint_verifier_lambda._get_connection")
def test_verify_4xx_marks_failed(
    mock_conn_ctx: MagicMock,
    mock_load_endpoint: MagicMock,
    mock_canonical: MagicMock,
    mock_load_contract: MagicMock,
    mock_http: MagicMock,
) -> None:
    """4xx response -> FAILED, audit ENDPOINT_VERIFY_FAILED."""
    mock_conn_ctx.return_value.__enter__.return_value = MagicMock()
    mock_load_endpoint.return_value = ResolvedEndpoint(
        vendor_code="LH001", operation_code="GET_RECEIPT", url="https://example.com/receipt",
        method="POST", timeout_ms=8000, vendor_auth_profile_id=None, payload_format="JSON",
        verification_status="PENDING", flow_direction="INBOUND", source="exact_match",
        matched_direction="INBOUND", row_id="ep-1",
    )
    mock_canonical.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": {"required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}},
    }
    mock_http.return_value = (404, {"error": "Not found"}, "HTTP 404: Not found")

    event = _endpoint_upserted_event()
    handler(event, None)

    conn = mock_conn_ctx.return_value.__enter__.return_value
    cur = conn.cursor.return_value.__enter__.return_value
    update_calls = [c for c in cur.execute.call_args_list if "UPDATE control_plane.vendor_endpoints" in str(c)]
    audit_calls = [c for c in cur.execute.call_args_list if "INSERT INTO data_plane.audit_events" in str(c)]
    assert len(update_calls) == 1
    params = update_calls[0][0][1]
    assert params[0] == "FAILED"
    assert "404" in str(params[2])
    assert len(audit_calls) == 1
    assert "ENDPOINT_VERIFY_FAILED" in str(audit_calls[0])


@patch("endpoint_verifier_lambda._make_verification_request")
@patch("endpoint_verifier_lambda._load_operation_contract")
@patch("endpoint_verifier_lambda._get_canonical_version")
@patch("endpoint_verifier_lambda.load_effective_endpoint")
@patch("endpoint_verifier_lambda._get_connection")
def test_verify_5xx_marks_failed(
    mock_conn_ctx: MagicMock,
    mock_load_endpoint: MagicMock,
    mock_canonical: MagicMock,
    mock_load_contract: MagicMock,
    mock_http: MagicMock,
) -> None:
    """5xx response -> FAILED."""
    mock_conn_ctx.return_value.__enter__.return_value = MagicMock()
    mock_load_endpoint.return_value = ResolvedEndpoint(
        vendor_code="LH001", operation_code="GET_RECEIPT", url="https://example.com/receipt",
        method="POST", timeout_ms=8000, vendor_auth_profile_id=None, payload_format="JSON",
        verification_status="PENDING", flow_direction="INBOUND", source="exact_match",
        matched_direction="INBOUND", row_id="ep-1",
    )
    mock_canonical.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": {"required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}},
    }
    mock_http.return_value = (500, {}, "HTTP 500: Internal Server Error")

    event = _endpoint_upserted_event()
    handler(event, None)

    conn = mock_conn_ctx.return_value.__enter__.return_value
    cur = conn.cursor.return_value.__enter__.return_value
    update_calls = [c for c in cur.execute.call_args_list if "UPDATE control_plane.vendor_endpoints" in str(c)]
    assert update_calls[0][0][1][0] == "FAILED"


# --- Handler: timeout / connection error FAILED ---


@patch("endpoint_verifier_lambda._make_verification_request")
@patch("endpoint_verifier_lambda._load_operation_contract")
@patch("endpoint_verifier_lambda._get_canonical_version")
@patch("endpoint_verifier_lambda.load_effective_endpoint")
@patch("endpoint_verifier_lambda._get_connection")
def test_verify_timeout_marks_failed(
    mock_conn_ctx: MagicMock,
    mock_load_endpoint: MagicMock,
    mock_canonical: MagicMock,
    mock_load_contract: MagicMock,
    mock_http: MagicMock,
) -> None:
    """Timeout -> FAILED with error message."""
    mock_conn_ctx.return_value.__enter__.return_value = MagicMock()
    mock_load_endpoint.return_value = ResolvedEndpoint(
        vendor_code="LH001", operation_code="GET_RECEIPT", url="https://example.com/receipt",
        method="POST", timeout_ms=8000, vendor_auth_profile_id=None, payload_format="JSON",
        verification_status="PENDING", flow_direction="INBOUND", source="exact_match",
        matched_direction="INBOUND", row_id="ep-1",
    )
    mock_canonical.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": {"required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}},
    }
    mock_http.return_value = (-1, "", "Timeout after 8s")

    event = _endpoint_upserted_event()
    handler(event, None)

    conn = mock_conn_ctx.return_value.__enter__.return_value
    cur = conn.cursor.return_value.__enter__.return_value
    update_calls = [c for c in cur.execute.call_args_list if "UPDATE control_plane.vendor_endpoints" in str(c)]
    params = update_calls[0][0][1]
    assert params[0] == "FAILED"
    assert "Timeout" in str(params[2])


@patch("endpoint_verifier_lambda._make_verification_request")
@patch("endpoint_verifier_lambda._load_operation_contract")
@patch("endpoint_verifier_lambda._get_canonical_version")
@patch("endpoint_verifier_lambda.load_effective_endpoint")
@patch("endpoint_verifier_lambda._get_connection")
def test_verify_connection_error_marks_failed(
    mock_conn_ctx: MagicMock,
    mock_load_endpoint: MagicMock,
    mock_canonical: MagicMock,
    mock_load_contract: MagicMock,
    mock_http: MagicMock,
) -> None:
    """Connection error -> FAILED."""
    mock_conn_ctx.return_value.__enter__.return_value = MagicMock()
    mock_load_endpoint.return_value = ResolvedEndpoint(
        vendor_code="LH001", operation_code="GET_RECEIPT", url="https://example.com/receipt",
        method="POST", timeout_ms=8000, vendor_auth_profile_id=None, payload_format="JSON",
        verification_status="PENDING", flow_direction="INBOUND", source="exact_match",
        matched_direction="INBOUND", row_id="ep-1",
    )
    mock_canonical.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": {"required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}},
    }
    mock_http.return_value = (-1, "", "Connection refused")

    event = _endpoint_upserted_event()
    handler(event, None)

    conn = mock_conn_ctx.return_value.__enter__.return_value
    cur = conn.cursor.return_value.__enter__.return_value
    update_calls = [c for c in cur.execute.call_args_list if "UPDATE control_plane.vendor_endpoints" in str(c)]
    assert update_calls[0][0][1][0] == "FAILED"


# --- Handler: non-JSON response FAILED ---


@patch("endpoint_verifier_lambda._make_verification_request")
@patch("endpoint_verifier_lambda._load_operation_contract")
@patch("endpoint_verifier_lambda._get_canonical_version")
@patch("endpoint_verifier_lambda.load_effective_endpoint")
@patch("endpoint_verifier_lambda._get_connection")
def test_verify_2xx_non_json_marks_failed(
    mock_conn_ctx: MagicMock,
    mock_load_endpoint: MagicMock,
    mock_canonical: MagicMock,
    mock_load_contract: MagicMock,
    mock_http: MagicMock,
) -> None:
    """2xx but non-JSON response -> FAILED (not parseable)."""
    mock_conn_ctx.return_value.__enter__.return_value = MagicMock()
    mock_load_endpoint.return_value = ResolvedEndpoint(
        vendor_code="LH001", operation_code="GET_RECEIPT", url="https://example.com/receipt",
        method="POST", timeout_ms=8000, vendor_auth_profile_id=None, payload_format="JSON",
        verification_status="PENDING", flow_direction="INBOUND", source="exact_match",
        matched_direction="INBOUND", row_id="ep-1",
    )
    mock_canonical.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": {"required": ["transactionId"], "properties": {"transactionId": {"type": "string"}}},
    }
    mock_http.return_value = (200, "plain text response", None)

    event = _endpoint_upserted_event()
    handler(event, None)

    conn = mock_conn_ctx.return_value.__enter__.return_value
    cur = conn.cursor.return_value.__enter__.return_value
    update_calls = [c for c in cur.execute.call_args_list if "UPDATE control_plane.vendor_endpoints" in str(c)]
    params = update_calls[0][0][1]
    assert params[0] == "FAILED"
    assert "parseable" in str(params[2]).lower()


# --- Handler: no contract FAILED ---


@patch("endpoint_verifier_lambda._load_operation_contract")
@patch("endpoint_verifier_lambda._get_canonical_version")
@patch("endpoint_verifier_lambda.load_effective_endpoint")
@patch("endpoint_verifier_lambda._get_connection")
def test_verify_no_contract_marks_failed(
    mock_conn_ctx: MagicMock,
    mock_load_endpoint: MagicMock,
    mock_canonical: MagicMock,
    mock_load_contract: MagicMock,
) -> None:
    """No active contract -> FAILED, no HTTP call."""
    mock_conn_ctx.return_value.__enter__.return_value = MagicMock()
    mock_load_endpoint.return_value = ResolvedEndpoint(
        vendor_code="LH001", operation_code="GET_RECEIPT", url="https://example.com/receipt",
        method="POST", timeout_ms=8000, vendor_auth_profile_id=None, payload_format="JSON",
        verification_status="PENDING", flow_direction="INBOUND", source="exact_match",
        matched_direction="INBOUND", row_id="ep-1",
    )
    mock_canonical.return_value = "v1"
    mock_load_contract.return_value = None

    event = _endpoint_upserted_event()
    handler(event, None)

    conn = mock_conn_ctx.return_value.__enter__.return_value
    cur = conn.cursor.return_value.__enter__.return_value
    update_calls = [c for c in cur.execute.call_args_list if "UPDATE control_plane.vendor_endpoints" in str(c)]
    params = update_calls[0][0][1]
    assert params[0] == "FAILED"
    assert "No active contract" in str(params[2])


@patch("endpoint_verifier_lambda._load_operation_contract")
@patch("endpoint_verifier_lambda._get_canonical_version")
@patch("endpoint_verifier_lambda.load_effective_endpoint")
@patch("endpoint_verifier_lambda._get_connection")
def test_verify_contract_empty_schema_marks_failed(
    mock_conn_ctx: MagicMock,
    mock_load_endpoint: MagicMock,
    mock_canonical: MagicMock,
    mock_load_contract: MagicMock,
) -> None:
    """Contract with no request_schema -> FAILED."""
    mock_conn_ctx.return_value.__enter__.return_value = MagicMock()
    mock_load_endpoint.return_value = ResolvedEndpoint(
        vendor_code="LH001", operation_code="GET_RECEIPT", url="https://example.com/receipt",
        method="POST", timeout_ms=8000, vendor_auth_profile_id=None, payload_format="JSON",
        verification_status="PENDING", flow_direction="INBOUND", source="exact_match",
        matched_direction="INBOUND", row_id="ep-1",
    )
    mock_canonical.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": None,
    }

    event = _endpoint_upserted_event()
    handler(event, None)

    conn = mock_conn_ctx.return_value.__enter__.return_value
    cur = conn.cursor.return_value.__enter__.return_value
    update_calls = [c for c in cur.execute.call_args_list if "UPDATE control_plane.vendor_endpoints" in str(c)]
    assert update_calls[0][0][1][0] == "FAILED"


# --- Effective contract: verifier uses vendor_code when available ---


@patch("endpoint_verifier_lambda._make_verification_request")
@patch("endpoint_verifier_lambda._load_operation_contract")
@patch("endpoint_verifier_lambda._get_canonical_version")
@patch("endpoint_verifier_lambda.load_effective_endpoint")
@patch("endpoint_verifier_lambda._get_connection")
def test_verify_uses_effective_contract_with_vendor_code(
    mock_conn_ctx: MagicMock,
    mock_load_endpoint: MagicMock,
    mock_canonical: MagicMock,
    mock_load_contract: MagicMock,
    mock_http: MagicMock,
) -> None:
    """With vendor_code in event, verifier calls load_effective_endpoint and _load_operation_contract (vendor-aware)."""
    mock_conn_ctx.return_value.__enter__.return_value = MagicMock()
    mock_load_endpoint.return_value = ResolvedEndpoint(
        vendor_code="LH001", operation_code="GET_RECEIPT", url="https://example.com/receipt",
        method="POST", timeout_ms=8000, vendor_auth_profile_id=None, payload_format="JSON",
        verification_status="PENDING", flow_direction="INBOUND", source="exact_match",
        matched_direction="INBOUND", row_id="ep-1",
    )
    mock_canonical.return_value = "v1"
    mock_load_contract.return_value = {
        "operation_code": "GET_RECEIPT",
        "canonical_version": "v1",
        "request_schema": {
            "required": ["vendorSpecificField"],
            "properties": {"vendorSpecificField": {"type": "string"}},
        },
    }
    mock_http.return_value = (200, {"result": "ok"}, None)

    event = _endpoint_upserted_event(vendor_code="LH001")
    handler(event, None)

    mock_load_contract.assert_called_once()
    call_pos, call_kw = mock_load_contract.call_args
    assert call_pos[1] == "GET_RECEIPT"
    assert call_pos[2] == "v1"
    assert call_kw.get("vendor_code") == "LH001"
    mock_http.assert_called_once()
    payload = mock_http.call_args[0][2]
    assert payload.get("vendorSpecificField") == "test"
    assert payload.get("operation") == "GET_RECEIPT"


# --- Handler: endpoint not found ---


@patch("endpoint_verifier_lambda._write_audit_event")
@patch("endpoint_verifier_lambda.load_effective_endpoint")
@patch("endpoint_verifier_lambda._get_connection")
def test_verify_endpoint_not_found_audits_and_returns_early(
    mock_conn_ctx: MagicMock,
    mock_load_endpoint: MagicMock,
    mock_audit: MagicMock,
) -> None:
    """When load_effective_endpoint raises EndpointNotFound -> audit ENDPOINT_VERIFY_FAILED, no update."""
    from endpoint_utils import EndpointNotFound

    mock_conn_ctx.return_value.__enter__.return_value = MagicMock()
    mock_load_endpoint.side_effect = EndpointNotFound("No active endpoint for LH001 + GET_RECEIPT")

    event = _endpoint_upserted_event()
    handler(event, None)

    mock_audit.assert_called_once()
    call_args = mock_audit.call_args[0]
    assert call_args[2] == "ENDPOINT_VERIFY_FAILED"
    assert "GET_RECEIPT" in str(call_args[3])


# --- Handler: missing fields early return ---


@patch("endpoint_verifier_lambda.load_effective_endpoint")
@patch("endpoint_verifier_lambda._get_connection")
def test_verify_missing_vendor_or_operation_skips_verification(
    mock_conn_ctx: MagicMock, mock_load_endpoint: MagicMock
) -> None:
    """Missing vendorCode or operationCode -> no DB calls, early return."""
    event = _endpoint_upserted_event()
    event["detail"]["vendorCode"] = ""

    handler(event, None)

    mock_conn_ctx.assert_not_called()
    mock_load_endpoint.assert_not_called()


# --- Integration: requests.request mock ---


@patch("requests.request")
def test_make_verification_request_invokes_requests(mock_request: MagicMock) -> None:
    """_make_verification_request calls requests.request with correct args."""
    from endpoint_verifier_lambda import _make_verification_request

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True}
    mock_resp.text = "{}"
    mock_request.return_value = mock_resp

    status, body, err = _make_verification_request(
        "https://test.example/op",
        "POST",
        {"transactionId": "test", "operation": "GET_RECEIPT"},
        5000,
    )

    assert status == 200
    assert body == {"ok": True}
    assert err is None
    mock_request.assert_called_once()
    call_kw = mock_request.call_args[1]
    assert call_kw["timeout"] == 5
    assert call_kw["json"] == {"transactionId": "test", "operation": "GET_RECEIPT"}
    assert call_kw["headers"]["Content-Type"] == "application/json"
