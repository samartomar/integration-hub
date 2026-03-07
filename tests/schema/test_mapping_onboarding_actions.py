"""Tests for mapping onboarding actions service."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from schema.mapping_onboarding_actions import (
    build_onboarding_action_payload,
    get_mapping_next_action,
    list_mapping_onboarding_actions,
    READY,
    GENERATE_SCAFFOLD,
    ADD_FIXTURES,
    RUN_CERTIFICATION,
    COMPLETE_MAPPING_DEFINITION,
    INVESTIGATE_WARN,
)


def test_ready_mapping_returns_ready_action() -> None:
    """READY mapping returns READY action."""
    item = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mappingDefinition": True,
        "fixtures": True,
        "certification": True,
        "status": "READY",
    }
    action = get_mapping_next_action(item)
    assert action["code"] == READY
    assert action["title"] == "Ready"
    assert action["targetRoute"] == "/admin/canonical-mappings"
    assert action["prefill"]["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert action["prefill"]["sourceVendor"] == "LH001"
    assert action["prefill"]["targetVendor"] == "LH002"


def test_missing_mapping_returns_generate_scaffold() -> None:
    """Missing mapping returns GENERATE_SCAFFOLD."""
    item = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH003",
        "mappingDefinition": False,
        "fixtures": False,
        "certification": False,
        "status": "MISSING",
    }
    action = get_mapping_next_action(item)
    assert action["code"] == GENERATE_SCAFFOLD
    assert "scaffold" in action["title"].lower()
    assert action["prefill"]["targetVendor"] == "LH003"


def test_mapping_without_fixtures_returns_add_fixtures() -> None:
    """Mapping with definition but no fixtures returns ADD_FIXTURES."""
    item = {
        "operationCode": "GET_MEMBER_ACCUMULATORS",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mappingDefinition": True,
        "fixtures": False,
        "certification": False,
        "status": "IN_PROGRESS",
    }
    action = get_mapping_next_action(item)
    assert action["code"] == ADD_FIXTURES
    assert "fixture" in action["title"].lower()


def test_mapping_with_fixtures_but_no_cert_returns_run_certification() -> None:
    """Mapping with fixtures but certification not passing returns RUN_CERTIFICATION."""
    item = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mappingDefinition": True,
        "fixtures": True,
        "certification": True,
        "status": "IN_PROGRESS",
    }
    action = get_mapping_next_action(item)
    assert action["code"] == RUN_CERTIFICATION
    assert "certification" in action["title"].lower()


def test_warn_status_returns_investigate_or_review() -> None:
    """WARN status returns INVESTIGATE_WARN or REVIEW_PROMOTION_ARTIFACT."""
    item = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "mappingDefinition": True,
        "fixtures": True,
        "certification": True,
        "status": "WARN",
    }
    action = get_mapping_next_action(item)
    assert action["code"] in (INVESTIGATE_WARN, "REVIEW_PROMOTION_ARTIFACT")
    assert action["targetRoute"] == "/admin/canonical-mappings"


def test_build_onboarding_action_payload_includes_prefill() -> None:
    """build_onboarding_action_payload includes targetRoute and prefill."""
    item = {
        "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
        "version": "1.0",
        "sourceVendor": "LH001",
        "targetVendor": "LH002",
        "status": "READY",
    }
    payload = build_onboarding_action_payload(item)
    assert payload["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert payload["status"] == "READY"
    assert "nextAction" in payload
    assert payload["nextAction"]["targetRoute"] == "/admin/canonical-mappings"
    assert payload["nextAction"]["prefill"]["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert payload["nextAction"]["prefill"]["sourceVendor"] == "LH001"
    assert payload["nextAction"]["prefill"]["targetVendor"] == "LH002"


@patch("schema.mapping_onboarding_actions.list_mapping_readiness")
def test_list_onboarding_actions_returns_items(mock_readiness: object) -> None:
    """list_mapping_onboarding_actions returns items with nextAction."""
    from schema.mapping_onboarding_actions import list_mapping_onboarding_actions

    mock_readiness.return_value = {
        "items": [
            {
                "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
                "mappingDefinition": True,
                "fixtures": True,
                "certification": True,
                "status": "READY",
            },
        ],
        "summary": {"total": 1, "ready": 1, "inProgress": 0, "missing": 0, "warn": 0},
        "notes": [],
    }
    result = list_mapping_onboarding_actions()
    assert len(result["items"]) == 1
    assert result["items"][0]["nextAction"]["code"] == READY
    assert result["items"][0]["nextAction"]["prefill"]["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert result["summary"]["total"] == 1


@patch("schema.mapping_onboarding_actions.list_mapping_readiness")
def test_list_onboarding_actions_filter_by_next_action(mock_readiness: object) -> None:
    """list_mapping_onboarding_actions filters by nextAction."""
    from schema.mapping_onboarding_actions import list_mapping_onboarding_actions

    mock_readiness.return_value = {
        "items": [
            {
                "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
                "mappingDefinition": True,
                "fixtures": True,
                "certification": True,
                "status": "READY",
            },
            {
                "operationCode": "GET_MEMBER_ACCUMULATORS",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH003",
                "mappingDefinition": False,
                "fixtures": False,
                "certification": False,
                "status": "MISSING",
            },
        ],
        "summary": {"total": 2, "ready": 1, "inProgress": 0, "missing": 1, "warn": 0},
        "notes": [],
    }
    result = list_mapping_onboarding_actions({"nextAction": "GENERATE_SCAFFOLD"})
    assert len(result["items"]) == 1
    assert result["items"][0]["nextAction"]["code"] == GENERATE_SCAFFOLD
    assert result["items"][0]["operationCode"] == "GET_MEMBER_ACCUMULATORS"
