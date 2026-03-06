"""GET_MEMBER_ACCUMULATORS canonical model - official version 1.0."""

from __future__ import annotations

from schema.canonical_envelope import build_envelope

OPERATION_CODE = "GET_MEMBER_ACCUMULATORS"
VERSION = "1.0"
VERSION_ALIASES = ["v1"]
TITLE = "Get Member Accumulators"
DESCRIPTION = "Retrieve member benefit accumulators (deductible, out-of-pocket) as of a given date."

# Accumulator object schema (reused for deductible and out-of-pocket)
ACCUMULATOR_OBJECT = {
    "type": "object",
    "required": ["total", "used", "remaining"],
    "properties": {
        "total": {"type": "number"},
        "used": {"type": "number"},
        "remaining": {"type": "number"},
    },
    "additionalProperties": False,
}

# Request payload schema
REQUEST_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["memberIdWithPrefix", "asOfDate"],
    "properties": {
        "memberIdWithPrefix": {"type": "string", "minLength": 1},
        "asOfDate": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
    },
    "additionalProperties": False,
}

# Response payload schema
RESPONSE_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "memberIdWithPrefix",
        "planYear",
        "currency",
        "individualDeductible",
        "individualOutOfPocket",
    ],
    "properties": {
        "memberIdWithPrefix": {"type": "string", "minLength": 1},
        "planYear": {"type": "integer"},
        "currency": {"type": "string", "minLength": 1},
        "individualDeductible": ACCUMULATOR_OBJECT,
        "familyDeductible": ACCUMULATOR_OBJECT,
        "individualOutOfPocket": ACCUMULATOR_OBJECT,
        "familyOutOfPocket": ACCUMULATOR_OBJECT,
    },
    "additionalProperties": False,
}

# Example request payload
EXAMPLE_REQUEST: dict[str, object] = {
    "memberIdWithPrefix": "LH001-12345",
    "asOfDate": "2025-03-06",
}

# Example response payload
EXAMPLE_RESPONSE: dict[str, object] = {
    "memberIdWithPrefix": "LH001-12345",
    "planYear": 2025,
    "currency": "USD",
    "individualDeductible": {"total": 2000, "used": 500, "remaining": 1500},
    "familyDeductible": {"total": 4000, "used": 500, "remaining": 3500},
    "individualOutOfPocket": {"total": 8000, "used": 1200, "remaining": 6800},
    "familyOutOfPocket": {"total": 16000, "used": 1200, "remaining": 14800},
}

# Example envelopes
EXAMPLE_REQUEST_ENVELOPE: dict[str, object] = build_envelope(
    OPERATION_CODE, VERSION, "REQUEST", dict(EXAMPLE_REQUEST),
    correlation_id="corr-accumulators-example", timestamp="2025-03-06T12:00:00Z",
)
EXAMPLE_RESPONSE_ENVELOPE: dict[str, object] = build_envelope(
    OPERATION_CODE, VERSION, "RESPONSE", dict(EXAMPLE_RESPONSE),
    correlation_id="corr-accumulators-example", timestamp="2025-03-06T12:00:05Z",
)
