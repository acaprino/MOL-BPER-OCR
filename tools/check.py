"""Run the fast pytest lane; pass additional pytest arguments after this script."""

from pathlib import Path
import subprocess
import sys


def main() -> int:
    """Use the active interpreter and return pytest's exit status."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-m", "not slow", *sys.argv[1:]],
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
