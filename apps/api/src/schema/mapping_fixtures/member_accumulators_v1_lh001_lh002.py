"""GET_MEMBER_ACCUMULATORS fixtures: LH001 -> LH002. Synthetic data only."""

from __future__ import annotations

ACCUMULATORS_FIXTURES: list[dict] = [
    {
        "fixtureId": "accumulators-c2v-basic",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH001-12345", "asOfDate": "2025-03-06"},
        "expectedOutput": {"memberIdWithPrefix": "LH001-12345", "asOfDate": "2025-03-06"},
        "notes": ["Happy-path canonical to vendor request"],
    },
    {
        "fixtureId": "accumulators-c2v-shape-variation",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH002-55555", "asOfDate": "2024-06-01"},
        "expectedOutput": {"memberIdWithPrefix": "LH002-55555", "asOfDate": "2024-06-01"},
        "notes": ["Different member and date"],
    },
    {
        "fixtureId": "accumulators-v2c-basic",
        "direction": "VENDOR_TO_CANONICAL",
        "inputPayload": {
            "memberIdWithPrefix": "LH001-12345",
            "planYear": 2025,
            "currency": "USD",
            "individualDeductible": {"total": 2000, "used": 500, "remaining": 1500},
            "familyDeductible": {"total": 4000, "used": 0, "remaining": 4000},
            "individualOutOfPocket": {"total": 6000, "used": 200, "remaining": 5800},
            "familyOutOfPocket": {"total": 12000, "used": 200, "remaining": 11800},
        },
        "expectedOutput": {
            "memberIdWithPrefix": "LH001-12345",
            "planYear": 2025,
            "currency": "USD",
            "individualDeductible": {"total": 2000, "used": 500, "remaining": 1500},
            "familyDeductible": {"total": 4000, "used": 0, "remaining": 4000},
            "individualOutOfPocket": {"total": 6000, "used": 200, "remaining": 5800},
            "familyOutOfPocket": {"total": 12000, "used": 200, "remaining": 11800},
        },
        "notes": ["Happy-path vendor to canonical with nested accumulator objects"],
    },
    {
        "fixtureId": "accumulators-v2c-shape-variation",
        "direction": "VENDOR_TO_CANONICAL",
        "inputPayload": {
            "memberIdWithPrefix": "LH002-77777",
            "planYear": 2024,
            "currency": "USD",
            "individualDeductible": 1500,
            "familyDeductible": 3000,
            "individualOutOfPocket": 5000,
            "familyOutOfPocket": 10000,
        },
        "expectedOutput": {
            "memberIdWithPrefix": "LH002-77777",
            "planYear": 2024,
            "currency": "USD",
            "individualDeductible": 1500,
            "familyDeductible": 3000,
            "individualOutOfPocket": 5000,
            "familyOutOfPocket": 10000,
        },
        "notes": ["Scalar accumulator values"],
    },
]
