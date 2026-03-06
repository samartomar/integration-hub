"""JWT authentication for Integration Hub - validate Bearer tokens via JWKS and map to vendor."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import jwt
import requests


@dataclass
class JwtAuthConfig:
    """Configuration for JWT IDP validation."""

    issuer: str
    jwks_uri: str
    audiences: list[str]
    vendor_claim: str
    allowed_alg: str  # Used when allowed_algs not set (DB config)
    clock_skew_seconds: int = 60
    allowed_algs: list[str] | None = None  # When set (env config), overrides allowed_alg for jwt.decode


@dataclass
class JwtAuthResult:
    """Result of successful JWT validation."""

    vendor_code: str
    claims: dict[str, Any]


class JwtValidationError(Exception):
    """JWT validation failed."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def load_jwt_auth_config(conn: Any) -> JwtAuthConfig | None:
    """
    Load JWT auth config from control_plane.vendor_auth_profiles
    where auth_type='JWT_IDP' and vendor_code='SYSTEM' (or first active JWT_IDP profile).

    Returns JwtAuthConfig if found, None otherwise.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT vendor_code, config
            FROM control_plane.vendor_auth_profiles
            WHERE auth_type = 'JWT_IDP' AND is_active = true
            ORDER BY CASE WHEN vendor_code = 'SYSTEM' THEN 0 ELSE 1 END,
                     updated_at DESC NULLS LAST
            LIMIT 1
            """,
        )
        row = cur.fetchone()
    if row is None:
        return None

    config_raw = row[1] if hasattr(row, "__getitem__") else row.get("config")
    if not isinstance(config_raw, dict):
        return None

    issuer = (config_raw.get("issuer") or "").strip()
    jwks_uri = (config_raw.get("jwks_uri") or "").strip()
    if not issuer or not jwks_uri:
        return None

    aud = config_raw.get("audiences")
    if isinstance(aud, str):
        audiences = [aud] if aud.strip() else []
    elif isinstance(aud, list):
        audiences = [str(a).strip() for a in aud if a]
    else:
        audiences = []

    vendor_claim = (config_raw.get("vendor_claim") or "bcpAuth").strip() or "bcpAuth"
    allowed_alg = (config_raw.get("allowed_alg") or "RS256").strip() or "RS256"
    clock_skew = config_raw.get("clock_skew_seconds")
    if isinstance(clock_skew, (int, float)):
        clock_skew_seconds = int(clock_skew)
    else:
        clock_skew_seconds = 60

    return JwtAuthConfig(
        issuer=issuer,
        jwks_uri=jwks_uri,
        audiences=audiences,
        vendor_claim=vendor_claim,
        allowed_alg=allowed_alg,
        clock_skew_seconds=clock_skew_seconds,
    )


def load_jwt_auth_config_from_env() -> JwtAuthConfig | None:
    """
    Load JWT auth config from environment variables (Tier-3 inbound IDP).
    IDP_JWKS_URL must be set for JWT to be enabled; if empty/unset returns None.
    Env vars: IDP_JWKS_URL, IDP_ISSUER, IDP_AUDIENCE, IDP_VENDOR_CLAIM, IDP_ALLOWED_ALGS.
    """
    jwks_url = (os.environ.get("IDP_JWKS_URL") or "").strip()
    if not jwks_url:
        return None

    issuer = (os.environ.get("IDP_ISSUER") or "").strip()
    audience_raw = (os.environ.get("IDP_AUDIENCE") or "").strip()
    audiences = [a.strip() for a in audience_raw.split(",") if a.strip()] if audience_raw else []
    vendor_claim = (os.environ.get("IDP_VENDOR_CLAIM") or "bcpAuth").strip() or "bcpAuth"
    algs_raw = (os.environ.get("IDP_ALLOWED_ALGS") or "RS256").strip()
    allowed_algs = [a.strip() for a in algs_raw.split(",") if a.strip()] or ["RS256"]

    if not issuer:
        return None

    return JwtAuthConfig(
        issuer=issuer,
        jwks_uri=jwks_url,
        audiences=audiences,
        vendor_claim=vendor_claim,
        allowed_alg=allowed_algs[0] if allowed_algs else "RS256",
        clock_skew_seconds=60,
        allowed_algs=allowed_algs,
    )


