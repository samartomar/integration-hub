"""Pytest conftest for platform invariants - ensure lambda path is on sys.path."""

import sys
from pathlib import Path

_tests_dir = Path(__file__).resolve().parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))

_lambda_dir = Path(__file__).resolve().parent.parent.parent / "apps" / "api" / "src" / "lambda"
if str(_lambda_dir) not in sys.path:
    sys.path.insert(0, str(_lambda_dir))
