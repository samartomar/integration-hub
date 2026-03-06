"""Unit tests for routing.transform module."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from routing.transform import apply_mapping, extract_json_path  # noqa: E402


def test_extract_json_path_missing() -> None:
    assert extract_json_path({}, "$.a") is None
    assert extract_json_path({"a": 1}, "$.b") is None
    assert extract_json_path({"a": {}}, "$.a.b") is None


def test_extract_json_path_found() -> None:
    assert extract_json_path({"a": 1}, "$.a") == 1
    assert extract_json_path({"a": {"b": 2}}, "$.a.b") == 2
    assert extract_json_path({"a": {"b": {"c": 3}}}, "$.a.b.c") == 3
    assert extract_json_path({"a": None}, "$.a") is None


def test_apply_mapping_selectors() -> None:
    out, v = apply_mapping({"x": 1, "y": 2}, {"a": "$.x", "b": "$.y"})
    assert out == {"a": 1, "b": 2}
    assert v == []


def test_apply_mapping_constants() -> None:
    out, v = apply_mapping({"x": 1}, {"fixed": 42, "label": "test"})
    assert out == {"fixed": 42, "label": "test"}
    assert v == []


def test_apply_mapping_missing_path_violation() -> None:
    out, v = apply_mapping({}, {"a": "$.missing"})
    assert "a" not in out or out.get("a") is None
    assert v == ["missing path $.missing for field a"]


def test_apply_mapping_nested_output() -> None:
    out, v = apply_mapping({"x": 1}, {"member.id": "$.x", "const": 42})
    assert out == {"member": {"id": 1}, "const": 42}
    assert v == []


def test_apply_mapping_mixed_with_violation() -> None:
    out, v = apply_mapping({"ok": 10}, {"a": "$.ok", "b": "$.bad", "c": 3})
    assert out.get("a") == 10
    assert out.get("c") == 3
    assert "missing path $.bad for field b" in v


def test_apply_mapping_from_canonical_produces_only_mapped_fields() -> None:
    """FROM_CANONICAL mapping must produce ONLY mapping output keys, no merge with canonical."""
    canonical_request_body = {"transactionId": "123"}
    mapping = {"txnId": "$.transactionId"}
    target_request_body, violations = apply_mapping(canonical_request_body, mapping)
    assert target_request_body == {"txnId": "123"}
    assert "transactionId" not in target_request_body
    assert violations == []


def test_apply_mapping_no_merge_with_input() -> None:
    """When no mapping: target_request_body = canonical_request_body (passthrough)."""
    canonical_request_body = {"transactionId": "123"}
    # No mapping case is handled by routing lambda (target_payload = canonical_payload).
    # Here we verify apply_mapping with identity-like mapping does not merge extra keys.
    mapping = {"transactionId": "$.transactionId"}
    out, v = apply_mapping(canonical_request_body, mapping)
    assert out == {"transactionId": "123"}
    assert v == []
