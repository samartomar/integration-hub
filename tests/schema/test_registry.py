"""Registry tests: lookup, version resolution, list_operations."""

from __future__ import annotations

import pytest

from schema.canonical_registry import get_operation, list_operations, resolve_version


def test_registry_lookup_exact_version() -> None:
    """Registry lookup works for exact version 1.0."""
    op = get_operation("GET_VERIFY_MEMBER_ELIGIBILITY", "1.0")
    assert op is not None
    assert op["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert op["version"] == "1.0"
    assert "requestPayloadSchema" in op
    assert "responsePayloadSchema" in op
    assert "examples" in op


def test_registry_lookup_alias_v1() -> None:
    """Registry lookup works for alias v1 -> 1.0."""
    op = get_operation("GET_VERIFY_MEMBER_ELIGIBILITY", "v1")
    assert op is not None
    assert op["version"] == "1.0"
    assert op["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"


def test_registry_latest_when_version_omitted() -> None:
    """Latest version lookup works when version omitted."""
    op = get_operation("GET_VERIFY_MEMBER_ELIGIBILITY")
    assert op is not None
    assert op["version"] == "1.0"


def test_resolve_version_alias() -> None:
    """resolve_version maps v1 -> 1.0."""
    assert resolve_version("GET_VERIFY_MEMBER_ELIGIBILITY", "v1") == "1.0"


def test_resolve_version_exact() -> None:
    """resolve_version returns 1.0 for exact version."""
    assert resolve_version("GET_VERIFY_MEMBER_ELIGIBILITY", "1.0") == "1.0"


def test_resolve_version_latest() -> None:
    """resolve_version returns latest when version is None."""
    assert resolve_version("GET_VERIFY_MEMBER_ELIGIBILITY", None) == "1.0"


def test_list_operations_returns_normalized() -> None:
    """list_operations returns items with latestVersion in official format."""
    items = list_operations()
    assert isinstance(items, list)
    ops = {item["operationCode"]: item for item in items}
    assert "GET_VERIFY_MEMBER_ELIGIBILITY" in ops
    assert ops["GET_VERIFY_MEMBER_ELIGIBILITY"]["latestVersion"] == "1.0"
    assert "GET_MEMBER_ACCUMULATORS" in ops
    assert ops["GET_MEMBER_ACCUMULATORS"]["latestVersion"] == "1.0"


def test_list_operations_item_has_versions() -> None:
    """Each list item has versions array with official version strings."""
    items = list_operations()
    for item in items:
        assert "versions" in item
        assert isinstance(item["versions"], list)
        assert "1.0" in item["versions"]


def test_resolve_version_accumulators_alias() -> None:
    """resolve_version maps v1 -> 1.0 for GET_MEMBER_ACCUMULATORS."""
    assert resolve_version("GET_MEMBER_ACCUMULATORS", "v1") == "1.0"


def test_get_operation_returns_full_canonical_definition() -> None:
    """get_operation returns full detail: versionAliases, envelopes, latestVersion."""
    op = get_operation("GET_VERIFY_MEMBER_ELIGIBILITY", "1.0")
    assert op is not None
    assert op["version"] == "1.0"
    assert op["latestVersion"] == "1.0"
    assert "versionAliases" in op
    assert "v1" in op["versionAliases"]
    assert "requestEnvelope" in op["examples"]
    assert "responseEnvelope" in op["examples"]
    assert op["examples"]["requestEnvelope"]["direction"] == "REQUEST"
    assert op["examples"]["responseEnvelope"]["direction"] == "RESPONSE"


def test_registry_accumulators_lookup_by_1_0() -> None:
    """Registry lookup for GET_MEMBER_ACCUMULATORS works with version 1.0."""
    op = get_operation("GET_MEMBER_ACCUMULATORS", "1.0")
    assert op is not None
    assert op["operationCode"] == "GET_MEMBER_ACCUMULATORS"
    assert op["version"] == "1.0"
    assert "individualDeductible" in str(op.get("responsePayloadSchema", {}))
    assert "requestEnvelope" in op.get("examples", {})


def test_registry_accumulators_lookup_by_v1() -> None:
    """Registry lookup for GET_MEMBER_ACCUMULATORS works with alias v1."""
    op = get_operation("GET_MEMBER_ACCUMULATORS", "v1")
    assert op is not None
    assert op["version"] == "1.0"


def test_get_operation_not_found() -> None:
    """get_operation returns None for unknown operation."""
    assert get_operation("UNKNOWN_OP_XYZ") is None


def test_resolve_version_not_found() -> None:
    """resolve_version returns None for unknown operation."""
    assert resolve_version("UNKNOWN_OP_XYZ", "1.0") is None
