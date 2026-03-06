"""GET_VERIFY_MEMBER_ELIGIBILITY canonical model - official version 1.0."""

from __future__ import annotations

from schema.canonical_envelope import build_envelope

OPERATION_CODE = "GET_VERIFY_MEMBER_ELIGIBILITY"
VERSION = "1.0"
VERSION_ALIASES = ["v1"]
TITLE = "Verify Member Eligibility"
DESCRIPTION = "Check member eligibility for a given date. Returns member details and status."

# Request payload schema
REQUEST_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["memberIdWithPrefix", "date"],
    "properties": {
        "memberIdWithPrefix": {"type": "string", "minLength": 1},
        "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
    },
    "additionalProperties": False,
}

# Response payload schema
RESPONSE_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["memberIdWithPrefix", "name", "dob", "status"],
    "properties": {
        "memberIdWithPrefix": {"type": "string", "minLength": 1},
        "name": {"type": "string", "minLength": 1},
        "dob": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "claimNumber": {"type": "string"},
        "dateOfService": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "status": {
            "type": "string",
            "enum": ["ACTIVE", "INACTIVE", "TERMINATED", "PENDING", "UNKNOWN"],
        },
    },
    "additionalProperties": False,
}

# Example request payload
EXAMPLE_REQUEST: dict[str, object] = {
    "memberIdWithPrefix": "LH001-12345",
    "date": "2025-03-06",
}

# Example response payload
EXAMPLE_RESPONSE: dict[str, object] = {
    "memberIdWithPrefix": "LH001-12345",
    "name": "Jane Doe",
    "dob": "1990-01-15",
    "claimNumber": "CLM-789",
    "dateOfService": "2025-03-06",
    "status": "ACTIVE",
}

# Example envelopes
EXAMPLE_REQUEST_ENVELOPE: dict[str, object] = build_envelope(
    OPERATION_CODE, VERSION, "REQUEST", dict(EXAMPLE_REQUEST),
    correlation_id="corr-eligibility-example", timestamp="2025-03-06T12:00:00Z",
)
EXAMPLE_RESPONSE_ENVELOPE: dict[str, object] = build_envelope(
    OPERATION_CODE, VERSION, "RESPONSE", dict(EXAMPLE_RESPONSE),
    correlation_id="corr-eligibility-example", timestamp="2025-03-06T12:00:05Z",
)
