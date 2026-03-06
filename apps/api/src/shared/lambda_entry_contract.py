"""Shared Lambda Entry Contract decorator for protected HTTP lambdas.

Provides a consistent pattern for:
- Auth validation
- Identity extraction
- Policy evaluation
- Canonical response handling
- Exception handling with canonical internal errors

When to use:
- New protected HTTP lambdas that require auth + policy.
- Lambdas that should follow the platform contract (auth -> identity -> policy -> business logic -> canonical response).

When NOT to use:
- Worker lambdas (EventBridge, SQS) that have no JWT.
- Lambdas with custom auth flows (e.g. API key + JWT hybrid).
- Lambdas that intentionally use a different response envelope (e.g. ai_gateway_lambda).
- Existing lambdas unless explicitly migrating (gradual adoption).

Usage:
    from lambda_entry_contract import with_entry_contract, EntryContractConfig

    config = EntryContractConfig(
        surface="VENDOR",
        action="REGISTRY_READ",
        require_auth=True,
        require_policy=True,
        canonicalize_success=True,
    )

    @with_entry_contract(config)
    def handler(event, context, claims):
        # claims.bcpAuth, claims.roles, claims.scopes available
        return {"items": [...]}
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

# Ensure lambda modules are importable when this shared module is used
_lambda_dir = Path(__file__).resolve().parent.parent / "lambda"
if _lambda_dir.exists() and str(_lambda_dir) not in sys.path:
    sys.path.insert(0, str(_lambda_dir))

_LOG = logging.getLogger(__name__)


@dataclass
class EntryContractConfig:
    """Configuration for the lambda entry contract decorator."""

    surface: Literal["ADMIN", "VENDOR", "RUNTIME"]
    action: str
    require_auth: bool = True
    require_policy: bool = True
    canonicalize_success: bool = True
    expected_audience_env: str = "VENDOR_API_AUDIENCE"
    admin_role_env: str = "ADMIN_REQUIRED_ROLE"


def with_entry_contract(config: EntryContractConfig):
    """Decorator that enforces auth, policy, and canonical response handling."""

    def decorator(handler_fn: Callable[..., dict[str, Any]]):
        def wrapped(event: dict[str, Any], context: object) -> dict[str, Any]:
            from bcp_auth import AuthError, validate_authorizer_claims, validate_jwt
            from canonical_response import canonical_error, canonical_ok, policy_denied_response
            from cors import add_cors_to_response
            from policy_engine import PolicyContext, evaluate_policy

            try:
                claims = None
                required_role: str | None = None
                if config.require_auth:
                    auth = (event.get("requestContext") or {}).get("authorizer") or {}
                    jwt_claims = auth.get("jwt", {}).get("claims", {}) if isinstance(auth.get("jwt"), dict) else {}
                    has_claims = isinstance(jwt_claims, dict) and bool(jwt_claims)
                    headers = event.get("headers") or {}
                    h_lower = {k.lower(): v for k, v in headers.items() if isinstance(v, str)}
                    auth_header = (h_lower.get("authorization") or "").strip()
                    has_bearer = auth_header.lower().startswith("bearer ")

                    import os

                    expected_aud = (
                        os.environ.get(config.expected_audience_env)
                        or os.environ.get("IDP_AUDIENCE")
                        or "api://default"
                    ).strip()
                    required_role = (
                        os.environ.get(config.admin_role_env) or ""
                    ).strip() or None if config.surface == "ADMIN" else None

                    if has_claims:
                        claims = validate_authorizer_claims(
                            jwt_claims,
                            expected_audience=expected_aud,
                            required_role=required_role,
                            allow_vendor=(config.surface != "ADMIN"),
                        )
                    elif has_bearer:
                        claims = validate_jwt(
                            auth_header,
                            expected_audience=expected_aud,
                            required_role=required_role,
                            allow_vendor=(config.surface != "ADMIN"),
                        )
                    else:
                        return add_cors_to_response(
                            canonical_error("AUTH_ERROR", "Missing Authorization or JWT claims", 401)
                        )

                if config.require_policy and claims is not None:
                    body = event.get("body") or "{}"
                    body_dict = {}
                    if isinstance(body, str):
                        try:
                            import json

                            body_dict = json.loads(body) if body.strip() else {}
                        except Exception:
                            pass
                    elif isinstance(body, dict):
                        body_dict = body

                    requested_vendor = (
                        (body_dict.get("sourceVendorCode") or body_dict.get("sourceVendor") or "").strip().upper()
                        or None
                    )
                    ctx = PolicyContext(
                        surface=config.surface,
                        action=config.action,
                        vendor_code=claims.bcpAuth if claims else None,
                        target_vendor_code=body_dict.get("targetVendorCode") or body_dict.get("targetVendor"),
                        operation_code=body_dict.get("operationCode") or body_dict.get("operation"),
                        requested_source_vendor_code=requested_vendor,
                        is_admin=bool(
                            required_role and claims and required_role.lower() in {r.lower() for r in claims.roles}
                        )
                        if config.surface == "ADMIN"
                        else False,
                        groups=list(claims.roles) if claims else [],
                        query=dict(event.get("queryStringParameters") or {}),
                    )
                    decision = evaluate_policy(ctx)
                    if not decision.allow:
                        return add_cors_to_response(policy_denied_response(decision))

                result = handler_fn(event, context, claims)

                if config.canonicalize_success and isinstance(result, dict):
                    if "statusCode" not in result and "error" not in result:
                        result = canonical_ok(result)
                    return add_cors_to_response(result)

                return add_cors_to_response(result) if isinstance(result, dict) else result

            except AuthError as e:
                return add_cors_to_response(
                    canonical_error(
                        getattr(e, "code", "AUTH_ERROR"),
                        str(e),
                        getattr(e, "status_code", 401),
                    )
                )
            except Exception as e:
                _LOG.exception("lambda_entry_contract_unhandled")
                return add_cors_to_response(
                    canonical_error(
                        "INTERNAL_ERROR",
                        "An unexpected error occurred",
                        500,
                        details={"type": type(e).__name__},
                    )
                )

        return wrapped

    return decorator
