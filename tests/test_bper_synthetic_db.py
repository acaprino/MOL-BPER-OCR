from datetime import date
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3

import pytest

from bper_synthetic_db import build_database, synthetic_practices


def cents(display: str) -> int:
    return int(100 * Decimal(display.replace(".", "").replace(",", ".")))


def test_catalog_has_reproducible_distinct_customer_identities() -> None:
    profiles = synthetic_practices()
    assert len(profiles) == 64
    assert len({row["ndg"] for row in profiles}) == len(profiles)
    assert len({row["number"] for row in profiles}) == len(profiles)
    assert profiles == synthetic_practices()
    assert len({row["scenario"] for row in profiles[:3]}) == 3
    assert {len(row["subjects"]) for row in profiles} == {1, 2, 3, 4}


def test_demo_deep_link_preserves_its_original_dossier() -> None:
    first = synthetic_practices()[0]
    assert (first["key"], first["ndg"], first["name"], first["number"]) == (
        "demo", "90000001", "ALBA MARTINA", "99000001"
    )
    assert [s["ndg"] for s in first["subjects"]] == ["90000001", "90000002"]
    assert first["fidi"][0]["account"] == "034 9001 0017 00000001"
    assert first["creditTotal"] == "120.000"
    assert first["guaranteeTotal"] == "204.000"


def test_dossier_totals_and_notes_follow_the_booked_credit_amounts() -> None:
    profiles = synthetic_practices()
    assert any(len(p["fidi"]) > 1 for p in profiles)
    assert any(not p["guarantees"] for p in profiles)
    assert any("," in p["creditTotal"] for p in profiles)
    for row in profiles:
        assert cents(row["creditTotal"]) == sum(cents(c["amount"]) for c in row["fidi"])
        assert cents(row["guaranteeTotal"]) == sum(cents(g["amount"]) for g in row["guarantees"])
        assert (row["creditTotal"] if "," in row["creditTotal"] else row["creditTotal"] + ",00") in row["notes"]
        assert row["subjects"][0]["ndg"] == row["ndg"]
        assert {g["creditId"] for g in row["guarantees"]} <= {c["id"] for c in row["fidi"]}
        created = date.fromisoformat("-".join(reversed(row["created"].split("/"))))
        for credit in row["fidi"]:
            assert date.fromisoformat("-".join(reversed(credit["due"].split("/")))) > created


def test_disk_catalog_drives_the_same_profiles_as_the_default_seed(tmp_path: Path) -> None:
    path = tmp_path / "sim.sqlite"
    build_database(path)
    assert synthetic_practices(path) == synthetic_practices()
    with sqlite3.connect(path) as con:
        con.execute("UPDATE subject SET name='ALBA TEST' WHERE ndg='90000001'")
    build_database(path)
    assert synthetic_practices(path)[0]["name"] == "ALBA TEST"


def test_sqlite_rejects_a_guarantee_linked_to_another_practices_credit(tmp_path: Path) -> None:
    path = tmp_path / "local.sqlite"
    build_database(path)
    with sqlite3.connect(path) as con:
        con.execute("PRAGMA foreign_keys=ON")
        assert not con.execute("PRAGMA foreign_key_check").fetchall()
        assert con.execute("SELECT count(*) FROM credit WHERE credit_id='F2'").fetchone()[0] > 0
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE guarantee SET credit_id='F2' WHERE practice_key='demo' AND guarantee_id='G1'")


def test_build_keeps_existing_unrelated_files_intact(tmp_path: Path) -> None:
    path = tmp_path / "unrelated.sqlite"
    path.write_bytes(b"existing content")
    with pytest.raises((ValueError, sqlite3.DatabaseError, FileExistsError)):
        build_database(path)
    assert path.read_bytes() == b"existing content"


def test_concurrent_first_use_publishes_one_complete_seed(tmp_path: Path) -> None:
    path = tmp_path / "shared.sqlite"
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(build_database, [path] * 4))
    assert len(synthetic_practices(path)) == 64


def test_synthetic_notes_include_household_capacity_and_repayment_horizon() -> None:
    profiles = synthetic_practices()
    assert all("mensil" in p["notes"].lower() and "anni" in p["notes"] for p in profiles)
    assert len({p["assignee"] for p in profiles}) > 1
    assert len({(p["operatorName"], p["operatorId"]) for p in profiles}) == 1
