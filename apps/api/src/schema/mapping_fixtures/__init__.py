"""Mapping fixtures for deterministic certification. Synthetic data only."""

from __future__ import annotations

from typing import Any

# Registry: (operation_code, version, source_vendor, target_vendor) -> list of fixture dicts
_FIXTURE_REGISTRY: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}


def _ensure_loaded() -> None:
    """Lazy-load fixture definitions."""
    if _FIXTURE_REGISTRY:
        return
    from schema.mapping_fixtures.eligibility_v1_lh001_lh002 import ELIGIBILITY_FIXTURES
    from schema.mapping_fixtures.member_accumulators_v1_lh001_lh002 import ACCUMULATORS_FIXTURES

    for f in ELIGIBILITY_FIXTURES:
        key = ("GET_VERIFY_MEMBER_ELIGIBILITY", "1.0", "LH001", "LH002")
        _FIXTURE_REGISTRY.setdefault(key, []).append(f)
    for f in ACCUMULATORS_FIXTURES:
        key = ("GET_MEMBER_ACCUMULATORS", "1.0", "LH001", "LH002")
        _FIXTURE_REGISTRY.setdefault(key, []).append(f)


def list_mapping_fixtures(
    operation_code: str | None = None,
    version: str | None = None,
    source_vendor: str | None = None,
    target_vendor: str | None = None,
) -> list[dict[str, Any]]:
    """List available fixture cases, optionally filtered."""
    _ensure_loaded()
    result: list[dict[str, Any]] = []
    op = (operation_code or "").strip().upper() if operation_code else None
    ver = (version or "").strip() if version else None
    src = (source_vendor or "").strip().upper() if source_vendor else None
    tgt = (target_vendor or "").strip().upper() if target_vendor else None

    for (k_op, k_ver, k_src, k_tgt), fixtures in _FIXTURE_REGISTRY.items():
        if op and k_op != op:
            continue
        if ver and k_ver != ver:
            continue
        if src and k_src != src:
            continue
        if tgt and k_tgt != tgt:
            continue
        result.extend(fixtures)
    return result
