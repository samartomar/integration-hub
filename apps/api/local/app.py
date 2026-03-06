"""Local HTTP API - wraps Lambda handlers for local development without AWS.

Exposes:
  POST /v1/execute               -> routing_lambda (Runtime API)
  POST /v1/ai/execute            -> ai_gateway_lambda (Runtime API - single source for execute)
  /v1/vendor/*                   -> vendor_registry_lambda
  /v1/registry/*                -> registry_lambda
  /v1/audit/*                    -> audit_lambda (Transactions, Events; JWT)
  /v1/admin/*                    -> routing_lambda (redrive; JWT)
  /v1/onboarding/*               -> onboarding_lambda (register; requires AWS in prod, may fail local)

Run: uvicorn apps.api.local.app:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Add apps/api/src/lambda so handlers can import sibling modules (admin_guard, etc.)
# app.py is at apps/api/local/app.py; repo root is parents[3].
_REPO_ROOT = Path(__file__).resolve().parents[3]
_LAMBDA_DIR = _REPO_ROOT / "apps" / "api" / "src" / "lambda"
if str(_LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(_LAMBDA_DIR))

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Integration Hub - Local API",
    description="Local development server wrapping Lambda handlers. No AWS.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _result_to_response(result: dict) -> Response:
    """Convert Lambda response dict to FastAPI Response."""
    import json

    status = result.get("statusCode", 500)
    body = result.get("body", "")
    if isinstance(body, dict):
        body = json.dumps(body, default=str)
    elif body is None:
        body = ""
    elif not isinstance(body, str):
        body = str(body)
    headers = result.get("headers") or {}
    headers = {k: str(v) for k, v in headers.items() if v is not None}
    content_type = headers.get("content-type") or headers.get("Content-Type") or "application/json"
    return Response(
        content=body,
        status_code=status,
        headers=headers,
        media_type=content_type,
    )


def _invoke_sync(handler, event: dict) -> Response:
    """Invoke Lambda handler and return HTTP response."""
    try:
        result = handler(event, None)
        if not isinstance(result, dict):
            return Response(content="Internal error: invalid handler response", status_code=500)
        return _result_to_response(result)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return Response(
            content=str(e),
            status_code=500,
            media_type="text/plain",
        )


# Lazy imports so apps/api/src/lambda is only loaded when handlers are used
def _get_routing_handler():
    from routing_lambda import handler

    return handler


def _get_vendor_handler():
    from vendor_registry_lambda import handler

    return handler


def _get_registry_handler():
    from registry_lambda import handler

    return handler


def _get_audit_handler():
    from audit_lambda import handler

    return handler


def _get_ai_handler():
    from ai_gateway_lambda import handler

    return handler


def _get_onboarding_handler():
    from onboarding_lambda import handler

    return handler


@app.api_route("/v1/execute", methods=["POST", "OPTIONS"])
async def runtime_execute(request: Request) -> Response:
    """Runtime API: POST /v1/execute (Authorization bearer JWT)."""
    if request.method == "OPTIONS":
        return Response(status_code=200)
    event = await _build_event(request)
    return _invoke_sync(_get_routing_handler(), event)


@app.api_route("/v1/ai/execute", methods=["POST", "OPTIONS"])
async def ai_execute(request: Request) -> Response:
    """AI Gateway: POST /v1/ai/execute."""
    if request.method == "OPTIONS":
        return Response(status_code=200)
    event = await _build_event(request)
    return _invoke_sync(_get_ai_handler(), event)


@app.api_route("/v1/ai/debug/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def ai_debug_api(request: Request, path: str) -> Response:
    """AI Debugger: /v1/ai/debug/* (JWT). Deterministic integration debugger."""
    if request.method == "OPTIONS":
        return Response(status_code=200)
    full_path = f"/v1/ai/debug/{path}" if path else "/v1/ai/debug"
    event = await _build_event(request, full_path)
    return _invoke_sync(_get_registry_handler(), event)


@app.api_route("/v1/vendor/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def vendor_api(request: Request, path: str) -> Response:   
    if request.method == "OPTIONS":
        return Response(status_code=200)
    full_path = f"/v1/vendor/{path}" if path else "/v1/vendor"
    event = await _build_event(request, full_path)
    # Proxy path for vendor: API Gateway sends proxy+ as pathParameters.proxy
    event["pathParameters"] = event.get("pathParameters") or {}
    event["pathParameters"]["proxy"] = path
    return _invoke_sync(_get_vendor_handler(), event)


@app.api_route("/v1/registry/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def registry_api(request: Request, path: str) -> Response:
    """Admin Registry: /v1/registry/* (JWT)."""
    if request.method == "OPTIONS":
        return Response(status_code=200)
    full_path = f"/v1/registry/{path}" if path else "/v1/registry"
    event = await _build_event(request, full_path)
    return _invoke_sync(_get_registry_handler(), event)


@app.api_route("/v1/flow/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"])
async def flow_api(request: Request, path: str) -> Response:
    """Admin Flow Builder: /v1/flow/* (JWT). Canonical-driven flow builder endpoints."""
    if request.method == "OPTIONS":
        return Response(status_code=200)
    full_path = f"/v1/flow/{path}" if path else "/v1/flow"
    event = await _build_event(request, full_path)
    return _invoke_sync(_get_registry_handler(), event)


@app.api_route("/v1/runtime/canonical/preflight", methods=["POST", "OPTIONS"])
async def runtime_preflight_api(request: Request) -> Response:
    """Runtime Preflight: POST /v1/runtime/canonical/preflight (JWT). Canonical runtime preflight."""
    if request.method == "OPTIONS":
        return Response(status_code=200)
    event = await _build_event(request, "/v1/runtime/canonical/preflight")
    return _invoke_sync(_get_registry_handler(), event)


@app.api_route("/v1/runtime/canonical/execute", methods=["POST", "OPTIONS"])
async def runtime_canonical_execute_api(request: Request) -> Response:
    """Canonical Execute: POST /v1/runtime/canonical/execute (JWT). Bridge canonical to runtime execute."""
    if request.method == "OPTIONS":
        return Response(status_code=200)
    event = await _build_event(request, "/v1/runtime/canonical/execute")
    return _invoke_sync(_get_registry_handler(), event)


@app.api_route("/v1/sandbox/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"])
async def sandbox_api(request: Request, path: str) -> Response:
    """Admin Sandbox: /v1/sandbox/* (JWT). Canonical-driven mock sandbox endpoints."""
    if request.method == "OPTIONS":
        return Response(status_code=200)
    full_path = f"/v1/sandbox/{path}" if path else "/v1/sandbox"
    event = await _build_event(request, full_path)
    return _invoke_sync(_get_registry_handler(), event)


@app.api_route("/v1/audit/{path:path}", methods=["GET", "OPTIONS"])
async def audit_api(request: Request, path: str) -> Response:
    """Audit: /v1/audit/* (JWT). Transactions list/detail, events."""
    if request.method == "OPTIONS":
        return Response(status_code=200)
    full_path = f"/v1/audit/{path}" if path else "/v1/audit"
    event = await _build_event(request, full_path)
    event["pathParameters"] = event.get("pathParameters") or {}
    if path:
        segments = path.strip("/").split("/")
        if segments and segments[0] == "transactions" and len(segments) > 1:
            event["pathParameters"]["transactionId"] = segments[1]
    return _invoke_sync(_get_audit_handler(), event)


@app.api_route("/v1/admin/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def admin_api(request: Request, path: str) -> Response:
    """Admin: /v1/admin/* (JWT). Redrive and other admin actions -> routing_lambda."""
    if request.method == "OPTIONS":
        return Response(status_code=200)
    full_path = f"/v1/admin/{path}" if path else "/v1/admin"
    event = await _build_event(request, full_path)
    event["pathParameters"] = event.get("pathParameters") or {}
    # routing_lambda expects path like /v1/admin/redrive/{transactionId}
    segments = path.strip("/").split("/")
    if len(segments) >= 2 and segments[0] == "redrive":
        event["pathParameters"]["transactionId"] = segments[1]
    return _invoke_sync(_get_routing_handler(), event)


@app.api_route("/v1/onboarding/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"])
async def onboarding_api(request: Request, path: str) -> Response:
    """Onboarding: /v1/onboarding/* (e.g. register). Requires AWS in prod; may fail locally."""
    if request.method == "OPTIONS":
        return Response(status_code=200)
    full_path = f"/v1/onboarding/{path}" if path else "/v1/onboarding"
    event = await _build_event(request, full_path)
    return _invoke_sync(_get_onboarding_handler(), event)


async def _build_event(request: Request, path: str | None = None) -> dict:
    """Build Lambda event from request (async body read)."""
    import os
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8", errors="replace") if body_bytes else None
    headers = {k.lower(): v for k, v in request.headers.items()}
    qs = request.query_params
    query_params = dict(qs) if qs else None
    p = path or request.url.path
    request_context = {
        "requestId": "local",
        "http": {"method": request.method, "path": p},
    }
    # AUTH_BYPASS: inject mock authorizer so Lambdas accept request without header auth.
    # Default is auth enforced; bypass only when explicitly enabled.
    auth_bypass_val = (os.environ.get("AUTH_BYPASS") or "").strip().lower()
    auth_bypass = auth_bypass_val in ("true", "1", "yes")
    if auth_bypass:
        default_vendor = os.environ.get("AUTH_BYPASS_VENDOR", "LH001").strip()
        default_lhcode = os.environ.get("AUTH_BYPASS_LHCODE", default_vendor).strip() or default_vendor
        request_context["authorizer"] = {
            "principalId": "local",
            "vendor_code": default_vendor,
            "jwt": {
                "claims": {
                    "sub": "local|auth-bypass",
                    "vendor_code": default_vendor,
                    # Keep local mock claims aligned with AWS JWT authorizer context.
                    "lhcode": default_lhcode,
                    "name": default_lhcode,
                },
            },
        }
    else:
        _attach_authorizer_from_bearer(headers, request_context, p)
    event = {
        "body": body_str,
        "headers": headers,
        "httpMethod": request.method,
        "path": p,
        "rawPath": p,
        "queryStringParameters": query_params,
        "pathParameters": {},
        "requestContext": request_context,
        "isBase64Encoded": False,
    }
    return event


def _extract_lhcode(value: str | None) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    match = re.search(r"\b(LH\d{3})\b", s, flags=re.IGNORECASE)
    return match.group(1).upper() if match else ""


def _local_auth_debug_enabled() -> bool:
    import os

    return (os.environ.get("LOCAL_AUTH_DEBUG") or "").strip().lower() in ("1", "true", "yes")


def _debug_auth(message: str, **fields: object) -> None:
    if not _local_auth_debug_enabled():
        return
    parts = [f"{k}={v}" for k, v in fields.items()]
    suffix = f" | {' '.join(parts)}" if parts else ""
    print(f"[local-auth] {message}{suffix}")


def _jwt_cfg_for_local_path(path: str):
    """Build route-aware JWT config for local auth parity."""
    import os
    from jwt_auth import JwtAuthConfig

    p = (path or "").strip().lower()
    is_admin = p.startswith("/v1/registry") or p.startswith("/v1/flow") or p.startswith("/v1/sandbox") or p.startswith("/v1/ai/debug") or p.startswith("/v1/audit") or p.startswith("/v1/admin") or p.startswith("/v1/runtime/canonical")
    is_vendor = p.startswith("/v1/vendor") or p.startswith("/v1/onboarding")
    is_runtime = p.startswith("/v1/execute") or p.startswith("/v1/ai/execute")
    route_profile = "admin" if is_admin else "vendor" if is_vendor else "runtime" if is_runtime else "generic"

    if is_admin:
        issuer = (os.environ.get("ADMIN_IDP_ISSUER") or os.environ.get("IDP_ISSUER") or "").strip().rstrip("/")
        audience = (os.environ.get("ADMIN_API_AUDIENCE") or os.environ.get("IDP_AUDIENCE") or "").strip()
        jwks_uri = (os.environ.get("ADMIN_IDP_JWKS_URL") or os.environ.get("IDP_JWKS_URL") or (f"{issuer}/v1/keys" if issuer else "")).strip()
    elif is_vendor:
        issuer = (os.environ.get("VENDOR_IDP_ISSUER") or os.environ.get("IDP_ISSUER") or "").strip().rstrip("/")
        audience = (os.environ.get("VENDOR_API_AUDIENCE") or os.environ.get("IDP_AUDIENCE") or "").strip()
        jwks_uri = (os.environ.get("VENDOR_IDP_JWKS_URL") or os.environ.get("IDP_JWKS_URL") or (f"{issuer}/v1/keys" if issuer else "")).strip()
    elif is_runtime:
        issuer = (os.environ.get("RUNTIME_IDP_ISSUER") or os.environ.get("IDP_ISSUER") or "").strip().rstrip("/")
        audience = (os.environ.get("RUNTIME_API_AUDIENCE") or os.environ.get("IDP_AUDIENCE") or "").strip()
        jwks_uri = (os.environ.get("RUNTIME_IDP_JWKS_URL") or os.environ.get("IDP_JWKS_URL") or (f"{issuer}/v1/keys" if issuer else "")).strip()
    else:
        issuer = (os.environ.get("IDP_ISSUER") or "").strip().rstrip("/")
        audience = (os.environ.get("IDP_AUDIENCE") or "").strip()
        jwks_uri = (os.environ.get("IDP_JWKS_URL") or (f"{issuer}/v1/keys" if issuer else "")).strip()

    if not issuer or not audience or not jwks_uri:
        _debug_auth(
            "missing jwt cfg",
            path=path,
            route_profile=route_profile,
            has_issuer=bool(issuer),
            has_audience=bool(audience),
            has_jwks=bool(jwks_uri),
        )
        return None

    algs_raw = (os.environ.get("IDP_ALLOWED_ALGS") or "RS256").strip()
    allowed_algs = [a.strip() for a in algs_raw.split(",") if a.strip()] or ["RS256"]
    _debug_auth(
        "selected jwt cfg",
        path=path,
        route_profile=route_profile,
        issuer=issuer,
        audience=audience,
        jwks_uri=jwks_uri,
    )
    return JwtAuthConfig(
        issuer=issuer,
        jwks_uri=jwks_uri,
        audiences=[audience],
        vendor_claim="bcpAuth",
        allowed_alg=allowed_algs[0],
        clock_skew_seconds=60,
        allowed_algs=allowed_algs,
    )


def _attach_authorizer_from_bearer(headers: dict[str, str], request_context: dict, path: str) -> None:
    """
    Local parity mode (AUTH_BYPASS=false):
    validate Authorization Bearer token via route-aware IDP env and attach authorizer claims.
    """
    auth_header = (headers.get("authorization") or "").strip()
    if not auth_header.lower().startswith("bearer "):
        _debug_auth("authorization header missing bearer", path=path, has_auth_header=bool(auth_header))
        return
    token = auth_header[7:].strip()
    if not token:
        _debug_auth("bearer token empty", path=path)
        return

    try:
        from jwt_auth import validate_jwt_for_authorizer

        cfg = _jwt_cfg_for_local_path(path)
        if not cfg:
            return
        claims = validate_jwt_for_authorizer(token, cfg)
        if not isinstance(claims, dict):
            _debug_auth("jwt validated but claims not dict", path=path)
            return

        bcp_auth = str(claims.get("bcpAuth") or "").strip().upper()
        vendor_candidates = (
            bcp_auth,
            claims.get("lhcode"),
            claims.get("vendor_code"),
            claims.get("name"),
            claims.get("entityId"),
            claims.get("preferred_username"),
            claims.get("email"),
            claims.get("sub"),
        )
        vendor_value = ""
        for c in vendor_candidates:
            val = str(c).strip() if c is not None and c != "" else ""
            if val:
                vendor_value = val
                break

        inferred_lhcode = _extract_lhcode(str(claims.get("lhcode") or bcp_auth or vendor_value))
        claims_for_ctx = dict(claims)
        if not str(claims_for_ctx.get("vendor_code") or "").strip():
            claims_for_ctx["vendor_code"] = bcp_auth or vendor_value or str(claims.get("sub") or "unknown")
        if not str(claims_for_ctx.get("lhcode") or "").strip():
            claims_for_ctx["lhcode"] = inferred_lhcode or bcp_auth or str(claims_for_ctx["vendor_code"])

        request_context["authorizer"] = {
            "principalId": str(vendor_value or claims.get("sub") or "unknown"),
            "vendor_code": str(claims_for_ctx["vendor_code"]),
            "jwt": {"claims": claims_for_ctx},
        }
        _debug_auth(
            "jwt attached to local authorizer",
            path=path,
            subject=claims.get("sub"),
            bcpAuth=claims.get("bcpAuth"),
            lhcode=claims_for_ctx.get("lhcode"),
            audience=claims.get("aud"),
            issuer=claims.get("iss"),
        )
    except Exception as e:
        _debug_auth("jwt validation failed", path=path, error=str(e))
        # Local dev parity mode: let downstream guards return auth errors naturally.
        return


@app.get("/health")
async def health() -> dict:
    """Health check for docker-compose."""
    import os
    auth_bypass_val = (os.environ.get("AUTH_BYPASS") or "").strip().lower()
    run_env = (os.environ.get("RUN_ENV") or "").strip().lower()
    auth_bypass = auth_bypass_val in ("true", "1", "yes")
    local_auth_debug = _local_auth_debug_enabled()
    return {
        "status": "ok",
        "mode": "local",
        "auth_bypass": auth_bypass,
        "local_auth_debug": local_auth_debug,
        "run_env": run_env or None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
