"""Registry Lambda - Control Plane API. POST-only upserts for vendors, operations, allowlist, endpoints."""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import os
import re
import socket
import time
import urllib.parse
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import psycopg2
import requests
from admin_guard import require_admin_secret
from approval_utils import GATE_BY_REQUEST_TYPE
from canonical_response import canonical_error, canonical_ok, policy_denied_response
from cors import add_cors_to_response
from observability import get_context, log_json, with_observability
from platform_rollout import (
    get_platform_rollout_state,
    list_platform_phases,
    set_current_phase,
    update_platform_feature,
)
from policy_engine import PolicyContext, evaluate_policy
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from readiness_mapping import is_mapping_configured_for_direction

# operation_code: uppercase alphanumeric with underscores (e.g. SEND_RECEIPT)
OPERATION_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
# URL basic validation
URL_PATTERN = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)

# Auth profile: Tier-1 outbound auth types (static values only, no OAuth)
AUTH_PROFILE_TYPES = frozenset({
    "API_KEY_HEADER", "API_KEY_QUERY", "STATIC_BEARER", "BASIC", "BEARER", "JWT", "MTLS", "JWT_BEARER_TOKEN",
})
AUTH_PROFILE_TYPE_ALIASES = {
    "STATIC_BEARER": "BEARER",
    "BEARER_TOKEN": "BEARER",
    "BASIC_AUTH": "BASIC",
    "JWT_BEARER_TOKEN": "JWT_BEARER_TOKEN",
}

MAX_TEST_TIMEOUT_MS = 10_000
DEFAULT_TEST_TIMEOUT_MS = 5_000
MAX_TEST_RESPONSE_PREVIEW = 2_048

JWT_PREVIEW_REFRESH_MARGIN_SEC = 30
JWT_PREVIEW_DEFAULT_EXPIRES_IN = 600
_jwt_preview_cache: dict[str, dict[str, Any]] = {}

AUDIT_ACTOR_POC = "COMPANY_A"
MAX_STRING_LENGTH = 256
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def validate_limit(param: str | int | None, default: int = 50, minimum: int = 1, maximum: int = 200) -> int:
    """Unifying limit validator for registry pagination. Returns clamped integer."""
    if param is None:
        return default
    if isinstance(param, int):
        return max(minimum, min(maximum, param))
    s = str(param).strip() if param else ""
    if not s:
        return default
    try:
        n = int(s)
    except ValueError:
        return default
    return max(minimum, min(maximum, n))


def _get_audit_actor(_event: dict[str, Any]) -> str:
    """
    Get vendor_code for audit attribution. POC: returns COMPANY_A.
    Later: derive from Cognito JWT (e.g. event['requestContext']['authorizer']['claims']['custom:vendor_code']).
    """
    return AUDIT_ACTOR_POC


def _resolve_db_creds() -> dict[str, str]:
    """Resolve DB credentials from DB_URL or DB_SECRET_ARN."""
    db_url = os.environ.get("DB_URL")
    if db_url:
        return {"connection_string": db_url}
    secret_arn = os.environ.get("DB_SECRET_ARN")
    if not secret_arn:
        raise ConnectionError("Neither DB_URL nor DB_SECRET_ARN is set")
    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    raw = json.loads(response["SecretString"])
    pw = raw["password"]
    pw_enc = urllib.parse.quote(str(pw), safe="")
    return {
        "connection_string": (
            f"postgresql://{raw.get('username') or raw.get('user')}:{pw_enc}"
            f"@{raw['host']}:{raw.get('port', 5432)}"
            f"/{raw.get('dbname', raw.get('database', 'integrationhub'))}"
        )
    }


