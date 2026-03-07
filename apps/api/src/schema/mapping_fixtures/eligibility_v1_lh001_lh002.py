"""GET_VERIFY_MEMBER_ELIGIBILITY fixtures: LH001 -> LH002. Synthetic data only."""

from __future__ import annotations

ELIGIBILITY_FIXTURES: list[dict] = [
    {
        "fixtureId": "eligibility-c2v-basic",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
        "expectedOutput": {"memberIdWithPrefix": "LH001-12345", "date": "2025-03-06"},
        "notes": ["Happy-path canonical to vendor request"],
    },
    {
        "fixtureId": "eligibility-c2v-shape-variation",
        "direction": "CANONICAL_TO_VENDOR",
        "inputPayload": {"memberIdWithPrefix": "LH002-99999", "date": "2024-12-01"},
        "expectedOutput": {"memberIdWithPrefix": "LH002-99999", "date": "2024-12-01"},
        "notes": ["Different member and date"],
    },
    {
        "fixtureId": "eligibility-v2c-basic",
        "direction": "VENDOR_TO_CANONICAL",
        "inputPayload": {
            "memberIdWithPrefix": "LH001-12345",
            "name": "Jane Doe",
            "dob": "1990-01-15",
            "claimNumber": "CLM-789",
            "dateOfService": "2025-03-06",
            "status": "ACTIVE",
        },
        "expectedOutput": {
            "memberIdWithPrefix": "LH001-12345",
            "name": "Jane Doe",
            "dob": "1990-01-15",
            "claimNumber": "CLM-789",
            "dateOfService": "2025-03-06",
            "status": "ACTIVE",
        },
        "notes": ["Happy-path vendor to canonical response"],
    },
    {
        "fixtureId": "eligibility-v2c-shape-variation",
        "direction": "VENDOR_TO_CANONICAL",
        "inputPayload": {
            "memberIdWithPrefix": "LH002-88888",
            "name": "John Smith",
            "dob": "1985-06-20",
            "claimNumber": "CLM-001",
            "dateOfService": "2024-11-15",
            "status": "PENDING",
        },
        "expectedOutput": {
            "memberIdWithPrefix": "LH002-88888",
            "name": "John Smith",
            "dob": "1985-06-20",
            "claimNumber": "CLM-001",
            "dateOfService": "2024-11-15",
            "status": "PENDING",
        },
        "notes": ["Different member and status"],
    },
]
