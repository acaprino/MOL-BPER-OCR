"""Thin shim — all logic lives in the src/extraction/ package."""

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Let the desktop load its environment and report startup errors in Qt.
if __name__ == "__main__" and "--gui" in sys.argv:
    sys.path.insert(0, str(_SRC_DIR / "edge-agent"))
    from edge_agent import main as gui_main
    sys.exit(gui_main())

# Preserve the batch entry point and the exports available to Python callers.
from dotenv import load_dotenv
load_dotenv()
from extraction import *  # noqa: F401,F403

if __name__ == "__main__":
    main()  # noqa: F405