@contextmanager
def _get_connection() -> Generator[Any, None, None]:
    """Get Postgres connection (read-write for registry writes)."""
    creds = _resolve_db_creds()
    conn = psycopg2.connect(
        creds["connection_string"],
        connect_timeout=10,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _execute_one(
    conn: Any,
    query: sql.Composed,
    params: tuple[Any, ...] | None = None,
) -> dict[str, Any] | None:
    """Execute and return first row or None."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params or ())
        row = cur.fetchone()
        return dict(row) if row else None


def _execute_mutation(
    conn: Any,
    query: sql.Composed,
    params: tuple[Any, ...] | None = None,
) -> int:
    """Execute INSERT/UPDATE and return rowcount."""
    with conn.cursor() as cur:
        cur.execute(query, params or ())
        return cur.rowcount


def _write_audit_event(
    conn: Any,
    transaction_id: str,
    action: str,
    vendor_code: str,
    details: dict[str, Any],
) -> None:
    """Insert into data_plane.audit_events."""
    q = sql.SQL(
        """
        INSERT INTO data_plane.audit_events (transaction_id, action, vendor_code, details)
        VALUES (%s, %s, %s, %s::jsonb)
        """
    )
    _execute_mutation(
        conn, q, (transaction_id, action, vendor_code, json.dumps(details))
    )


def _publish_endpoint_upserted(
    vendor_code: str,
    operation_code: str,
    url: str,
    http_method: str | None,
    payload_format: str | None,
    timeout_ms: int | None,
) -> None:
    """Publish endpoint.upserted to EventBridge."""
    bus_arn = os.environ.get("EVENT_BUS_ARN")
    if not bus_arn:
        return
    import boto3

    detail = {
        "vendorCode": vendor_code,
        "operationCode": operation_code,
        "url": url,
        "http_method": http_method,
        "payload_format": payload_format,
        "timeout_ms": timeout_ms,
    }
    events_client = boto3.client("events")
    events_client.put_events(
        Entries=[
            {
                "Source": "integrationhub.registry",
                "DetailType": "endpoint.upserted",
                "Detail": json.dumps(detail),
                "EventBusName": bus_arn,
            }
        ]
    )


# --- Validation ---


DEPRECATED_VENDOR_CODES = frozenset({"HUB", "LH000"})


def _validate_vendor_code(value: str | None) -> str:
    """Validate vendor_code (non-empty, reasonable length). Rejects deprecated/reserved codes."""
    if not value or not isinstance(value, str):
        raise ValueError("vendor_code is required")
    s = value.strip().upper()
    if not s:
        raise ValueError("vendor_code cannot be empty")
    if s in DEPRECATED_VENDOR_CODES:
        raise ValueError(f"Vendor code '{s}' is deprecated. Use the actual vendor code.")
    if len(s) > 64:
        raise ValueError("vendor_code must be at most 64 characters")
    return s


def _validate_operation_code(value: str | None) -> str:
    """Validate operation_code (e.g. SEND_RECEIPT)."""
    if not value or not isinstance(value, str):
        raise ValueError("operation_code is required")
    s = value.strip().upper()
    if not s:
        raise ValueError("operation_code cannot be empty")
    if len(s) > 64:
        raise ValueError("operation_code must be at most 64 characters")
    if not OPERATION_CODE_PATTERN.match(s):
        raise ValueError(
            "operation_code must be uppercase alphanumeric with underscores (e.g. SEND_RECEIPT)"
        )
    return s


def _validate_vendor_name(value: str | None) -> str:
    """Validate vendor_name."""
    if not value or not isinstance(value, str):
        raise ValueError("vendor_name is required")
    s = value.strip()
    if not s:
        raise ValueError("vendor_name cannot be empty")
    if len(s) > MAX_STRING_LENGTH:
        raise ValueError("vendor_name must be at most 256 characters")
    return s


def _validate_url(value: str | None) -> str:
    """Validate URL."""
    if not value or not isinstance(value, str):
        raise ValueError("url is required")
    s = value.strip()
    if not s:
        raise ValueError("url cannot be empty")
    if len(s) > 2048:
        raise ValueError("url must be at most 2048 characters")
    if not URL_PATTERN.match(s):
        raise ValueError("url must be a valid HTTP/HTTPS URL")
    return s


def _validate_optional_str(value: Any, name: str, max_len: int = MAX_STRING_LENGTH) -> str | None:
    """Validate optional string."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    s = value.strip()
    if not s:
        return None
    if len(s) > max_len:
        raise ValueError(f"{name} must be at most {max_len} characters")
    return s


def _validate_optional_int(
    value: Any, name: str, min_val: int = 0, max_val: int = 300_000
) -> int | None:
    """Validate optional integer."""
    if value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a valid integer")
    if n < min_val or n > max_val:
        raise ValueError(f"{name} must be between {min_val} and {max_val}")
    return n


def _validate_auth_type(value: str | None) -> str:
    """Validate auth_type is in allowed set."""
    if not value or not isinstance(value, str):
        raise ValueError("auth_type is required")
    s = value.strip().upper()
    s = AUTH_PROFILE_TYPE_ALIASES.get(s, s)
    if s not in AUTH_PROFILE_TYPES:
        raise ValueError(
            f"auth_type must be one of: {sorted(AUTH_PROFILE_TYPES)}"
        )
    return s


def _validate_auth_config(value: Any, auth_type: str) -> dict[str, Any]:
    """
    Validate config for Tier-1 auth types. Must be a JSON object with required keys.
    - API_KEY_HEADER: headerName, value (inline; no Secrets Manager)
    - API_KEY_QUERY: paramName, value
    - BEARER/STATIC_BEARER: token (inline)
    - BASIC: username, password
    - JWT_BEARER_TOKEN: tokenUrl, clientId, clientSecret, scope(optional)
    - MTLS: certificate, privateKey, certificateAuthority(optional)
    """
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("config must be a JSON object")
    config = dict(value)
    t = (auth_type or "").strip().upper()
    if t == "API_KEY_HEADER":
        val = config.get("value")
        if val is None or (isinstance(val, str) and not val.strip()):
            raise ValueError("config.value is required for API_KEY_HEADER")
        if not isinstance(val, str):
            raise ValueError("config.value must be a string")
    elif t == "API_KEY_QUERY":
        param = config.get("paramName")
        val = config.get("value")
        if not param or not isinstance(param, str) or not str(param).strip():
            raise ValueError("config.paramName is required for API_KEY_QUERY")
        if val is None or (isinstance(val, str) and not val.strip()):
            raise ValueError("config.value is required for API_KEY_QUERY")
        if not isinstance(val, str):
            raise ValueError("config.value must be a string")
    elif t in ("STATIC_BEARER", "BEARER"):
        token = config.get("token")
        if token is None or (isinstance(token, str) and not token.strip()):
            raise ValueError("config.token is required for BEARER")
        if not isinstance(token, str):
            raise ValueError("config.token must be a string")
    elif t == "BASIC":
        username = config.get("username")
        password = config.get("password")
        if username is None or not isinstance(username, str) or not username.strip():
            raise ValueError("config.username is required for BASIC")
        if password is None or not isinstance(password, str) or not password.strip():
            raise ValueError("config.password is required for BASIC")
    elif t == "JWT":
        token = config.get("token")
        if token is None or (isinstance(token, str) and not token.strip()):
            raise ValueError("config.token is required for JWT")
        if not isinstance(token, str):
            raise ValueError("config.token must be a string")
    elif t == "JWT_BEARER_TOKEN":
        token_url = config.get("tokenUrl")
        client_id = config.get("clientId")
        client_secret = config.get("clientSecret")
        if token_url is None or not isinstance(token_url, str) or not token_url.strip():
            raise ValueError("config.tokenUrl is required for JWT_BEARER_TOKEN")
        if client_id is None or not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("config.clientId is required for JWT_BEARER_TOKEN")
        if client_secret is None or not isinstance(client_secret, str) or not client_secret.strip():
            raise ValueError("config.clientSecret is required for JWT_BEARER_TOKEN")
        scope = config.get("scope")
        if scope is not None and not isinstance(scope, str):
            raise ValueError("config.scope must be a string")
    elif t == "MTLS":
        certificate = config.get("certificate") or config.get("certPem")
        private_key = config.get("privateKey") or config.get("keyPem")
        if certificate is None or not isinstance(certificate, str) or not certificate.strip():
            raise ValueError("config.certificate is required for MTLS")
        if private_key is None or not isinstance(private_key, str) or not private_key.strip():
            raise ValueError("config.privateKey is required for MTLS")
    # Unknown auth_type (legacy): allow config as object, no strict validation
    return config


def _auth_profile_to_dto(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize vendor_auth_profile row to AuthProfileItem DTO (camelCase, ISO8601 dates)."""
    created = row.get("created_at")
    updated = row.get("updated_at")
    return {
        "id": str(row["id"]) if row.get("id") else None,
        "vendorCode": row.get("vendor_code") or "",
        "name": row.get("profile_name") or row.get("name") or "",
        "authType": row.get("auth_type") or "",
        "config": row.get("config") if isinstance(row.get("config"), dict) else {},
        "isDefault": bool(row.get("is_default", False)),
        "isActive": bool(row.get("is_active", True)),
        "createdAt": created.isoformat() if hasattr(created, "isoformat") else str(created) if created else None,
        "updatedAt": updated.isoformat() if hasattr(updated, "isoformat") else str(updated) if updated else None,
    }


# --- Auth diagnostics helpers ---


def _ssrf_dev_allowed() -> bool:
    return (os.environ.get("ALLOW_SSRF_DEV") or "").strip().lower() in ("1", "true", "yes")


def _normalize_test_auth_type(value: str | None) -> str:
    t = (value or "").strip().upper()
    t = AUTH_PROFILE_TYPE_ALIASES.get(t, t)
    if t not in ("API_KEY_HEADER", "API_KEY_QUERY", "BASIC", "BEARER", "JWT", "JWT_BEARER_TOKEN", "MTLS"):
        raise ValueError("authType must be one of API_KEY_HEADER, API_KEY_QUERY, BASIC, BEARER, JWT_BEARER_TOKEN, MTLS")
    return t


def _normalize_test_timeout(timeout_ms: Any) -> int:
    if timeout_ms is None:
        return DEFAULT_TEST_TIMEOUT_MS
    try:
        n = int(timeout_ms)
    except (TypeError, ValueError):
        raise ValueError("timeoutMs must be an integer")
    if n < 1:
        raise ValueError("timeoutMs must be >= 1")
    return min(n, MAX_TEST_TIMEOUT_MS)


def _redact_token(value: str) -> str:
    s = str(value or "")
    if len(s) <= 18:
        return "***REDACTED***"
    return f"{s[:12]}...{s[-6:]}"


def _redact_header_value(header_name: str, value: str) -> str:
    name = (header_name or "").strip().lower()
    if name in {"authorization", "proxy-authorization"}:
        if value.lower().startswith("bearer "):
            return "Bearer ***REDACTED***"
        if value.lower().startswith("basic "):
            return "Basic ***REDACTED***"
        return "***REDACTED***"
    if "token" in name or "secret" in name or "key" in name or "password" in name:
        return "***REDACTED***"
    return value


def _normalize_preview_body(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, str):
        return body[:MAX_TEST_RESPONSE_PREVIEW]
    try:
        return json.dumps(body, default=str)[:MAX_TEST_RESPONSE_PREVIEW]
    except Exception:
        return str(body)[:MAX_TEST_RESPONSE_PREVIEW]


def _is_private_or_local_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _validate_outbound_test_target(url: str) -> tuple[bool, str | None]:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").strip()
    scheme = (parsed.scheme or "").lower()
    if not host:
        return False, "Target URL must include a host"
    if not _ssrf_dev_allowed() and scheme != "https":
        return False, "Only HTTPS targets are allowed"
    host_lower = host.lower()
    if not _ssrf_dev_allowed() and host_lower in {"localhost", "127.0.0.1", "::1"}:
        return False, "Target host is blocked by SSRF protection"
    try:
        addr_infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False, "Unable to resolve target host"
    if not _ssrf_dev_allowed():
        for info in addr_infos:
            addr = info[4][0]
            if _is_private_or_local_ip(addr):
                return False, "Target host is blocked by SSRF protection"
    return True, None


def _decode_jwt_claims_unsafe(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    pad = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + pad)
        claims = json.loads(decoded.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return claims if isinstance(claims, dict) else None


def _jwt_cache_key(token_url: str, client_id: str, scope: str | None) -> str:
    raw = f"{token_url}|{client_id}|{scope or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fetch_jwt_preview_token(config: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    token_url = str(config.get("tokenUrl") or "").strip()
    client_id = str(config.get("clientId") or "").strip()
    client_secret = str(config.get("clientSecret") or "").strip()
    scope = str(config.get("scope") or "").strip()
    if not token_url or not client_id or not client_secret:
        raise ValueError("tokenUrl, clientId, and clientSecret are required")

    cache_key = _jwt_cache_key(token_url, client_id, scope or None)
    now = datetime.now(UTC)
    cached = _jwt_preview_cache.get(cache_key)
    if cached:
        expires_at = cached.get("expiresAt")
        if isinstance(expires_at, datetime) and expires_at > now:
            return {
                "accessToken": cached.get("accessToken") or "",
                "expiresIn": int(cached.get("expiresIn") or JWT_PREVIEW_DEFAULT_EXPIRES_IN),
                "cacheDiagnostics": {
                    "cacheKeyHash": cache_key,
                    "expiresAt": expires_at.isoformat(),
                    "lastFetchedAt": cached.get("lastFetchedAt").isoformat() if isinstance(cached.get("lastFetchedAt"), datetime) else None,
                    "fromCache": True,
                },
            }

    form = {"grant_type": "client_credentials"}
    if scope:
        form["scope"] = scope
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode("ascii")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {basic}",
    }
    timeout_sec = min(max(timeout_ms / 1000.0, 0.1), MAX_TEST_TIMEOUT_MS / 1000.0)
    resp = requests.post(
        token_url,
        data=urllib.parse.urlencode(form),
        headers=headers,
        timeout=timeout_sec,
        allow_redirects=False,
    )
    if resp.status_code in (401, 403):
        raise PermissionError("Token endpoint rejected credentials")
    if resp.status_code >= 400:
        raise RuntimeError(f"Token endpoint error: HTTP {resp.status_code}")
    payload = resp.json()
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("Token endpoint did not return access_token")
    expires_in = payload.get("expires_in")
    try:
        expires_in_int = int(expires_in) if expires_in is not None else JWT_PREVIEW_DEFAULT_EXPIRES_IN
    except (TypeError, ValueError):
        expires_in_int = JWT_PREVIEW_DEFAULT_EXPIRES_IN
    refresh_delta = max(0, expires_in_int - JWT_PREVIEW_REFRESH_MARGIN_SEC)
    expires_at = datetime.fromtimestamp(now.timestamp() + refresh_delta, tz=UTC)
    fetched_at = datetime.now(UTC)
    _jwt_preview_cache[cache_key] = {
        "accessToken": access_token,
        "expiresIn": expires_in_int,
        "expiresAt": expires_at,
        "lastFetchedAt": fetched_at,
    }
    return {
        "accessToken": access_token,
        "expiresIn": expires_in_int,
        "cacheDiagnostics": {
            "cacheKeyHash": cache_key,
            "expiresAt": expires_at.isoformat(),
            "lastFetchedAt": fetched_at.isoformat(),
            "fromCache": False,
        },
    }


def _safe_request_headers(input_headers: Any) -> dict[str, str]:
    if not isinstance(input_headers, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in input_headers.items():
        name = str(k or "").strip()
        if not name:
            continue
        lower = name.lower()
        if lower in ("authorization", "proxy-authorization"):
            continue
        out[name] = str(v)[:512]
    return out


def _build_test_auth_parts(auth_type: str, auth_config: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    headers: dict[str, str] = {}
    query: dict[str, str] = {}
    resolved_headers_redacted: dict[str, str] = {}
    resolved_query_redacted: dict[str, str] = {}
    client_cert: tuple[str, str] | None = None

    if auth_type == "API_KEY_HEADER":
        header_name = str(auth_config.get("headerName") or "Api-Key").strip() or "Api-Key"
        key_value = str(auth_config.get("key") or auth_config.get("value") or "").strip()
        if not key_value:
            raise ValueError("authConfig.key is required for API_KEY_HEADER")
        headers[header_name] = key_value
        resolved_headers_redacted[header_name] = "***REDACTED***"
    elif auth_type == "API_KEY_QUERY":
        param_name = str(auth_config.get("paramName") or "api_key").strip() or "api_key"
        key_value = str(auth_config.get("key") or auth_config.get("value") or "").strip()
        if not key_value:
            raise ValueError("authConfig.key is required for API_KEY_QUERY")
        query[param_name] = key_value
        resolved_query_redacted[param_name] = "***REDACTED***"
    elif auth_type == "BASIC":
        username = str(auth_config.get("username") or "").strip()
        password = str(auth_config.get("password") or "").strip()
        if not username or not password:
            raise ValueError("authConfig.username and authConfig.password are required for BASIC")
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"
        resolved_headers_redacted["Authorization"] = "Basic ***REDACTED***"
    elif auth_type == "BEARER":
        token = str(auth_config.get("token") or "").strip()
        if not token:
            raise ValueError("authConfig.token is required for BEARER")
        headers["Authorization"] = f"Bearer {token}"
        resolved_headers_redacted["Authorization"] = "Bearer ***REDACTED***"
    elif auth_type == "JWT_BEARER_TOKEN":
        token_result = _fetch_jwt_preview_token(auth_config, timeout_ms)
        token = str(token_result.get("accessToken") or "").strip()
        headers["Authorization"] = f"Bearer {token}"
        resolved_headers_redacted["Authorization"] = "Bearer ***REDACTED***"
    elif auth_type == "MTLS":
        cert = str(auth_config.get("certificate") or auth_config.get("certPem") or "").strip()
        key = str(auth_config.get("privateKey") or auth_config.get("keyPem") or "").strip()
        if not cert or not key:
            raise ValueError("authConfig.certificate and authConfig.privateKey are required for MTLS")
        # requests supports cert path or (cert, key) tuple. Passing inline PEM here for diagnostics only.
        client_cert = (cert, key)

    return {
        "headers": headers,
        "query": query,
        "resolvedHeadersRedacted": resolved_headers_redacted,
        "resolvedQueryRedacted": resolved_query_redacted,
        "clientCert": client_cert,
    }


def _classify_test_error(exc: Exception, http_status: int | None = None) -> tuple[str, str]:
    if http_status in (401, 403):
        return "AUTH", "Authentication failed"
    if http_status and http_status >= 500:
        return "UPSTREAM", "Upstream service error"
    if isinstance(exc, requests.Timeout):
        return "TIMEOUT", "Request timed out"
    if isinstance(exc, requests.SSLError):
        return "TLS", "TLS handshake failed"
    if isinstance(exc, requests.ConnectionError):
        text = str(exc).lower()
        if "name or service not known" in text or "nodename nor servname provided" in text:
            return "DNS", "DNS resolution failed"
        return "UPSTREAM", "Connection failed"
    if isinstance(exc, PermissionError):
        return "AUTH", "Authentication failed"
    if isinstance(exc, ValueError):
        return "BLOCKED", str(exc)
    return "UNKNOWN", str(exc)[:240]

# --- Upserts ---


def _upsert_vendor(
    conn: Any,
    vendor_code: str,
    vendor_name: str,
    audit_actor: str,
    request_id: str,
) -> dict[str, Any]:
    """Upsert vendor. ON CONFLICT DO UPDATE."""
    q = sql.SQL(
        """
        INSERT INTO control_plane.vendors (vendor_code, vendor_name)
        VALUES (%s, %s)
        ON CONFLICT (vendor_code) DO UPDATE SET
            vendor_name = EXCLUDED.vendor_name,
            updated_at = now()
        RETURNING id, vendor_code, vendor_name, created_at, updated_at
        """
    )
    row = _execute_one(conn, q, (vendor_code, vendor_name))
    if row:
        _write_audit_event(
            conn,
            transaction_id=f"registry-{request_id}",
            action="vendor_upsert",
            vendor_code=audit_actor,
            details={
                "vendor_code": vendor_code,
                "vendor_name": vendor_name,
            },
        )
    assert row is not None
    return row


# Operation direction policy: direction is defined at operation level, not per rule.
OPERATION_DIRECTION_POLICY = ("PROVIDER_RECEIVES_ONLY", "TWO_WAY")
# Legacy values (migration v44 maps these to new values)
DIRECTION_POLICY_LEGACY_MAP = {
    "service_outbound_only": "PROVIDER_RECEIVES_ONLY",
    "exchange_bidirectional": "TWO_WAY",
}

OPERATION_AI_MODES = ("RAW_ONLY", "RAW_AND_FORMATTED")
OPERATION_AI_MODE_LEGACY_MAP = {
    "canonical_to_text": "RAW_AND_FORMATTED",
    "ai_summary_optional": "RAW_AND_FORMATTED",
    "ai_summary_default": "RAW_AND_FORMATTED",
}


def derive_flow_direction_for_operation(direction_policy: str | None) -> str:
    """
    Map an operation's direction policy to a default flow_direction for allowlist rows.

    - PROVIDER_RECEIVES_ONLY: callers send to the provider => OUTBOUND
    - TWO_WAY: either direction allowed => BOTH
    - None/empty/unknown: default to BOTH
    """
    if not direction_policy:
        return "BOTH"
    policy = direction_policy.strip().upper()
    if policy == "PROVIDER_RECEIVES_ONLY":
        return "OUTBOUND"
    if policy == "TWO_WAY":
        return "BOTH"
    return "BOTH"


class DirectionPolicyViolation(ValueError):
    """Raised when an allowlist rule conflicts with the operation's direction policy."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _get_operation_direction_policy(conn: Any, operation_code: str) -> str | None:
    """
    Fetch direction_policy for an operation.
    Returns normalized value: PROVIDER_RECEIVES_ONLY or TWO_WAY.
    Legacy values are mapped; NULL/unexpected -> TWO_WAY (with warning logged).
    """
    row = _execute_one(
        conn,
        sql.SQL(
            "SELECT direction_policy FROM control_plane.operations WHERE operation_code = %s"
        ),
        (operation_code.strip().upper(),),
    )
    if not row:
        return None
    raw = (row.get("direction_policy") or "").strip()
    if not raw:
        return "TWO_WAY"
    raw_lower = raw.lower()
    raw_upper = raw.upper()
    # Map legacy to new
    if raw_lower in DIRECTION_POLICY_LEGACY_MAP:
        return DIRECTION_POLICY_LEGACY_MAP[raw_lower]
    if raw_upper in OPERATION_DIRECTION_POLICY:
        return raw_upper
    log_json("WARN", "unexpected_direction_policy", operation_code=operation_code, value=raw)
    return "TWO_WAY"


def _validate_direction_policy_value(value: str | None) -> str | None:
    """Validate direction_policy for operations. Accepts PROVIDER_RECEIVES_ONLY, TWO_WAY, or legacy mapped values."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    s = value.strip()
    s_upper = s.upper()
    s_lower = s.lower()
    # New values
    if s_upper in OPERATION_DIRECTION_POLICY:
        return s_upper
    # Legacy values -> map to new
    if s_lower in DIRECTION_POLICY_LEGACY_MAP:
        return DIRECTION_POLICY_LEGACY_MAP[s_lower]
    raise ValueError(
        f"directionPolicy must be one of: {', '.join(OPERATION_DIRECTION_POLICY)}"
    )


def _validate_operation_ai_mode(value: str | None) -> str | None:
    """Validate and normalize ai_presentation_mode."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    s = value.strip()
    s_upper = s.upper()
    s_lower = s.lower()
    if s_upper in OPERATION_AI_MODES:
        return s_upper
    if s_lower in OPERATION_AI_MODE_LEGACY_MAP:
        return OPERATION_AI_MODE_LEGACY_MAP[s_lower]
    raise ValueError(
        f"aiPresentationMode must be one of: {', '.join(OPERATION_AI_MODES)}"
    )


def _upsert_operation(
    conn: Any,
    operation_code: str,
    description: str | None,
    canonical_version: str | None,
    is_async_capable: bool | None,
    is_active: bool | None,
    direction_policy: str | None,
    ai_presentation_mode: str | None,
    ai_formatter_prompt: str | None,
    ai_formatter_model: str | None,
    audit_actor: str,
    request_id: str,
) -> dict[str, Any]:
    """Upsert operation. ON CONFLICT DO UPDATE."""
    q = sql.SQL(
        """
        INSERT INTO control_plane.operations (
            operation_code, description, canonical_version, is_async_capable, is_active, direction_policy,
            ai_presentation_mode, ai_formatter_prompt, ai_formatter_model
        )
        VALUES (%s, %s, %s, COALESCE(%s, true), COALESCE(%s, true), %s, %s, %s, %s)
        ON CONFLICT (operation_code) DO UPDATE SET
            description = COALESCE(EXCLUDED.description, control_plane.operations.description),
            canonical_version = COALESCE(EXCLUDED.canonical_version, control_plane.operations.canonical_version),
            is_async_capable = COALESCE(EXCLUDED.is_async_capable, control_plane.operations.is_async_capable),
            is_active = COALESCE(EXCLUDED.is_active, control_plane.operations.is_active),
            direction_policy = COALESCE(EXCLUDED.direction_policy, control_plane.operations.direction_policy),
            ai_presentation_mode = COALESCE(EXCLUDED.ai_presentation_mode, control_plane.operations.ai_presentation_mode),
            ai_formatter_prompt = COALESCE(EXCLUDED.ai_formatter_prompt, control_plane.operations.ai_formatter_prompt),
            ai_formatter_model = COALESCE(EXCLUDED.ai_formatter_model, control_plane.operations.ai_formatter_model),
            updated_at = now()
        RETURNING id, operation_code, description, canonical_version, is_async_capable, is_active, direction_policy,
                  ai_presentation_mode, ai_formatter_prompt, ai_formatter_model, created_at, updated_at
        """
    )
    row = _execute_one(
        conn,
        q,
        (
            operation_code,
            description,
            canonical_version,
            is_async_capable,
            is_active,
            direction_policy,
            ai_presentation_mode,
            ai_formatter_prompt,
            ai_formatter_model,
        ),
    )
    if row:
        _write_audit_event(
            conn,
            transaction_id=f"registry-{request_id}",
            action="operation_upsert",
            vendor_code=audit_actor,
            details={
                "operation_code": operation_code,
                "description": description,
                "ai_presentation_mode": ai_presentation_mode,
            },
        )
    assert row is not None
    return row


def _validate_flow_direction(flow_direction: str | None) -> str:
    """
    Ensure flow_direction is one of INBOUND, OUTBOUND, BOTH (case-insensitive).
    None/"" is not allowed here; callers should handle defaulting separately.
    """
    if flow_direction is None:
        raise ValueError("flowDirection must be one of INBOUND, OUTBOUND, BOTH")
    value = flow_direction.strip().upper()
    if value in {"INBOUND", "OUTBOUND", "BOTH"}:
        return value
    raise ValueError("flowDirection must be one of INBOUND, OUTBOUND, BOTH")


def _parse_bool(v: Any) -> bool:
    """Parse bool from request body. Handles True, "true", None, missing."""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("true", "1", "yes")


def _upsert_allowlist(
    conn: Any,
    source_vendor_code: str,
    target_vendor_code: str,
    operation_code: str,
    flow_direction: str,
    audit_actor: str,
    request_id: str,
) -> dict[str, Any]:
    """Upsert explicit allowlist pair. ON CONFLICT DO NOTHING; return existing or inserted."""
    q = sql.SQL(
        """
        INSERT INTO control_plane.vendor_operation_allowlist
        (source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, rule_scope, flow_direction)
        VALUES (%s, %s, FALSE, FALSE, %s, 'admin', %s)
        ON CONFLICT (COALESCE(source_vendor_code, '*'), is_any_source, COALESCE(target_vendor_code, '*'), is_any_target, operation_code, rule_scope, flow_direction) DO NOTHING
        """
    )
    _execute_mutation(
        conn, q,
        (source_vendor_code, target_vendor_code, operation_code, flow_direction),
    )

    q2 = sql.SQL(
        """
        SELECT id, source_vendor_code, target_vendor_code, is_any_source, is_any_target, operation_code, flow_direction, created_at
        FROM control_plane.vendor_operation_allowlist
        WHERE source_vendor_code = %s AND target_vendor_code = %s AND operation_code = %s
          AND rule_scope = 'admin' AND flow_direction = %s
        """
    )
    row = _execute_one(conn, q2, (source_vendor_code, target_vendor_code, operation_code, flow_direction))
    if row:
        _write_audit_event(
            conn,
            transaction_id=f"registry-{request_id}",
            action="allowlist_upsert",
            vendor_code=audit_actor,
            details={
                "source_vendor_code": source_vendor_code,
                "target_vendor_code": target_vendor_code,
                "is_any_source": False,
                "is_any_target": False,
                "operation_code": operation_code,
            },
        )
    assert row is not None
    return row


def _delete_allowlist(conn: Any, entry_id: str) -> bool:
    """Delete allowlist entry by id. Returns True if deleted, False if not found."""
    import uuid as uuid_mod
    try:
        uuid_mod.UUID(entry_id)
    except (ValueError, TypeError):
        return False
    q = sql.SQL(
        """
        DELETE FROM control_plane.vendor_operation_allowlist
        WHERE id = %s
        """
    )
    with conn.cursor() as cur:
        cur.execute(q, (entry_id.strip(),))
        return cur.rowcount > 0


def _validate_endpoint_flow_direction(value: str | None) -> str:
    """Validate endpoint flow_direction: INBOUND or OUTBOUND. Default OUTBOUND."""
    if not value or not isinstance(value, str):
        return "OUTBOUND"
    fd = value.strip().upper()
    if fd not in ("INBOUND", "OUTBOUND"):
        raise ValueError(f"flowDirection must be INBOUND or OUTBOUND (got {value})")
    return fd


def _upsert_endpoint(
    conn: Any,
    vendor_code: str,
    operation_code: str,
    url: str,
    http_method: str | None,
    payload_format: str | None,
    timeout_ms: int | None,
    is_active: bool | None,
    audit_actor: str,
    request_id: str,
    auth_profile_id: str | None = None,
    flow_direction: str = "OUTBOUND",
) -> dict[str, Any]:
    """Upsert vendor_endpoints. ON CONFLICT DO UPDATE. Matches v35 partial unique (vendor_code, operation_code, flow_direction) WHERE is_active."""
    q = sql.SQL(
        """
        INSERT INTO control_plane.vendor_endpoints (
            vendor_code, operation_code, flow_direction, url, http_method, payload_format, timeout_ms, is_active, vendor_auth_profile_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, COALESCE(%s, true), %s::uuid)
        ON CONFLICT (vendor_code, operation_code, flow_direction) WHERE is_active = true DO UPDATE SET
            url = EXCLUDED.url,
            http_method = COALESCE(EXCLUDED.http_method, control_plane.vendor_endpoints.http_method),
            payload_format = COALESCE(EXCLUDED.payload_format, control_plane.vendor_endpoints.payload_format),
            timeout_ms = COALESCE(EXCLUDED.timeout_ms, control_plane.vendor_endpoints.timeout_ms),
            is_active = COALESCE(EXCLUDED.is_active, control_plane.vendor_endpoints.is_active),
            vendor_auth_profile_id = EXCLUDED.vendor_auth_profile_id,
            updated_at = now()
        RETURNING id, vendor_code, operation_code, flow_direction, url, http_method, payload_format, timeout_ms, is_active, vendor_auth_profile_id, created_at, updated_at
        """
    )
    row = _execute_one(
        conn,
        q,
        (
            vendor_code,
            operation_code,
            flow_direction,
            url,
            http_method,
            payload_format,
            timeout_ms,
            is_active,
            auth_profile_id,
        ),
    )
    if row:
        _write_audit_event(
            conn,
            transaction_id=f"registry-{request_id}",
            action="ENDPOINT_UPSERT",
            vendor_code=audit_actor,
            details={
                "vendorCode": vendor_code,
                "operationCode": operation_code,
                "url": url,
                "http_method": http_method,
                "payload_format": payload_format,
                "timeout_ms": timeout_ms,
            },
        )
        _publish_endpoint_upserted(
            vendor_code=vendor_code,
            operation_code=operation_code,
            url=url,
            http_method=http_method,
            payload_format=payload_format,
            timeout_ms=timeout_ms,
        )
    assert row is not None
    return row


# --- Auth Profiles ---


def _list_auth_profiles(
    conn: Any,
    *,
    vendor_code: str | None = None,
    is_active: bool | None = None,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """List auth profiles. vendor_code and is_active optional. Returns (items, next_cursor)."""
    conditions: list[sql.Composable] = []
    params: list[Any] = []
    if vendor_code:
        conditions.append(sql.SQL("vendor_code = %s"))
        params.append(vendor_code)
    if is_active is not None:
        conditions.append(sql.SQL("COALESCE(is_active, true) = %s"))
        params.append(is_active)

    decoded = _decode_cursor(cursor) if cursor else None
    if decoded:
        conditions.append(sql.SQL("(created_at, id) < (%s::timestamptz, %s::uuid)"))
        params.extend(decoded)

    where = sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("true")
    params.append(limit + 1)

    q = sql.SQL(
        """
        SELECT id, vendor_code, profile_name, auth_type, config, is_default, is_active, created_at, updated_at
        FROM control_plane.vendor_auth_profiles
        WHERE {}
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """
    ).format(where)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, tuple(params))
        rows = cur.fetchall()

    items: list[dict[str, Any]] = []
    next_cursor: str | None = None
    for i, r in enumerate(rows):
        if i >= limit:
            next_cursor = _encode_cursor(r["created_at"], r["id"])
            break
        items.append(_auth_profile_to_dto(dict(r)))
    return items, next_cursor


def _upsert_auth_profile(
    conn: Any,
    vendor_code: str,
    name: str,
    auth_type: str,
    config: dict[str, Any],
    is_active: bool | None,
    audit_actor: str,
    request_id: str,
    profile_id: str | None = None,
    is_default: bool | None = None,
) -> dict[str, Any]:
    """Create or update auth_profile. If profile_id provided, update by id; else insert."""
    is_active_val = is_active if is_active is not None else True
    is_default_val = is_default if is_default is not None else False
    if profile_id and str(profile_id).strip():
        q = sql.SQL(
            """
            UPDATE control_plane.vendor_auth_profiles
            SET vendor_code = %s, profile_name = %s, auth_type = %s, config = %s::jsonb, is_default = %s, is_active = %s, updated_at = now()
            WHERE id = %s::uuid
            RETURNING id, vendor_code, profile_name, auth_type, config, is_default, is_active, created_at, updated_at
            """
        )
        row = _execute_one(
            conn,
            q,
            (vendor_code, name, auth_type, json.dumps(config), is_default_val, is_active_val, profile_id.strip()),
        )
    else:
        q = sql.SQL(
            """
            INSERT INTO control_plane.vendor_auth_profiles (vendor_code, profile_name, auth_type, config, is_default, is_active)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (vendor_code, profile_name) DO UPDATE SET
                auth_type = EXCLUDED.auth_type,
                config = EXCLUDED.config,
                is_default = EXCLUDED.is_default,
                is_active = EXCLUDED.is_active,
                updated_at = now()
            RETURNING id, vendor_code, profile_name, auth_type, config, is_default, is_active, created_at, updated_at
            """
        )
        row = _execute_one(
            conn,
            q,
            (vendor_code, name, auth_type, json.dumps(config), is_default_val, is_active_val),
        )
    if row:
        _write_audit_event(
            conn,
            transaction_id=f"registry-{request_id}",
            action="auth_profile_upsert",
            vendor_code=audit_actor,
            details={
                "authType": auth_type,
                "authProfileId": str(row["id"]),
                "vendorCode": vendor_code,
                "name": name,
            },
        )
    assert row is not None
    return _auth_profile_to_dto(row)


def _patch_auth_profile(
    conn: Any,
    profile_id: str,
    vendor_code: str,
    *,
    is_active: bool | None = None,
    config: dict[str, Any] | None = None,
    is_default: bool | None = None,
    audit_actor: str,
    request_id: str,
) -> dict[str, Any] | None:
    """Patch auth profile by id. Validates vendor_code ownership. Returns DTO or None."""
    row = _execute_one(
        conn,
        sql.SQL(
            """
            SELECT id, vendor_code, profile_name, auth_type, config, is_default, is_active, created_at, updated_at
            FROM control_plane.vendor_auth_profiles
            WHERE id = %s::uuid AND vendor_code = %s
            """
        ),
        (profile_id, vendor_code),
    )
    if not row:
        return None
    updates: list[str] = ["updated_at = now()"]
    vals: list[Any] = []
    if is_active is not None:
        updates.append("is_active = %s")
        vals.append(is_active)
    if config is not None:
        updates.append("config = %s::jsonb")
        vals.append(json.dumps(config))
    if is_default is not None:
        updates.append("is_default = %s")
        vals.append(is_default)
    if len(vals) == 0:
        return _auth_profile_to_dto(row)
    vals.extend([profile_id, vendor_code])
    q = sql.SQL(
        """
        UPDATE control_plane.vendor_auth_profiles
        SET {}
        WHERE id = %s::uuid AND vendor_code = %s
        RETURNING id, vendor_code, profile_name, auth_type, config, is_default, is_active, created_at, updated_at
        """
    ).format(sql.SQL(", ").join(sql.SQL(u) for u in updates))
    updated = _execute_one(conn, q, tuple(vals))
    if updated:
        _write_audit_event(
            conn,
            transaction_id=f"registry-{request_id}",
            action="auth_profile_upsert",
            vendor_code=audit_actor,
            details={
                "authType": updated.get("auth_type"),
                "authProfileId": str(updated["id"]),
                "vendorCode": vendor_code,
            },
        )
        return _auth_profile_to_dto(updated)
    return None


def _soft_delete_auth_profile(conn: Any, profile_id: str) -> dict[str, Any] | None:
    """Soft delete: set is_active=false. Returns updated row or None if not found."""
    q = sql.SQL(
        """
        UPDATE control_plane.vendor_auth_profiles
        SET is_active = false, updated_at = now()
        WHERE id = %s::uuid
        RETURNING id, is_active, updated_at
        """
    )
    row = _execute_one(conn, q, (profile_id.strip(),))
    return dict(row) if row else None


def _get_auth_profile_for_vendor(
    conn: Any,
    auth_profile_id: str,
    vendor_code: str,
    require_active: bool = True,
) -> dict[str, Any] | None:
    """
    Get auth profile by id if it belongs to vendor_code.
    When require_active=True (default), only returns row if is_active is true.
    Returns row or None.
    """
    if require_active:
        q = sql.SQL(
            """
            SELECT id, vendor_code, profile_name, auth_type, config, is_default, is_active
            FROM control_plane.vendor_auth_profiles
            WHERE id = %s::uuid AND vendor_code = %s AND COALESCE(is_active, true)
            """
        )
    else:
        q = sql.SQL(
            """
            SELECT id, vendor_code, profile_name, auth_type, config, is_default, is_active
            FROM control_plane.vendor_auth_profiles
            WHERE id = %s::uuid AND vendor_code = %s
            """
        )
    return _execute_one(conn, q, (auth_profile_id, vendor_code))


# --- Response helpers ---


def _success(status: int, data: dict[str, Any]) -> dict[str, Any]:
    """Build canonical success response with CORS headers."""
    return add_cors_to_response(canonical_ok(data, status))


def _error(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build canonical error response with CORS headers."""
    return add_cors_to_response(canonical_error(code, message, status, details))


# --- Canonical Contracts API ---


def _get_contract(
    conn: Any,
    operation_code: str,
    canonical_version: str,
) -> dict[str, Any] | None:
    """
    Get active contract for (operation_code, canonical_version).
    Requires both operation and contract to exist and be active.
    Returns None if not found.
    """
    q = sql.SQL(
        """
        SELECT oc.operation_code, oc.canonical_version, oc.request_schema, oc.is_active
        FROM control_plane.operation_contracts oc
        JOIN control_plane.operations o ON o.operation_code = oc.operation_code AND COALESCE(o.is_active, true)
        WHERE oc.operation_code = %s
          AND oc.canonical_version = %s
          AND oc.is_active = true
        ORDER BY oc.updated_at DESC NULLS LAST
        LIMIT 1
        """
    )
    row = _execute_one(conn, q, (operation_code, canonical_version))
    return row


def _list_operation_contracts(
    conn: Any,
    *,
    limit: int = DEFAULT_LIMIT,
    operation_code: str | None = None,
    canonical_version: str | None = None,
    is_active: bool | None = None,
) -> list[dict[str, Any]]:
    """List operation_contracts with optional filters. Sorted by updated_at DESC."""
    conditions: list[sql.Composable] = []
    params: list[Any] = []

    if operation_code:
        conditions.append(sql.SQL("operation_code = %s"))
        params.append(operation_code)
    if canonical_version:
        conditions.append(sql.SQL("canonical_version = %s"))
        params.append(canonical_version)
    if is_active is not None:
        conditions.append(sql.SQL("COALESCE(is_active, true) = %s"))
        params.append(is_active)

    where = sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("true")
    params.append(limit)

    q = sql.SQL(
        """
        SELECT id, operation_code, canonical_version, request_schema, response_schema,
               COALESCE(is_active, true) AS is_active, created_at, updated_at
        FROM control_plane.operation_contracts
        WHERE {}
        ORDER BY updated_at DESC NULLS LAST, id DESC
        LIMIT %s
        """
    ).format(where)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, tuple(params))
        rows = cur.fetchall()

    return [
        _to_camel_case_dict({
            "id": str(r["id"]) if r.get("id") else None,
            "operation_code": r["operation_code"],
            "canonical_version": r["canonical_version"],
            "request_schema": r["request_schema"],
            "response_schema": r.get("response_schema"),
            "is_active": bool(r.get("is_active", True)),
            "created_at": str(r["created_at"]) if r.get("created_at") else None,
            "updated_at": str(r["updated_at"]) if r.get("updated_at") else None,
        })
        for r in rows
    ]


def _upsert_operation_contract(
    conn: Any,
    operation_code: str,
    canonical_version: str,
    request_schema: dict[str, Any],
    response_schema: dict[str, Any] | None,
    is_active: bool,
    audit_actor: str,
    request_id: str,
) -> dict[str, Any]:
    """Upsert canonical contract. Uses SELECT-then-UPDATE-or-INSERT (no ON CONFLICT) because
    the DB has a partial unique index UNIQUE (operation_code, canonical_version) WHERE is_active = true.
    """
    req_json = json.dumps(request_schema)
    resp_json = json.dumps(response_schema) if response_schema is not None else None

    # 1. Look up existing active row
    q_find = sql.SQL(
        """
        SELECT id FROM control_plane.operation_contracts
        WHERE operation_code = %s AND canonical_version = %s AND is_active = true
        """
    )
    existing = _execute_one(conn, q_find, (operation_code, canonical_version))

    if existing:
        # 2a. Update existing active row
        q_update = sql.SQL(
            """
            UPDATE control_plane.operation_contracts
            SET request_schema = %s::jsonb, response_schema = %s::jsonb, updated_at = now()
            WHERE id = %s
            RETURNING id, operation_code, canonical_version, request_schema, response_schema,
                      is_active, created_at, updated_at
            """
        )
        row = _execute_one(conn, q_update, (req_json, resp_json, existing["id"]))
    else:
        # 2b. No active row: mark any previous rows inactive, then insert
        q_deactivate = sql.SQL(
            """
            UPDATE control_plane.operation_contracts
            SET is_active = false, updated_at = now()
            WHERE operation_code = %s AND canonical_version = %s AND is_active = true
            """
        )
        _execute_mutation(conn, q_deactivate, (operation_code, canonical_version))

        q_insert = sql.SQL(
            """
            INSERT INTO control_plane.operation_contracts (
                id, operation_code, canonical_version, request_schema, response_schema,
                is_active, created_at, updated_at
            )
            VALUES (gen_random_uuid(), %s, %s, %s::jsonb, %s::jsonb, true, now(), now())
            RETURNING id, operation_code, canonical_version, request_schema, response_schema,
                      is_active, created_at, updated_at
            """
        )
        row = _execute_one(conn, q_insert, (operation_code, canonical_version, req_json, resp_json))

    if row:
        _write_audit_event(
            conn,
            transaction_id=f"registry-{request_id}",
            action="canonical_contract_upsert",
            vendor_code=audit_actor,
            details={"operation_code": operation_code, "canonical_version": canonical_version, "is_active": row.get("is_active", True)},
        )
    assert row is not None
    return _to_camel_case_dict(dict(row))


def _handle_get_contracts(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/registry/contracts?operationCode=&canonicalVersion=&isActive= (all optional). Returns {contracts} sorted by updated_at desc."""
    try:
        qp = _parse_query_params(event)
        lp = _parse_list_params(qp)
        if lp.get("operation_code"):
            lp["operation_code"] = _validate_operation_code(lp["operation_code"])
        if lp.get("canonical_version"):
            cv = _validate_optional_str(lp["canonical_version"], "canonicalVersion", 32)
            if cv:
                lp["canonical_version"] = cv
        with _get_connection() as conn:
            contracts = _list_operation_contracts(
                conn,
                limit=lp["limit"],
                operation_code=lp.get("operation_code"),
                canonical_version=lp.get("canonical_version"),
                is_active=lp.get("is_active"),
            )
            return _success(200, {"contracts": contracts})
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_post_contracts(event: dict[str, Any]) -> dict[str, Any]:
    """POST /v1/registry/contracts - upsert canonical contract."""
    body = _parse_body(event.get("body"))
    req_ctx = event.get("requestContext") or {}
    request_id = req_ctx.get("requestId") or str(uuid.uuid4())
    audit_actor = _get_audit_actor(event)

    operation_code_raw = body.get("operationCode") or body.get("operation_code")
    canonical_version_raw = body.get("canonicalVersion") or body.get("canonical_version")
    request_schema = body.get("requestSchema") or body.get("request_schema")
    response_schema = body.get("responseSchema") or body.get("response_schema")
    is_active = body.get("isActive")
    if is_active is None:
        is_active = body.get("is_active")
    if is_active is None:
        is_active = True
    elif not isinstance(is_active, bool):
        is_active = str(is_active).lower() in ("true", "1", "yes")

    if not operation_code_raw or (isinstance(operation_code_raw, str) and not operation_code_raw.strip()):
        return _error(400, "VALIDATION_ERROR", "operationCode is required")
    if not canonical_version_raw or (isinstance(canonical_version_raw, str) and not canonical_version_raw.strip()):
        return _error(400, "VALIDATION_ERROR", "canonicalVersion is required")
    if not request_schema or not isinstance(request_schema, dict):
        return _error(400, "VALIDATION_ERROR", "requestSchema must be a JSON object")

    if response_schema is not None and not isinstance(response_schema, dict):
        return _error(400, "VALIDATION_ERROR", "responseSchema must be a JSON object or null")

    try:
        operation_code = _validate_operation_code(operation_code_raw)
        canonical_version = str(canonical_version_raw).strip()
        if not canonical_version or len(canonical_version) > 32:
            return _error(400, "VALIDATION_ERROR", "canonicalVersion must be 1-32 chars")

        with _get_connection() as conn:
            row = _upsert_operation_contract(
                conn,
                operation_code=operation_code,
                canonical_version=canonical_version,
                request_schema=request_schema,
                response_schema=response_schema,
                is_active=is_active,
                audit_actor=audit_actor,
                request_id=request_id,
            )
            return _success(200, {"contract": row})
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _parse_body(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    """Parse request body to dict."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


def _normalize_event(event: dict[str, Any]) -> None:
    """Normalize HTTP API v2 payload."""
    if "httpMethod" not in event and "requestContext" in event:
        http = event.get("requestContext", {}).get("http", {})
        event["httpMethod"] = http.get("method", "").upper()
    path = event.get("path") or event.get("rawPath") or ""
    if not event.get("path") and event.get("rawPath"):
        event["path"] = path
    # Strip optional stage prefix (e.g. /prod/v1/registry/... -> /v1/registry/...)
    segments = [s for s in path.strip("/").split("/") if s]
    if len(segments) >= 2 and segments[1] == "v1" and segments[0] != "v1":
        event["path"] = "/" + "/".join(segments[1:])


def _parse_query_params(event: dict[str, Any]) -> dict[str, str]:
    """Parse queryStringParameters into a simple dict (lowercased keys)."""
    params = event.get("queryStringParameters") or {}
    if not isinstance(params, dict):
        return {}
    return {k.lower(): (v if isinstance(v, str) else str(v)) for k, v in params.items()}


def _snake_to_camel(key: str) -> str:
    """Convert snake_case to camelCase."""
    parts = key.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def _to_camel_case_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Convert dict keys from snake_case to camelCase."""
    return {_snake_to_camel(k): v for k, v in row.items()}


def _encode_cursor(created_at: Any, row_id: Any) -> str:
    """Encode cursor as base64(created_at_iso|id)."""
    ts = str(created_at) if created_at is not None else ""
    rid = str(row_id) if row_id is not None else ""
    raw = f"{ts}|{rid}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str] | None:
    """Decode cursor to (created_at_iso, id). Returns None if invalid."""
    if not cursor or not cursor.strip():
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        parts = raw.split("|", 1)
        if len(parts) != 2:
            return None
        return (parts[0].strip(), parts[1].strip())
    except Exception:
        return None


def _parse_list_params(qp: dict[str, str]) -> dict[str, Any]:
    """
    Parse list query params: limit, cursor, vendorCode, operationCode,
    sourceVendorCode, targetVendorCode, isActive.
    Returns validated dict. Raises ValueError on invalid values.
    """
    def _int(name: str, default: int, lo: int, hi: int) -> int:
        v = qp.get(name, "").strip()
        if not v:
            return default
        try:
            n = int(v)
        except ValueError:
            raise ValueError(f"{name} must be a valid integer") from None
        if n < lo or n > hi:
            raise ValueError(f"{name} must be between {lo} and {hi}")
        return n

    def _bool(name: str, default: bool | None = None) -> bool | None:
        v = qp.get(name, "").strip().lower()
        if not v:
            return default
        if v in ("true", "1", "yes"):
            return True
        if v in ("false", "0", "no"):
            return False
        raise ValueError(f"{name} must be true or false")

    def _opt_str(name: str) -> str | None:
        v = qp.get(name, "").strip()
        return v if v else None

    limit = _int("limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
    cursor = _opt_str("cursor")
    vendor_code = _opt_str("vendorcode")
    operation_code = _opt_str("operationcode")
    source_vendor_code = _opt_str("sourcevendorcode") or _opt_str("sourcevendor")
    target_vendor_code = _opt_str("targetvendorcode") or _opt_str("targetvendor")
    canonical_version = _opt_str("canonicalversion")
    is_active = _bool("isactive")

    return {
        "limit": limit,
        "cursor": cursor,
        "vendor_code": vendor_code,
        "operation_code": operation_code,
        "canonical_version": canonical_version,
        "source_vendor_code": source_vendor_code,
        "target_vendor_code": target_vendor_code,
        "is_active": is_active,
    }


def _list_vendors(
    conn: Any,
    *,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
    vendor_code: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """List vendors with filters and cursor pagination. Returns (items, next_cursor)."""
    conditions: list[sql.Composable] = []
    params: list[Any] = []

    if vendor_code:
        conditions.append(sql.SQL("vendor_code = %s"))
        params.append(vendor_code)
    if is_active is not None:
        conditions.append(sql.SQL("COALESCE(is_active, true) = %s"))
        params.append(is_active)

    decoded = _decode_cursor(cursor) if cursor else None
    if decoded:
        conditions.append(sql.SQL("(created_at, id) < (%s::timestamptz, %s::uuid)"))
        params.extend(decoded)

    where = sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("true")
    params.append(limit + 1)

    q = sql.SQL(
        """
        SELECT id, vendor_code, vendor_name, COALESCE(is_active, true) AS is_active,
               created_at, updated_at
        FROM control_plane.vendors
        WHERE {}
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """
    ).format(where)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, tuple(params))
        rows = cur.fetchall()

    items: list[dict[str, Any]] = []
    next_cursor: str | None = None
    for i, r in enumerate(rows):
        if i >= limit:
            next_cursor = _encode_cursor(r["created_at"], r["id"])
            break
        items.append(_to_camel_case_dict({
            "id": str(r["id"]) if r.get("id") else None,
            "vendor_code": r["vendor_code"],
            "vendor_name": r["vendor_name"],
            "is_active": bool(r.get("is_active", True)),
            "created_at": str(r["created_at"]) if r.get("created_at") else None,
            "updated_at": str(r["updated_at"]) if r.get("updated_at") else None,
        }))
    return items, next_cursor


def _list_allowlist(
    conn: Any,
    *,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
    source_vendor_code: str | None = None,
    target_vendor_code: str | None = None,
    operation_code: str | None = None,
    vendor_code: str | None = None,
    scope: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """List allowlist entries with filters and cursor pagination. Returns (items, next_cursor)."""
    conditions: list[sql.Composable] = []
    params: list[Any] = []

    if source_vendor_code:
        conditions.append(sql.SQL("source_vendor_code = %s"))
        params.append(source_vendor_code)
    if target_vendor_code:
        conditions.append(sql.SQL("target_vendor_code = %s"))
        params.append(target_vendor_code)
    if operation_code:
        conditions.append(sql.SQL("operation_code = %s"))
        params.append(operation_code)
    if vendor_code:
        conditions.append(sql.SQL("(source_vendor_code = %s OR target_vendor_code = %s)"))
        params.append(vendor_code)
        params.append(vendor_code)

    if scope == "global":
        conditions.append(sql.SQL("LOWER(COALESCE(rule_scope, 'admin')) = 'admin'"))
    elif scope == "vendor_specific":
        conditions.append(sql.SQL("LOWER(COALESCE(rule_scope, 'admin')) = 'vendor'"))

    decoded = _decode_cursor(cursor) if cursor else None
    if decoded:
        conditions.append(sql.SQL("(created_at, id) < (%s::timestamptz, %s::uuid)"))
        params.extend(decoded)

    sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("true")
    params.append(limit + 1)

    # Include rule_scope and flow_direction for UI grouping; filter admin-only by default
    base_conds = list(conditions) if conditions else []
    base_params = list(params)
    base_conds.append(sql.SQL("(COALESCE(rule_scope, 'admin') = 'admin')"))
    base_where = sql.SQL(" AND ").join(base_conds)
    # params already has limit+1; base_params is a copy

    q = sql.SQL(
        """
        SELECT id, source_vendor_code, target_vendor_code, is_any_source, is_any_target,
               operation_code, rule_scope, flow_direction, created_at
        FROM control_plane.vendor_operation_allowlist
        WHERE {}
        ORDER BY operation_code ASC, flow_direction ASC, created_at DESC, id DESC
        LIMIT %s
        """
    ).format(base_where)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, tuple(base_params))
        rows = cur.fetchall()

    items: list[dict[str, Any]] = []
    next_cursor: str | None = None
    for i, r in enumerate(rows):
        if i >= limit:
            next_cursor = _encode_cursor(r["created_at"], r["id"])
            break
        is_any_src = bool(r.get("is_any_source"))
        is_any_tgt = bool(r.get("is_any_target"))
        is_global = (r.get("rule_scope") or "admin") == "admin"
        items.append(_to_camel_case_dict({
            "id": str(r["id"]) if r.get("id") else None,
            "source_vendor_code": r["source_vendor_code"],
            "target_vendor_code": r["target_vendor_code"],
            "is_any_source": is_any_src,
            "is_any_target": is_any_tgt,
            "operation_code": r["operation_code"],
            "rule_scope": r.get("rule_scope") or "admin",
            "flow_direction": r.get("flow_direction") or "BOTH",
            "created_at": str(r["created_at"]) if r.get("created_at") else None,
            "is_global": is_global,
        }))
    return items, next_cursor


def _list_endpoints(
    conn: Any,
    *,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
    vendor_code: str | None = None,
    operation_code: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """List endpoints with filters and cursor pagination. Returns (items, next_cursor)."""
    conditions: list[sql.Composable] = []
    params: list[Any] = []

    if vendor_code:
        conditions.append(sql.SQL("vendor_code = %s"))
        params.append(vendor_code)
    if operation_code:
        conditions.append(sql.SQL("operation_code = %s"))
        params.append(operation_code)
    if is_active is not None:
        conditions.append(sql.SQL("COALESCE(is_active, true) = %s"))
        params.append(is_active)

    decoded = _decode_cursor(cursor) if cursor else None
    if decoded:
        conditions.append(sql.SQL("(created_at, id) < (%s::timestamptz, %s::uuid)"))
        params.extend(decoded)

    where = sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("true")
    params.append(limit + 1)

    q = sql.SQL(
        """
        SELECT id, vendor_code, operation_code, url, http_method, payload_format,
               timeout_ms, COALESCE(is_active, true) AS is_active, vendor_auth_profile_id, created_at, updated_at
        FROM control_plane.vendor_endpoints
        WHERE {}
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """
    ).format(where)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, tuple(params))
        rows = cur.fetchall()

    items: list[dict[str, Any]] = []
    next_cursor: str | None = None
    for i, r in enumerate(rows):
        if i >= limit:
            next_cursor = _encode_cursor(r["created_at"], r["id"])
            break
        items.append(_to_camel_case_dict({
            "id": str(r["id"]) if r.get("id") else None,
            "vendor_code": r["vendor_code"],
            "operation_code": r["operation_code"],
            "url": r["url"],
            "http_method": r.get("http_method") or "POST",
            "payload_format": r.get("payload_format"),
            "timeout_ms": r.get("timeout_ms"),
            "is_active": bool(r.get("is_active", True)),
            "vendor_auth_profile_id": str(r["vendor_auth_profile_id"]) if r.get("vendor_auth_profile_id") else None,
            "auth_profile_id": str(r["vendor_auth_profile_id"]) if r.get("vendor_auth_profile_id") else None,
            "created_at": str(r["created_at"]) if r.get("created_at") else None,
            "updated_at": str(r["updated_at"]) if r.get("updated_at") else None,
        }))
    return items, next_cursor


def _list_operations(
    conn: Any,
    *,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
    operation_code: str | None = None,
    is_active: bool | None = None,
    source_vendor: str | None = None,
    target_vendor: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    List operations with filters and cursor pagination. When source_vendor and target_vendor
    provided, filter by allowlist. Returns (items, next_cursor).
    """
    conditions: list[sql.Composable] = []
    params: list[Any] = []
    base_from = sql.SQL("FROM control_plane.operations o")

    if source_vendor and target_vendor:
        # Explicit pair allowlist only.
        conditions.append(
            sql.SQL(
                "EXISTS (SELECT 1 FROM control_plane.vendor_operation_allowlist a "
                "WHERE a.operation_code = o.operation_code "
                "AND a.source_vendor_code = %s "
                "AND a.target_vendor_code = %s)"
            )
        )
        params.extend([source_vendor, target_vendor])

    if operation_code:
        conditions.append(sql.SQL("o.operation_code = %s"))
        params.append(operation_code)
    if is_active is not None:
        conditions.append(sql.SQL("COALESCE(o.is_active, true) = %s"))
        params.append(is_active)

    decoded = _decode_cursor(cursor) if cursor else None
    if decoded:
        conditions.append(sql.SQL("(o.created_at, o.id) < (%s::timestamptz, %s::uuid)"))
        params.extend(decoded)

    where = sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("true")
    params.append(limit + 1)

    q = sql.SQL(
        """
        SELECT o.id, o.operation_code, o.description, o.canonical_version,
               o.is_async_capable, o.is_active, o.direction_policy,
               o.ai_presentation_mode, o.ai_formatter_prompt, o.ai_formatter_model,
               o.created_at, o.updated_at
        {}
        WHERE {}
        ORDER BY o.created_at DESC, o.id DESC
        LIMIT %s
        """
    ).format(base_from, where)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, tuple(params))
        rows = cur.fetchall()

    items: list[dict[str, Any]] = []
    next_cursor: str | None = None
    for i, r in enumerate(rows):
        if i >= limit:
            next_cursor = _encode_cursor(r["created_at"], r["id"])
            break
        items.append(_to_camel_case_dict({
            "id": str(r["id"]) if r.get("id") else None,
            "operation_code": r["operation_code"],
            "description": r.get("description") or "",
            "canonical_version": r.get("canonical_version") or "v1",
            "is_async_capable": bool(r.get("is_async_capable", True)),
            "is_active": bool(r.get("is_active", True)),
            "direction_policy": r.get("direction_policy"),
            "ai_presentation_mode": r.get("ai_presentation_mode") or "RAW_ONLY",
            "ai_formatter_prompt": r.get("ai_formatter_prompt"),
            "ai_formatter_model": r.get("ai_formatter_model"),
            "created_at": str(r["created_at"]) if r.get("created_at") else None,
            "updated_at": str(r["updated_at"]) if r.get("updated_at") else None,
        }))
    return items, next_cursor


def _handle_get_operations(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/registry/operations?limit=&cursor=&operationCode=&isActive=&sourceVendorCode=&targetVendorCode="""
    try:
        qp = _parse_query_params(event)
        lp = _parse_list_params(qp)
        source_vendor = lp.get("source_vendor_code")
        target_vendor = lp.get("target_vendor_code")
        if (source_vendor and not target_vendor) or (target_vendor and not source_vendor):
            return _error(400, "VALIDATION_ERROR", "sourceVendorCode and targetVendorCode must both be provided or both omitted")
        if source_vendor and target_vendor:
            source_vendor = _validate_vendor_code(source_vendor)
            target_vendor = _validate_vendor_code(target_vendor)
        if lp.get("operation_code"):
            lp["operation_code"] = _validate_operation_code(lp["operation_code"])
        with _get_connection() as conn:
            items, next_cursor = _list_operations(
                conn,
                limit=lp["limit"],
                cursor=lp.get("cursor"),
                operation_code=lp.get("operation_code"),
                is_active=lp.get("is_active"),
                source_vendor=source_vendor,
                target_vendor=target_vendor,
            )
            return _success(200, {"items": items, "nextCursor": next_cursor})
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_set_canonical_version(event: dict[str, Any], operation_code_raw: str | None) -> dict[str, Any]:
    """
    POST /v1/registry/operations/{operationCode}/canonical-version
    Body: { "canonicalVersion": "v2" }
    Sets operations.canonical_version for the given operation. Requires an active contract for that version.
    """
    if not operation_code_raw or not str(operation_code_raw).strip():
        return _error(400, "VALIDATION_ERROR", "operationCode is required")
    body = _parse_body(event.get("body"))
    canonical_version_raw = body.get("canonicalVersion") or body.get("canonical_version")
    if not canonical_version_raw or not str(canonical_version_raw).strip():
        return _error(400, "VALIDATION_ERROR", "canonicalVersion is required")
    try:
        operation_code = _validate_operation_code(operation_code_raw)
        canonical_version = str(canonical_version_raw).strip()
        if len(canonical_version) > 32:
            return _error(400, "VALIDATION_ERROR", "canonicalVersion must be 1-32 chars")
        req_ctx = event.get("requestContext") or {}
        request_id = req_ctx.get("requestId") or str(uuid.uuid4())
        audit_actor = _get_audit_actor(event)

        with _get_connection() as conn:
            op_row = _execute_one(
                conn,
                sql.SQL(
                    "SELECT operation_code FROM control_plane.operations WHERE operation_code = %s"
                ),
                (operation_code,),
            )
            if not op_row:
                return _error(404, "NOT_FOUND", f"Operation {operation_code} not found")

            contract_row = _execute_one(
                conn,
                sql.SQL(
                    """
                    SELECT 1 FROM control_plane.operation_contracts
                    WHERE operation_code = %s AND canonical_version = %s AND is_active = true
                    """
                ),
                (operation_code, canonical_version),
            )
            if not contract_row:
                return _error(
                    400,
                    "NO_ACTIVE_CONTRACT_FOR_VERSION",
                    f"No active contract for {operation_code} version {canonical_version}. Create and save the contract first.",
                )

            q = sql.SQL(
                """
                UPDATE control_plane.operations
                SET canonical_version = %s, updated_at = now()
                WHERE operation_code = %s
                RETURNING operation_code, canonical_version, updated_at
                """
            )
            row = _execute_one(conn, q, (canonical_version, operation_code))
            if row:
                _write_audit_event(
                    conn,
                    transaction_id=f"registry-{request_id}",
                    action="operation_canonical_version_set",
                    vendor_code=audit_actor,
                    details={
                        "operation_code": operation_code,
                        "canonical_version": canonical_version,
                    },
                )
                return _success(
                    200,
                    {
                        "operationCode": row["operation_code"],
                        "canonicalVersion": row["canonical_version"],
                        "updatedAt": row["updated_at"].isoformat() if row.get("updated_at") else None,
                    },
                )
            return _error(500, "INTERNAL_ERROR", "Update failed")
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_get_vendors(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/registry/vendors?limit=&cursor=&vendorCode=&isActive="""
    try:
        qp = _parse_query_params(event)
        lp = _parse_list_params(qp)
        if lp.get("vendor_code"):
            lp["vendor_code"] = _validate_vendor_code(lp["vendor_code"])
        with _get_connection() as conn:
            items, next_cursor = _list_vendors(
                conn,
                limit=lp["limit"],
                cursor=lp.get("cursor"),
                vendor_code=lp.get("vendor_code"),
                is_active=lp.get("is_active"),
            )
            return _success(200, {"items": items, "nextCursor": next_cursor})
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_get_usage(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/registry/usage?from=&to=&vendorCode=&limit= - aggregate transaction counts (admin)."""
    params = event.get("queryStringParameters") or {}
    from_ts = (params.get("from") or "").strip()
    to_ts = (params.get("to") or "").strip()
    if not from_ts or not to_ts:
        return _error(400, "VALIDATION_ERROR", "from and to (ISO 8601) are required")
    try:
        from datetime import datetime
        datetime.fromisoformat(from_ts.replace("Z", "+00:00"))
        datetime.fromisoformat(to_ts.replace("Z", "+00:00"))
    except ValueError:
        return _error(400, "VALIDATION_ERROR", "from and to must be valid ISO 8601")
    vendor_code = (params.get("vendorCode") or params.get("vendorcode") or "").strip() or None
    limit = validate_limit(params.get("limit"), default=50, minimum=1, maximum=200)

    try:
        with _get_connection() as conn:
            by_vendor: list[dict[str, Any]] = []
            # byVendor: transaction_metrics_daily. Index idx_tx_metrics_daily_vendor_bucket.
            # Time-bounded by bucket_start; partition-friendly (rollup is non-partitioned, small).
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT vendor_code, SUM(count) AS cnt
                    FROM data_plane.transaction_metrics_daily
                    WHERE bucket_start >= %s::timestamptz AND bucket_start <= %s::timestamptz
                    """ + (" AND vendor_code = %s" if vendor_code else "") + """
                    GROUP BY vendor_code ORDER BY cnt DESC LIMIT %s
                    """,
                    (from_ts, to_ts) + ((vendor_code,) if vendor_code else ()) + (limit,),
                )
                for r in cur.fetchall():
                    by_vendor.append({"vendorCode": r["vendor_code"], "count": int(r["cnt"] or 0)})
            # byApiKey: removed (vendor_api_keys table and api_key_id no longer used)
            by_api_key: list[dict[str, Any]] = []
        return _success(200, {
            "from": from_ts,
            "to": to_ts,
            "byVendor": by_vendor,
            "byApiKey": by_api_key,
        })
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_get_allowlist(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/registry/allowlist?limit=&cursor=&vendorCode=&operationCode=&sourceVendorCode=&targetVendorCode=&scope="""
    try:
        qp = _parse_query_params(event)
        lp = _parse_list_params(qp)
        scope_raw = (qp.get("scope") or "").strip().lower()
        scope = scope_raw if scope_raw in ("global", "vendor_specific", "all") else None
        if lp.get("vendor_code"):
            lp["vendor_code"] = _validate_vendor_code(lp["vendor_code"])
        if lp.get("source_vendor_code"):
            lp["source_vendor_code"] = _validate_vendor_code(lp["source_vendor_code"])
        if lp.get("target_vendor_code"):
            lp["target_vendor_code"] = _validate_vendor_code(lp["target_vendor_code"])
        if lp.get("operation_code"):
            lp["operation_code"] = _validate_operation_code(lp["operation_code"])
        with _get_connection() as conn:
            items, next_cursor = _list_allowlist(
                conn,
                limit=lp["limit"],
                cursor=lp.get("cursor"),
                source_vendor_code=lp.get("source_vendor_code"),
                target_vendor_code=lp.get("target_vendor_code"),
                operation_code=lp.get("operation_code"),
                vendor_code=lp.get("vendor_code"),
                scope=scope,
            )
            return _success(200, {"items": items, "nextCursor": next_cursor})
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_get_endpoints(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/registry/endpoints?limit=&cursor=&vendorCode=&operationCode=&isActive="""
    try:
        qp = _parse_query_params(event)
        lp = _parse_list_params(qp)
        if lp.get("vendor_code"):
            lp["vendor_code"] = _validate_vendor_code(lp["vendor_code"])
        if lp.get("operation_code"):
            lp["operation_code"] = _validate_operation_code(lp["operation_code"])
        with _get_connection() as conn:
            items, next_cursor = _list_endpoints(
                conn,
                limit=lp["limit"],
                cursor=lp.get("cursor"),
                vendor_code=lp.get("vendor_code"),
                operation_code=lp.get("operation_code"),
                is_active=lp.get("is_active"),
            )
            return _success(200, {"items": items, "nextCursor": next_cursor})
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_get_auth_profiles(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/registry/auth-profiles?vendorCode=&isActive=&limit=&cursor= (vendorCode optional)."""
    try:
        qp = _parse_query_params(event)
        vendor_code_raw = (qp.get("vendorcode") or "").strip()
        vendor_code = _validate_vendor_code(vendor_code_raw) if vendor_code_raw else None
        is_active = None
        is_active_raw = (qp.get("isactive") or "").strip().lower()
        if is_active_raw in ("true", "1", "yes"):
            is_active = True
        elif is_active_raw in ("false", "0", "no"):
            is_active = False
        limit = validate_limit(qp.get("limit"), default=DEFAULT_LIMIT, minimum=1, maximum=MAX_LIMIT)
        cursor = (qp.get("cursor") or "").strip() or None
        with _get_connection() as conn:
            if vendor_code:
                vendor_row = _execute_one(
                    conn,
                    sql.SQL("SELECT 1 FROM control_plane.vendors WHERE vendor_code = %s"),
                    (vendor_code,),
                )
                if not vendor_row:
                    return _error(400, "VALIDATION_ERROR", f"vendorCode {vendor_code} not found")
            items, next_cursor = _list_auth_profiles(
                conn, vendor_code=vendor_code, is_active=is_active, limit=limit, cursor=cursor
            )
            return _success(200, {"items": items, "nextCursor": next_cursor})
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_post_auth_profiles(event: dict[str, Any]) -> dict[str, Any]:
    """POST /v1/registry/auth-profiles - create/upsert auth profile. id in body for update."""
    body = _parse_body(event.get("body"))
    req_ctx = event.get("requestContext") or {}
    request_id = req_ctx.get("requestId") or str(uuid.uuid4())
    audit_actor = _get_audit_actor(event)
    try:
        profile_id_raw = body.get("id")
        profile_id = str(profile_id_raw).strip() if profile_id_raw else None
        vendor_code = _validate_vendor_code(body.get("vendorCode") or body.get("vendor_code"))
        name = _validate_optional_str(body.get("name") or body.get("profileName"), "name", 64)
        if not name:
            raise ValueError("name is required")
        auth_type = _validate_auth_type(body.get("authType") or body.get("auth_type"))
        config = _validate_auth_config(body.get("config"), auth_type)
        is_active = body.get("isActive") if body.get("isActive") is not None else body.get("is_active")
        if is_active is not None and not isinstance(is_active, bool):
            is_active = str(is_active).lower() in ("true", "1")
        is_default = body.get("isDefault") if body.get("isDefault") is not None else body.get("is_default")
        if is_default is not None and not isinstance(is_default, bool):
            is_default = str(is_default).lower() in ("true", "1")
        with _get_connection() as conn:
            vendor_row = _execute_one(
                conn,
                sql.SQL("SELECT 1 FROM control_plane.vendors WHERE vendor_code = %s AND COALESCE(is_active, true)"),
                (vendor_code,),
            )
            if not vendor_row:
                raise ValueError(f"vendor_code {vendor_code} not found or inactive")
            row = _upsert_auth_profile(
                conn, vendor_code, name, auth_type, config, is_active, audit_actor, request_id, profile_id, is_default
            )
            return _success(200, {"item": row})
    except ValueError as e:
        log_json("WARN", "validation_failed", ctx=get_context(event, None), error=str(e))
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_delete_auth_profile(profile_id: str | None) -> dict[str, Any]:
    """DELETE /v1/registry/auth-profiles/{id} - soft delete (is_active=false)."""
    if not profile_id or not str(profile_id).strip():
        return _error(400, "VALIDATION_ERROR", "auth profile id is required")
    profile_id = profile_id.strip()
    try:
        with _get_connection() as conn:
            row = _soft_delete_auth_profile(conn, profile_id)
            if not row:
                return _error(404, "NOT_FOUND", "Auth profile not found")
            return _success(200, {"id": str(row["id"]), "isActive": False})
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_delete_allowlist(
    event: dict[str, Any], context: object, entry_id: str | None
) -> dict[str, Any]:
    """DELETE /v1/registry/allowlist/{id} - hard delete allowlist entry."""
    if not entry_id or not str(entry_id).strip():
        return _error(400, "VALIDATION_ERROR", "allowlist entry id is required")
    entry_id = str(entry_id).strip()
    try:
        with _get_connection() as conn:
            deleted = _delete_allowlist(conn, entry_id)
            if not deleted:
                return _error(404, "NOT_FOUND", "Allowlist entry not found")
            return _success(200, {"deleted": True, "id": entry_id})
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        log_json("ERROR", "allowlist delete failed", ctx=get_context(event, context), error=str(e))
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_patch_auth_profile(event: dict[str, Any], profile_id: str | None) -> dict[str, Any]:
    """PATCH /v1/registry/auth-profiles/{id} - toggle isActive, update config."""
    if not profile_id or not str(profile_id).strip():
        return _error(400, "VALIDATION_ERROR", "auth profile id is required")
    profile_id = profile_id.strip()
    body = _parse_body(event.get("body"))
    qp = _parse_query_params(event)
    vendor_code_raw = qp.get("vendorcode") or (body.get("vendorCode") or body.get("vendor_code"))
    if not vendor_code_raw or not str(vendor_code_raw).strip():
        return _error(400, "VALIDATION_ERROR", "vendorCode query param or body is required")
    try:
        vendor_code = _validate_vendor_code(vendor_code_raw)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    req_ctx = event.get("requestContext") or {}
    request_id = req_ctx.get("requestId") or str(uuid.uuid4())
    audit_actor = _get_audit_actor(event)
    is_active = body.get("isActive") if body.get("isActive") is not None else body.get("is_active")
    if is_active is not None and not isinstance(is_active, bool):
        is_active = str(is_active).lower() in ("true", "1")
    is_default = body.get("isDefault") if body.get("isDefault") is not None else body.get("is_default")
    if is_default is not None and not isinstance(is_default, bool):
        is_default = str(is_default).lower() in ("true", "1")
    config = body.get("config")
    if is_active is None and is_default is None and config is None:
        return _error(400, "VALIDATION_ERROR", "Provide isActive, isDefault and/or config to update")
    try:
        with _get_connection() as conn:
            if config is not None:
                existing = _execute_one(
                    conn,
                    sql.SQL(
                        "SELECT auth_type FROM control_plane.vendor_auth_profiles "
                        "WHERE id = %s::uuid AND vendor_code = %s"
                    ),
                    (profile_id, vendor_code),
                )
                if not existing:
                    return _error(404, "NOT_FOUND", "Auth profile not found")
                try:
                    config = _validate_auth_config(config, existing.get("auth_type") or "NONE")
                except ValueError as e:
                    return _error(400, "VALIDATION_ERROR", str(e))
            row = _patch_auth_profile(
                conn,
                profile_id,
                vendor_code,
                is_active=is_active,
                config=config,
                is_default=is_default,
                audit_actor=audit_actor,
                request_id=request_id,
            )
            if not row:
                return _error(404, "NOT_FOUND", "Auth profile not found")
            return _success(200, {"authProfile": row})
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_post_auth_profile_test_connection(event: dict[str, Any]) -> dict[str, Any]:
    body = _parse_body(event.get("body")) or {}
    try:
        auth_type = _normalize_test_auth_type(body.get("authType"))
        auth_config = body.get("authConfig")
        if not isinstance(auth_config, dict):
            raise ValueError("authConfig must be an object")
        url = _validate_url(body.get("url"))
        method = str(body.get("method") or "GET").strip().upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError("method must be one of GET, POST, PUT, PATCH, DELETE")
        timeout_ms = _normalize_test_timeout(body.get("timeoutMs"))
        allowed, reason = _validate_outbound_test_target(url)
        if not allowed:
            category = "DNS" if (reason or "").lower().startswith("unable to resolve") else "BLOCKED"
            return _success(
                200,
                {
                    "ok": False,
                    "httpStatus": None,
                    "latencyMs": 0,
                    "responsePreview": "",
                    "error": {"category": category, "message": reason or "Target blocked"},
                    "debug": {"resolvedAuth": {"type": auth_type, "appliedHeaders": {}, "appliedQuery": {}}},
                },
            )

        auth_parts = _build_test_auth_parts(auth_type, auth_config, timeout_ms)
        headers = _safe_request_headers(body.get("headers"))
        headers.update(auth_parts["headers"])
        params = dict(auth_parts["query"])
        request_body = body.get("body")

        start = time.perf_counter()
        req_kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
            "params": params if params else None,
            "timeout": min(MAX_TEST_TIMEOUT_MS / 1000.0, max(timeout_ms / 1000.0, 0.1)),
            "allow_redirects": False,
        }
        if request_body is not None and method in {"POST", "PUT", "PATCH", "DELETE"}:
            if isinstance(request_body, (dict, list)):
                req_kwargs["json"] = request_body
            else:
                req_kwargs["data"] = str(request_body)

        # mTLS with inline PEM is written to temp files only for this test invocation.
        if auth_parts.get("clientCert"):
            import tempfile

            cert_pem, key_pem = auth_parts["clientCert"]
            with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=True) as cert_file:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=True) as key_file:
                    cert_file.write(cert_pem)
                    key_file.write(key_pem)
                    cert_file.flush()
                    key_file.flush()
                    req_kwargs["cert"] = (cert_file.name, key_file.name)
                    resp = requests.request(**req_kwargs)
        else:
            resp = requests.request(**req_kwargs)

        latency_ms = int((time.perf_counter() - start) * 1000)
        preview = _normalize_preview_body(resp.text if isinstance(resp.text, str) else resp.content)
        status = int(resp.status_code)
        if 200 <= status < 400:
            error_obj = None
            ok = True
        else:
            category = "AUTH" if status in (401, 403) else ("UPSTREAM" if status >= 500 else "UNKNOWN")
            error_obj = {"category": category, "message": f"HTTP {status}"}
            ok = False
        return _success(
            200,
            {
                "ok": ok,
                "httpStatus": status,
                "latencyMs": latency_ms,
                "responsePreview": preview[:MAX_TEST_RESPONSE_PREVIEW],
                "error": error_obj,
                "debug": {
                    "resolvedAuth": {
                        "type": auth_type,
                        "appliedHeaders": auth_parts.get("resolvedHeadersRedacted") or {},
                        "appliedQuery": auth_parts.get("resolvedQueryRedacted") or {},
                    }
                },
            },
        )
    except Exception as exc:
        category, message = _classify_test_error(exc)
        return _success(
            200,
            {
                "ok": False,
                "httpStatus": None,
                "latencyMs": 0,
                "responsePreview": "",
                "error": {"category": category, "message": message},
                "debug": {"resolvedAuth": {"type": None, "appliedHeaders": {}, "appliedQuery": {}}},
            },
        )


def _handle_post_auth_profile_token_preview(event: dict[str, Any]) -> dict[str, Any]:
    body = _parse_body(event.get("body")) or {}
    try:
        auth_type = _normalize_test_auth_type(body.get("authType"))
        if auth_type not in ("JWT_BEARER_TOKEN", "JWT"):
            raise ValueError("authType must be JWT_BEARER_TOKEN")
        auth_config = body.get("authConfig")
        if not isinstance(auth_config, dict):
            raise ValueError("authConfig must be an object")
        timeout_ms = _normalize_test_timeout(body.get("timeoutMs"))
        token_data = _fetch_jwt_preview_token(auth_config, timeout_ms)
        token = str(token_data.get("accessToken") or "")
        claims = _decode_jwt_claims_unsafe(token)
        return _success(
            200,
            {
                "ok": True,
                "tokenRedacted": _redact_token(token),
                "tokenLength": len(token),
                "expiresIn": token_data.get("expiresIn"),
                "jwtClaims": (
                    {
                        "iss": claims.get("iss"),
                        "aud": claims.get("aud"),
                        "exp": claims.get("exp"),
                        "iat": claims.get("iat"),
                    }
                    if claims
                    else None
                ),
                "cacheDiagnostics": token_data.get("cacheDiagnostics"),
                "error": None,
            },
        )
    except Exception as exc:
        category, message = _classify_test_error(exc)
        if category == "BLOCKED":
            category = "UNKNOWN"
        return _success(
            200,
            {
                "ok": False,
                "tokenRedacted": None,
                "expiresIn": None,
                "jwtClaims": None,
                "cacheDiagnostics": None,
                "error": {"category": category, "message": message},
            },
        )


def _handle_post_auth_profile_mtls_validate(event: dict[str, Any]) -> dict[str, Any]:
    body = _parse_body(event.get("body")) or {}
    cert_pem = str(body.get("certificatePem") or "").strip()
    key_pem = str(body.get("privateKeyPem") or "").strip()
    ca_bundle = str(body.get("caBundlePem") or "").strip()
    if not cert_pem or not key_pem:
        return _error(400, "VALIDATION_ERROR", "certificatePem and privateKeyPem are required")
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
    except Exception:
        return _error(500, "INTERNAL_ERROR", "cryptography dependency is required")

    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
        private_key = serialization.load_pem_private_key(key_pem.encode("utf-8"), password=None)
    except Exception:
        return _success(
            200,
            {
                "ok": False,
                "expiresAt": None,
                "daysRemaining": None,
                "subject": None,
                "issuer": None,
                "sans": [],
                "warnings": [],
                "error": {"category": "PARSE", "message": "Certificate or private key could not be parsed"},
            },
        )

    try:
        cert_pub = cert.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        key_pub = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if cert_pub != key_pub:
            return _success(
                200,
                {
                    "ok": False,
                    "expiresAt": cert.not_valid_after_utc.isoformat(),
                    "daysRemaining": int((cert.not_valid_after_utc - datetime.now(UTC)).total_seconds() // 86400),
                    "subject": cert.subject.rfc4514_string(),
                    "issuer": cert.issuer.rfc4514_string(),
                    "sans": [],
                    "warnings": [],
                    "error": {"category": "MISMATCH", "message": "Private key does not match certificate"},
                },
            )
    except Exception:
        return _success(
            200,
            {
                "ok": False,
                "expiresAt": None,
                "daysRemaining": None,
                "subject": None,
                "issuer": None,
                "sans": [],
                "warnings": [],
                "error": {"category": "UNKNOWN", "message": "Unable to validate certificate-key consistency"},
            },
        )

    warnings: list[str] = []
    now = datetime.now(UTC)
    days_remaining = int((cert.not_valid_after_utc - now).total_seconds() // 86400)
    if days_remaining < 0:
        warnings.append("EXPIRED")
    elif days_remaining < 30:
        warnings.append("EXPIRING_SOON")

    sans: list[str] = []
    try:
        san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        sans = [str(name.value) for name in san_ext]
    except Exception:
        sans = []

    if ca_bundle:
        try:
            pem_blobs = re.findall(
                r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
                ca_bundle,
                flags=re.DOTALL,
            )
            if not pem_blobs:
                raise ValueError("No CA certificates found")
            for blob in pem_blobs:
                x509.load_pem_x509_certificate(blob.encode("utf-8"))
        except Exception:
            warnings.append("CA_BUNDLE_PARSE_FAILED")

    return _success(
        200,
        {
            "ok": "EXPIRED" not in warnings,
            "expiresAt": cert.not_valid_after_utc.isoformat(),
            "daysRemaining": days_remaining,
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "sans": sans,
            "warnings": warnings,
            "error": None if "EXPIRED" not in warnings else {"category": "PARSE", "message": "Certificate is expired"},
        },
    )


def _compute_readiness(
    conn: Any,
    vendor_code: str,
    operation_code: str,
) -> dict[str, Any]:
    """
    Compute readiness report for vendor+operation.
    Checks: endpoint_configured, endpoint_verified, canonical_contract_present, mappings_present.
    """
    checks: list[dict[str, Any]] = []
    overall_ok = True

    # 1. endpoint_configured
    ep_row = _execute_one(
        conn,
        sql.SQL(
            """
            SELECT url, verification_status, last_verified_at, last_verification_error
            FROM control_plane.vendor_endpoints
            WHERE vendor_code = %s AND operation_code = %s AND is_active = true
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """
        ),
        (vendor_code, operation_code),
    )
    if ep_row:
        checks.append({
            "name": "endpoint_configured",
            "ok": True,
            "details": {},
        })
        status = (ep_row.get("verification_status") or "PENDING").upper()
        ok_verified = status == "VERIFIED"
        checks.append({
            "name": "endpoint_verified",
            "ok": ok_verified,
            "details": {"status": status},
        })
        if not ok_verified:
            overall_ok = False
    else:
        checks.append({
            "name": "endpoint_configured",
            "ok": False,
            "details": {},
        })
        checks.append({
            "name": "endpoint_verified",
            "ok": False,
            "details": {"status": "PENDING"},
        })
        overall_ok = False

    # 2. canonical_contract_present (get canonical_version from operations)
    op_row = _execute_one(
        conn,
        sql.SQL(
            """
            SELECT canonical_version FROM control_plane.operations
            WHERE operation_code = %s AND COALESCE(is_active, true)
            """
        ),
        (operation_code,),
    )
    canonical_version = (op_row.get("canonical_version") or "v1") if op_row else "v1"
    canon_row = _execute_one(
        conn,
        sql.SQL(
            """
            SELECT 1 FROM control_plane.operation_contracts
            WHERE operation_code = %s AND canonical_version = %s AND is_active = true
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """
        ),
        (operation_code, canonical_version),
    )
    ok_canon = canon_row is not None
    checks.append({
        "name": "canonical_contract_present",
        "ok": ok_canon,
    })
    if not ok_canon:
        overall_ok = False

    # 3. mappings_present (canonical pass-through: no vendor contract => no mapping required)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT DISTINCT direction FROM control_plane.vendor_operation_mappings
            WHERE vendor_code = %s AND operation_code = %s AND canonical_version = %s
              AND is_active = true
            ORDER BY direction
            """,
            (vendor_code, operation_code, canonical_version),
        )
        present_dirs = {r["direction"] for r in cur.fetchall()}
    vc_row = _execute_one(
        conn,
        sql.SQL(
            """
            SELECT 1 FROM control_plane.vendor_operation_contracts
            WHERE vendor_code = %s AND operation_code = %s AND canonical_version = %s
              AND is_active = true
            """
        ),
        (vendor_code, operation_code, canonical_version),
    )
    has_vendor_contract = vc_row is not None

    outbound_ok, out_req_canon, out_resp_canon = is_mapping_configured_for_direction(
        present_directions=present_dirs,
        has_vendor_contract=has_vendor_contract,
        flow_direction="OUTBOUND",
    )
    inbound_ok, in_req_canon, in_resp_canon = is_mapping_configured_for_direction(
        present_directions=present_dirs,
        has_vendor_contract=has_vendor_contract,
        flow_direction="INBOUND",
    )
    ok_mappings = outbound_ok or inbound_ok
    uses_canonical_request = out_req_canon or in_req_canon
    uses_canonical_response = out_resp_canon or in_resp_canon

    if not ok_mappings:
        missing = sorted(
            ({"TO_CANONICAL", "FROM_CANONICAL_RESPONSE"} | {"FROM_CANONICAL", "TO_CANONICAL_RESPONSE"})
            - present_dirs
        )
    else:
        missing = []
    checks.append({
        "name": "mappings_present",
        "ok": ok_mappings,
        "details": {"missing": missing} if missing else {},
    })
    if not ok_mappings:
        overall_ok = False

    effective_mapping_configured = ok_mappings
    has_vendor_request = bool(
        present_dirs & {"FROM_CANONICAL"} or present_dirs & {"TO_CANONICAL", "TO_CANONICAL_REQUEST"}
    )
    has_vendor_response = (
        "TO_CANONICAL_RESPONSE" in present_dirs or "FROM_CANONICAL_RESPONSE" in present_dirs
    )
    result: dict[str, Any] = {
        "vendorCode": vendor_code,
        "operationCode": operation_code,
        "checks": checks,
        "overallOk": overall_ok,
    }
    result["mappingConfigured"] = ok_mappings
    result["effectiveMappingConfigured"] = effective_mapping_configured
    result["usesCanonicalRequestMapping"] = uses_canonical_request
    result["usesCanonicalResponseMapping"] = uses_canonical_response
    result["hasVendorRequestMapping"] = has_vendor_request
    result["hasVendorResponseMapping"] = has_vendor_response
    return result


def _get_vendor_operations_for_readiness(conn: Any, vendor_code: str) -> list[str]:
    """
    Get operation_codes to report for vendor (all ops).
    Union of vendor_supported_operations and vendor_endpoints.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT DISTINCT operation_code FROM (
                SELECT operation_code FROM control_plane.vendor_supported_operations
                WHERE vendor_code = %s AND is_active = true
                UNION
                SELECT operation_code FROM control_plane.vendor_endpoints
                WHERE vendor_code = %s AND is_active = true
            ) u
            ORDER BY operation_code
            """,
            (vendor_code, vendor_code),
        )
        return [r["operation_code"] for r in cur.fetchall()]


def _batch_load_readiness_inputs(
    conn: Any, vendor_code: str, operation_codes: list[str]
) -> dict[str, Any]:
    """
    Load all data needed for readiness in at most 4 queries.
    Returns structure suitable for _compute_readiness_from_batch.
    """
    if not operation_codes:
        return {
            "endpoints": {},
            "operations": {},
            "contracts": {},
            "mappings": {},
            "vendor_contracts": {},
        }

    # 1. All endpoints for (vendor_code, operation_code IN operation_codes)
    endpoints_map: dict[tuple[str, str], dict[str, Any] | None] = {}
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (vendor_code, operation_code)
                vendor_code, operation_code, url, verification_status,
                last_verified_at, last_verification_error
            FROM control_plane.vendor_endpoints
            WHERE vendor_code = %s AND operation_code = ANY(%s) AND is_active = true
            ORDER BY vendor_code, operation_code, updated_at DESC NULLS LAST
            """,
            (vendor_code, operation_codes),
        )
        for r in cur.fetchall():
            key = (r["vendor_code"], r["operation_code"])
            endpoints_map[key] = dict(r)
        for op in operation_codes:
            key = (vendor_code, op)
            if key not in endpoints_map:
                endpoints_map[key] = None

    # 2. All operations rows for operation_codes -> canonical_version map
    operations_map: dict[str, dict[str, Any] | None] = {}
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT operation_code, canonical_version
            FROM control_plane.operations
            WHERE operation_code = ANY(%s) AND COALESCE(is_active, true)
            """,
            (operation_codes,),
        )
        for r in cur.fetchall():
            operations_map[r["operation_code"]] = dict(r)
        for op in operation_codes:
            if op not in operations_map:
                operations_map[op] = None

    # Build (op, canonical_version) pairs for contracts and mappings
    op_version_pairs: list[tuple[str, str]] = []
    for op in operation_codes:
        op_row = operations_map.get(op)
        canon = (op_row.get("canonical_version") or "v1") if op_row else "v1"
        op_version_pairs.append((op, canon))

    # 3. All contracts for (operation_code, canonical_version) pairs
    contracts_map: dict[tuple[str, str], bool] = {}
    if op_version_pairs:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT operation_code, canonical_version FROM control_plane.operation_contracts
                WHERE (operation_code, canonical_version) IN %s AND is_active = true
                """,
                (tuple(op_version_pairs),),
            )
            for r in cur.fetchall():
                contracts_map[(r["operation_code"], r["canonical_version"])] = True
        for op, canon in op_version_pairs:
            if (op, canon) not in contracts_map:
                contracts_map[(op, canon)] = False

    # 4. All mappings for (vendor_code, operation_code, canonical_version)
    mappings_map: dict[tuple[str, str, str], set[str]] = {}
    for op, canon in op_version_pairs:
        mappings_map[(vendor_code, op, canon)] = set()
    if op_version_pairs:
        pairs_tuple = tuple((op, v) for op, v in op_version_pairs)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT operation_code, canonical_version, direction
                FROM control_plane.vendor_operation_mappings
                WHERE vendor_code = %s AND (operation_code, canonical_version) IN %s
                  AND is_active = true
                """,
                (vendor_code, pairs_tuple),
            )
            for r in cur.fetchall():
                key = (vendor_code, r["operation_code"], r["canonical_version"])
                if key in mappings_map:
                    mappings_map[key].add(r["direction"])

    # 5. Vendor contracts (for canonical pass-through: no vendor override => pass-through ok)
    vendor_contracts_map: dict[tuple[str, str, str], bool] = {}
    for op, canon in op_version_pairs:
        vendor_contracts_map[(vendor_code, op, canon)] = False
    if op_version_pairs:
        pairs_tuple = tuple((op, v) for op, v in op_version_pairs)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT operation_code, canonical_version
                FROM control_plane.vendor_operation_contracts
                WHERE vendor_code = %s AND (operation_code, canonical_version) IN %s
                  AND is_active = true
                """,
                (vendor_code, pairs_tuple),
            )
            for r in cur.fetchall():
                vendor_contracts_map[(vendor_code, r["operation_code"], r["canonical_version"])] = True

    return {
        "endpoints": endpoints_map,
        "operations": operations_map,
        "contracts": contracts_map,
        "mappings": mappings_map,
        "vendor_contracts": vendor_contracts_map,
    }


def _compute_readiness_from_batch(
    vendor_code: str, operation_code: str, batch_data: dict[str, Any]
) -> dict[str, Any]:
    """
    Same output shape as _compute_readiness, but reads from batch_data instead of DB.
    """
    checks: list[dict[str, Any]] = []
    overall_ok = True

    endpoints_map = batch_data.get("endpoints") or {}
    operations_map = batch_data.get("operations") or {}
    contracts_map = batch_data.get("contracts") or {}
    mappings_map = batch_data.get("mappings") or {}
    vendor_contracts_map = batch_data.get("vendor_contracts") or {}

    # 1. endpoint_configured and endpoint_verified
    ep_row = endpoints_map.get((vendor_code, operation_code))
    if ep_row:
        checks.append({"name": "endpoint_configured", "ok": True, "details": {}})
        status = (ep_row.get("verification_status") or "PENDING").upper()
        ok_verified = status == "VERIFIED"
        checks.append({
            "name": "endpoint_verified",
            "ok": ok_verified,
            "details": {"status": status},
        })
        if not ok_verified:
            overall_ok = False
    else:
        checks.append({"name": "endpoint_configured", "ok": False, "details": {}})
        checks.append({
            "name": "endpoint_verified",
            "ok": False,
            "details": {"status": "PENDING"},
        })
        overall_ok = False

    # 2. canonical_contract_present
    op_row = operations_map.get(operation_code)
    canonical_version = (op_row.get("canonical_version") or "v1") if op_row else "v1"
    ok_canon = contracts_map.get((operation_code, canonical_version), False)
    checks.append({"name": "canonical_contract_present", "ok": ok_canon})
    if not ok_canon:
        overall_ok = False

    # 3. mappings_present (canonical pass-through: no vendor contract => no mapping required)
    present_dirs = mappings_map.get((vendor_code, operation_code, canonical_version)) or set()
    has_vendor_contract = vendor_contracts_map.get((vendor_code, operation_code, canonical_version), False)

    outbound_ok, out_req_canon, out_resp_canon = is_mapping_configured_for_direction(
        present_directions=present_dirs,
        has_vendor_contract=has_vendor_contract,
        flow_direction="OUTBOUND",
    )
    inbound_ok, in_req_canon, in_resp_canon = is_mapping_configured_for_direction(
        present_directions=present_dirs,
        has_vendor_contract=has_vendor_contract,
        flow_direction="INBOUND",
    )
    ok_mappings = outbound_ok or inbound_ok
    uses_canonical_request = out_req_canon or in_req_canon
    uses_canonical_response = out_resp_canon or in_resp_canon

    if not ok_mappings:
        missing = sorted(
            ({"TO_CANONICAL", "FROM_CANONICAL_RESPONSE"} | {"FROM_CANONICAL", "TO_CANONICAL_RESPONSE"})
            - present_dirs
        )
    else:
        missing = []
    checks.append({
        "name": "mappings_present",
        "ok": ok_mappings,
        "details": {"missing": missing} if missing else {},
    })
    if not ok_mappings:
        overall_ok = False

    effective_mapping_configured = ok_mappings
    present_dirs = mappings_map.get((vendor_code, operation_code, canonical_version)) or set()
    has_vendor_request = bool(
        present_dirs & {"FROM_CANONICAL"} or present_dirs & {"TO_CANONICAL", "TO_CANONICAL_REQUEST"}
    )
    has_vendor_response = (
        "TO_CANONICAL_RESPONSE" in present_dirs or "FROM_CANONICAL_RESPONSE" in present_dirs
    )
    result: dict[str, Any] = {
        "vendorCode": vendor_code,
        "operationCode": operation_code,
        "checks": checks,
        "overallOk": overall_ok,
    }
    result["mappingConfigured"] = ok_mappings
    result["effectiveMappingConfigured"] = effective_mapping_configured
    result["usesCanonicalRequestMapping"] = uses_canonical_request
    result["usesCanonicalResponseMapping"] = uses_canonical_response
    result["hasVendorRequestMapping"] = has_vendor_request
    result["hasVendorResponseMapping"] = has_vendor_response
    return result


def _handle_get_readiness(event: dict[str, Any]) -> dict[str, Any]:
    """
    GET /v1/registry/readiness?vendorCode=LH002&operationCode=GET_RECEIPT
    GET /v1/registry/readiness?vendorCode=LH002 (all ops for vendor)

    Returns structured readiness report(s). vendorCode required.
    """
    try:
        qp = event.get("queryStringParameters") or {}
        if not isinstance(qp, dict):
            qp = {}
        qp_lower = {k.lower(): v for k, v in qp.items()}
        vendor_code = (qp_lower.get("vendorcode") or qp_lower.get("vendor_code") or "").strip()
        operation_code = (qp_lower.get("operationcode") or qp_lower.get("operation_code") or "").strip() or None

        if not vendor_code:
            return _error(400, "VALIDATION_ERROR", "vendorCode is required")
        vendor_code = _validate_vendor_code(vendor_code)
        if operation_code:
            operation_code = _validate_operation_code(operation_code)

        with _get_connection() as conn:
            vendor_row = _execute_one(
                conn,
                sql.SQL("SELECT 1 FROM control_plane.vendors WHERE vendor_code = %s AND COALESCE(is_active, true)"),
                (vendor_code,),
            )
            if not vendor_row:
                return _error(400, "VALIDATION_ERROR", f"vendorCode {vendor_code} not found")

            if operation_code:
                report = _compute_readiness(conn, vendor_code, operation_code)
                return _success(200, report)
            ops = _get_vendor_operations_for_readiness(conn, vendor_code)
            if not ops:
                return _success(200, {
                    "vendorCode": vendor_code,
                    "items": [],
                })
            batch_data = _batch_load_readiness_inputs(conn, vendor_code, ops)
            items = [
                _compute_readiness_from_batch(vendor_code, op, batch_data)
                for op in ops
            ]
            return _success(200, {"vendorCode": vendor_code, "items": items})
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_post_readiness_batch(event: dict[str, Any]) -> dict[str, Any]:
    """
    POST /v1/registry/readiness/batch
    Request: { "vendorCodes": ["LH001", "LH002"], "operationCode": "GET_RECEIPT" } (operationCode optional)
    Response: { "items": [ { vendorCode, items?, checks?, overallOk?, error? }, ... ] }
    Per-vendor errors are returned in the item; 200 with partial results.
    """
    try:
        body = _parse_body(event.get("body"))
        vendor_codes_raw = body.get("vendorCodes") or body.get("vendor_codes")
        if not isinstance(vendor_codes_raw, list) or len(vendor_codes_raw) == 0:
            return _error(400, "VALIDATION_ERROR", "vendorCodes must be a non-empty array")

        vendor_codes = []
        for v in vendor_codes_raw:
            s = (v or "").strip().upper()
            if s:
                vendor_codes.append(_validate_vendor_code(s))

        operation_code_raw = (body.get("operationCode") or body.get("operation_code") or "").strip()
        operation_code = _validate_operation_code(operation_code_raw) if operation_code_raw else None

        items: list[dict[str, Any]] = []
        with _get_connection() as conn:
            for vc in vendor_codes:
                try:
                    if operation_code:
                        report = _compute_readiness(conn, vc, operation_code)
                        item = {
                            "vendorCode": vc,
                            "operationCode": operation_code,
                            "checks": report.get("checks", []),
                            "overallOk": report.get("overallOk", False),
                            "error": None,
                        }
                        if "mappingConfigured" in report:
                            item["mappingConfigured"] = report["mappingConfigured"]
                        if "usesCanonicalRequestMapping" in report:
                            item["usesCanonicalRequestMapping"] = report["usesCanonicalRequestMapping"]
                        if "usesCanonicalResponseMapping" in report:
                            item["usesCanonicalResponseMapping"] = report["usesCanonicalResponseMapping"]
                        items.append(item)
                    else:
                        ops = _get_vendor_operations_for_readiness(conn, vc)
                        if not ops:
                            items.append({
                                "vendorCode": vc,
                                "items": [],
                                "error": None,
                            })
                        else:
                            batch_data = _batch_load_readiness_inputs(conn, vc, ops)
                            op_items = [
                                _compute_readiness_from_batch(vc, op, batch_data)
                                for op in ops
                            ]
                            items.append({
                                "vendorCode": vc,
                                "items": op_items,
                                "error": None,
                            })
                except Exception as e:
                    items.append({
                        "vendorCode": vc,
                        "error": {"code": "READINESS_ERROR", "message": str(e)},
                    })

        return _success(200, {"items": items})
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _list_mission_control_topology(conn: Any) -> dict[str, list[dict[str, Any]]]:
    """Return active vendors as nodes and explicit allowlist links as edges."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT v.vendor_code, v.vendor_name
            FROM control_plane.vendors v
            WHERE COALESCE(v.is_active, true)
            ORDER BY v.vendor_code ASC
            """
        )
        vendor_rows = [dict(r) for r in (cur.fetchall() or [])]

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                a.source_vendor_code,
                a.target_vendor_code,
                a.operation_code,
                COALESCE(a.flow_direction, 'BOTH') AS flow_direction
            FROM control_plane.vendor_operation_allowlist a
            JOIN control_plane.vendors sv
              ON sv.vendor_code = a.source_vendor_code
             AND COALESCE(sv.is_active, true)
            JOIN control_plane.vendors tv
              ON tv.vendor_code = a.target_vendor_code
             AND COALESCE(tv.is_active, true)
            JOIN control_plane.operations o
              ON o.operation_code = a.operation_code
             AND COALESCE(o.is_active, true)
            WHERE a.source_vendor_code IS NOT NULL
              AND a.target_vendor_code IS NOT NULL
              AND COALESCE(a.is_any_source, false) = false
              AND COALESCE(a.is_any_target, false) = false
              AND LOWER(COALESCE(a.rule_scope, 'admin')) = 'admin'
            ORDER BY a.source_vendor_code ASC, a.target_vendor_code ASC, a.operation_code ASC
            """
        )
        edge_rows = [dict(r) for r in (cur.fetchall() or [])]

    nodes = [
        {
            "vendorCode": row.get("vendor_code"),
            "vendorName": row.get("vendor_name"),
        }
        for row in vendor_rows
    ]
    edges = [
        {
            "sourceVendorCode": row.get("source_vendor_code"),
            "targetVendorCode": row.get("target_vendor_code"),
            "operationCode": row.get("operation_code"),
            "flowDirection": row.get("flow_direction") or "BOTH",
        }
        for row in edge_rows
    ]
    return {"nodes": nodes, "edges": edges}


def _handle_get_mission_control_topology(_event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/registry/mission-control/topology (admin-only, metadata-only)."""
    try:
        with _get_connection() as conn:
            topology = _list_mission_control_topology(conn)
        return _success(200, topology)
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _derive_execute_stage(status: str | None) -> str:
    val = (status or "").strip().lower()
    if val in {"pending", "started", "in_progress", "queued", "running"}:
        return "EXECUTE_START"
    if val in {"success", "succeeded", "completed", "ok"}:
        return "EXECUTE_SUCCESS"
    return "EXECUTE_ERROR"


def _list_mission_control_activity(
    conn: Any,
    *,
    lookback_minutes: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Return combined transaction + policy deny activity, newest first."""
    tx_limit = max(1, min(200, limit))
    pd_limit = max(1, min(200, limit))

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                created_at,
                transaction_id,
                correlation_id,
                source_vendor,
                target_vendor,
                operation,
                status,
                http_status
            FROM data_plane.transactions
            WHERE created_at >= (now() - (%s || ' minutes')::interval)
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (lookback_minutes, tx_limit),
        )
        tx_rows = [dict(r) for r in (cur.fetchall() or [])]

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                occurred_at,
                transaction_id,
                correlation_id,
                vendor_code,
                target_vendor_code,
                operation_code,
                decision_code,
                http_status
            FROM policy.policy_decisions
            WHERE occurred_at >= (now() - (%s || ' minutes')::interval)
              AND COALESCE(allowed, false) = false
            ORDER BY occurred_at DESC
            LIMIT %s
            """,
            (lookback_minutes, pd_limit),
        )
        policy_rows = [dict(r) for r in (cur.fetchall() or [])]

    events: list[dict[str, Any]] = []
    for row in tx_rows:
        ts_val = row.get("created_at")
        events.append(
            {
                "ts": ts_val.isoformat() if hasattr(ts_val, "isoformat") else str(ts_val) if ts_val else None,
                "transactionId": row.get("transaction_id"),
                "correlationId": row.get("correlation_id"),
                "sourceVendorCode": row.get("source_vendor"),
                "targetVendorCode": row.get("target_vendor"),
                "operationCode": row.get("operation"),
                "stage": _derive_execute_stage(row.get("status")),
                "statusCode": row.get("http_status"),
                "latencyMs": None,
            }
        )

    for row in policy_rows:
        ts_val = row.get("occurred_at")
        events.append(
            {
                "ts": ts_val.isoformat() if hasattr(ts_val, "isoformat") else str(ts_val) if ts_val else None,
                "transactionId": row.get("transaction_id"),
                "correlationId": row.get("correlation_id"),
                "sourceVendorCode": row.get("vendor_code"),
                "targetVendorCode": row.get("target_vendor_code"),
                "operationCode": row.get("operation_code"),
                "stage": "POLICY_DENY",
                "decisionCode": row.get("decision_code"),
                "statusCode": row.get("http_status"),
                "latencyMs": None,
            }
        )

    events.sort(key=lambda e: (e.get("ts") or ""), reverse=True)
    return events[:limit]


def _handle_get_mission_control_activity(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/registry/mission-control/activity (admin-only, metadata-only)."""
    try:
        qp = _parse_query_params(event)
        lookback_minutes = validate_limit(qp.get("lookbackminutes"), default=10, minimum=1, maximum=60)
        limit = validate_limit(qp.get("limit"), default=100, minimum=1, maximum=200)
        with _get_connection() as conn:
            items = _list_mission_control_activity(
                conn,
                lookback_minutes=lookback_minutes,
                limit=limit,
            )
        return _success(
            200,
            {
                "items": items,
                "count": len(items),
                "lookbackMinutes": lookback_minutes,
            },
        )
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _list_policy_decisions(
    conn: Any,
    *,
    vendor_code: str | None,
    operation_code: str | None,
    decision_code: str | None,
    date_from: str | None,
    date_to: str | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    conditions: list[sql.Composable] = []
    params: list[Any] = []

    if vendor_code:
        conditions.append(sql.SQL("vendor_code = %s"))
        params.append(vendor_code)
    if operation_code:
        conditions.append(sql.SQL("operation_code = %s"))
        params.append(operation_code)
    if decision_code:
        conditions.append(sql.SQL("decision_code = %s"))
        params.append(decision_code)
    if date_from:
        conditions.append(sql.SQL("occurred_at >= %s::timestamptz"))
        params.append(date_from)
    if date_to:
        conditions.append(sql.SQL("occurred_at <= %s::timestamptz"))
        params.append(date_to)

    decoded = _decode_cursor(cursor) if cursor else None
    if decoded:
        conditions.append(sql.SQL("(occurred_at, id::text) < (%s::timestamptz, %s)"))
        params.extend(decoded)

    where = sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("true")
    q = sql.SQL(
        """
        SELECT id, occurred_at, surface, action, vendor_code, target_vendor_code,
               operation_code, decision_code, allowed, http_status,
               correlation_id, transaction_id, metadata
        FROM policy.policy_decisions
        WHERE {}
        ORDER BY occurred_at DESC, id DESC
        LIMIT %s
        """
    ).format(where)

    fetch_limit = min(max(1, limit), MAX_LIMIT) + 1
    params.append(fetch_limit)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(q, tuple(params))
        rows = [dict(r) for r in (cur.fetchall() or [])]

    next_cursor = None
    if len(rows) > fetch_limit - 1:
        rows = rows[: fetch_limit - 1]
        last = rows[-1]
        next_cursor = _encode_cursor(last.get("occurred_at"), last.get("id"))

    items = []
    for r in rows:
        items.append(
            {
                "id": str(r.get("id")) if r.get("id") else None,
                "occurredAt": r.get("occurred_at").isoformat() if hasattr(r.get("occurred_at"), "isoformat") else str(r.get("occurred_at")) if r.get("occurred_at") else None,
                "surface": r.get("surface"),
                "action": r.get("action"),
                "vendorCode": r.get("vendor_code"),
                "targetVendorCode": r.get("target_vendor_code"),
                "operationCode": r.get("operation_code"),
                "decisionCode": r.get("decision_code"),
                "allowed": bool(r.get("allowed")),
                "httpStatus": r.get("http_status"),
                "correlationId": r.get("correlation_id"),
                "transactionId": r.get("transaction_id"),
                "metadata": r.get("metadata") if isinstance(r.get("metadata"), dict) else {},
            }
        )

    return items, next_cursor


def _handle_get_policy_decisions(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/registry/policy-decisions?vendorCode=&operationCode=&decisionCode=&dateFrom=&dateTo=&limit=&cursor="""
    try:
        qp = _parse_query_params(event)
        limit = validate_limit(qp.get("limit"), default=DEFAULT_LIMIT, minimum=1, maximum=MAX_LIMIT)
        vendor_code = (qp.get("vendorcode") or "").strip() or None
        operation_code = (qp.get("operationcode") or "").strip() or None
        decision_code = (qp.get("decisioncode") or "").strip() or None
        date_from = (qp.get("datefrom") or "").strip() or None
        date_to = (qp.get("dateto") or "").strip() or None
        cursor = (qp.get("cursor") or "").strip() or None

        with _get_connection() as conn:
            items, next_cursor = _list_policy_decisions(
                conn,
                vendor_code=vendor_code,
                operation_code=operation_code,
                decision_code=decision_code,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                cursor=cursor,
            )
        return _success(200, {"items": items, "nextCursor": next_cursor, "count": len(items)})
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


POLICY_SIMULATOR_ACTIONS = frozenset({
    "EXECUTE",
    "AI_EXECUTE_DATA",
    "AI_EXECUTE_PROMPT",
    "AUDIT_READ",
    "AUDIT_EXPAND_SENSITIVE",
})


def _extract_authorizer_groups(event: dict[str, Any]) -> list[str]:
    auth = (event.get("requestContext") or {}).get("authorizer") or {}
    jwt_obj = auth.get("jwt") if isinstance(auth, dict) else {}
    claims = jwt_obj.get("claims") if isinstance(jwt_obj, dict) else {}
    if not isinstance(claims, dict):
        return []
    raw = claims.get("groups") or claims.get("group")
    if isinstance(raw, list):
        return [str(v).strip() for v in raw if str(v).strip()]
    if isinstance(raw, str) and raw.strip():
        return [part.strip() for part in raw.replace(",", " ").split() if part.strip()]
    return []


def _handle_get_policy_simulator(event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/registry/policy-simulator?vendorCode=&operationCode=&targetVendorCode=&action="""
    try:
        qp = _parse_query_params(event)
        action = (qp.get("action") or "").strip().upper()
        if action not in POLICY_SIMULATOR_ACTIONS:
            return _error(
                400,
                "VALIDATION_ERROR",
                f"action must be one of: {', '.join(sorted(POLICY_SIMULATOR_ACTIONS))}",
            )

        vendor_code = (qp.get("vendorcode") or "").strip() or None
        operation_code = (qp.get("operationcode") or "").strip() or None
        target_vendor_code = (qp.get("targetvendorcode") or "").strip() or None
        groups = _extract_authorizer_groups(event)

        ctx = PolicyContext(
            surface="ADMIN",
            action=action,
            vendor_code=vendor_code,
            target_vendor_code=target_vendor_code,
            operation_code=operation_code,
            requested_source_vendor_code=None,
            is_admin=True,
            groups=groups,
            query={"log_decision": False, "enforce_allowlist": True},
        )

        with _get_connection() as conn:
            decision = evaluate_policy(ctx, conn=conn)

        return _success(
            200,
            {
                "allowed": decision.allow,
                "decisionCode": decision.decision_code,
                "httpStatus": decision.http_status,
                "message": decision.message,
                "metadata": decision.metadata,
            },
        )
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


EXTRA_GLOBAL_GATE_KEYS = frozenset({"ai_formatter_enabled"})
VALID_GATE_KEYS = frozenset(set(GATE_BY_REQUEST_TYPE.values()) | set(EXTRA_GLOBAL_GATE_KEYS))

GATE_DESCRIPTIONS = {
    "GATE_ALLOWLIST_RULE": "Vendor changes to allowlist rules require admin approval",
    "GATE_MAPPING_CONFIG": "Vendor changes to mappings require admin approval",
    "GATE_VENDOR_CONTRACT_CHANGE": "Vendor contract overrides require admin approval",
    "GATE_ENDPOINT_CONFIG": "Vendor endpoint config changes require admin approval",
    "ai_formatter_enabled": "Global AI formatter enable/disable toggle",
}


def _handle_get_feature_gates(event: dict[str, Any]) -> dict[str, Any]:
    """
    GET /v1/registry/feature-gates
    Returns array of feature gates with gateKey (feature_code), enabled (is_enabled), updatedAt.
    """
    try:
        with _get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT feature_code, vendor_code, is_enabled, updated_at
                    FROM control_plane.feature_gates
                    ORDER BY feature_code, vendor_code NULLS FIRST
                    """,
                )
                rows = cur.fetchall() or []

        items = []
        for r in rows:
            d = dict(r)
            items.append({
                "gateKey": d.get("feature_code"),
                "enabled": bool(d.get("is_enabled", False)),
                "vendorCode": d.get("vendor_code"),
                "updatedAt": d.get("updated_at").isoformat() if d.get("updated_at") else None,
            })
        return _success(200, {"items": items})
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_put_feature_gate(event: dict[str, Any], gate_key: str | None) -> dict[str, Any]:
    """
    PUT /v1/registry/feature-gates/{gateKey}
    Body: { "enabled": true | false }
    Updates control_plane.feature_gates.is_enabled for global gate (vendor_code NULL).
    """
    feature_code = (gate_key or "").strip()
    if not feature_code or feature_code not in VALID_GATE_KEYS:
        return _error(
            400,
            "VALIDATION_ERROR",
            f"gateKey must be one of: {', '.join(sorted(VALID_GATE_KEYS))}",
        )

    body = _parse_body(event.get("body"))
    if not isinstance(body, dict):
        return _error(400, "VALIDATION_ERROR", "Request body must be a JSON object")

    enabled_raw = body.get("enabled")
    if enabled_raw is None:
        return _error(400, "VALIDATION_ERROR", "enabled is required")

    is_enabled = enabled_raw if isinstance(enabled_raw, bool) else str(enabled_raw).lower() in ("true", "1", "yes")

    try:
        with _get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO control_plane.feature_gates (feature_code, vendor_code, is_enabled)
                    VALUES (%s, NULL, %s)
                    ON CONFLICT (feature_code) WHERE (vendor_code IS NULL) DO UPDATE SET
                        is_enabled = EXCLUDED.is_enabled,
                        updated_at = now()
                    RETURNING feature_code, vendor_code, is_enabled, updated_at
                    """,
                    (feature_code, is_enabled),
                )
                row = cur.fetchone()

        if not row:
            return _error(500, "INTERNAL_ERROR", "Failed to update feature gate")
        d = dict(row)
        out = {
            "gateKey": d.get("feature_code"),
            "enabled": bool(d.get("is_enabled", False)),
            "vendorCode": d.get("vendor_code"),
            "updatedAt": d.get("updated_at").isoformat() if d.get("updated_at") else None,
        }
        return _success(200, out)
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_get_platform_features(_event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/registry/platform/features."""
    try:
        with _get_connection() as conn:
            state = get_platform_rollout_state(conn)
        return _success(200, state)
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_get_platform_phases(_event: dict[str, Any]) -> dict[str, Any]:
    """GET /v1/registry/platform/phases."""
    try:
        with _get_connection() as conn:
            phases = list_platform_phases(conn)
        return _success(200, {"items": phases})
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_put_platform_current_phase(event: dict[str, Any]) -> dict[str, Any]:
    """PUT /v1/registry/platform/settings/current-phase."""
    body = _parse_body(event.get("body"))
    if not isinstance(body, dict):
        return _error(400, "VALIDATION_ERROR", "Request body must be a JSON object")
    phase_code = body.get("phaseCode") or body.get("phase_code")
    if not phase_code:
        return _error(400, "VALIDATION_ERROR", "phaseCode is required")
    try:
        with _get_connection() as conn:
            updated = set_current_phase(conn, str(phase_code))
            state = get_platform_rollout_state(conn)
        return _success(
            200,
            {
                "setting": updated,
                "currentPhase": state.get("currentPhase"),
                "effectiveFeatures": state.get("effectiveFeatures", {}),
            },
        )
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_put_platform_feature(event: dict[str, Any], feature_code: str | None) -> dict[str, Any]:
    """PUT /v1/registry/platform/features/{featureCode}."""
    code = (feature_code or "").strip()
    if not code:
        return _error(400, "VALIDATION_ERROR", "featureCode is required")
    body = _parse_body(event.get("body"))
    if not isinstance(body, dict):
        return _error(400, "VALIDATION_ERROR", "Request body must be a JSON object")
    if "isEnabled" not in body and "is_enabled" not in body:
        return _error(400, "VALIDATION_ERROR", "isEnabled is required (true|false|null)")
    enabled_raw = body.get("isEnabled") if "isEnabled" in body else body.get("is_enabled")
    if enabled_raw not in (True, False, None):
        return _error(400, "VALIDATION_ERROR", "isEnabled must be true, false, or null")

    description_is_present = "description" in body
    description_val = body.get("description")
    if description_is_present and description_val is not None and not isinstance(description_val, str):
        return _error(400, "VALIDATION_ERROR", "description must be a string or null")
    if isinstance(description_val, str):
        description_val = description_val.strip() or None
    try:
        with _get_connection() as conn:
            updated = update_platform_feature(
                conn,
                code,
                enabled_raw,
                description_is_present=description_is_present,
                description=description_val,
            )
            state = get_platform_rollout_state(conn)
        updated["effectiveEnabled"] = bool(state.get("effectiveFeatures", {}).get(updated["featureCode"], False))
        return _success(200, updated)
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_get_change_requests(event: dict[str, Any]) -> dict[str, Any]:
    """
    GET /v1/registry/change-requests?status=PENDING&vendorCode=&limit=&offset=&source=
    Lists change requests. source=allowlist -> allowlist_change_requests; else vendor_change_requests.
    """
    qp = _parse_query_params(event)
    status = (qp.get("status") or "PENDING").strip().upper()
    vendor_code = (qp.get("vendorcode") or "").strip().upper() or None
    source = (qp.get("source") or "").strip().lower()
    if status not in ("PENDING", "APPROVED", "REJECTED", "CANCELLED"):
        status = "PENDING"
    limit_val = validate_limit(qp.get("limit"), 50, 1, 200)
    offset_val = 0
    try:
        raw_offset = qp.get("offset")
        if raw_offset is not None:
            offset_val = max(0, int(raw_offset))
    except (TypeError, ValueError):
        pass
    try:
        with _get_connection() as conn:
            if source == "allowlist":
                conditions = ["status = %s"]
                params: list[Any] = [status]
                if vendor_code:
                    conditions.append("source_vendor_code = %s")
                    params.append(vendor_code)
                where = " AND ".join(conditions)
                params.extend([limit_val, offset_val])
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        f"""
                        SELECT id, source_vendor_code, target_vendor_codes, use_wildcard_target,
                               operation_code, direction, request_type, rule_scope, status,
                               requested_by, reviewed_by, decision_reason, created_at, updated_at, raw_payload
                        FROM control_plane.allowlist_change_requests
                        WHERE {where}
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        params,
                    )
                    rows = cur.fetchall()
                items = []
                for r in rows or []:
                    d = dict(r)
                    items.append({
                        "id": str(d.get("id", "")),
                        "sourceVendorCode": d.get("source_vendor_code"),
                        "targetVendorCodes": d.get("target_vendor_codes") or [],
                        "useWildcardTarget": d.get("use_wildcard_target", False),
                        "operationCode": d.get("operation_code"),
                        "direction": d.get("direction"),
                        "requestType": d.get("request_type"),
                        "ruleScope": d.get("rule_scope"),
                        "status": d.get("status"),
                        "requestedBy": d.get("requested_by"),
                        "reviewedBy": d.get("reviewed_by"),
                        "decisionReason": d.get("decision_reason"),
                        "createdAt": d.get("created_at").isoformat() if d.get("created_at") else None,
                        "updatedAt": d.get("updated_at").isoformat() if d.get("updated_at") else None,
                        "rawPayload": d.get("raw_payload"),
                    })
            else:
                conditions = ["status = %s"]
                params = [status]
                if vendor_code:
                    conditions.append("requesting_vendor_code = %s")
                    params.append(vendor_code)
                where = " AND ".join(conditions)
                params.extend([limit_val, offset_val])
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        f"""
                        SELECT id, requesting_vendor_code, target_vendor_code, request_type, operation_code,
                               flow_direction, payload, summary, status, created_at, updated_at
                        FROM control_plane.vendor_change_requests
                        WHERE {where}
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        params,
                    )
                    rows = cur.fetchall()
                items = []
                for r in rows or []:
                    d = dict(r)
                    items.append({
                        "id": str(d.get("id", "")),
                        "requestType": d.get("request_type"),
                        "status": d.get("status"),
                        "requestingVendorCode": d.get("requesting_vendor_code"),
                        "targetVendorCode": d.get("target_vendor_code"),
                        "operationCode": d.get("operation_code"),
                        "flowDirection": d.get("flow_direction"),
                        "summary": d.get("summary"),
                        "createdAt": d.get("created_at").isoformat() if d.get("created_at") else None,
                        "updatedAt": d.get("updated_at").isoformat() if d.get("updated_at") else None,
                        "payload": d.get("payload"),
                    })
            return _success(200, {"items": items})
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_post_change_request_decision(event: dict[str, Any], request_id: str) -> dict[str, Any]:
    """
    POST /v1/registry/change-requests/{id}/decision - approve or reject.
    Tries allowlist_change_requests first; if not found, uses vendor_change_requests.
    """
    if not request_id or not str(request_id).strip():
        return _error(400, "VALIDATION_ERROR", "Change request id is required")
    try:
        import uuid as uuid_mod
        uuid_mod.UUID(request_id)
    except (ValueError, TypeError):
        return _error(400, "VALIDATION_ERROR", "Invalid change request id")

    body = _parse_body(event.get("body")) or {}
    action_raw = (body.get("action") or "").strip().upper()
    if action_raw not in ("APPROVE", "REJECT"):
        return _error(400, "VALIDATION_ERROR", "action must be APPROVE or REJECT")
    reason = (body.get("reason") or body.get("decisionReason") or "").strip() or None
    decided_by = _get_audit_actor(event)

    try:
        with _get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM control_plane.allowlist_change_requests WHERE id = %s::uuid",
                    (request_id,),
                )
                acr_row = cur.fetchone()
            if acr_row is not None:
                row_d = dict(acr_row)
                if (row_d.get("status") or "").upper() != "PENDING":
                    return _error(400, "VALIDATION_ERROR", f"Change request is not PENDING (status={row_d.get('status')})")
                src_vendor = row_d.get("source_vendor_code", "")

                if action_raw == "REJECT":
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE control_plane.allowlist_change_requests
                            SET status = 'REJECTED', reviewed_by = %s, decision_reason = %s, updated_at = now()
                            WHERE id = %s::uuid
                            """,
                            (decided_by, reason, request_id),
                        )
                    _write_audit_event(
                        conn,
                        transaction_id=f"allowlist-change-request-{request_id}",
                        action="ALLOWLIST_CHANGE_REQUEST_REJECTED",
                        vendor_code=src_vendor,
                        details={"id": request_id, "decided_by": decided_by, "reason": reason},
                    )
                    return _success(200, {"id": request_id, "status": "REJECTED"})

                from approval_utils import apply_allowlist_change_request
                try:
                    apply_allowlist_change_request(conn, row_d, decided_by, reason)
                    _write_audit_event(
                        conn,
                        transaction_id=f"allowlist-change-request-{request_id}",
                        action="ALLOWLIST_CHANGE_REQUEST_APPROVED",
                        vendor_code=src_vendor,
                        details={"id": request_id, "decided_by": decided_by},
                    )
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute(
                            "SELECT id, status, updated_at FROM control_plane.allowlist_change_requests WHERE id = %s::uuid",
                            (request_id,),
                        )
                        r = cur.fetchone()
                    return _success(200, {
                        "id": str(r["id"]),
                        "status": "APPROVED",
                        "updatedAt": r["updated_at"].isoformat() if r.get("updated_at") else None,
                    })
                except ValueError as e:
                    return _error(400, "APPLICATION_ERROR", str(e))
                except Exception as e:
                    return _error(500, "APPLICATION_ERROR", str(e))

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM control_plane.vendor_change_requests WHERE id = %s::uuid",
                    (request_id,),
                )
                row = cur.fetchone()
            if not row:
                return _error(404, "NOT_FOUND", "Change request not found")
            row_d = dict(row)
            if (row_d.get("status") or "").upper() != "PENDING":
                return _error(400, "VALIDATION_ERROR", f"Change request is not PENDING (status={row_d.get('status')})")

            if action_raw == "REJECT":
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE control_plane.vendor_change_requests
                        SET status = 'REJECTED', decision_reason = %s, decided_by = %s, decided_at = now(), updated_at = now()
                        WHERE id = %s::uuid
                        """,
                        (reason, decided_by, request_id),
                    )
                _write_audit_event(
                    conn,
                    transaction_id=f"vendor-change-request-{request_id}",
                    action="VENDOR_CHANGE_REQUEST_REJECTED",
                    vendor_code=row_d.get("requesting_vendor_code", ""),
                    details={"id": request_id, "decided_by": decided_by, "reason": reason},
                )
                return _success(200, {"id": request_id, "status": "REJECTED"})

            from approval_utils import apply_vendor_change_request
            try:
                apply_vendor_change_request(conn, row_d, decided_by, reason)
                _write_audit_event(
                    conn,
                    transaction_id=f"vendor-change-request-{request_id}",
                    action="VENDOR_CHANGE_REQUEST_APPROVED",
                    vendor_code=row_d.get("requesting_vendor_code", ""),
                    details={"id": request_id, "decided_by": decided_by},
                )
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        "SELECT id, status, decided_at FROM control_plane.vendor_change_requests WHERE id = %s::uuid",
                        (request_id,),
                    )
                    r = cur.fetchone()
                return _success(200, {
                    "id": str(r["id"]),
                    "status": "APPROVED",
                    "decidedAt": r["decided_at"].isoformat() if r.get("decided_at") else None,
                })
            except ValueError as e:
                return _error(400, "APPLICATION_ERROR", str(e))
            except Exception as e:
                return _error(500, "APPLICATION_ERROR", str(e))
    except ValueError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _handle_approve_change_request(event: dict[str, Any], request_id: str) -> dict[str, Any]:
    """POST /v1/registry/change-requests/{id}/approve - delegates to decision endpoint for vendor_change_requests."""
    event = dict(event)
    if "body" not in event or not event["body"]:
        event["body"] = json.dumps({"action": "APPROVE"})
    elif isinstance(event["body"], str):
        try:
            b = json.loads(event["body"]) if event["body"] else {}
        except json.JSONDecodeError:
            b = {}
        b["action"] = "APPROVE"
        event["body"] = json.dumps(b)
    return _handle_post_change_request_decision(event, request_id)


