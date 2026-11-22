"""The clean practice archive (data/dataset): sources, truth and roles under uniform names, no history."""

import csv
import hashlib
from pathlib import Path

import pytest
from PIL import Image

from tools.build_dataset_archive import build_dataset_archive

TRUTH_HEAD = ["Fotogramma", "Denominazione da attribuire", "Valore rilevato", "Esito", "Stato revisione", "Pratica",
              "Lotto", "Gruppo", "Riga Excel", "Correzione"]
SCREENS_HEAD = ["Schermata", "Pratica", "Lotto", "Gruppo", "Percorso", "SHA256 immagine", "SHA256 pixel", "Larghezza",
                "Altezza", "Esempio"]
PRACTICES_HEAD = ["Pratica", "Lotto", "Gruppo", "Ruolo", "Schermate", "Righe"]


def _write_csv(path: Path, head: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(head)
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def _png(path: Path, shade: int) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), (shade, 0, 0)).save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(tmp_path: Path, stems: dict[str, list[str]], values: list[tuple[str, str, str, str]] | None = None,
            roles: dict[str, str] | None = None) -> tuple[Path, Path]:
    """A truth bundle and a practice folder as the old layout has them, with lot and group columns."""
    truth, pratiche = tmp_path / "truth", tmp_path / "pratiche"
    truth.mkdir()
    screens, shade = [], 1
    for practice, names in stems.items():
        for name in names:
            sha = _png(pratiche / practice / f"{name}.png", shade)
            shade += 1
            screens.append([f"{practice}__{name}", practice, "lotto-vecchio", "train", f"{practice}/{name}.png", sha,
                            "p" * 64, "8", "6", "sì"])
    roles = roles or {practice: "addestramento" for practice in stems}
    _write_csv(truth / "screens.csv", SCREENS_HEAD, screens)
    _write_csv(truth / "practices.csv", PRACTICES_HEAD,
               [[practice, "lotto-vecchio", "train", roles[practice], str(len(stems[practice])), "0"] for practice in stems])
    rows = [[f"{screen}", display, value, esito, "Confermato", screen.split("__")[0], "lotto-vecchio", "train", "2", ""]
            for screen, display, value, esito in (values or [])]
    _write_csv(truth / "ground_truth.csv", TRUTH_HEAD, rows)
    return truth, pratiche


def _build(tmp_path: Path, stems: dict[str, list[str]], values: list[tuple[str, str, str, str]] | None = None,
           roles: dict[str, str] | None = None) -> Path:
    truth, pratiche = _source(tmp_path, stems, values, roles)
    out = tmp_path / "dataset"
    build_dataset_archive(truth, pratiche, out)
    return out


def test_a_page_is_numbered_from_its_base_screen_in_two_digits(tmp_path: Path) -> None:
    out = _build(tmp_path, {"111": ["Elenco_dx", "Elenco", "Elenco_tooltip1", "Soggetti"]})
    files = sorted(path.name for path in (out / "pratiche" / "111").iterdir())
    assert files == ["elenco-01.png", "elenco-02.png", "elenco-03.png", "soggetti-01.png"]
    base = _read_csv(out / "schermate.csv")
    assert [row["Schermata"] for row in base] == ["111/elenco-01", "111/elenco-02", "111/elenco-03", "111/soggetti-01"]


def test_the_variant_of_a_screen_is_read_from_its_old_name(tmp_path: Path) -> None:
    names = ["Elenco", "Elenco_dx", "Elenco_tooltip1", "GestioneFidi_Tooltip2", "GestioneFidi_down", "Note_chiuso",
             "Elenco2", "Scheda_Privati_3"]
    out = _build(tmp_path, {"111": names})
    variants = {(row["Pagina"], row["Numero"]): row["Variante"] for row in _read_csv(out / "schermate.csv")}
    assert variants[("elenco", "01")] == ""
    assert variants[("elenco", "02")] == ""          # Elenco2: delivered numbered, content not described
    assert variants[("elenco", "03")] == "destra"
    assert variants[("elenco", "04")] == "tooltip"
    assert variants[("gestione-fidi", "01")] == "basso"
    assert variants[("gestione-fidi", "02")] == "tooltip"
    assert variants[("note", "01")] == "chiuso"
    assert variants[("scheda-privati", "01")] == ""


