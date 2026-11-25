"""Test setup: make the repo root importable so tests use ``src.*``."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