def _handle_reject_change_request(event: dict[str, Any], request_id: str) -> dict[str, Any]:
    """POST /v1/registry/change-requests/{id}/reject - delegates to decision endpoint for vendor_change_requests."""
    body = _parse_body(event.get("body")) or {}
    reason = (body.get("reason") or "").strip() or None
    event = dict(event)
    event["body"] = json.dumps({"action": "REJECT", "reason": reason})
    return _handle_post_change_request_decision(event, request_id)


def _handler_impl(event: dict[str, Any], context: object) -> dict[str, Any]:
    """
    Handle Control Plane Registry API.

    All GET and POST under /v1/registry/* require JWT authorizer (Okta).

    GET  /v1/registry/vendors     -> list_vendors()  -> { items, nextCursor }
    GET  /v1/registry/operations -> list_operations() -> { items, nextCursor }
    GET  /v1/registry/allowlist   -> list_allowlist() -> { items, nextCursor }
    GET  /v1/registry/endpoints   -> list_endpoints() -> { items, nextCursor }
    GET  /v1/registry/readiness   -> ?vendorCode=&operationCode= -> { vendorCode, operationCode?, checks, overallOk } or { vendorCode, items }
    GET  /v1/registry/contracts   -> { operationCode, canonicalVersion, requestSchema }
    POST /v1/registry/vendors     -> { vendor_code, vendor_name }
    POST /v1/registry/operations  -> { operation_code, description?, ... }
    POST /v1/registry/allowlist   -> { source_vendor_code, target_vendor_code, operation_code }
    POST /v1/registry/endpoints  -> { vendor_code, operation_code, url, ... }

    Validation: vendor_code like LH001, operation_code like SEND_RECEIPT.
    Upserts are idempotent. Audit events written with vendor_code=COMPANY_A (POC).
    """
    _normalize_event(event)
    path = event.get("path", "") or event.get("rawPath", "")
    segments = [s for s in path.strip("/").split("/") if s]

    # Require JWT authorizer for all /v1/registry/* GET and POST
    if len(segments) >= 2 and segments[:2] == ["v1", "registry"]:
        auth_err = require_admin_secret(event)  # JWT (admin role)
        is_admin = auth_err is None
        if auth_err is not None:
            return add_cors_to_response(auth_err)
        decision = evaluate_policy(
            PolicyContext(
                surface="ADMIN",
                action="REGISTRY_READ" if event.get("httpMethod") == "GET" else "REGISTRY_WRITE",
                vendor_code="ADMIN" if is_admin else None,
                target_vendor_code=None,
                operation_code=None,
                requested_source_vendor_code=None,
                is_admin=is_admin,
                groups=[],
                query={},
            )
        )
        if not decision.allow:
            return add_cors_to_response(policy_denied_response(decision))

    # POST /v1/registry/readiness/batch - batch readiness for multiple vendors
    if (
        len(segments) == 4
        and segments[:4] == ["v1", "registry", "readiness", "batch"]
        and event.get("httpMethod") == "POST"
    ):
        return _handle_post_readiness_batch(event)

    # GET /v1/registry/readiness - vendor readiness report
    if segments == ["v1", "registry", "readiness"] and event.get("httpMethod") == "GET":
        return _handle_get_readiness(event)

    # GET /v1/registry/contracts - list with optional filters
    if segments == ["v1", "registry", "contracts"] and event.get("httpMethod") == "GET":
        return _handle_get_contracts(event)

    # POST /v1/registry/contracts - upsert canonical contract
    if segments == ["v1", "registry", "contracts"] and event.get("httpMethod") == "POST":
        return _handle_post_contracts(event)

    # POST /v1/registry/operations/{operationCode}/canonical-version - set default version
    if (
        len(segments) == 5
        and segments[:3] == ["v1", "registry", "operations"]
        and segments[4] == "canonical-version"
        and event.get("httpMethod") == "POST"
    ):
        operation_code = segments[3] or (event.get("pathParameters") or {}).get("operationCode")
        return _handle_set_canonical_version(event, operation_code)

    # GET /v1/registry/operations - read-only
    if segments == ["v1", "registry", "operations"] and event.get("httpMethod") == "GET":
        return _handle_get_operations(event)

    # GET /v1/registry/vendors - read-only
    if segments == ["v1", "registry", "vendors"] and event.get("httpMethod") == "GET":
        return _handle_get_vendors(event)

    # GET /v1/registry/usage - aggregate counts per vendor/api_key (admin, cost visibility)
    if segments == ["v1", "registry", "usage"] and event.get("httpMethod") == "GET":
        return _handle_get_usage(event)

    # GET /v1/registry/mission-control/topology - integration graph nodes + allowlist edges
    if segments == ["v1", "registry", "mission-control", "topology"] and event.get("httpMethod") == "GET":
        return _handle_get_mission_control_topology(event)

    # GET /v1/registry/mission-control/activity - recent execute + policy deny metadata
    if segments == ["v1", "registry", "mission-control", "activity"] and event.get("httpMethod") == "GET":
        return _handle_get_mission_control_activity(event)

    # GET /v1/registry/policy-decisions - policy observability stream (admin)
    if segments == ["v1", "registry", "policy-decisions"] and event.get("httpMethod") == "GET":
        return _handle_get_policy_decisions(event)

    # GET /v1/registry/policy-simulator - evaluate policy without execution side effects
    if segments == ["v1", "registry", "policy-simulator"] and event.get("httpMethod") == "GET":
        return _handle_get_policy_simulator(event)

    # GET /v1/registry/platform/features
    if segments == ["v1", "registry", "platform", "features"] and event.get("httpMethod") == "GET":
        return _handle_get_platform_features(event)

    # GET /v1/registry/platform/phases
    if segments == ["v1", "registry", "platform", "phases"] and event.get("httpMethod") == "GET":
        return _handle_get_platform_phases(event)

    # PUT /v1/registry/platform/settings/current-phase
    if (
        segments == ["v1", "registry", "platform", "settings", "current-phase"]
        and event.get("httpMethod") == "PUT"
    ):
        return _handle_put_platform_current_phase(event)

    # PUT /v1/registry/platform/features/{featureCode}
    if (
        len(segments) == 5
        and segments[:4] == ["v1", "registry", "platform", "features"]
        and event.get("httpMethod") == "PUT"
    ):
        feature_code = segments[4] or (event.get("pathParameters") or {}).get("featureCode")
        return _handle_put_platform_feature(event, feature_code)

    # GET /v1/registry/feature-gates - list feature gates
    if (
        len(segments) == 3
        and segments[:3] == ["v1", "registry", "feature-gates"]
        and event.get("httpMethod") == "GET"
    ):
        return _handle_get_feature_gates(event)

    # PUT /v1/registry/feature-gates/{gateKey} - update feature gate
    if (
        len(segments) == 4
        and segments[:3] == ["v1", "registry", "feature-gates"]
        and event.get("httpMethod") == "PUT"
    ):
        gate_key = segments[3] or (event.get("pathParameters") or {}).get("gateKey")
        return _handle_put_feature_gate(event, gate_key)

    # GET /v1/registry/change-requests - list change requests (admin approvals)
    if (
        len(segments) == 3
        and segments[:3] == ["v1", "registry", "change-requests"]
        and event.get("httpMethod") == "GET"
    ):
        return _handle_get_change_requests(event)

    # POST /v1/registry/change-requests/{id}/decision
    if (
        len(segments) == 5
        and segments[:3] == ["v1", "registry", "change-requests"]
        and segments[4] == "decision"
        and event.get("httpMethod") == "POST"
    ):
        req_id = segments[3] or (event.get("pathParameters") or {}).get("id")
        return _handle_post_change_request_decision(event, req_id)

    # POST /v1/registry/change-requests/{id}/approve
    if (
        len(segments) == 5
        and segments[:3] == ["v1", "registry", "change-requests"]
        and segments[4] == "approve"
        and event.get("httpMethod") == "POST"
    ):
        req_id = segments[3] or (event.get("pathParameters") or {}).get("id")
        return _handle_approve_change_request(event, req_id)

    # POST /v1/registry/change-requests/{id}/reject
    if (
        len(segments) == 5
        and segments[:3] == ["v1", "registry", "change-requests"]
        and segments[4] == "reject"
        and event.get("httpMethod") == "POST"
    ):
        req_id = segments[3] or (event.get("pathParameters") or {}).get("id")
        return _handle_reject_change_request(event, req_id)

    # GET /v1/registry/allowlist - read-only
    if segments == ["v1", "registry", "allowlist"] and event.get("httpMethod") == "GET":
        return _handle_get_allowlist(event)

    # GET /v1/registry/endpoints - read-only
    if segments == ["v1", "registry", "endpoints"] and event.get("httpMethod") == "GET":
        return _handle_get_endpoints(event)

    # GET /v1/registry/auth-profiles - list (vendorCode required)
    if segments == ["v1", "registry", "auth-profiles"] and event.get("httpMethod") == "GET":
        return _handle_get_auth_profiles(event)

    # POST /v1/registry/auth-profiles
    if segments == ["v1", "registry", "auth-profiles"] and event.get("httpMethod") == "POST":
        return _handle_post_auth_profiles(event)

    # POST /v1/registry/auth-profiles/test-connection
    if (
        len(segments) == 4
        and segments == ["v1", "registry", "auth-profiles", "test-connection"]
        and event.get("httpMethod") == "POST"
    ):
        return _handle_post_auth_profile_test_connection(event)

    # POST /v1/registry/auth-profiles/token-preview
    if (
        len(segments) == 4
        and segments == ["v1", "registry", "auth-profiles", "token-preview"]
        and event.get("httpMethod") == "POST"
    ):
        return _handle_post_auth_profile_token_preview(event)

    # POST /v1/registry/auth-profiles/mtls-validate
    if (
        len(segments) == 4
        and segments == ["v1", "registry", "auth-profiles", "mtls-validate"]
        and event.get("httpMethod") == "POST"
    ):
        return _handle_post_auth_profile_mtls_validate(event)

    # PATCH /v1/registry/auth-profiles/{id}
    if (
        len(segments) == 4
        and segments[:3] == ["v1", "registry", "auth-profiles"]
        and event.get("httpMethod") == "PATCH"
    ):
        profile_id = segments[3] or (event.get("pathParameters") or {}).get("id")
        return _handle_patch_auth_profile(event, profile_id)

    # DELETE /v1/registry/auth-profiles/{id}
    if (
        len(segments) == 4
        and segments[:3] == ["v1", "registry", "auth-profiles"]
        and event.get("httpMethod") == "DELETE"
    ):
        profile_id = segments[3] or (event.get("pathParameters") or {}).get("id")
        return _handle_delete_auth_profile(profile_id)

    # DELETE /v1/registry/allowlist/{id}
    if (
        len(segments) >= 4
        and segments[:3] == ["v1", "registry", "allowlist"]
        and event.get("httpMethod") == "DELETE"
    ):
        # Prefer pathParameters (reliable with API Gateway); fallback to path segment
        path_params = event.get("pathParameters") or {}
        entry_id = path_params.get("id") or (segments[3] if len(segments) > 3 else None)
        return _handle_delete_allowlist(event, context, entry_id)

    if event.get("httpMethod") != "POST":
        return _error(405, "METHOD_NOT_ALLOWED", "Method not allowed")

    if segments != ["v1", "registry", "vendors"] and segments != ["v1", "registry", "operations"] and segments != ["v1", "registry", "allowlist"] and segments != ["v1", "registry", "endpoints"] and segments != ["v1", "registry", "contracts"]:
        return _error(404, "NOT_FOUND", "Not found")

    resource = segments[2]
    body = _parse_body(event.get("body"))
    req_ctx = event.get("requestContext") or {}
    request_id = req_ctx.get("requestId") or str(uuid.uuid4())
    audit_actor = _get_audit_actor(event)

    try:
        with _get_connection() as conn:
            if resource == "vendors":
                vendor_code = _validate_vendor_code(body.get("vendor_code") or body.get("vendorCode"))
                vendor_name = _validate_vendor_name(body.get("vendor_name") or body.get("vendorName"))
                row = _upsert_vendor(conn, vendor_code, vendor_name, audit_actor, request_id)
                return _success(200, {"vendor": row})

            if resource == "operations":
                operation_code = _validate_operation_code(body.get("operation_code") or body.get("operationCode"))
                description = _validate_optional_str(body.get("description"), "description")
                canonical_version = _validate_optional_str(body.get("canonical_version") or body.get("canonicalVersion"), "canonical_version", 32)
                is_async_capable = body.get("is_async_capable") if body.get("is_async_capable") is not None else (body.get("isAsyncCapable") if body.get("isAsyncCapable") is not None else None)
                if is_async_capable is not None and not isinstance(is_async_capable, bool):
                    is_async_capable = str(is_async_capable).lower() in ("true", "1")
                is_active = body.get("is_active") if body.get("is_active") is not None else (body.get("isActive") if body.get("isActive") is not None else None)
                if is_active is not None and not isinstance(is_active, bool):
                    is_active = str(is_active).lower() in ("true", "1")
                direction_policy = _validate_direction_policy_value(
                    body.get("direction_policy") or body.get("directionPolicy")
                    or body.get("hub_direction_policy") or body.get("hubDirectionPolicy")
                )
                ai_presentation_mode = _validate_operation_ai_mode(
                    body.get("ai_presentation_mode") or body.get("aiPresentationMode")
                )
                ai_formatter_prompt = _validate_optional_str(
                    body.get("ai_formatter_prompt") or body.get("aiFormatterPrompt"),
                    "ai_formatter_prompt",
                    4000,
                )
                ai_formatter_model = _validate_optional_str(
                    body.get("ai_formatter_model") or body.get("aiFormatterModel"),
                    "ai_formatter_model",
                    256,
                )
                row = _upsert_operation(
                    conn,
                    operation_code,
                    description,
                    canonical_version,
                    is_async_capable,
                    is_active,
                    direction_policy,
                    ai_presentation_mode,
                    ai_formatter_prompt,
                    ai_formatter_model,
                    audit_actor,
                    request_id,
                )
                return _success(
                    200,
                    {"operation": _to_camel_case_dict(dict(row))},
                )

            if resource == "allowlist":
                op_code = _validate_operation_code(body.get("operation_code") or body.get("operationCode"))
                direction_policy = _get_operation_direction_policy(conn, op_code)

                raw_flow_direction = body.get("flow_direction") or body.get("flowDirection")
                if isinstance(raw_flow_direction, str) and not raw_flow_direction.strip():
                    raw_flow_direction = None
                try:
                    if not raw_flow_direction:
                        flow_direction = derive_flow_direction_for_operation(direction_policy)
                    else:
                        flow_direction = _validate_flow_direction(raw_flow_direction)
                        if (
                            direction_policy
                            and direction_policy.strip().upper() == "PROVIDER_RECEIVES_ONLY"
                            and flow_direction != "OUTBOUND"
                        ):
                            raise DirectionPolicyViolation(
                                f"{op_code} flow_direction must be OUTBOUND for this operation. "
                                "Only 'Outbound – source calls target' is allowed for this operation."
                            )
                except DirectionPolicyViolation:
                    raise
                except ValueError as exc:
                    raise ValueError(str(exc)) from exc

                # Explicit pairs only: accept either scalar source/target or arrays sourceVendorCodes/targetVendorCodes.
                source_list_raw = body.get("source_vendor_codes") or body.get("sourceVendorCodes")
                target_list_raw = body.get("target_vendor_codes") or body.get("targetVendorCodes")
                source_raw = body.get("source_vendor_code") or body.get("sourceVendorCode")
                target_raw = body.get("target_vendor_code") or body.get("targetVendorCode")

                source_values: list[str] = []
                target_values: list[str] = []
                if isinstance(source_list_raw, list):
                    source_values = [_validate_vendor_code(str(v).strip()) for v in source_list_raw if str(v).strip()]
                elif source_raw and str(source_raw).strip():
                    source_values = [_validate_vendor_code(str(source_raw).strip())]
                if isinstance(target_list_raw, list):
                    target_values = [_validate_vendor_code(str(v).strip()) for v in target_list_raw if str(v).strip()]
                elif target_raw and str(target_raw).strip():
                    target_values = [_validate_vendor_code(str(target_raw).strip())]

                source_values = sorted(set(source_values))
                target_values = sorted(set(target_values))
                if not source_values:
                    raise ValueError("source_vendor_code or source_vendor_codes[] is required")
                if not target_values:
                    raise ValueError("target_vendor_code or target_vendor_codes[] is required")

                inserted: list[dict[str, Any]] = []
                for source in source_values:
                    for target in target_values:
                        row = _upsert_allowlist(
                            conn, source, target, op_code, flow_direction, audit_actor, request_id
                        )
                        inserted.append(_to_camel_case_dict(row))
                return _success(200, {"allowlist": inserted[0], "allowlists": inserted, "count": len(inserted)})

            if resource == "endpoints":
                vendor_code = _validate_vendor_code(body.get("vendor_code") or body.get("vendorCode"))
                operation_code = _validate_operation_code(body.get("operation_code") or body.get("operationCode"))
                flow_direction = _validate_endpoint_flow_direction(
                    body.get("flow_direction") or body.get("flowDirection")
                )
                url = _validate_url(body.get("url"))
                http_method = _validate_optional_str(body.get("http_method") or body.get("httpMethod"), "http_method", 16)
                payload_format = _validate_optional_str(body.get("payload_format") or body.get("payloadFormat"), "payload_format", 64)
                timeout_ms = _validate_optional_int(body.get("timeout_ms") or body.get("timeoutMs"), "timeout_ms")
                is_active = body.get("is_active") if body.get("is_active") is not None else (body.get("isActive") if body.get("isActive") is not None else None)
                if is_active is not None and not isinstance(is_active, bool):
                    is_active = str(is_active).lower() in ("true", "1")
                auth_profile_id_raw = body.get("authProfileId") or body.get("auth_profile_id")
                auth_profile_id = None
                if auth_profile_id_raw is not None and str(auth_profile_id_raw).strip():
                    auth_profile_id = str(auth_profile_id_raw).strip()
                    profile_row = _get_auth_profile_for_vendor(conn, auth_profile_id, vendor_code)
                    if not profile_row:
                        raise ValueError(
                            f"authProfileId {auth_profile_id} not found or does not belong to vendor {vendor_code}"
                        )
                row = _upsert_endpoint(
                    conn,
                    vendor_code,
                    operation_code,
                    url,
                    http_method,
                    payload_format,
                    timeout_ms,
                    is_active,
                    audit_actor,
                    request_id,
                    auth_profile_id=auth_profile_id,
                    flow_direction=flow_direction,
                )
                endpoint = _to_camel_case_dict(dict(row))
                if "vendorAuthProfileId" in endpoint and "authProfileId" not in endpoint:
                    endpoint["authProfileId"] = endpoint.get("vendorAuthProfileId")
                return _success(200, {"endpoint": endpoint})

    except DirectionPolicyViolation as e:
        log_json("WARN", "direction_policy_violation", ctx=get_context(event, context), error=str(e))
        return _error(400, "DIRECTION_POLICY_VIOLATION", str(e))
    except ValueError as e:
        log_json("WARN", "validation_failed", ctx=get_context(event, context), error=str(e))
        return _error(400, "VALIDATION_ERROR", str(e))
    except ConnectionError as e:
        return _error(503, "DB_ERROR", str(e))
    except Exception as e:
        return _error(500, "INTERNAL_ERROR", str(e))


def _safe_handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Catch unhandled exceptions to return structured 500 instead of generic API Gateway error."""
    try:
        return with_observability(_handler_impl, "registry")(event, context)
    except Exception as e:
        log_json("ERROR", "registry_unhandled", error=str(e))
        return _error(
            500,
            "INTERNAL_ERROR",
            str(e),
            details={"type": type(e).__name__},
        )


handler = _safe_handler
