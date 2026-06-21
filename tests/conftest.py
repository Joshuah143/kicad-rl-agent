"""Pytest bootstrap.

Prepends the project's ``src/`` directory to ``sys.path`` so the tests can
``import circuit_agent.*`` without requiring an editable install. This mirrors
the path shim used by the entry scripts.
"""

from __future__ import annotations

import pathlib
import sys

_SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))
