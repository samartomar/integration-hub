"""Pytest conftest - add schema package to path."""

import sys
from pathlib import Path

_src_dir = Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
