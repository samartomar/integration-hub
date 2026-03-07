"""Unit tests for Syntegris Adoption Workbench API endpoints."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from registry_lambda import handler  # noqa: E402

JWT_AUTHORIZER = {
    "principalId": "okta|test",
    "jwt": {"claims": {"sub": "okta|test", "aud": "api://default", "groups": ["admins", "admin"]}},
}
AUTH_REQUEST_CONTEXT = {"http": {"method": "GET"}, "authorizer": JWT_AUTHORIZER}


def _syntegris_event(path: str, query_params: dict | None = None) -> dict:
    """Build GET event for syntegris routes."""
    return {
        "path": path,
        "rawPath": path,
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": query_params or {},
        "pathParameters": {},
        "requestContext": AUTH_REQUEST_CONTEXT,
    }


def _mock_inventory_result() -> dict:
    return {
        "items": [
            {
                "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
                "inventoryEvidence": {
                    "operationExists": True,
                    "allowlistExists": True,
                    "operationContractExists": True,
                    "vendorMappingExists": True,
                    "endpointConfigExists": True,
                },
                "notes": [],
            },
        ],
        "summary": {"total": 1, "withFullEvidence": 1, "partial": 0},
        "notes": [],
    }


def _mock_adoption_result() -> dict:
    return {
        "items": [
            {
                "operationCode": "GET_VERIFY_MEMBER_ELIGIBILITY",
                "version": "1.0",
                "sourceVendor": "LH001",
                "targetVendor": "LH002",
                "adoptionStatus": "SYNTEGRIS_READY",
                "inventoryEvidence": {},
                "syntegrisEvidence": {
                    "canonicalDefined": True,
                    "mappingReady": True,
                    "releaseReady": True,
                    "runtimeIntegrated": True,
                },
                "nextAction": {"code": "READY", "title": "Ready", "targetRoute": "/admin/canonical-mapping-readiness"},
                "notes": [],
            },
        ],
        "summary": {
            "total": 1,
            "legacyOnly": 0,
            "canonDefined": 0,
            "mappingInProgress": 0,
            "certified": 0,
            "releaseReady": 0,
            "syntegrisReady": 1,
            "blocked": 0,
        },
        "notes": [],
    }


@patch("registry_lambda._get_connection")
@patch("schema.integration_inventory.list_integration_inventory")
def test_get_syntegris_inventory_returns_200(mock_list, mock_conn) -> None:
    """GET /v1/syntegris/inventory returns 200 with items."""
    mock_conn.return_value.__enter__.return_value = MagicMock()
    mock_conn.return_value.__exit__.return_value = None
    mock_list.return_value = _mock_inventory_result()

    event = _syntegris_event("/v1/syntegris/inventory")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "items" in body
    assert len(body["items"]) == 1
    assert body["items"][0]["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
    assert body["items"][0]["sourceVendor"] == "LH001"
    assert body["items"][0]["targetVendor"] == "LH002"
    assert "summary" in body
    assert body["summary"]["total"] == 1


@patch("registry_lambda._get_connection")
@patch("schema.integration_inventory.list_integration_inventory")
def test_get_syntegris_inventory_by_operation_returns_200(mock_list, mock_conn) -> None:
    """GET /v1/syntegris/inventory/{operationCode} returns 200."""
    mock_conn.return_value.__enter__.return_value = MagicMock()
    mock_conn.return_value.__exit__.return_value = None
    mock_list.return_value = _mock_inventory_result()

    event = _syntegris_event("/v1/syntegris/inventory/GET_VERIFY_MEMBER_ELIGIBILITY")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "items" in body
    assert body["items"][0]["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"


@patch("registry_lambda._get_connection")
@patch("schema.integration_inventory.list_integration_inventory")
def test_get_syntegris_inventory_by_operation_empty_operation_returns_400(mock_list, mock_conn) -> None:
    """GET /v1/syntegris/inventory/ with whitespace-only operationCode returns 400."""
    mock_conn.return_value.__enter__.return_value = MagicMock()
    mock_conn.return_value.__exit__.return_value = None
    # Path with trailing space as operationCode segment triggers validation
    event = _syntegris_event("/v1/syntegris/inventory/ ")
    resp = handler(event, None)

    assert resp["statusCode"] == 400


@patch("registry_lambda._get_connection")
@patch("schema.syntegris_adoption.list_syntegris_adoption")
@patch("schema.syntegris_adoption.summarize_syntegris_adoption")
def test_get_syntegris_adoption_summary_returns_200(mock_summarize, mock_list, mock_conn) -> None:
    """GET /v1/syntegris/adoption/summary returns 200 with summary."""
    mock_conn.return_value.__enter__.return_value = MagicMock()
    mock_conn.return_value.__exit__.return_value = None
    mock_list.return_value = _mock_adoption_result()
    mock_summarize.return_value = _mock_adoption_result()["summary"]

    event = _syntegris_event("/v1/syntegris/adoption/summary")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "summary" in body
    assert body["summary"]["syntegrisReady"] == 1
    assert body["summary"]["total"] == 1


@patch("registry_lambda._get_connection")
@patch("schema.syntegris_adoption.list_syntegris_adoption")
def test_get_syntegris_adoption_returns_200(mock_list, mock_conn) -> None:
    """GET /v1/syntegris/adoption returns 200 with items."""
    mock_conn.return_value.__enter__.return_value = MagicMock()
    mock_conn.return_value.__exit__.return_value = None
    mock_list.return_value = _mock_adoption_result()

    event = _syntegris_event("/v1/syntegris/adoption")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "items" in body
    assert len(body["items"]) == 1
    assert body["items"][0]["adoptionStatus"] == "SYNTEGRIS_READY"
    assert "summary" in body


@patch("registry_lambda._get_connection")
@patch("schema.syntegris_adoption.list_syntegris_adoption")
def test_get_syntegris_adoption_by_operation_returns_200(mock_list, mock_conn) -> None:
    """GET /v1/syntegris/adoption/{operationCode} returns 200."""
    mock_conn.return_value.__enter__.return_value = MagicMock()
    mock_conn.return_value.__exit__.return_value = None
    mock_list.return_value = _mock_adoption_result()

    event = _syntegris_event("/v1/syntegris/adoption/GET_VERIFY_MEMBER_ELIGIBILITY")
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "items" in body
    assert body["items"][0]["operationCode"] == "GET_VERIFY_MEMBER_ELIGIBILITY"
