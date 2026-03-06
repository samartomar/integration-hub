"""Integration Hub API client. Calls POST /v1/integrations/execute only. Never crafts raw downstream HTTP."""

from __future__ import annotations

import json
from typing import Any

from config import get_integration_api_key, get_integration_hub_api_url


def call_integration_api(envelope: dict[str, Any]) -> dict[str, Any]:
    """
    Call Integration Hub API POST /v1/integrations/execute.

    Sends envelope as request body. Returns hub response body unchanged.
    Does not make any raw downstream HTTP calls - only the Hub API.
    """
    import urllib.request

    url = get_integration_hub_api_url()
    data: bytes = json.dumps(envelope).encode("utf-8")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    api_key = get_integration_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, data=data, method="POST", headers=headers)

    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else {}
