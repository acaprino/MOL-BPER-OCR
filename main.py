"""Thin shim — all logic lives in the extraction/ package."""

from dotenv import load_dotenv; load_dotenv()  # noqa: E702
from extraction import *  # noqa: F401,F403

if __name__ == "__main__":
    main()  # noqa: F405
