"""Where the CLI finds the truth of the folder it extracts: a dati.csv beside the screenshots, else the archive."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from extraction.evaluation import resolve_ground_truth

HEADER = ("Schermata", "Campo", "Valore", "Esito", "Stato revisione", "Riga Excel", "Correzione")


def _archive(tmp_path: Path, practice: str = "123") -> Path:
    """data/pratiche in miniature: the practice folder and the archive workbook beside it."""
    folder = tmp_path / "pratiche" / practice
    folder.mkdir(parents=True)
    workbook = Workbook()
    workbook.active.title = "Indice"
    sheet = workbook.create_sheet(practice)
    sheet.append(HEADER)
    sheet.append(("Elenco", "NDG", "26871394", "TRASCRITTO", None, 2, None))
    sheet.append(("Elenco", "Tipo", None, "VUOTO", None, 3, None))
    sheet.append(("Soggetti", "Ruolo 1", "Richiedente", "TRASCRITTO", None, 4, None))
    workbook.save(tmp_path / "pratiche" / "pratiche.xlsx")
    return folder


def test_a_practice_folder_takes_its_truth_from_the_archive_workbook(tmp_path: Path) -> None:
    truth = resolve_ground_truth(str(_archive(tmp_path)))
    assert truth == {"Elenco": {"NDG": "26871394", "Tipo": ""}, "Soggetti": {"Ruolo 1": "Richiedente"}}


def test_a_dati_csv_beside_the_screenshots_wins_over_the_archive(tmp_path: Path) -> None:
    folder = _archive(tmp_path)
    (folder / "dati.csv").write_text("Fotogramma,Denominazione da attribuire,Valore rilevato\nscreen 1,NDG,1\n",
                                     encoding="utf-8")
    assert resolve_ground_truth(str(folder)) == {"screen 1": {"NDG": "1"}}


def test_a_practice_missing_from_the_archive_workbook_is_refused(tmp_path: Path) -> None:
    _archive(tmp_path)
    (tmp_path / "pratiche" / "999").mkdir()
    with pytest.raises(ValueError, match="999"):
        resolve_ground_truth(str(tmp_path / "pratiche" / "999"))


def test_a_folder_without_any_truth_is_refused(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_ground_truth(str(tmp_path))
