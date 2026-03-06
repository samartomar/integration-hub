"""Canonical error taxonomy for Integration Hub.

Shared module imported by routing_lambda, registry_lambda, audit_lambda,
vendor_registry_lambda, and ai_tool. Sync to lambdas/ai_tool in buildspec.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    """Canonical error categories."""

    VALIDATION = "VALIDATION"
    POLICY = "POLICY"
    MAPPING = "MAPPING"
    DOWNSTREAM = "DOWNSTREAM"
    PLATFORM = "PLATFORM"
    AUTH = "AUTH"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMIT = "RATE_LIMIT"


class ErrorCode(StrEnum):
    """Canonical error codes."""

    # Validation / configuration
    INVALID_JSON = "INVALID_JSON"
    MISSING_FIELD = "MISSING_FIELD"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    VENDOR_NOT_FOUND = "VENDOR_NOT_FOUND"
    OPERATION_NOT_FOUND = "OPERATION_NOT_FOUND"
    ENDPOINT_NOT_FOUND = "ENDPOINT_NOT_FOUND"
    ENDPOINT_NOT_VERIFIED = "ENDPOINT_NOT_VERIFIED"
    CONTRACT_NOT_FOUND = "CONTRACT_NOT_FOUND"
    MAPPING_NOT_FOUND = "MAPPING_NOT_FOUND"
    MAPPING_FAILED = "MAPPING_FAILED"
    ALLOWLIST_DENIED = "ALLOWLIST_DENIED"
    ALLOWLIST_VENDOR_DENIED = "ALLOWLIST_VENDOR_DENIED"

    # Downstream
    DOWNSTREAM_HTTP_ERROR = "DOWNSTREAM_HTTP_ERROR"
    DOWNSTREAM_TIMEOUT = "DOWNSTREAM_TIMEOUT"
    DOWNSTREAM_CONNECTION_ERROR = "DOWNSTREAM_CONNECTION_ERROR"

    # Platform / system
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"

    # Conflict / not found
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    IN_FLIGHT = "IN_FLIGHT"
    REDRIVE_NOT_FOUND = "REDRIVE_NOT_FOUND"

    # Auth
    AUTH_ERROR = "AUTH_ERROR"
    FORBIDDEN = "FORBIDDEN"

    # Legacy / aliases
    DB_ERROR = "DB_ERROR"
    NOT_FOUND = "NOT_FOUND"
    DOWNSTREAM_INVALID_RESPONSE = "DOWNSTREAM_INVALID_RESPONSE"


_ERROR_CATEGORY: dict[ErrorCode, ErrorCategory] = {
    ErrorCode.INVALID_JSON: ErrorCategory.VALIDATION,
    ErrorCode.MISSING_FIELD: ErrorCategory.VALIDATION,
    ErrorCode.SCHEMA_VALIDATION_FAILED: ErrorCategory.VALIDATION,
    ErrorCode.VENDOR_NOT_FOUND: ErrorCategory.NOT_FOUND,
    ErrorCode.OPERATION_NOT_FOUND: ErrorCategory.NOT_FOUND,
    ErrorCode.ENDPOINT_NOT_FOUND: ErrorCategory.NOT_FOUND,
    ErrorCode.ENDPOINT_NOT_VERIFIED: ErrorCategory.VALIDATION,
    ErrorCode.CONTRACT_NOT_FOUND: ErrorCategory.NOT_FOUND,
    ErrorCode.MAPPING_NOT_FOUND: ErrorCategory.MAPPING,
    ErrorCode.MAPPING_FAILED: ErrorCategory.MAPPING,
    ErrorCode.ALLOWLIST_DENIED: ErrorCategory.POLICY,
    ErrorCode.ALLOWLIST_VENDOR_DENIED: ErrorCategory.POLICY,
    ErrorCode.DOWNSTREAM_HTTP_ERROR: ErrorCategory.DOWNSTREAM,
    ErrorCode.DOWNSTREAM_TIMEOUT: ErrorCategory.DOWNSTREAM,
    ErrorCode.DOWNSTREAM_CONNECTION_ERROR: ErrorCategory.DOWNSTREAM,
    ErrorCode.INTERNAL_ERROR: ErrorCategory.PLATFORM,
    ErrorCode.DEPENDENCY_ERROR: ErrorCategory.PLATFORM,
    ErrorCode.IDEMPOTENCY_CONFLICT: ErrorCategory.CONFLICT,
    ErrorCode.IN_FLIGHT: ErrorCategory.CONFLICT,
    ErrorCode.REDRIVE_NOT_FOUND: ErrorCategory.NOT_FOUND,
    ErrorCode.AUTH_ERROR: ErrorCategory.AUTH,
    ErrorCode.FORBIDDEN: ErrorCategory.AUTH,
    ErrorCode.DB_ERROR: ErrorCategory.PLATFORM,
    ErrorCode.NOT_FOUND: ErrorCategory.NOT_FOUND,
    ErrorCode.DOWNSTREAM_INVALID_RESPONSE: ErrorCategory.DOWNSTREAM,
}

_RETRYABLE: dict[ErrorCode, bool] = {
    ErrorCode.DOWNSTREAM_TIMEOUT: True,
    ErrorCode.DOWNSTREAM_CONNECTION_ERROR: True,
    ErrorCode.DB_ERROR: True,
    ErrorCode.DEPENDENCY_ERROR: True,
    ErrorCode.IN_FLIGHT: True,
}


def build_error_envelope(
    transaction_id: str,
    correlation_id: str,
    code: str,
    message: str,
    http_status: int,
    category: ErrorCategory | str,
    retryable: bool,
    details: dict[str, Any] | None = None,
    violations: list[str] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build full API error envelope: {transactionId, correlationId, error: {code, message, category, retryable, details?}}.
    Used by routing, registry, audit, ai_tool lambdas for consistent error responses.
    Envelope shape matches existing API: transactionId/correlationId at top level.
    """
    cat_str = category.value if isinstance(category, ErrorCategory) else str(category)
    err_obj: dict[str, Any] = {
        "code": code,
        "message": message,
        "category": cat_str,
        "retryable": retryable,
    }
    if details:
        err_obj["details"] = dict(details)
    if violations is not None:
        err_obj.setdefault("details", {})["violations"] = violations
    return {
        "transactionId": transaction_id,
        "correlationId": correlation_id,
        "error": err_obj,
    }


