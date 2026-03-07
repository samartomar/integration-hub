"""GET_VERIFY_MEMBER_ELIGIBILITY mapping: LH001 -> LH002.

Canonical and vendor use similar structures. Direct field copy with optional renames.
"""

from __future__ import annotations

# CANONICAL_TO_VENDOR: input=canonical payload, output=vendor payload
# Format: { "vendor_out_key": "$.canonical_in_key" } or { "vendor_out_key": constant }
ELIGIBILITY_CANONICAL_TO_VENDOR: dict[str, str | object] = {
    "memberIdWithPrefix": "$.memberIdWithPrefix",
    "date": "$.date",
}

# VENDOR_TO_CANONICAL: input=vendor payload, output=canonical payload
ELIGIBILITY_VENDOR_TO_CANONICAL: dict[str, str | object] = {
    "memberIdWithPrefix": "$.memberIdWithPrefix",
    "name": "$.name",
    "dob": "$.dob",
    "claimNumber": "$.claimNumber",
    "dateOfService": "$.dateOfService",
    "status": "$.status",
}
