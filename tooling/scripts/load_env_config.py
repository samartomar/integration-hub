#!/usr/bin/env python3
"""Print shell exports from packages/env-config/env-config.json for use in buildspecs.

Usage:
  eval $(python tooling/scripts/load_env_config.py)      # sources ENVIRONMENT, CUSTOM_DOMAIN_ROOT, ...
  python scripts/load_env_config.py --cdk        # prints CDK -c flags for cdk deploy
  eval $(python tooling/scripts/load_env_config.py -v)   # also VITE_* vars for frontend build (when custom domains)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add repo root for imports (tooling/scripts → parents[2])
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from infra.env_config import load_env_config


def main() -> None:
    env_overrides = {
        "ENVIRONMENT": os.environ.get("ENVIRONMENT"),
        "CUSTOM_DOMAIN_ROOT": os.environ.get("CUSTOM_DOMAIN_ROOT"),
        "CUSTOM_DOMAIN_HOSTED_ZONE_ID": os.environ.get("CUSTOM_DOMAIN_HOSTED_ZONE_ID"),
    }
    cfg = load_env_config(env_overrides={k: v for k, v in env_overrides.items() if v})
    want_vite = "-v" in sys.argv or "--vite" in sys.argv

    if "--cdk" in sys.argv:
        parts = ["-c", f"Environment={cfg['environment']}"]
        if cfg.get("customDomainRoot"):
            parts.extend(["-c", f"CustomDomainRoot={cfg['customDomainRoot']}"])
            if cfg.get("customDomainHostedZoneId"):
                parts.extend(["-c", f"CustomDomainHostedZoneId={cfg['customDomainHostedZoneId']}"])
        print(" ".join(parts))
    else:
        print(f"export ENVIRONMENT={cfg['environment']}")
        print(f"export CUSTOM_DOMAIN_ROOT={cfg['customDomainRoot']}")
        print(f"export CUSTOM_DOMAIN_HOSTED_ZONE_ID={cfg['customDomainHostedZoneId']}")
        if want_vite and cfg.get("customDomainRoot"):
            from infra.stacks.custom_domain_utils import resolve_domain_names
            dm = resolve_domain_names(cfg["customDomainRoot"], cfg["environment"])
            print(f"export VITE_ADMIN_API_BASE_URL=https://{dm['adminApi']}")
            print(f"export VITE_VENDOR_API_BASE_URL=https://{dm['partnersApi']}")
            print(f"export VITE_RUNTIME_API_BASE_URL=https://{dm['runtimeApi']}")


if __name__ == "__main__":
    main()
