from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from platform_rollout import evaluate_effective_enabled  # noqa: E402
from registry_lambda import handler as registry_handler  # noqa: E402
from vendor_registry_lambda import handler as vendor_handler  # noqa: E402
from vendor_registry_jwt import add_jwt_auth  # noqa: E402


def test_effective_enabled_phase_0_inherit() -> None:
    assert evaluate_effective_enabled(None, True) is True
    assert evaluate_effective_enabled(None, False) is False


def test_effective_enabled_override_true_forces_enabled() -> None:
    assert evaluate_effective_enabled(True, False) is True
    assert evaluate_effective_enabled(True, True) is True


def test_effective_enabled_override_false_forces_disabled() -> None:
    assert evaluate_effective_enabled(False, True) is False
    assert evaluate_effective_enabled(False, False) is False


def test_unknown_feature_defaults_disabled() -> None:
    effective = {"known_feature": True}
    assert bool(effective.get("unknown_feature", False)) is False


def test_registry_platform_features_requires_admin_auth() -> None:
    event = {
        "path": "/v1/registry/platform/features",
        "rawPath": "/v1/registry/platform/features",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "requestContext": {},
    }
    resp = registry_handler(event, None)
    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "AUTH_ERROR"


@patch("vendor_registry_lambda._get_connection")
def test_vendor_platform_features_requires_vendor_auth(mock_conn_ctx: MagicMock) -> None:
    event = {
        "path": "/v1/vendor/platform/features",
        "rawPath": "/v1/vendor/platform/features",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": {"http": {"method": "GET"}, "requestId": "test"},
    }
    resp = vendor_handler(event, None)
    assert resp["statusCode"] == 401
    mock_conn_ctx.assert_not_called()


@patch("vendor_registry_lambda._get_connection")
def test_vendor_platform_features_with_auth_succeeds(mock_conn_ctx: MagicMock) -> None:
    conn_validate = MagicMock()
    cur_validate = MagicMock()
    cur_validate.fetchone.return_value = ("LH001", True)
    conn_validate.cursor.return_value.__enter__.return_value = cur_validate

    conn_features = MagicMock()
    cur_features = MagicMock()
    cur_features.fetchone.return_value = {"settings_value": "PHASE_0"}
    cur_features.fetchall.return_value = [
        {
            "feature_code": "home_welcome",
            "description": None,
            "is_enabled": None,
            "phase_enabled": True,
        }
    ]
    conn_features.cursor.return_value.__enter__.return_value = cur_features
    ctx_validate = MagicMock()
    ctx_validate.__enter__.return_value = conn_validate
    ctx_validate.__exit__.return_value = None
    ctx_features = MagicMock()
    ctx_features.__enter__.return_value = conn_features
    ctx_features.__exit__.return_value = None
    mock_conn_ctx.side_effect = [ctx_validate, ctx_features]

    event = {
        "path": "/v1/vendor/platform/features",
        "rawPath": "/v1/vendor/platform/features",
        "httpMethod": "GET",
        "headers": {},
        "queryStringParameters": {},
        "pathParameters": {},
        "requestContext": {"http": {"method": "GET"}, "requestId": "test"},
    }
    add_jwt_auth(event, "LH001")
    resp = vendor_handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["currentPhase"] == "PHASE_0"
    assert body["effectiveFeatures"]["home_welcome"] is True
