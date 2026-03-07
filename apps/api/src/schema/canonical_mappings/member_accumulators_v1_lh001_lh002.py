"""GET_MEMBER_ACCUMULATORS mapping: LH001 -> LH002.

Canonical uses asOfDate; vendor may use as_of_date. Nested accumulator objects.
"""

from __future__ import annotations

# CANONICAL_TO_VENDOR: input=canonical payload, output=vendor payload
ACCUMULATORS_CANONICAL_TO_VENDOR: dict[str, str | object] = {
    "memberIdWithPrefix": "$.memberIdWithPrefix",
    "asOfDate": "$.asOfDate",
}

# VENDOR_TO_CANONICAL: input=vendor payload, output=canonical payload
ACCUMULATORS_VENDOR_TO_CANONICAL: dict[str, str | object] = {
    "memberIdWithPrefix": "$.memberIdWithPrefix",
    "planYear": "$.planYear",
    "currency": "$.currency",
    "individualDeductible": "$.individualDeductible",
    "familyDeductible": "$.familyDeductible",
    "individualOutOfPocket": "$.individualOutOfPocket",
    "familyOutOfPocket": "$.familyOutOfPocket",
}
