"""The profile format: one JSON object per practice, the single shape every catalogue source produces."""

import json
from pathlib import Path

import pytest

from bper_profiles import check_profiles, load_profiles, validate_profile
from bper_site_fixture import fictitious_profile as fictitious, write_profiles as write
from bper_synthetic_db import synthetic_practices

REPO = Path(__file__).resolve().parents[1]
ARCHIVE = REPO / "data" / "dataset"


def test_every_synthetic_catalogue_practice_is_a_valid_profile() -> None:
    assert [(p["key"], validate_profile(p)) for p in synthetic_practices() if validate_profile(p)] == []


def test_a_profile_file_loads_its_practices_unchanged(tmp_path: Path) -> None:
    profiles = [fictitious("fittizia-001"), fictitious("fittizia-002", "test")]
    assert load_profiles(write(tmp_path / "profili.json", profiles), archive=ARCHIVE) == profiles


def test_a_profile_missing_a_field_is_refused() -> None:
    profile = fictitious()
    del profile["fidi"][0]["due"]
    assert any("fidi.0.due" in problem for problem in validate_profile(profile))


def test_a_profile_with_a_value_of_the_wrong_type_is_refused() -> None:
    profile = fictitious()
    profile["scheda"]["details"]["employerRegistered"] = "no"
    assert any("scheda.details.employerRegistered" in problem for problem in validate_profile(profile))


def test_a_profile_with_an_unknown_field_is_refused() -> None:
    profile = fictitious()
    profile["importoTotale"] = "1"
    assert any("importoTotale" in problem for problem in validate_profile(profile))


@pytest.mark.parametrize("role", ["", "training", "Test", "riferimento"])
def test_a_profile_with_an_unknown_role_is_refused(role: str) -> None:
    assert any("role" in problem for problem in validate_profile(fictitious(role=role)))


def test_a_profile_with_an_unknown_page_is_refused() -> None:
    profile = fictitious()
    profile["pages"] = ["elenco", "garanzie"]
    assert any("pages" in problem for problem in validate_profile(profile))


def test_a_file_with_two_profiles_under_one_key_is_refused(tmp_path: Path) -> None:
    path = write(tmp_path / "doppio.json", [fictitious("fittizia-001"), fictitious("fittizia-001")])
    with pytest.raises(ValueError, match="fittizia-001"):
        load_profiles(path, archive=ARCHIVE)


def test_a_file_of_another_format_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "altro.json"
    path.write_text(json.dumps({"format": "altro/1", "profiles": [fictitious()]}), encoding="utf-8")
    with pytest.raises(ValueError, match="altro.json"):
        load_profiles(path, archive=ARCHIVE)


def archive_identity(key: str) -> str:
    """One NDG or name of a training practice of the real archive, never printed: a failure shows only keys."""
    import csv
    with (ARCHIVE / "pratiche.csv").open(encoding="utf-8-sig", newline="") as source:
        training = {row["Pratica"] for row in csv.DictReader(source, delimiter=";") if row["Ruolo"] == "addestramento"}
    with (ARCHIVE / "valori.csv").open(encoding="utf-8-sig", newline="") as source:
        return next(row["Valore"] for row in csv.DictReader(source, delimiter=";")
                    if row["Schermata"].split("/")[0] in training and row["Chiave"] == key
                    and row["Esito"] == "TRASCRITTO" and row["Valore"].strip())


@pytest.mark.parametrize("field", ["ndg", "name"])
def test_a_synthetic_profile_may_not_carry_an_identity_of_the_real_archive(field: str) -> None:
    profile = fictitious()
    profile["subjects"][-1][field] = archive_identity("ndg" if field == "ndg" else "denominazione")
    with pytest.raises(ValueError) as refused:
        check_profiles([profile], archive=ARCHIVE)
    message = str(refused.value)
    names_the_profile_only = "fittizia-001" in message and profile["subjects"][-1][field] not in message
    assert names_the_profile_only  # a boolean, so a failure prints no real value


def test_the_identity_check_applies_only_to_synthetic_profiles() -> None:
    profile = fictitious(role="addestramento")
    profile["subjects"][-1]["ndg"] = archive_identity("ndg")
    check_profiles([profile], archive=ARCHIVE)
