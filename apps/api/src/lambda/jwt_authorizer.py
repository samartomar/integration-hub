"""
REST API Token Authorizer - validates Okta JWT for Vendor REST API.

Used by API Gateway REST API (token authorizer). Receives authorizationToken (Bearer <jwt>),
validates via JWKS, returns IAM policy allow/deny. Context is passed to integration Lambda.

Env: IDP_ISSUER, IDP_JWKS_URL, VENDOR_API_AUDIENCE (or IDP_AUDIENCE fallback).
"""

from __future__ import annotations

import os

from bcp_auth import AuthError, validate_jwt


def handler(event: dict, context: object) -> dict:
    """Token authorizer: validate JWT, return policy. Event has authorizationToken, methodArn."""
    token = _extract_token(event.get("authorizationToken") or "")
    if not token:
        return _deny_policy(event.get("methodArn", ""), "Missing Authorization header")

    try:
        expected_audience = (
            os.environ.get("VENDOR_API_AUDIENCE")
            or os.environ.get("IDP_AUDIENCE")
            or "api://default"
        ).strip()
        validated = validate_jwt(
            token,
            expected_audience=expected_audience,
            allow_vendor=True,
        )
        principal = str(validated.bcpAuth or validated.subject or "vendor").strip()
        ctx_claims = {
            "sub": validated.subject,
            "bcpAuth": validated.bcpAuth or "",
            "groups": ",".join(validated.roles),
            "scp": " ".join(validated.scopes),
        }
        return _allow_policy(event.get("methodArn", ""), principal=principal, claims=ctx_claims)
    except AuthError as e:
        return _deny_policy(event.get("methodArn", ""), e.message)
    except Exception as e:
        return _deny_policy(event.get("methodArn", ""), str(e))


def _extract_token(val: str) -> str:
    """Extract Bearer token from 'Bearer <token>' or raw token."""
    val = (val or "").strip()
    if val.lower().startswith("bearer "):
        return val[7:].strip()
    return val


def _allow_policy(method_arn: str, principal: str, claims: dict | None = None) -> dict:
    """Return IAM policy allow. Context passed to Lambda."""
    region = method_arn.split(":")[3] if ":" in method_arn else "*"
    account = method_arn.split(":")[4] if ":" in method_arn else "*"
    api_id = method_arn.split("/")[0].split(":")[-1] if "/" in method_arn else "*"
    stage = method_arn.split("/")[1] if "/" in method_arn and len(method_arn.split("/")) > 1 else "*"
    policy = {
        "principalId": principal,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Allow",
                    "Resource": f"arn:aws:execute-api:{region}:{account}:{api_id}/{stage}/*",
                }
            ],
        },
        "context": {},
    }
    if claims:
        for k, v in claims.items():
            if isinstance(v, (str, int, bool)):
                policy["context"][k] = str(v)
    return policy


def _deny_policy(method_arn: str, reason: str) -> dict:
    """Return IAM policy deny."""
    return {
        "principalId": "denied",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [{"Action": "execute-api:Invoke", "Effect": "Deny", "Resource": "*"}],
        },
        "context": {},
    }
