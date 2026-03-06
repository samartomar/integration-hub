"""Unit tests for observability module - EMF metrics."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from observability import emit_metric  # noqa: E402


def _capture_emit(fn):
    """Run fn and return the first JSON log line from the observability logger."""
    log_lines = []

    def _handler(msg, *args, **kwargs):
        log_lines.append(msg if isinstance(msg, str) else str(msg))

    logger = __import__("logging").getLogger("observability")
    with patch.object(logger, "info", side_effect=_handler):
        fn()
    return log_lines[0] if log_lines else None


def _parse_emf(line: str) -> dict:
    """Parse EMF JSON and return the dict."""
    return json.loads(line)


def test_emit_metric_produces_valid_emf_json() -> None:
    """emit_metric produces valid JSON parseable as EMF."""
    line = _capture_emit(lambda: emit_metric("ExecuteSuccess", operation="GET_RECEIPT"))
    assert line is not None
    obj = _parse_emf(line)
    assert "_aws" in obj
    assert "CloudWatchMetrics" in obj["_aws"]
    assert obj["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "IntegrationHub/Routing"
    assert obj["_aws"]["CloudWatchMetrics"][0]["Metrics"][0]["Name"] == "ExecuteSuccess"
    assert obj["_aws"]["CloudWatchMetrics"][0]["Metrics"][0]["Unit"] == "Count"
    assert obj["ExecuteSuccess"] == 1
    assert obj["operation"] == "GET_RECEIPT"


def test_emit_metric_low_dimension_mode() -> None:
    """METRICS_DIMENSION_MODE=LOW emits only operation dimension."""
    with patch.dict("os.environ", {"METRICS_DIMENSION_MODE": "LOW"}, clear=False):
        line = _capture_emit(
            lambda: emit_metric("DownstreamError", operation="GET_RECEIPT", source_vendor="LH001", target_vendor="LH002")
        )
    obj = _parse_emf(line)
    dims = obj["_aws"]["CloudWatchMetrics"][0]["Dimensions"][0]
    assert dims == ["operation"]
    assert "operation" in obj
    assert "source_vendor" not in obj or obj.get("source_vendor") is None
    assert "target_vendor" not in obj or obj.get("target_vendor") is None


def test_emit_metric_high_dimension_mode() -> None:
    """METRICS_DIMENSION_MODE=HIGH emits operation + source_vendor + target_vendor."""
    with patch.dict("os.environ", {"METRICS_DIMENSION_MODE": "HIGH"}, clear=False):
        line = _capture_emit(
            lambda: emit_metric("Replay", operation="GET_RECEIPT", source_vendor="LH001", target_vendor="LH002")
        )
    obj = _parse_emf(line)
    dims = obj["_aws"]["CloudWatchMetrics"][0]["Dimensions"][0]
    assert "operation" in dims
    assert "source_vendor" in dims
    assert "target_vendor" in dims
    assert obj["operation"] == "GET_RECEIPT"
    assert obj["source_vendor"] == "LH001"
    assert obj["target_vendor"] == "LH002"
    assert obj["Replay"] == 1


def test_emit_metric_default_dimension_mode_is_low() -> None:
    """Default (no env) uses LOW dimension mode."""
    with patch.dict("os.environ", {}, clear=False):
        if "METRICS_DIMENSION_MODE" in __import__("os").environ:
            del __import__("os").environ["METRICS_DIMENSION_MODE"]
    line = _capture_emit(lambda: emit_metric("ExecuteAuthFailed", operation="-"))
    obj = _parse_emf(line)
    dims = obj["_aws"]["CloudWatchMetrics"][0]["Dimensions"][0]
    assert dims == ["operation"]


def test_emit_metric_custom_value() -> None:
    """emit_metric accepts custom value."""
    line = _capture_emit(lambda: emit_metric("ExecuteSuccess", value=5, operation="SEND_INVOICE"))
    obj = _parse_emf(line)
    assert obj["ExecuteSuccess"] == 5
    assert obj["operation"] == "SEND_INVOICE"


def test_emit_metric_has_timestamp() -> None:
    """EMF object includes Timestamp in _aws."""
    line = _capture_emit(lambda: emit_metric("RedriveRequested", operation="GET_RECEIPT"))
    obj = _parse_emf(line)
    ts = obj["_aws"]["Timestamp"]
    assert isinstance(ts, int)
    assert ts > 0


_ROUTING_METRICS = [
    "ExecuteSuccess",
    "ExecuteValidationFailed",
    "ExecuteAuthFailed",
    "ExecuteAllowlistDenied",
    "DownstreamTimeout",
    "DownstreamError",
    "Replay",
    "RedriveRequested",
    "RedriveSuccess",
    "RedriveFailed",
]


def test_all_routing_metrics_emit_valid_emf() -> None:
    """All 10 routing metrics produce valid EMF JSON with correct structure."""
    for metric in _ROUTING_METRICS:
        line = _capture_emit(lambda m=metric: emit_metric(m, operation="TEST_OP"))
        assert line is not None, f"No output for metric {metric}"
        obj = _parse_emf(line)
        assert "_aws" in obj
        assert "CloudWatchMetrics" in obj["_aws"]
        ns = obj["_aws"]["CloudWatchMetrics"][0]
        assert ns["Namespace"] == "IntegrationHub/Routing"
        assert ns["Metrics"][0]["Name"] == metric
        assert ns["Metrics"][0]["Unit"] == "Count"
        assert metric in obj
        assert obj[metric] == 1
        assert obj["operation"] == "TEST_OP"
