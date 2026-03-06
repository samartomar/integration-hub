"""Integration router Lambda handler - thin orchestration layer."""

from __future__ import annotations

from typing import Any

from allowlist import enforce_allowlist
from config import load_vendor_config
from downstream import invoke_downstream
from envelope import build_canonical_envelope
from idempotency import check_idempotency
from response import build_error_response, build_response, generate_ids
from timeout import ensure_sufficient_time
from transaction import log_transaction
from validation import validate_request


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """
    Handle API Gateway proxy integration requests.

    Orchestrates layers: validate -> config -> allowlist -> idempotency ->
    envelope -> downstream -> log -> response. Returns canonical error on failure.
    """
    transaction_id, correlation_id = generate_ids()

    def _err(status_code: int, code: str, msg: str, details: dict[str, Any] | None = None):
        return build_error_response(
            status_code=status_code,
            error_code=code,
            message=msg,
            details=details,
            transaction_id=transaction_id,
            correlation_id=correlation_id,
        )

    try:
        validated = validate_request(event)
    except ValueError as e:
        return _err(400, "VALIDATION_ERROR", str(e))

    source = validated["source_vendor"]
    target = validated["target_vendor"]
    operation = validated["operation"]
    idempotency_key = validated["idempotency_key"]
    request_type = validated["request_type"]
    callback_url = validated["callback_url"]

    try:
        load_vendor_config(source, target, operation)
        try:
            enforce_allowlist(source, target, operation)
        except ValueError as e:
            return _err(403, "ALLOWLIST_VIOLATION", str(e))
        try:
            check_idempotency(idempotency_key)
        except ValueError as e:
            return _err(409, "IDEMPOTENCY_CONFLICT", str(e))

        envelope = build_canonical_envelope(
            source, target, operation, correlation_id,
            idempotency_key=idempotency_key,
            request_type=request_type,
            callback_url=callback_url,
        )
        ensure_sufficient_time(context)
        try:
            downstream_response = invoke_downstream(envelope)
        except Exception as e:
            return _err(502, "DOWNSTREAM_ERROR", str(e), details={"type": type(e).__name__})
        log_transaction(transaction_id, correlation_id, envelope, downstream_response)
        return build_response(transaction_id, correlation_id, envelope, downstream_response)
    except TimeoutError as e:
        return _err(504, "TIMEOUT", str(e))
    except Exception as e:
        return _err(500, "INTERNAL_ERROR", str(e), details={"type": type(e).__name__})
