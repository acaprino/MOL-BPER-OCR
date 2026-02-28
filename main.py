"""Thin shim — all logic lives in the extraction/ package."""

from extraction import *  # noqa: F401,F403
from extraction.cli import main

if __name__ == "__main__":
    main()
