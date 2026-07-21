"""Thin shim — all logic lives in the extraction/ package."""

# Warning filters live in extraction/__init__.py and apply on first import below.
from dotenv import load_dotenv; load_dotenv()  # noqa: E702
from extraction import *  # noqa: F401,F403

if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    # Se viene passato --gui, avvia l'Edge Agent
    if "--gui" in sys.argv:
        edge_agent_dir = Path(__file__).parent / "edge-agent"
        if str(edge_agent_dir) not in sys.path:
            sys.path.insert(0, str(edge_agent_dir))
        from edge_agent import main as gui_main  # edge-agent/edge_agent.py
        sys.exit(gui_main())
    else:
        # Altrimenti esegui la batch extraction standard
        main()  # noqa: F405
