"""Load environment config from packages/env-config/env-config.json (single source of truth).

Config files are always picked up when present:
- packages/env-config/env-config.json = base (dev defaults)
- packages/env-config/env-config.prod.json = prod overrides (optional)
CDK context (-c) and env vars override file values.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_DIR = _REPO_ROOT / "packages" / "env-config"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return {}


def load_env_config(
    context_overrides: dict[str, Any] | None = None,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """Load env config from file, then apply context and env overrides.

    Load order:
    1. packages/env-config/env-config.json (base)
    2. packages/env-config/env-config.{environment}.json (env-specific overrides, if present)
    3. env_overrides (e.g. ENVIRONMENT, CUSTOM_DOMAIN_ROOT from buildspec)
    4. context_overrides (CDK -c flags)

    Args:
        context_overrides: e.g. from app.node.try_get_context (CDK -c flags)
        env_overrides: e.g. from os.environ (buildspec exports)

    Returns:
        Dict with: environment, customDomainRoot, customDomainHostedZoneId
    """
    defaults: dict[str, str] = {
        "environment": "dev",
        "customDomainRoot": "",
        "customDomainHostedZoneId": "",
    }

    # 1. Base config
    base = _load_json(_CONFIG_DIR / "env-config.json")
    for k in defaults:
        if k in base and base[k] is not None:
            defaults[k] = str(base[k]).strip()

    # 2. Resolve environment early (env override can change which env file we load)
    if env_overrides and env_overrides.get("ENVIRONMENT"):
        env = str(env_overrides["ENVIRONMENT"]).strip().lower()
    else:
        env = defaults["environment"].lower()
    if env not in ("prod", "dev"):
        env = "dev"

    # 3. Environment-specific overrides (e.g. packages/env-config/env-config.prod.json)
    env_file = _CONFIG_DIR / f"env-config.{env}.json"
    if env_file.exists():
        env_raw = _load_json(env_file)
        for k in defaults:
            if k in env_raw and env_raw[k] is not None:
                defaults[k] = str(env_raw[k]).strip()
    defaults["environment"] = env

    # 4. Apply env overrides (e.g. CUSTOM_DOMAIN_ROOT from buildspec)
    if env_overrides:
        mapping = {
            "ENVIRONMENT": "environment",
            "CUSTOM_DOMAIN_ROOT": "customDomainRoot",
            "CUSTOM_DOMAIN_HOSTED_ZONE_ID": "customDomainHostedZoneId",
        }
        for env_key, config_key in mapping.items():
            if env_key in env_overrides and env_overrides[env_key]:
                defaults[config_key] = str(env_overrides[env_key]).strip()

    # 5. Apply context overrides (CDK -c flags)
    if context_overrides:
        mapping = {
            "Environment": "environment",
            "CustomDomainRoot": "customDomainRoot",
            "CustomDomainHostedZoneId": "customDomainHostedZoneId",
        }
        for ctx_key, config_key in mapping.items():
            if ctx_key in context_overrides and context_overrides[ctx_key]:
                defaults[config_key] = str(context_overrides[ctx_key]).strip()

    return defaults
