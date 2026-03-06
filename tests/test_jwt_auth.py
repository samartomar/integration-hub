"""Unit tests for jwt_auth module - JWT validation and vendor mapping."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "src" / "lambda"))

from jwt_auth import (
    JwtAuthConfig,
    JwtAuthResult,
    JwtValidationError,
    load_jwt_auth_config_from_env,
    validate_jwt_and_map_vendor,
)


def _jwt_config() -> JwtAuthConfig:
    return JwtAuthConfig(
        issuer="https://idp.example.com",
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
        audiences=["hub-api"],
        vendor_claim="hub_vendor",
        allowed_alg="RS256",
        clock_skew_seconds=60,
    )


def test_missing_auth_header_raises() -> None:
    """Missing or empty Authorization header raises JwtValidationError."""
    config = _jwt_config()
    with pytest.raises(JwtValidationError) as exc_info:
        validate_jwt_and_map_vendor(None, config, {})
    assert exc_info.value.code == "MISSING_AUTH"

    with pytest.raises(JwtValidationError) as exc_info:
        validate_jwt_and_map_vendor("", config, {})
    assert exc_info.value.code == "MISSING_AUTH"


def test_invalid_auth_format_raises() -> None:
    """Non-Bearer Authorization format raises JwtValidationError."""
    config = _jwt_config()
    with pytest.raises(JwtValidationError) as exc_info:
        validate_jwt_and_map_vendor("Basic abc123", config, {})
    assert exc_info.value.code == "INVALID_AUTH_FORMAT"


@patch("jwt_auth.fetch_jwks")
def test_valid_jwt_returns_vendor_and_claims(mock_fetch_jwks: object) -> None:
    """Valid JWT with vendor claim returns JwtAuthResult."""
    config = _jwt_config()
    payload = {"hub_vendor": "VENDOR01", "sub": "user1", "iss": config.issuer, "aud": config.audiences}
    # Use HS256 for test - we'll mock JWKS to return a symmetric key representation
    # Actually PyJWT RS256 needs real RSA keys. Simpler: mock jwt.decode to return payload
    with patch("jwt_auth.jwt.decode") as mock_decode:
        mock_decode.return_value = {
            "hub_vendor": "VENDOR01",
            "sub": "user1",
            "iss": config.issuer,
            "aud": config.audiences[0],
            "exp": 9999999999,
            "nbf": 0,
        }
        mock_fetch_jwks.return_value = {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "test-kid",
                    "alg": "RS256",
                }
            ]
        }
        with patch("jwt_auth.jwt.get_unverified_header") as mock_header:
            mock_header.return_value = {"alg": "RS256", "kid": "test-kid"}
            with patch("jwt_auth.jwt.PyJWK") as mock_pyjwk:
                mock_key = type("Key", (), {"key": "mock"})()
                mock_pyjwk.from_dict.return_value = mock_key

                result = validate_jwt_and_map_vendor(
                    "Bearer eyJhbG.eyJzdWIiOiJ1c2VyMSJ9.sig",
                    config,
                    {},
                )

    assert result.vendor_code == "VENDOR01"
    assert "hub_vendor" in result.claims


@patch("jwt_auth.fetch_jwks")
def test_missing_vendor_claim_raises(mock_fetch_jwks: object) -> None:
    """JWT without vendor claim raises JwtValidationError."""
    config = _jwt_config()
    mock_fetch_jwks.return_value = {"keys": [{"kty": "RSA", "kid": "k1", "alg": "RS256"}]}
    with patch("jwt_auth.jwt.get_unverified_header") as mock_header:
        mock_header.return_value = {"alg": "RS256", "kid": "k1"}
        with patch("jwt_auth.jwt.PyJWK") as mock_pyjwk:
            mock_key = type("Key", (), {"key": "mock"})()
            mock_pyjwk.from_dict.return_value = mock_key
            with patch("jwt_auth.jwt.decode") as mock_decode:
                mock_decode.return_value = {"sub": "u1", "iss": config.issuer}
                with pytest.raises(JwtValidationError) as exc_info:
                    validate_jwt_and_map_vendor("Bearer x.y.z", config, {})
                assert exc_info.value.code == "MISSING_VENDOR_CLAIM"
                assert "hub_vendor" in exc_info.value.message


@patch.dict("os.environ", {"IDP_JWKS_URL": "", "IDP_ISSUER": ""}, clear=False)
def test_load_jwt_auth_config_from_env_empty_jwks_returns_none() -> None:
    """Empty IDP_JWKS_URL -> returns None (JWT disabled)."""
    assert load_jwt_auth_config_from_env() is None


@patch.dict(
    "os.environ",
    {
        "IDP_JWKS_URL": "https://idp.example.com/.well-known/jwks.json",
        "IDP_ISSUER": "https://idp.example.com",
        "IDP_AUDIENCE": "hub-api",
        "IDP_ALLOWED_ALGS": "RS256,RS384",
    },
    clear=False,
)
def test_load_jwt_auth_config_from_env_returns_config() -> None:
    """When IDP_JWKS_URL set, returns JwtAuthConfig with env values."""
    config = load_jwt_auth_config_from_env()
    assert config is not None
    assert config.jwks_uri == "https://idp.example.com/.well-known/jwks.json"
    assert config.issuer == "https://idp.example.com"
    assert config.audiences == ["hub-api"]
    assert config.vendor_claim == "bcpAuth"
    assert config.allowed_algs == ["RS256", "RS384"]
