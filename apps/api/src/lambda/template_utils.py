"""Small, safe templating helper for endpoint verification and routing."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

# Matches {{ foo }} style placeholders
_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


def render_template_string(template: str, params: Mapping[str, Any] | None) -> str:
    """
    Replace {{key}} placeholders with params[key] when present.
    Leaves unknown placeholders untouched (so missing params are debuggable).
    Always returns a string.
    """
    if not template:
        return template or ""

    if not isinstance(params, Mapping):
        params = {}

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in params or params[key] is None:
            return match.group(0)
        value = params[key]
        if isinstance(value, (dict, list)):
            return json.dumps(value, separators=(",", ":"))
        return str(value)

    return _TEMPLATE_RE.sub(_replace, template)
