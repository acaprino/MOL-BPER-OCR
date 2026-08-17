"""Shared test setup: make repo root and edge-agent/ importable."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EDGE_AGENT_DIR = REPO_ROOT / "edge-agent"

for _p in (str(REPO_ROOT), str(EDGE_AGENT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
