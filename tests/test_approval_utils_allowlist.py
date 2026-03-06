"""Unit tests for approval_utils ALLOWLIST_RULE apply logic."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from approval_utils import apply_vendor_change_request  # noqa: E402


@patch("approval_utils._apply_allowlist_payload")
def test_apply_vendor_change_request_allowlist_rules_format(
    mock_apply: MagicMock,
) -> None:
    """apply_vendor_change_request with rules payload calls _apply_allowlist_payload."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    request_row = {
        "id": "cr-1",
        "request_type": "ALLOWLIST_RULE",
        "requesting_vendor_code": "LH001",
        "target_vendor_code": "LH002",
        "payload": {
            "sourceVendorCode": "LH001",
            "direction": "OUTBOUND",
            "rules": [
                {
                    "sourceVendorCode": "LH001",
                    "targetVendorCode": "LH002",
                    "operationCode": "GET_WEATHER",
                    "ruleScope": "vendor",
                    "flowDirection": "OUTBOUND",
                    "isAnySource": False,
                    "isAnyTarget": False,
                },
            ],
            "wildcard": {"isAnySource": False, "isAnyTarget": False},
        },
    }

    apply_vendor_change_request(conn, request_row, "admin@test.com")

    mock_apply.assert_called_once()
    call_args = mock_apply.call_args[0]
    assert call_args[1] == request_row["payload"]
    assert call_args[2] == "LH002"
