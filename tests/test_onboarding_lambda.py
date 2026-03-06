"""Unit tests for Onboarding Lambda - JWT vendor identity enforcement."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from onboarding_lambda import handler  # noqa: E402


def _register_event(
    vendor_code: str = "LH001",
    vendor_name: str | None = None,
    force_rotate: bool = False,
    headers: dict | None = None,
) -> dict:
    body = {"vendorCode": vendor_code}
    if vendor_name is not None:
        body["vendorName"] = vendor_name
    if force_rotate:
        body["forceRotate"] = True
    return {
        "path": "/v1/onboarding/register",
        "httpMethod": "POST",
        "body": json.dumps(body),
        "headers": headers or {},
        "requestContext": {},
    }


@patch("onboarding_lambda._get_connection")
def test_jwt_lh001_with_body_lh002_ignores_body_vendor(
    mock_conn_ctx: MagicMock,
) -> None:
    """JWT lhcode is source of truth; conflicting body vendorCode is ignored."""
    mock_conn = MagicMock()
    mock_conn_ctx.return_value.__enter__.return_value = mock_conn

    event = _register_event(vendor_code="LH002")
    event["requestContext"] = {
        "authorizer": {
            "lhcode": "LH001",
            "jwt": {"claims": {"lhcode": "LH001"}},
            "principalId": "LH001",
        }
    }
    resp = handler(event, None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body.get("vendorCode") == "LH001"
