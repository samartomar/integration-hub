"""Mapping engine for routing lambda: JSONPath extraction and apply_mapping."""

from __future__ import annotations

from typing import Any


def _extract_with_found(obj: dict[str, Any], path: str) -> tuple[Any, bool]:
    """
    Extract value from obj using JSONPath-like path.
    Returns (value, found). found=False when path is missing.
    """
    if not path or not isinstance(path, str) or not path.strip().startswith("$."):
        return None, False
    keys = path.strip()[2:].split(".")
    if not keys or not all(k.strip() for k in keys):
        return None, False
    keys = [k.strip() for k in keys]
    current: Any = obj
    for key in keys:
        if not isinstance(current, dict):
            return None, False
        if key not in current:
            return None, False
        current = current[key]
    return current, True


def extract_json_path(obj: dict[str, Any], path: str) -> Any:
    """
    Extract value from obj using JSONPath-like path.
    Supports: $.a, $.a.b, $.a.b.c
    Returns None if path is missing. Returns value (including None) if path exists.
    """
    value, _ = _extract_with_found(obj, path)
    return value


def _set_nested(output: dict[str, Any], key_path: str, value: Any) -> None:
    """Set value at dot-separated path, creating nested dicts as needed."""
    parts = key_path.split(".")
    if not parts:
        return
    target = output
    for i, part in enumerate(parts[:-1]):
        if part not in target:
            target[part] = {}
        nest = target[part]
        if not isinstance(nest, dict):
            nest = {}
            target[part] = nest
        target = nest
    target[parts[-1]] = value


def apply_mapping(input_payload: dict[str, Any], mapping: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Apply mapping rules to input_payload.
    For each (out_key, selector_or_const):
      - if string starting with '$.': extract from input_payload; if path missing -> violation
      - else: treat as constant literal
    Supports nested output keys via dot notation (e.g. 'member.id' -> { member: { id: ... } }).
    Returns (output_payload, violations).
    """
    output: dict[str, Any] = {}
    violations: list[str] = []

    for out_key, selector_or_const in mapping.items():
        if isinstance(selector_or_const, str) and selector_or_const.strip().startswith("$."):
            value, found = _extract_with_found(input_payload, selector_or_const)
            if not found:
                violations.append(f"missing path {selector_or_const} for field {out_key}")
                continue
            _set_nested(output, out_key, value)
        else:
            _set_nested(output, out_key, selector_or_const)

    return output, violations
