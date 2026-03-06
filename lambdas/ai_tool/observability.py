"""Shared observability module for Routing, Audit, Registry, AI Tool lambdas."""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Request-scoped context (set by with_observability decorator)
_request_ctx: ContextVar[dict[str, Any] | None] = ContextVar("observability_ctx", default=None)

_METRICS_NAMESPACE = "IntegrationHub/Routing"


def _metrics_dimension_mode() -> str:
    """METRICS_DIMENSION_MODE: LOW=operation only; HIGH=operation+source_vendor+target_vendor."""
    return (os.environ.get("METRICS_DIMENSION_MODE") or "LOW").strip().upper()


def emit_metric(
    metric_name: str,
    value: int | float = 1,
    operation: str = "-",
    source_vendor: str | None = None,
    target_vendor: str | None = None,
) -> None:
    """
    Emit a CloudWatch metric in Embedded Metric Format (EMF).
    Prints a JSON line to stdout which CloudWatch Logs ingests.
    operation is always included; source_vendor and target_vendor only in HIGH mode.
    """
    mode = _metrics_dimension_mode()
    dims: list[str] = ["operation"]
    root: dict[str, Any] = {"operation": operation or "-", metric_name: value}
    if mode == "HIGH":
        dims.extend(["source_vendor", "target_vendor"])
        root["source_vendor"] = source_vendor or "-"
        root["target_vendor"] = target_vendor or "-"
    ts_ms = int(datetime.now(UTC).timestamp() * 1000)
    emf = {
        "_aws": {
            "Timestamp": ts_ms,
            "CloudWatchMetrics": [
                {
                    "Namespace": _METRICS_NAMESPACE,
                    "Dimensions": [dims],
                    "Metrics": [{"Name": metric_name, "Unit": "Count"}],
                }
            ],
        },
        **root,
    }
    line = json.dumps(emf)
    logging.getLogger("observability").info(line)


def get_current_ctx() -> dict[str, Any] | None:
    """Get the current request's observability context (set by decorator)."""
    return _request_ctx.get()

# --- get_context ---


def _get_body_dict(event: dict[str, Any]) -> dict[str, Any]:
    """Extract and parse body from event. Supports HTTP API, Bedrock, direct invoke."""
    raw = event.get("body") or event.get("input") or event.get("requestBody") or event.get("detail") or {}
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw, dict):
        return {}
    # Bedrock: parameters array [{name, value}, ...] -> flatten into body
    params = raw.get("parameters") or raw.get("parameter") or []
    if isinstance(params, list):
        result = dict(raw)
        for p in params:
            if isinstance(p, dict) and "name" in p and "value" in p:
                result[p["name"]] = p["value"]
        return result
    # GET requests (audit): fallback to query params
    if not raw and event.get("queryStringParameters"):
        return dict(event.get("queryStringParameters") or {})
    return raw


def _get_headers(event: dict[str, Any]) -> dict[str, str]:
    """Get normalized headers (lowercase keys)."""
    h = event.get("headers") or {}
    if not isinstance(h, dict):
        return {}
    return {k.lower(): (v if isinstance(v, str) else str(v)) for k, v in h.items()}


def get_context(event: dict[str, Any], context: object) -> dict[str, Any]:
    """
    Extract observability context from event and Lambda context.
    Returns dict with: transaction_id, correlation_id, trace_id, aws_request_id,
    source_vendor, target_vendor, operation, idempotency_key (when present).
    """
    body = _get_body_dict(event)
    headers = _get_headers(event)
    ctx = getattr(context, "aws_request_id", "") or ""

    # transaction_id: body.transactionId or generated
    transaction_id = body.get("transactionId") or body.get("transaction_id")
    if not (transaction_id and isinstance(transaction_id, str) and transaction_id.strip()):
        transaction_id = str(uuid.uuid4())
    else:
        transaction_id = transaction_id.strip()

    # correlation_id: body.correlationId, headers x-correlation-id, or generated
    correlation_id = body.get("correlationId") or body.get("correlation_id")
    if not (correlation_id and isinstance(correlation_id, str) and correlation_id.strip()):
        correlation_id = headers.get("x-correlation-id") or headers.get("x-correlation_id") or ""
    if not (correlation_id and str(correlation_id).strip()):
        correlation_id = str(uuid.uuid4())
    else:
        correlation_id = str(correlation_id).strip()

    # trace_id: X-Ray _X_AMZN_TRACE_ID (format: Root=...;Parent=...;Sampled=1)
    trace_id = os.environ.get("_X_AMZN_TRACE_ID") or ""

    # source_vendor, target_vendor, operation, idempotency_key
    src = body.get("sourceVendor") or body.get("source_vendor") or body.get("vendorCode") or body.get("vendor_code")
    tgt = body.get("targetVendor") or body.get("target_vendor")
    op = body.get("operation") or body.get("operationCode") or body.get("operation_code")
    idem = body.get("idempotencyKey") or body.get("idempotency_key")

    return {
        "transaction_id": transaction_id,
        "correlation_id": correlation_id,
        "trace_id": trace_id,
        "aws_request_id": ctx,
        "source_vendor": str(src).strip() if src else None,
        "target_vendor": str(tgt).strip() if tgt else None,
        "operation": str(op).strip() if op else None,
        "idempotency_key": str(idem).strip() if idem else None,
    }


