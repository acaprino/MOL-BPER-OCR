"""Thin shim — all logic lives in the src/extraction/ package."""

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Warning filters live in src/extraction/__init__.py and apply on first import below.
from dotenv import load_dotenv; load_dotenv()  # noqa: E702
from extraction import *  # noqa: F401,F403

if __name__ == "__main__":
    # Se viene passato --gui, avvia l'Edge Agent
    if "--gui" in sys.argv:
        edge_agent_dir = _SRC_DIR / "edge-agent"
        if str(edge_agent_dir) not in sys.path:
            sys.path.insert(0, str(edge_agent_dir))
        from edge_agent import main as gui_main  # src/edge-agent/edge_agent.py
        sys.exit(gui_main())
    else:
        # Altrimenti esegui la batch extraction standard
        main()  # noqa: F405
