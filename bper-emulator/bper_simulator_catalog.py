"""Share one catalogue of practice profiles between the HTTP and portable sites.

The SQLite seed always joins; profile files (--profiles) join when given; the real archive joins only with
include_archive; and a practice whose role is test joins only with include_test, whatever its source.
"""
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

from bper_archive import archive_profiles
from bper_profiles import check_profiles, load_profiles
from bper_simulator_data import reference_schede
from bper_simulator_truth import available_steps, scheda_states
from bper_synthetic_db import build_database, set_aside_older, synthetic_practices


DEFAULT_DB = Path(__file__).resolve().parents[1] / ".tritech" / "local" / "bper-synthetic.sqlite3"


class Catalog(TypedDict):
    practices: list[dict]
    hasReference: bool


def ensure_database(path: Path, *, replace_older: bool = False) -> Path | None:
    """Create the database on first use; refuse one of another version, naming the file.

    replace_older is for the launcher's default database only: one of an older simulator version is renamed
    beside it (set_aside_older) and rebuilt, and its new name is returned.
    """
    backup = set_aside_older(path) if replace_older else None
    build_database(path)
    return backup


def read_catalog(db_path: Path, include_reference: bool, *, include_archive: bool = False,
                 include_test: bool = False, profiles: Sequence[Path] = ()) -> Catalog:
    practices = synthetic_practices(db_path)
    for path in profiles:
        practices += load_profiles(path)
    if include_archive:
        practices += archive_profiles(include_test=include_test)
    practices = [p for p in practices if include_test or p["role"] != "test"]
    check_profiles(practices, archive=None, source="catalogo")  # one key per practice across the sources
    # Scheda Privati pages are looked up by their customer's NDG: two different ones would hide each other.
    by_customer: dict[str, dict] = {}
    for practice in practices:
        if practice["scheda"]:
            seen = by_customer.setdefault(practice["scheda"]["ndg"], practice)
            if seen["scheda"] != practice["scheda"]:
                raise ValueError(f"catalogo: {seen['key']} e {practice['key']} hanno schede diverse dello stesso NDG")
    for practice in practices:
        practice["availableSteps"] = available_steps(practice)
        practice["schedaStates"] = scheda_states(practice["scheda"]) if practice["scheda"] else []
    return {"practices": practices, "hasReference": include_reference}


def catalog_schede(catalog: Catalog) -> dict[str, dict]:
    """Scheda Privati pages keyed by the NDG of their customer: the reference fixture only when opted in, and
    every practice's own page, which wins over the fixture for the same customer (the fixture's note has
    invented text, so an archive practice would render one page and assert another)."""
    schede = reference_schede() if catalog["hasReference"] else {}
    schede.update({p["scheda"]["ndg"]: p["scheda"] for p in catalog["practices"] if p["scheda"]})
    return schede
