"""The interactive reference practice uses the same truth as the image benchmark."""

import csv
from pathlib import Path

from bper_simulator_data import reference_practice
from bper_synthetic_db import synthetic_practices


REFERENCE_CSV = Path(__file__).resolve().parents[1] / "tools" / "reference" / "dati.csv"


def test_subjects_include_only_populated_reference_rows() -> None:
    practice = reference_practice()

    assert [row["role"] for row in practice["subjects"]] == [
        "Richiedente", "Nuovo Garante/nuovo Datore Di Pegno", "Cointestazione"
    ]
    assert practice["subjects"][0]["ndg"] == practice["ndg"]


def test_tooltips_describe_their_own_cells() -> None:
    practice = reference_practice()

    assert practice["evidenceTooltip"] == "Origination BSTORE"
    assert practice["fidi"][0]["tooltip"].startswith("340176")
    assert [(row["id"], row["tooltip"].split("-")[0]) for row in practice["guarantees"]] == [
        ("G1", "457"), ("G2", "55")
    ]


def test_each_tooltip_names_the_field_its_truth_label_gives() -> None:
    practice = reference_practice()
    assert [row["tooltipField"] for row in practice["fidi"] + practice["guarantees"]] == [
        "tooltip_descrizione_m_consap", "tooltip_descrizione_consap_dr_bis", "tooltip_descrizione_ipoteca"]


def test_note_lines_preserve_every_word_of_the_ground_truth() -> None:
    with REFERENCE_CSV.open(encoding="utf-8-sig", newline="") as source:
        original = next(row["Valore rilevato"] for row in csv.DictReader(source)
                        if row["Denominazione da attribuire"] == "Note della richiesta")

    rendered = reference_practice()["notes"]

    assert rendered.split() == original.split()
    assert len([line for line in rendered.splitlines() if line.startswith("- ")]) == 7
    assert len([line for line in rendered.splitlines() if line.lstrip().startswith("IMPORTO ")]) == 3
    assert rendered.splitlines()[-2].startswith("RICHIESTA DI MUTUO")
    assert rendered.splitlines()[-1].startswith("LUNARDI GIANMARCO - 32 ANNI")


def test_reference_list_cells_use_the_product_of_its_type_and_evidence() -> None:
    # The archive has no list code for this practice (its Tipo cell is out of view): it takes the catalogue's
    # product for a BPI Mutui practice with the B evidence, as every such training or control practice shows.
    practice = reference_practice()
    products = {(p["type"], p["evidence"]): (p["typeCode"], p["typeName"]) for p in synthetic_practices()}
    assert (practice["type"], practice["evidence"]) == ("BPI Mutui", "B")
    assert (practice["typeCode"], practice["typeName"]) == products[("BPI Mutui", "B")]


def test_reference_assigned_office_is_named_as_in_the_catalogue() -> None:
    practice = reference_practice()
    offices = {p["assignee"]: p["assigneeName"] for p in synthetic_practices()}
    assert practice["assigneeName"] == offices[practice["assignee"]] == "BPI MUTUI"


def test_reference_list_displays_the_csv_status(tmp_path: Path) -> None:
    changed = tmp_path / "dati.csv"
    source = REFERENCE_CSV.read_text(encoding="utf-8-sig")
    changed.write_text(source.replace("screen 1,Stato,LAV", "screen 1,Stato,SOSP"), encoding="utf-8-sig")

    assert reference_practice(changed)["state"] == "SOSP"
