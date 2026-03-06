"""Unit tests for approval_utils feature gates (is_feature_gated)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from approval_utils import is_feature_gated  # noqa: E402


def test_is_feature_gated_uses_db_value_when_row_exists() -> None:
    """When a feature_gates row exists, is_feature_gated returns the DB enabled value."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchone.return_value = (True,)

    assert is_feature_gated(conn, "MAPPING_CONFIG") is True
    cursor.execute.assert_called_once()
    call_args = cursor.execute.call_args[0]
    assert "GATE_MAPPING_CONFIG" in str(call_args[1])

    cursor.fetchone.return_value = (False,)
    assert is_feature_gated(conn, "MAPPING_CONFIG") is False


def test_is_feature_gated_falls_back_to_default_when_row_missing() -> None:
    """When no feature_gates row exists, fall back to DEFAULT_GATE_ENABLED."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchone.return_value = None

    assert is_feature_gated(conn, "MAPPING_CONFIG") is True
    assert is_feature_gated(conn, "ALLOWLIST_RULE") is True
    assert is_feature_gated(conn, "VENDOR_CONTRACT_CHANGE") is True
    assert is_feature_gated(conn, "ENDPOINT_CONFIG") is False


def test_is_feature_gated_unknown_request_type_returns_true() -> None:
    """Unknown request_type stays gated (safe default)."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchone.return_value = None

    assert is_feature_gated(conn, "UNKNOWN_TYPE") is True
