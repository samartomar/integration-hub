"""Unit tests for canonical error taxonomy - httpStatus, code, category, retryable, violations."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from canonical_error import (  # noqa: E402
    ErrorCategory,
    ErrorCode,
    allowlist_denied,
    auth_error,
    build_error,
    build_error_envelope,
    contract_not_found,
    db_error,
    downstream_connection_error,
    downstream_http_error,
    downstream_http_error_response_body,
    downstream_invalid_response,
    downstream_timeout,
    endpoint_not_found,
    endpoint_not_verified,
    forbidden,
    idempotency_conflict,
    in_flight,
    internal_error,
    invalid_json,
    mapping_failed,
    mapping_not_found,
    missing_field,
    operation_not_found,
    redrive_not_found,
    schema_validation_failed,
    to_response_body,
)


def _assert_taxonomy(
    err: dict,
    *,
    code: str,
    http_status: int,
    category: str,
    retryable: bool = False,
    has_violations: bool = False,
) -> None:
    """Assert core taxonomy fields."""
    assert err["code"] == code
    assert err["http_status"] == http_status
    assert err["category"] == category
    assert err["retryable"] is retryable
    if has_violations:
        assert "violations" in err or (err.get("details") or {}).get("violations") is not None


def test_invalid_json() -> None:
    e = invalid_json("Invalid JSON body")
    _assert_taxonomy(e, code="INVALID_JSON", http_status=400, category="VALIDATION")
    assert "requestBodyRaw" not in (e.get("details") or {})

    e2 = invalid_json("Invalid JSON", request_body_raw="bad {")
    assert e2["details"]["requestBodyRaw"] == "bad {"


def test_schema_validation_failed() -> None:
    violations = ["Missing required field 'x'", "Invalid type at path y"]
    e = schema_validation_failed("Schema validation failed", violations)
    _assert_taxonomy(e, code="SCHEMA_VALIDATION_FAILED", http_status=400, category="VALIDATION", has_violations=True)
    assert e["violations"] == violations

    e2 = schema_validation_failed("Stage failed", ["v1"], stage="canonical")
    assert e2["details"]["stage"] == "CANONICAL_REQUEST"
    assert e2["violations"] == ["v1"]


def test_mapping_not_found() -> None:
    e = mapping_not_found("Missing mapping TO_CANONICAL")
    _assert_taxonomy(e, code="MAPPING_NOT_FOUND", http_status=409, category="MAPPING")
    assert e.get("details", {}).get("direction") is None

    e2 = mapping_not_found("Missing mapping", direction="TO_CANONICAL")
    assert e2["details"]["direction"] == "TO_CANONICAL"


def test_mapping_failed() -> None:
    violations = ["Path 'a.b' not found", "Path 'c' type mismatch"]
    e = mapping_failed("Mapping violations", violations)
    _assert_taxonomy(e, code="MAPPING_FAILED", http_status=422, category="MAPPING", has_violations=True)
    assert e["details"]["violations"] == violations


def test_downstream_http_error() -> None:
    e = downstream_http_error(404, {"error": "Not found"})
    _assert_taxonomy(e, code="DOWNSTREAM_HTTP_ERROR", http_status=502, category="DOWNSTREAM")
    assert e["details"]["vendorStatusCode"] == 404
    assert e["details"]["vendorBody"] == {"error": "Not found"}

    e2 = downstream_http_error(500, "Server error", message="Custom message")
    assert e2["message"] == "Custom message"


def test_downstream_timeout() -> None:
    e = downstream_timeout()
    _assert_taxonomy(e, code="DOWNSTREAM_TIMEOUT", http_status=504, category="DOWNSTREAM", retryable=True)
    assert e["details"]["statusCode"] == 504


def test_downstream_connection_error() -> None:
    e = downstream_connection_error("Connection refused", exc_type="ConnectionError")
    _assert_taxonomy(e, code="DOWNSTREAM_CONNECTION_ERROR", http_status=502, category="DOWNSTREAM", retryable=True)
    assert e["details"]["type"] == "ConnectionError"


def test_downstream_invalid_response() -> None:
    e = downstream_invalid_response(raw="<html>...</html>")
    _assert_taxonomy(e, code="DOWNSTREAM_INVALID_RESPONSE", http_status=502, category="DOWNSTREAM")
    assert e["details"]["raw"] == "<html>...</html>"


def test_operation_not_found() -> None:
    e = operation_not_found()
    _assert_taxonomy(e, code="OPERATION_NOT_FOUND", http_status=404, category="NOT_FOUND")


def test_contract_not_found() -> None:
    e = contract_not_found("No active contract for target vendor")
    _assert_taxonomy(e, code="CONTRACT_NOT_FOUND", http_status=409, category="NOT_FOUND")


def test_allowlist_denied() -> None:
    e = allowlist_denied("Allowlist does not permit this operation")
    _assert_taxonomy(e, code="ALLOWLIST_DENIED", http_status=403, category="POLICY")


def test_endpoint_not_verified() -> None:
    e = endpoint_not_verified("Endpoint not verified for this vendor")
    _assert_taxonomy(e, code="ENDPOINT_NOT_VERIFIED", http_status=412, category="VALIDATION")


def test_auth_error() -> None:
    e = auth_error("Missing or invalid API key")
    _assert_taxonomy(e, code="AUTH_ERROR", http_status=401, category="AUTH")


def test_forbidden() -> None:
    e = forbidden("Access denied for vendor")
    _assert_taxonomy(e, code="FORBIDDEN", http_status=403, category="AUTH")


def test_db_error() -> None:
    e = db_error("Database connection failed", exc_type="ConnectionError")
    _assert_taxonomy(e, code="DB_ERROR", http_status=503, category="PLATFORM", retryable=True)
    assert e["details"]["type"] == "ConnectionError"


def test_internal_error() -> None:
    e = internal_error("Unexpected error", exc_type="ValueError")
    _assert_taxonomy(e, code="INTERNAL_ERROR", http_status=500, category="PLATFORM")
    assert "errorId" in e["details"]
    assert e["details"]["type"] == "ValueError"


def test_build_error_with_violations() -> None:
    violations = [{"path": "a", "message": "required"}]
    e = build_error(ErrorCode.SCHEMA_VALIDATION_FAILED, "Validation failed", violations=violations)
    _assert_taxonomy(e, code="SCHEMA_VALIDATION_FAILED", http_status=400, category="VALIDATION", has_violations=True)
    assert e["details"]["violations"] == violations  # build_error puts violations in details


def test_to_response_body_includes_category_retryable() -> None:
    e = downstream_timeout()
    body = to_response_body(e)
    assert body["error"]["code"] == "DOWNSTREAM_TIMEOUT"
    assert body["error"]["category"] == "DOWNSTREAM"
    assert body["error"]["retryable"] is True
    assert "details" in body["error"]


def test_build_error_envelope() -> None:
    """build_error_envelope produces full API envelope with transactionId, correlationId, error."""
    env = build_error_envelope(
        "tx-123",
        "corr-456",
        "MAPPING_FAILED",
        "Path not found",
        400,
        ErrorCategory.MAPPING,
        False,
        details={"stage": "request"},
        violations=["$.x missing"],
    )
    assert env["transactionId"] == "tx-123"
    assert env["correlationId"] == "corr-456"
    assert env["error"]["code"] == "MAPPING_FAILED"
    assert env["error"]["message"] == "Path not found"
    assert env["error"]["category"] == "MAPPING"
    assert env["error"]["retryable"] is False
    assert env["error"]["details"]["stage"] == "request"
    assert env["error"]["details"]["violations"] == ["$.x missing"]


def test_to_response_body_with_violations() -> None:
    e = mapping_failed("Failed", ["v1", "v2"])
    body = to_response_body(e)
    assert body["error"]["details"]["violations"] == ["v1", "v2"]  # mapping_failed uses details.violations

    e2 = schema_validation_failed("Schema failed", ["v1"], stage="target")
    body2 = to_response_body(e2)
    assert body2["error"]["violations"] == ["v1"]
    assert body2["error"]["details"]["stage"] == "TARGET_REQUEST"


def test_missing_field() -> None:
    e = missing_field("transactionId is required", field="transactionId")
    _assert_taxonomy(e, code="MISSING_FIELD", http_status=400, category="VALIDATION")
    assert e["details"]["field"] == "transactionId"


def test_endpoint_not_found() -> None:
    e = endpoint_not_found("Endpoint not found for operation")
    _assert_taxonomy(e, code="ENDPOINT_NOT_FOUND", http_status=404, category="NOT_FOUND")


def test_idempotency_conflict() -> None:
    e = idempotency_conflict("Duplicate request with same idempotency key")
    _assert_taxonomy(e, code="IDEMPOTENCY_CONFLICT", http_status=409, category="CONFLICT")


def test_in_flight() -> None:
    """in_flight(transaction_id) -> IN_FLIGHT, 409, CONFLICT, retryable=true, details.transactionId."""
    e = in_flight("tx-abc-123")
    _assert_taxonomy(e, code="IN_FLIGHT", http_status=409, category="CONFLICT", retryable=True)
    assert e["message"] == "Request is still in progress"
    assert e["details"]["transactionId"] == "tx-abc-123"


def test_to_response_body_includes_details_for_in_flight() -> None:
    """to_response_body includes error.details when present (e.g. in_flight)."""
    e = in_flight("tx-xyz-789")
    body = to_response_body(e)
    assert body["error"]["code"] == "IN_FLIGHT"
    assert body["error"]["category"] == "CONFLICT"
    assert body["error"]["retryable"] is True
    assert "details" in body["error"]
    assert body["error"]["details"]["transactionId"] == "tx-xyz-789"


def test_redrive_not_found() -> None:
    e = redrive_not_found("Transaction tx-123 not found")
    _assert_taxonomy(e, code="REDRIVE_NOT_FOUND", http_status=404, category="NOT_FOUND")


def test_downstream_http_error_response_body() -> None:
    """downstream_http_error_response_body produces storage format with error + details (vendorCode, operation)."""
    body = downstream_http_error_response_body(404, {"error": "Not found"}, vendor_code="LH002", operation="GET_RECEIPT")
    assert "error" in body
    assert body["error"]["code"] == "DOWNSTREAM_HTTP_ERROR"
    assert body["error"]["message"]
    assert "details" in body
    assert body["details"]["vendorStatusCode"] == 404
    assert body["details"]["vendorBody"] == {"error": "Not found"}
    assert body["details"]["vendorCode"] == "LH002"
    assert body["details"]["operation"] == "GET_RECEIPT"