def _fetch_jwks(jwks_uri: str) -> dict[str, Any]:
    """Fetch JWKS from URI. Raises JwtValidationError on failure."""
    try:
        resp = requests.get(jwks_uri, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise JwtValidationError("JWKS_FETCH_FAILED", str(e), {"jwks_uri": jwks_uri})
    except ValueError as e:
        raise JwtValidationError("JWKS_INVALID_JSON", str(e), {"jwks_uri": jwks_uri})

    if not isinstance(data, dict):
        raise JwtValidationError("JWKS_INVALID_FORMAT", "JWKS response is not an object")
    return data


# In-memory JWKS cache: jwks_uri -> (expiry_ts, keys_dict)
_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
DEFAULT_CACHE_TTL_SEC = 300


def fetch_jwks(
    jwks_uri: str,
    cache: dict[str, tuple[float, dict[str, Any]]] | None = None,
    ttl_sec: int = DEFAULT_CACHE_TTL_SEC,
) -> dict[str, Any]:
    """
    Fetch JWKS from URI with in-memory cache.
    cache: optional dict to use (default: module-level _JWKS_CACHE).
    ttl_sec: cache TTL in seconds.
    Returns JWKS dict (with 'keys' array).
    """
    import time as _time

    cache = cache if cache is not None else _JWKS_CACHE
    now = _time.time()
    if jwks_uri in cache:
        expiry, jwks = cache[jwks_uri]
        if now < expiry:
            return jwks

    jwks = _fetch_jwks(jwks_uri)
    cache[jwks_uri] = (now + ttl_sec, jwks)
    return jwks


def validate_jwt_and_map_vendor(
    raw_auth_header: str | None,
    jwt_config: JwtAuthConfig,
    jwks_cache: dict[str, tuple[float, dict[str, Any]]] | None = None,
) -> JwtAuthResult:
    """
    Parse Bearer token, verify via JWKS, validate iss/aud/exp/nbf, extract vendor from vendor_claim.

    raw_auth_header: "Bearer <token>" or None
    jwt_config: JwtAuthConfig from load_jwt_auth_config
    jwks_cache: optional cache dict for JWKS (uses module-level cache if None)

    Returns JwtAuthResult on success.
    Raises JwtValidationError on failure.
    """
    if not raw_auth_header or not raw_auth_header.strip():
        raise JwtValidationError("MISSING_AUTH", "Missing Authorization header")

    parts = raw_auth_header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise JwtValidationError("INVALID_AUTH_FORMAT", "Authorization must be 'Bearer <token>'")

    token = parts[1]
    if not token:
        raise JwtValidationError("MISSING_TOKEN", "Bearer token is empty")

    jwks = fetch_jwks(jwt_config.jwks_uri, jwks_cache)

    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise JwtValidationError("MISSING_KID", "JWT header missing 'kid'")
        keys = jwks.get("keys") or []
        signing_key = None
        algs_to_try = getattr(jwt_config, "allowed_algs", None) or [jwt_config.allowed_alg]
        for jwk in keys:
            if isinstance(jwk, dict) and jwk.get("kid") == kid:
                for alg in algs_to_try:
                    try:
                        signing_key = jwt.PyJWK.from_dict(jwk, algorithm=alg)
                        break
                    except Exception:
                        continue
                if signing_key:
                    break
        if signing_key is None:
            raise JwtValidationError(
                "JWKS_KEY_NOT_FOUND",
                f"No key with kid '{kid}' in JWKS",
                {"kid": kid, "jwks_uri": jwt_config.jwks_uri},
            )
    except JwtValidationError:
        raise
    except Exception as e:
        raise JwtValidationError("JWKS_KEY_NOT_FOUND", str(e), {"hint": "No matching key in JWKS"})

    decode_algs = getattr(jwt_config, "allowed_algs", None) or [jwt_config.allowed_alg]
    try:
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=decode_algs,
            issuer=jwt_config.issuer,
            audience=jwt_config.audiences if jwt_config.audiences else None,
            options={
                "verify_iss": True,
                "verify_aud": bool(jwt_config.audiences),
                "verify_exp": True,
                "verify_nbf": True,
            },
            leeway=jwt_config.clock_skew_seconds,
        )
    except jwt.ExpiredSignatureError as e:
        raise JwtValidationError("TOKEN_EXPIRED", str(e))
    except jwt.InvalidIssuerError as e:
        raise JwtValidationError("INVALID_ISSUER", str(e))
    except jwt.InvalidAudienceError as e:
        raise JwtValidationError("INVALID_AUDIENCE", str(e))
    except jwt.InvalidTokenError as e:
        raise JwtValidationError("INVALID_TOKEN", str(e))

    if not isinstance(payload, dict):
        raise JwtValidationError("INVALID_CLAIMS", "JWT payload is not an object")

    vendor_code = payload.get(jwt_config.vendor_claim)
    if not vendor_code:
        raise JwtValidationError(
            "MISSING_VENDOR_CLAIM",
            f"JWT missing required claim '{jwt_config.vendor_claim}'",
            {"vendor_claim": jwt_config.vendor_claim},
        )

    vendor_code = str(vendor_code).strip()
    if not vendor_code:
        raise JwtValidationError(
            "EMPTY_VENDOR_CLAIM",
            f"Claim '{jwt_config.vendor_claim}' is empty",
            {"vendor_claim": jwt_config.vendor_claim},
        )

    return JwtAuthResult(vendor_code=vendor_code, claims=dict(payload))


