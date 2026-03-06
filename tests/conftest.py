"""Pytest conftest - ensure tests dir is on path for vendor_registry_jwt import."""

import sys
from pathlib import Path

_tests_dir = Path(__file__).resolve().parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))
