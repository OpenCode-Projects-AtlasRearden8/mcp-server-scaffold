"""Offline pytest suite: validates schema, dispatch, and guards with zero network access."""

import io
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR.parent))
