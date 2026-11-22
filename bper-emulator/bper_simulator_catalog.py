"""Share one SQLite source of synthetic dossiers between the HTTP and portable sites."""
from pathlib import Path
from typing import TypedDict

from bper_simulator_truth import available_steps
from bper_synthetic_db import build_database, synthetic_practices


DEFAULT_DB = Path(__file__).resolve().parents[1] / ".tritech" / "local" / "bper-synthetic.sqlite3"


class Catalog(TypedDict):
    practices: list[dict]
    hasReference: bool


def ensure_database(path: Path) -> None:
    if not path.exists():
        build_database(path)


def read_catalog(db_path: Path, include_reference: bool) -> Catalog:
    practices = synthetic_practices(db_path)
    for practice in practices:
        practice["availableSteps"] = available_steps(practice)
    return {"practices": practices, "hasReference": include_reference}