def validate_jwt_for_authorizer(
    token: str,
    jwt_config: JwtAuthConfig,
    jwks_cache: dict[str, tuple[float, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """
    Validate JWT (iss, aud, exp, signature) and return claims. Does not require vendor_claim.
    Used by REST API token authorizer when vendor_code may not be in the token.
    Returns payload dict; raises JwtValidationError on failure.
    """
    jwks = fetch_jwks(jwt_config.jwks_uri, jwks_cache)
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise JwtValidationError("MISSING_KID", "JWT header missing 'kid'")
        keys = jwks.get("keys") or []
        signing_key = None
        algs_to_try = getattr(jwt_config, "allowed_algs", None) or [jwt_config.allowed_alg]
        for jwk in keys:
            if isinstance(jwk, dict) and jwk.get("kid") == kid:
                for alg in algs_to_try:
                    try:
                        signing_key = jwt.PyJWK.from_dict(jwk, algorithm=alg)
                        break
                    except Exception:
                        continue
                if signing_key:
                    break
        if signing_key is None:
            raise JwtValidationError("JWKS_KEY_NOT_FOUND", f"No key with kid '{kid}' in JWKS")
    except JwtValidationError:
        raise
    except Exception as e:
        raise JwtValidationError("JWKS_KEY_NOT_FOUND", str(e))

    decode_algs = getattr(jwt_config, "allowed_algs", None) or [jwt_config.allowed_alg]
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=decode_algs,
        issuer=jwt_config.issuer,
        audience=jwt_config.audiences if jwt_config.audiences else None,
        options={
            "verify_iss": True,
            "verify_aud": bool(jwt_config.audiences),
            "verify_exp": True,
            "verify_nbf": True,
        },
        leeway=jwt_config.clock_skew_seconds,
    )
    if not isinstance(payload, dict):
        raise JwtValidationError("INVALID_CLAIMS", "JWT payload is not an object")
    return dict(payload)
