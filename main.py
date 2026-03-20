"""Thin shim — all logic lives in the extraction/ package."""

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_core")

from dotenv import load_dotenv; load_dotenv()  # noqa: E702
from extraction import *  # noqa: F401,F403

if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    # Se viene passato --gui, avvia l'Edge Agent
    if "--gui" in sys.argv:
        from edge_agent.edge_agent import main as gui_main
        sys.exit(gui_main())
    else:
        # Altrimenti esegui la batch extraction standard
        main()  # noqa: F405
