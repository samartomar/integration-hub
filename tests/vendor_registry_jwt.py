"""Shared JWT auth helper for vendor registry lambda tests.

Vendor registry uses JWT-only auth. Tests must add requestContext.authorizer
so the handler accepts the request. Call add_jwt_auth(event, vendor_code) before
invoking the handler.
"""

from __future__ import annotations


def add_jwt_auth(event: dict, vendor_code: str = "LH001") -> None:
    """Add JWT authorizer context to event so vendor registry handler accepts it."""
    ctx = event.get("requestContext") or {}
    ctx["authorizer"] = {
        "principalId": vendor_code,
        "jwt": {
            "claims": {
                "sub": f"okta|{vendor_code}",
                "aud": "api://default",
                "bcpAuth": vendor_code,
                "vendor_code": vendor_code,
                "lhcode": vendor_code,
            }
        },
    }
    event["requestContext"] = ctx