def get_context_from_parsed(
    event: dict[str, Any],
    context: object,
    *,
    transaction_id: str | None = None,
    correlation_id: str | None = None,
    source_vendor: str | None = None,
    target_vendor: str | None = None,
    operation: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """
    Build context with explicit overrides (e.g. when routing parses body early).
    Missing fields fall back to event/body.
    """
    body = _get_body_dict(event)
    headers = _get_headers(event)

    tx_raw = transaction_id or body.get("transactionId") or body.get("transaction_id")
    tx = (str(tx_raw).strip() if tx_raw else None) or str(uuid.uuid4())

    corr_raw = correlation_id or body.get("correlationId") or body.get("correlation_id") or headers.get("x-correlation-id") or headers.get("x-correlation_id")
    corr = (str(corr_raw).strip() if corr_raw else None) or str(uuid.uuid4())

    trace_id = os.environ.get("_X_AMZN_TRACE_ID") or ""
    aws_request_id = getattr(context, "aws_request_id", "") or ""

    src = source_vendor or (body.get("sourceVendor") or body.get("source_vendor") or body.get("vendorCode") or body.get("vendor_code"))
    tgt = target_vendor or (body.get("targetVendor") or body.get("target_vendor"))
    op = operation or (body.get("operation") or body.get("operationCode") or body.get("operation_code"))
    idem = idempotency_key or (body.get("idempotencyKey") or body.get("idempotency_key"))

    return {
        "transaction_id": tx,
        "correlation_id": corr,
        "trace_id": trace_id,
        "aws_request_id": aws_request_id,
        "source_vendor": str(src).strip() if src else None,
        "target_vendor": str(tgt).strip() if tgt else None,
        "operation": str(op).strip() if op else None,
        "idempotency_key": str(idem).strip() if idem else None,
    }


# --- log_json ---


def log_json(level: str, message: str, ctx: dict[str, Any] | None = None, **fields: Any) -> None:
    """
    Emit a JSON log line with level, message, timestamp, and context/fields.
    Always include transaction_id and correlation_id when present in ctx.
    """
    log = {
        "level": level.upper(),
        "message": message,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if ctx:
        for k in ("transaction_id", "correlation_id", "trace_id", "aws_request_id"):
            if ctx.get(k):
                log[k] = ctx[k]
    for k, v in fields.items():
        if v is not None:
            log[k] = v
    # Use standard logger so CloudWatch picks it up
    line = json.dumps(log, default=str)
    logger = logging.getLogger("observability")
    if level.upper() == "ERROR":
        logger.error(line)
    elif level.upper() == "WARN":
        logger.warning(line)
    elif level.upper() == "DEBUG":
        logger.debug(line)
    else:
        logger.info(line)


# --- Decorator / wrapper for START/END with duration ---


def with_observability(
    handler_fn: Any,
    lambda_name: str,
) -> Any:
    """
    Wrap a Lambda handler to log START/END with duration.
    """
    def wrapped(event: dict[str, Any], context: object) -> Any:
        import time
        start = time.perf_counter()
        ctx = get_context(event, context)
        _request_ctx.set(ctx)
        log_json("INFO", "START", ctx=ctx, lambda_name=lambda_name)
        try:
            result = handler_fn(event, context)
            dur_ms = (time.perf_counter() - start) * 1000
            log_json("INFO", "END", ctx=ctx, lambda_name=lambda_name, duration_ms=round(dur_ms, 2))
            return result
        except Exception as e:
            dur_ms = (time.perf_counter() - start) * 1000
            log_json("ERROR", "END", ctx=ctx, lambda_name=lambda_name, duration_ms=round(dur_ms, 2), error=str(e))
            raise
        finally:
            _request_ctx.set(None)
    return wrapped