def build_error(
    code: ErrorCode | str,
    message: str,
    http_status: int = 400,
    details: dict[str, Any] | None = None,
    violations: list[str] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build canonical error payload.
    Returns dict with code, message, category, retryable, details?, http_status.
    """
    code_str = code.value if isinstance(code, ErrorCode) else str(code)
    try:
        ec = ErrorCode(code_str)
        category = _ERROR_CATEGORY.get(ec, ErrorCategory.PLATFORM)
        retryable = _RETRYABLE.get(ec, False)
    except ValueError:
        category = ErrorCategory.PLATFORM
        retryable = False

    cat_str = category.value if isinstance(category, ErrorCategory) else str(category)
    err: dict[str, Any] = {
        "code": code_str,
        "message": message,
        "category": cat_str,
        "retryable": retryable,
        "http_status": http_status,
    }
    if details:
        err["details"] = {**details}
    if violations is not None:
        err.setdefault("details", {})["violations"] = violations
    return err


def invalid_json(message: str, request_body_raw: str | None = None) -> dict[str, Any]:
    return build_error(
        ErrorCode.INVALID_JSON,
        message,
        http_status=400,
        details={"requestBodyRaw": request_body_raw[:500]} if request_body_raw else None,
    )


# Normalized stage values for schema validation
SchemaStage = str  # CANONICAL_REQUEST | TARGET_REQUEST | CANONICAL_RESPONSE
_STAGE_MAP: dict[str, str] = {
    "source": "CANONICAL_REQUEST",
    "canonical": "CANONICAL_REQUEST",
    "target": "TARGET_REQUEST",
    "target_response": "CANONICAL_RESPONSE",
    "canonical_response": "CANONICAL_RESPONSE",
}


def _normalize_schema_stage(stage: str | None) -> str | None:
    """Map internal stage names to canonical: CANONICAL_REQUEST, TARGET_REQUEST, CANONICAL_RESPONSE."""
    if not stage:
        return None
    return _STAGE_MAP.get(stage.lower() if isinstance(stage, str) else "", stage.upper())


def schema_validation_failed(
    message: str,
    violations: list[str],
    stage: str | None = None,
) -> dict[str, Any]:
    """Build SCHEMA_VALIDATION_FAILED error. Violations at error.violations, stage in details.stage."""
    details: dict[str, Any] = {}
    norm_stage = _normalize_schema_stage(stage)
    if norm_stage:
        details["stage"] = norm_stage
    err = build_error(
        ErrorCode.SCHEMA_VALIDATION_FAILED,
        message,
        http_status=400,
        details=details if details else None,
        violations=None,  # we put violations at top level, not in details
    )
    err["violations"] = violations
    return err


def mapping_not_found(
    message: str,
    direction: str | None = None,
    violations: list[str] | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] | None = {"direction": direction} if direction else None
    if details is None and violations is not None:
        details = {}
    if details is not None and violations is not None:
        details["violations"] = violations
    return build_error(ErrorCode.MAPPING_NOT_FOUND, message, http_status=409, details=details)


def mapping_failed(
    message: str,
    violations: list[str],
    direction: str | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {"direction": direction} if direction else None
    return build_error(ErrorCode.MAPPING_FAILED, message, http_status=422, violations=violations, details=details)


def downstream_http_error(status_code: int, body: Any, message: str | None = None) -> dict[str, Any]:
    """Build error for downstream non-2xx. details include vendorStatusCode and vendorBody for persistence."""
    msg = message or f"Downstream returned {status_code}"
    return build_error(
        ErrorCode.DOWNSTREAM_HTTP_ERROR,
        msg,
        http_status=502,
        details={"vendorStatusCode": status_code, "vendorBody": body},
    )


def downstream_http_error_response_body(
    status_code: int,
    body: Any,
    vendor_code: str | None = None,
    operation: str | None = None,
) -> dict[str, Any]:
    """Build response_body for storage when downstream returns 4xx/5xx.
    Format: { error: { code, message, category, retryable }, details: { vendorStatusCode, vendorBody, vendorCode?, operation? } }.
    """
    err = downstream_http_error(status_code, body)
    details: dict[str, Any] = {"vendorStatusCode": status_code, "vendorBody": body}
    if vendor_code is not None:
        details["vendorCode"] = vendor_code
    if operation is not None:
        details["operation"] = operation
    return {
        "error": {
            "code": err["code"],
            "message": err["message"],
            "category": err.get("category"),
            "retryable": err.get("retryable", False),
        },
        "details": details,
    }


def downstream_timeout(message: str = "Downstream request timed out") -> dict[str, Any]:
    return build_error(ErrorCode.DOWNSTREAM_TIMEOUT, message, http_status=504, details={"statusCode": 504})


def downstream_invalid_response(message: str = "Downstream returned non-JSON response", raw: str | None = None) -> dict[str, Any]:
    details = {"raw": raw[:500]} if raw else None
    return build_error(ErrorCode.DOWNSTREAM_INVALID_RESPONSE, message, http_status=502, details=details)


def downstream_connection_error(message: str, exc_type: str | None = None) -> dict[str, Any]:
    details = {"type": exc_type} if exc_type else None
    return build_error(ErrorCode.DOWNSTREAM_CONNECTION_ERROR, message, http_status=502, details=details)


def db_error(message: str, exc_type: str | None = None) -> dict[str, Any]:
    details = {"type": exc_type} if exc_type else None
    return build_error(ErrorCode.DB_ERROR, message, http_status=503, details=details)


def internal_error(message: str, error_id: str | None = None, exc_type: str | None = None) -> dict[str, Any]:
    eid = error_id or str(uuid.uuid4())
    details: dict[str, Any] = {"errorId": eid}
    if exc_type:
        details["type"] = exc_type
    return build_error(ErrorCode.INTERNAL_ERROR, message, http_status=500, details=details)


def vendor_not_found(message: str) -> dict[str, Any]:
    return build_error(ErrorCode.VENDOR_NOT_FOUND, message, http_status=404)


def operation_not_found(message: str = "Operation not found or inactive") -> dict[str, Any]:
    return build_error(ErrorCode.OPERATION_NOT_FOUND, message, http_status=404)


def contract_not_found(message: str) -> dict[str, Any]:
    return build_error(ErrorCode.CONTRACT_NOT_FOUND, message, http_status=409)


def allowlist_denied(message: str) -> dict[str, Any]:
    return build_error(ErrorCode.ALLOWLIST_DENIED, message, http_status=403)


def allowlist_vendor_denied(message: str) -> dict[str, Any]:
    """Provider narrowed access; caller not in vendor whitelist. 403."""
    return build_error(ErrorCode.ALLOWLIST_VENDOR_DENIED, message, http_status=403)


def endpoint_not_verified(message: str) -> dict[str, Any]:
    return build_error(ErrorCode.ENDPOINT_NOT_VERIFIED, message, http_status=412)


def auth_error(message: str) -> dict[str, Any]:
    return build_error(ErrorCode.AUTH_ERROR, message, http_status=401)


def forbidden(message: str) -> dict[str, Any]:
    return build_error(ErrorCode.FORBIDDEN, message, http_status=403)


def missing_field(message: str, field: str | None = None) -> dict[str, Any]:
    """Build error for missing required field."""
    details = {"field": field} if field else None
    return build_error(ErrorCode.MISSING_FIELD, message, http_status=400, details=details)


def endpoint_not_found(message: str = "Endpoint not found") -> dict[str, Any]:
    return build_error(ErrorCode.ENDPOINT_NOT_FOUND, message, http_status=404)


def idempotency_conflict(message: str = "Duplicate idempotency key") -> dict[str, Any]:
    return build_error(ErrorCode.IDEMPOTENCY_CONFLICT, message, http_status=409)


def in_flight(transaction_id: str) -> dict[str, Any]:
    """Build IN_FLIGHT error (HTTP 409). code=IN_FLIGHT, category=CONFLICT, retryable=true, details.transactionId."""
    return build_error(
        ErrorCode.IN_FLIGHT,
        "Request is still in progress",
        http_status=409,
        details={"transactionId": transaction_id},
    )


def in_flight_error(
    message: str = "Request is still in progress",
    transaction_id: str | None = None,
    status: str = "received",
) -> dict[str, Any]:
    """Build IN_FLIGHT error (HTTP 409) when idempotent request is still processing."""
    details: dict[str, Any] = {}
    if transaction_id is not None:
        details["transactionId"] = transaction_id
    details["status"] = status
    return build_error(ErrorCode.IN_FLIGHT, message, http_status=409, details=details)


def redrive_not_found(message: str = "Transaction not found for redrive") -> dict[str, Any]:
    return build_error(ErrorCode.REDRIVE_NOT_FOUND, message, http_status=404)


def dependency_error(message: str, service: str | None = None) -> dict[str, Any]:
    details = {"service": service} if service else None
    return build_error(ErrorCode.DEPENDENCY_ERROR, message, http_status=503, details=details)


def _http_status_from_error(err: dict[str, Any]) -> int:
    """Map error code to HTTP status if not in err."""
    code = err.get("code", "")
    status_map = {
        "AUTH_ERROR": 401,
        "FORBIDDEN": 403,
        "NOT_FOUND": 404,
        "ENDPOINT_NOT_FOUND": 404,
        "REDRIVE_NOT_FOUND": 404,
        "ALLOWLIST_DENIED": 403,
        "ALLOWLIST_VENDOR_DENIED": 403,
        "ENDPOINT_NOT_VERIFIED": 412,
        "IDEMPOTENCY_CONFLICT": 409,
        "IN_FLIGHT": 409,
        "DOWNSTREAM_TIMEOUT": 504,
        "DB_ERROR": 503,
        "DEPENDENCY_ERROR": 503,
    }
    return status_map.get(code, 400)


def to_response_body(err: dict[str, Any]) -> dict[str, Any]:
    """Convert error dict to response format: {error: {code, message, category?, retryable?, violations?, details?}}.
    Violations at error.violations (top-level envelope); details.stage for schema errors."""
    out: dict[str, Any] = {"error": {"code": err["code"], "message": err["message"]}}
    if err.get("category"):
        out["error"]["category"] = err["category"]
    if "retryable" in err:
        out["error"]["retryable"] = err["retryable"]
    if err.get("violations") is not None:
        out["error"]["violations"] = err["violations"]
    if err.get("details"):
        out["error"]["details"] = err["details"]
    return out


def to_pipeline_err(err: dict[str, Any]) -> dict[str, Any]:
    """Convert to pipeline_err format: {code, message, details?}."""
    out: dict[str, Any] = {"code": err["code"], "message": err["message"]}
    if err.get("details"):
        out["details"] = err["details"]
    return out
