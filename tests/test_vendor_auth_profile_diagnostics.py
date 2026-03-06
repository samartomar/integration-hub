from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from vendor_registry_jwt import add_jwt_auth  # noqa: E402
from vendor_registry_lambda import handler  # noqa: E402


@pytest.fixture(autouse=True)
def _mock_connection() -> None:
    with patch("vendor_registry_lambda._get_connection") as mocked:
        mocked.return_value.__enter__.return_value = MagicMock()
        yield


def _event(path: str, body: dict) -> dict:
    ev = {
        "path": path,
        "rawPath": path,
        "httpMethod": "POST",
        "headers": {},
        "body": json.dumps(body),
        "pathParameters": {},
        "requestContext": {"http": {"method": "POST"}, "requestId": "req-1"},
    }
    add_jwt_auth(ev, "LH001")
    return ev


@patch("vendor_registry_lambda.socket.getaddrinfo")
def test_vendor_test_connection_blocks_ssrf(mock_getaddrinfo) -> None:
    mock_getaddrinfo.return_value = [(None, None, None, None, ("169.254.169.254", 443))]
    event = _event(
        "/v1/vendor/auth-profiles/test-connection",
        {
            "authType": "API_KEY_HEADER",
            "authConfig": {"headerName": "Api-Key", "key": "secret-value"},
            "url": "http://169.254.169.254/latest/meta-data",
            "method": "GET",
            "timeoutMs": 5000,
        },
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["ok"] is False
    assert body["error"]["category"] == "BLOCKED"


@patch("vendor_registry_lambda.requests.request")
@patch("vendor_registry_lambda.socket.getaddrinfo")
def test_vendor_test_connection_redacts_secrets(mock_getaddrinfo, mock_request) -> None:
    class _Resp:
        status_code = 200
        text = "ok"

    mock_getaddrinfo.return_value = [(None, None, None, None, ("8.8.8.8", 443))]
    mock_request.return_value = _Resp()
    event = _event(
        "/v1/vendor/auth-profiles/test-connection",
        {
            "authType": "BEARER",
            "authConfig": {"token": "very-secret-token"},
            "url": "https://example.com/health",
            "method": "GET",
        },
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is True
    assert body["debug"]["resolvedAuth"]["appliedHeaders"]["Authorization"] == "Bearer ***REDACTED***"
    assert "very-secret-token" not in json.dumps(body)


@patch("vendor_registry_lambda.requests.request", side_effect=requests.Timeout("timeout"))
@patch("vendor_registry_lambda.socket.getaddrinfo")
def test_vendor_test_connection_timeout_enforced(mock_getaddrinfo, _mock_request) -> None:
    mock_getaddrinfo.return_value = [(None, None, None, None, ("8.8.8.8", 443))]
    event = _event(
        "/v1/vendor/auth-profiles/test-connection",
        {
            "authType": "API_KEY_QUERY",
            "authConfig": {"paramName": "api_key", "key": "secret"},
            "url": "https://example.com/health",
            "method": "GET",
            "timeoutMs": 20000,
        },
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is False
    assert body["error"]["category"] == "TIMEOUT"


@patch("vendor_registry_lambda.requests.post")
def test_vendor_token_preview_redacts_token(mock_post) -> None:
    class _Resp:
        status_code = 200

        def json(self):
            return {"access_token": "abcdefghijklmnopqrstuvwx.yyy.zzzzzz", "expires_in": 3600}

    mock_post.return_value = _Resp()
    event = _event(
        "/v1/vendor/auth-profiles/token-preview",
        {
            "authType": "JWT_BEARER_TOKEN",
            "authConfig": {
                "tokenUrl": "https://idp.example.com/token",
                "clientId": "client",
                "clientSecret": "secret",
            },
        },
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is True
    assert body["tokenRedacted"] is not None
    assert "secret" not in json.dumps(body)


@patch("vendor_registry_lambda.requests.post")
def test_vendor_token_preview_non_jwt_claims_null(mock_post) -> None:
    class _Resp:
        status_code = 200

        def json(self):
            return {"access_token": "opaque_access_token", "expires_in": 3600}

    mock_post.return_value = _Resp()
    event = _event(
        "/v1/vendor/auth-profiles/token-preview",
        {
            "authType": "JWT_BEARER_TOKEN",
            "authConfig": {
                "tokenUrl": "https://idp.example.com/token",
                "clientId": "client-non-jwt",
                "clientSecret": "secret",
            },
        },
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is True
    assert body["jwtClaims"] is None


def test_vendor_mtls_validate_parse_failures_safe() -> None:
    pytest.importorskip("cryptography")
    event = _event(
        "/v1/vendor/auth-profiles/mtls-validate",
        {
            "certificatePem": "invalid",
            "privateKeyPem": "invalid",
        },
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is False
    assert body["error"]["category"] == "PARSE"


def test_vendor_mtls_validate_mismatched_key_returns_invalid() -> None:
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from datetime import datetime, timedelta, timezone

    key1 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key2 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "example.com")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key1.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=30))
        .sign(key1, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    wrong_key_pem = key2.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    event = _event(
        "/v1/vendor/auth-profiles/mtls-validate",
        {"certificatePem": cert_pem, "privateKeyPem": wrong_key_pem},
    )
    resp = handler(event, None)
    body = json.loads(resp["body"])
    assert body["ok"] is False
    assert body["error"]["category"] == "MISMATCH"
