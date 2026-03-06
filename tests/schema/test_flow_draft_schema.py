"""Unit tests for flow_draft_schema validation and normalization."""

from __future__ import annotations

import pytest

from schema.flow_draft_schema import (
    FlowDraftValidationError,
    normalize_flow_draft,
    validate_flow_draft,
)

VALID_DRAFT = {
    "name": "Eligibility Check Flow",
    "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
    "version": "1.0",
    "sourceVendor": "LH001",
    "targetVendor": "LH002",
    "trigger": {"type": "MANUAL"},
    "mappingMode": "CANONICAL_FIRST",
    "notes": "optional string",
}


def test_valid_draft_passes() -> None:
    """Valid draft passes validation."""
    validate_flow_draft(VALID_DRAFT)


def test_missing_name_fails() -> None:
    """Missing name raises FlowDraftValidationError."""
    bad = {**VALID_DRAFT, "name": ""}
    with pytest.raises(FlowDraftValidationError) as exc_info:
        validate_flow_draft(bad)
    assert exc_info.value.field == "name"
    assert "name" in str(exc_info.value).lower()


def test_missing_source_vendor_fails() -> None:
    """Missing sourceVendor raises."""
    bad = {**VALID_DRAFT, "sourceVendor": ""}
    with pytest.raises(FlowDraftValidationError) as exc_info:
        validate_flow_draft(bad)
    assert exc_info.value.field == "sourceVendor"


def test_missing_target_vendor_fails() -> None:
    """Missing targetVendor raises."""
    bad = {**VALID_DRAFT, "targetVendor": ""}
    with pytest.raises(FlowDraftValidationError) as exc_info:
        validate_flow_draft(bad)
    assert exc_info.value.field == "targetVendor"


def test_invalid_trigger_type_fails() -> None:
    """Invalid trigger.type raises."""
    bad = {**VALID_DRAFT, "trigger": {"type": "SCHEDULED"}}
    with pytest.raises(FlowDraftValidationError) as exc_info:
        validate_flow_draft(bad)
    assert "trigger" in str(exc_info.value.field).lower()


def test_invalid_mapping_mode_fails() -> None:
    """Invalid mappingMode raises."""
    bad = {**VALID_DRAFT, "mappingMode": "CUSTOM"}
    with pytest.raises(FlowDraftValidationError) as exc_info:
        validate_flow_draft(bad)
    assert exc_info.value.field == "mappingMode"


def test_unknown_operation_code_fails() -> None:
    """Unknown operationCode raises."""
    bad = {**VALID_DRAFT, "operationCode": "UNKNOWN_OP_XYZ"}
    with pytest.raises(FlowDraftValidationError) as exc_info:
        validate_flow_draft(bad)
    assert exc_info.value.field == "operationCode"


def test_version_alias_v1_normalizes_to_1_0() -> None:
    """Version alias v1 normalizes to 1.0."""
    draft = {**VALID_DRAFT, "version": "v1"}
    result = normalize_flow_draft(draft)
    assert result["version"] == "1.0"
    assert result["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert result["name"] == "Eligibility Check Flow"
    assert result["sourceVendor"] == "LH001"
    assert result["targetVendor"] == "LH002"
    assert result["trigger"] == {"type": "MANUAL"}
    assert result["mappingMode"] == "CANONICAL_FIRST"


def test_normalize_trims_strings() -> None:
    """Normalization trims string fields."""
    draft = {
        "name": "  My Flow  ",
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": " LH001 ",
        "targetVendor": " LH002 ",
        "trigger": {"type": "MANUAL"},
        "mappingMode": "CANONICAL_FIRST",
    }
    result = normalize_flow_draft(draft)
    assert result["name"] == "My Flow"
    assert result["sourceVendor"] == "LH001"
    assert result["targetVendor"] == "LH002"


def test_normalize_snake_case_input() -> None:
    """Normalization accepts snake_case input."""
    draft = {
        "name": "Test",
        "operation_code": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "source_vendor": "LH001",
        "target_vendor": "LH002",
        "trigger": {"type": "API"},
        "mapping_mode": "CANONICAL_FIRST",
    }
    result = normalize_flow_draft(draft)
    assert result["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert result["sourceVendor"] == "LH001"
    assert result["targetVendor"] == "LH002"
    assert result["trigger"]["type"] == "API"