def test_the_copied_image_is_the_same_file_under_its_new_name(tmp_path: Path) -> None:
    truth, pratiche = _source(tmp_path, {"111": ["Elenco_dx"]})
    out = tmp_path / "dataset"
    build_dataset_archive(truth, pratiche, out)
    assert (out / "pratiche" / "111" / "elenco-01.png").read_bytes() == (pratiche / "111" / "Elenco_dx.png").read_bytes()
    row = _read_csv(out / "schermate.csv")[0]
    assert row["SHA256"] == hashlib.sha256((pratiche / "111" / "Elenco_dx.png").read_bytes()).hexdigest()
    assert (row["Larghezza"], row["Altezza"], row["File"]) == ("8", "6", "pratiche/111/elenco-01.png")


def test_an_image_that_differs_from_the_recorded_digest_is_refused(tmp_path: Path) -> None:
    truth, pratiche = _source(tmp_path, {"111": ["Elenco"]})
    _png(pratiche / "111" / "Elenco.png", 200)
    with pytest.raises(ValueError, match="differisce"):
        build_dataset_archive(truth, pratiche, tmp_path / "dataset")


def test_values_follow_their_screen_to_the_new_name_with_the_field_key(tmp_path: Path) -> None:
    values = [("111__Elenco_dx", "NDG", "32015734", "TRASCRITTO"), ("111__Soggetti", "Agente proponente", "ROSSI", "TRASCRITTO")]
    out = _build(tmp_path, {"111": ["Elenco_dx", "Soggetti"]}, values)
    rows = _read_csv(out / "valori.csv")
    assert [(r["Schermata"], r["Campo"], r["Chiave"], r["Valore"], r["Esito"]) for r in rows] == [
        ("111/elenco-01", "NDG", "ndg", "32015734", "TRASCRITTO"),
        ("111/soggetti-01", "Agente proponente", "", "ROSSI", "TRASCRITTO")]


def test_a_value_on_an_unknown_screen_is_refused(tmp_path: Path) -> None:
    truth, pratiche = _source(tmp_path, {"111": ["Elenco"]}, [("111__Soggetti", "NDG", "1", "TRASCRITTO")])
    with pytest.raises(ValueError, match="schermata"):
        build_dataset_archive(truth, pratiche, tmp_path / "dataset")


def test_a_screen_name_outside_the_known_pages_is_refused(tmp_path: Path) -> None:
    truth, pratiche = _source(tmp_path, {"111": ["Mistero"]})
    with pytest.raises(ValueError, match="Mistero"):
        build_dataset_archive(truth, pratiche, tmp_path / "dataset")


def test_the_role_is_kept_and_lot_group_and_old_names_are_dropped(tmp_path: Path) -> None:
    stems = {"111": ["Elenco_dx"], "222": ["Elenco"]}
    out = _build(tmp_path, stems, [("111__Elenco_dx", "NDG", "1", "TRASCRITTO")], {"111": "addestramento", "222": "test"})
    practices = _read_csv(out / "pratiche.csv")
    assert [(p["Pratica"], p["Ruolo"], p["Schermate"], p["Valori"]) for p in practices] == [
        ("111", "addestramento", "1", "1"), ("222", "test", "1", "0")]
    text = "".join(path.read_text(encoding="utf-8-sig") for path in out.glob("*.csv"))
    for leftover in ("lotto-vecchio", "Elenco_dx", "train", "Lotto", "Gruppo"):
        assert leftover not in text


def test_off_topic_screens_are_not_copied(tmp_path: Path) -> None:
    truth, pratiche = _source(tmp_path, {"111": ["Elenco"]})
    _png(pratiche / "111" / "offtopic" / "Altro.png", 90)
    out = tmp_path / "dataset"
    build_dataset_archive(truth, pratiche, out)
    assert [path.name for path in (out / "pratiche" / "111").rglob("*.png")] == ["elenco-01.png"]


def test_an_existing_archive_is_never_overwritten(tmp_path: Path) -> None:
    truth, pratiche = _source(tmp_path, {"111": ["Elenco"]})
    out = tmp_path / "dataset"
    out.mkdir()
    (out / "note.txt").write_text("già qui", encoding="utf-8")
    with pytest.raises(FileExistsError):
        build_dataset_archive(truth, pratiche, out)
    assert (out / "note.txt").read_text(encoding="utf-8") == "già qui"
