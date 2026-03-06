"""
REST API Token Authorizer - validates Okta JWT for Vendor REST API.

Used by API Gateway REST API (token authorizer). Receives authorizationToken (Bearer <jwt>),
validates via JWKS, returns IAM policy allow/deny. Context is passed to integration Lambda.

Env: IDP_JWKS_URL, IDP_ISSUER, IDP_AUDIENCE, AUTH_BYPASS (optional),
     IDP_VENDOR_CLAIM (optional) - single claim name for vendor identity.
       Default: lhcode.
"""

from __future__ import annotations

import os


def handler(event: dict, context: object) -> dict:
    """Token authorizer: validate JWT, return policy. Event has authorizationToken, methodArn."""
    bypass = (os.environ.get("AUTH_BYPASS") or "").strip().lower() in ("true", "1", "yes")
    if bypass:
        return _allow_policy(event.get("methodArn", ""), principal="bypass", claims={"sub": "local", "lhcode": "LOCAL"})

    token = _extract_token(event.get("authorizationToken") or "")
    if not token:
        return _deny_policy(event.get("methodArn", ""), "Missing Authorization header")

    jwt_config = _load_config()
    if not jwt_config:
        return _deny_policy(event.get("methodArn", ""), "JWT auth not configured")

    try:
        from jwt_auth import validate_jwt_for_authorizer
        claims = validate_jwt_for_authorizer(token, jwt_config)
        vendor_claim = _parse_vendor_claim()
        vendor_value = str(claims.get(vendor_claim) or "").strip().upper()
        if not vendor_value:
            return _deny_policy(event.get("methodArn", ""), f"Missing required vendor claim '{vendor_claim}'")

        principal = vendor_value
        # Keep both lhcode and vendor_code set for downstream lambdas during migration.
        ctx_claims = dict(claims)
        ctx_claims["lhcode"] = vendor_value
        ctx_claims["vendor_code"] = vendor_value
        return _allow_policy(event.get("methodArn", ""), principal=str(principal), claims=ctx_claims)
    except Exception as e:
        return _deny_policy(event.get("methodArn", ""), str(e))


def _parse_vendor_claim() -> str:
    """Resolve single vendor claim key used for identity. Default: lhcode."""
    raw = (os.environ.get("IDP_VENDOR_CLAIM") or "lhcode").strip()
    return raw or "lhcode"


def _extract_token(val: str) -> str:
    """Extract Bearer token from 'Bearer <token>' or raw token."""
    val = (val or "").strip()
    if val.lower().startswith("bearer "):
        return val[7:].strip()
    return val


def _load_config() -> object | None:
    """Load JwtAuthConfig from env (Okta/IDP)."""
    from jwt_auth import JwtAuthConfig
    jwks_url = (os.environ.get("IDP_JWKS_URL") or "").strip()
    if not jwks_url:
        return None
    issuer = (os.environ.get("IDP_ISSUER") or "").strip()
    aud_raw = (os.environ.get("IDP_AUDIENCE") or "").strip()
    audiences = [a.strip() for a in aud_raw.split(",") if a.strip()] if aud_raw else []
    if not audiences:
        return None
    return JwtAuthConfig(
        issuer=issuer,
        jwks_uri=jwks_url,
        audiences=audiences,
        vendor_claim=_parse_vendor_claim(),
        allowed_alg="RS256",
        clock_skew_seconds=60,
        allowed_algs=["RS256"],
    )


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
