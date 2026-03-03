"""Thin shim — all logic lives in the extraction/ package."""

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_core")

from dotenv import load_dotenv; load_dotenv()  # noqa: E702
from extraction import *  # noqa: F401,F403

if __name__ == "__main__":
    main()  # noqa: F405
