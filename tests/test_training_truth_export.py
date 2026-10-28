"""The single workbook exported from a reviewed bundle: one sheet per truth table, nothing executable."""

from __future__ import annotations

import json
from pathlib import Path

from openpyxl import load_workbook

from training.truth_export import export_workbook


def _bundle(tmp_path: Path, value: str = "123") -> Path:
    (tmp_path / "manifest.json").write_text(json.dumps({"dataset_version": "ground-truth-v3.2",
                                                         "truth_counts": {"rows": 1, "screens": 1, "practices": 1},
                                                         "sources": [{"lotto": "riscontro-2026-10-07",
                                                                      "workbook": {"path": "x.xlsx", "sha256": "abc"}}]}),
                                            encoding="utf-8")
    (tmp_path / "practices.csv").write_text("Pratica;Lotto;Gruppo;Schermate;Righe\n1;riscontro-2026-10-07;train;1;1\n",
                                            encoding="utf-8-sig")
    (tmp_path / "screens.csv").write_text("Schermata;Pratica;Lotto;Gruppo;Percorso;SHA256 immagine;SHA256 pixel;"
                                          "Larghezza;Altezza;Esempio\n1__Elenco;1;riscontro-2026-10-07;train;1/Elenco.png;"
                                          "aa;bb;200;100;sì\n", encoding="utf-8-sig")
    (tmp_path / "ground_truth.csv").write_text("Fotogramma;Denominazione da attribuire;Valore rilevato;Esito;"
                                               "Stato revisione;Pratica;Lotto;Gruppo;Riga Excel;Correzione\n"
                                               f"1__Elenco;NDG;{value};TRASCRITTO;Confermato;1;riscontro-2026-10-07;"
                                               "train;2;\n", encoding="utf-8-sig")
    return tmp_path


def test_exports_one_sheet_per_truth_table(tmp_path: Path) -> None:
    out = tmp_path / "truth.xlsx"
    export_workbook(_bundle(tmp_path), out)
    workbook = load_workbook(out)
    assert workbook.sheetnames == ["Info", "Pratiche", "Schermate", "Valori"]
    values = workbook["Valori"]
    assert [cell.value for cell in values[1]][:3] == ["Fotogramma", "Denominazione da attribuire", "Valore rilevato"]
    assert [cell.value for cell in values[2]][:4] == ["1__Elenco", "NDG", "123", "TRASCRITTO"]
    assert workbook["Schermate"]["H2"].value == 200
    assert workbook["Info"]["B1"].value == "ground-truth-v3.2"


def test_a_value_that_looks_like_a_formula_stays_text(tmp_path: Path) -> None:
    out = tmp_path / "truth.xlsx"
    export_workbook(_bundle(tmp_path, value="=1+2"), out)
    cell = load_workbook(out)["Valori"]["C2"]
    assert (cell.value, cell.data_type) == ("=1+2", "s")
