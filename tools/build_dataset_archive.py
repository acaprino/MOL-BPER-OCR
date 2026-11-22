"""Build the clean practice archive (data/dataset) from a truth bundle and its practice folders.

The archive holds sources, truth and roles under uniform names, with no lots, versions or old file names:
what a training from scratch needs and nothing derived (OCR and models are rebuilt from it).

    python tools/build_dataset_archive.py --truth <bundle> --pratiche <folder> --out data/dataset
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ============================================================
# Naming
# ============================================================

PAGES = {"elenco": "elenco", "soggetti": "soggetti", "gestionefidi": "gestione-fidi", "note": "note",
         "scheda_privati": "scheda-privati"}
PAGE_ORDER = list(PAGES.values())
BASE_STEM = {slug: stem for stem, slug in PAGES.items()}     # the unnumbered screen of a page comes first
VARIANTS = {"dx": "destra", "down": "basso", "chiuso": "chiuso", "tooltip": "tooltip"}
STEM = re.compile(r"^(Elenco|Soggetti|GestioneFidi|Note|Scheda_Privati)(?:_?(?:(dx|down|chiuso)|(tooltip)\d+|\d+))?$",
                  re.IGNORECASE)

SCREENS_HEAD = ["Schermata", "Pratica", "Pagina", "Numero", "Variante", "File", "SHA256", "Larghezza", "Altezza"]
VALUES_HEAD = ["Schermata", "Campo", "Chiave", "Valore", "Esito"]
PRACTICES_HEAD = ["Pratica", "Ruolo", "Schermate", "Valori"]


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def _write(path: Path, head: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";", lineterminator="\r\n")
        writer.writerow(head)
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_stem(stem: str) -> tuple[str, str]:
    """Old file stem -> (page slug, variant). A trailing number says nothing about the content."""
    match = STEM.match(stem)
    if not match:
        raise ValueError(f"Nome di schermata fuori dalle pagine note: {stem}.")
    page = PAGES[re.sub(r"[^a-z_]", "", match.group(1).lower())]
    variant = match.group(2) or match.group(3) or ""
    return page, VARIANTS.get(variant.lower(), "")


def _field_keys() -> dict[str, str]:
    sys.path.insert(0, str(ROOT / "src"))
    from training.schema import vocabulary

    return vocabulary()[1]


# ============================================================
# Build
# ============================================================

def build_dataset_archive(truth_dir: Path, practices_dir: Path, out_dir: Path) -> dict[str, int]:
    """Write the archive under out_dir, which must be empty or missing; returns the counts."""
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"{out_dir} non è vuota: un archivio esistente non si sovrascrive.")
    practices = _read(truth_dir / "practices.csv")
    roles = {row["Pratica"]: row["Ruolo"] for row in practices}
    keys = _field_keys()

    by_practice: dict[str, list[dict[str, str]]] = {}
    for row in _read(truth_dir / "screens.csv"):
        by_practice.setdefault(row["Pratica"], []).append(row)
    unknown_role = sorted(set(by_practice) - set(roles))
    if unknown_role:
        raise ValueError(f"Pratiche senza ruolo: {unknown_role}.")

    plan, new_id = [], {}
    for practice in sorted(by_practice):
        grouped: dict[str, list[tuple[str, dict[str, str], str]]] = {}
        for row in by_practice[practice]:
            stem = row["Schermata"].split("__", 1)[1]
            page, variant = _parse_stem(stem)
            grouped.setdefault(page, []).append((stem, row, variant))
        for page in PAGE_ORDER:
            members = sorted(grouped.get(page, []), key=lambda m: (m[0].lower() != BASE_STEM[page], m[0].lower(), m[0]))
            for number, (stem, row, variant) in enumerate(members, 1):
                name = f"{page}-{number:02d}"
                new_id[row["Schermata"]] = f"{practice}/{name}"
                plan.append((practice, page, number, variant, name, row))

    values = []
    for row in _read(truth_dir / "ground_truth.csv"):
        if row["Fotogramma"] not in new_id:
            raise ValueError(f"Valore su una schermata sconosciuta: {row['Fotogramma']}.")
        display = row["Denominazione da attribuire"]
        values.append([new_id[row["Fotogramma"]], display, keys.get(display, ""), row["Valore rilevato"], row["Esito"]])

    for practice, _page, _number, _variant, _name, row in plan:       # verify every source before writing anything
        source = practices_dir / row["Percorso"]
        if not source.is_file() or _sha256(source) != row["SHA256 immagine"]:
            raise ValueError(f"{row['Percorso']} manca o differisce dall'immagine registrata.")

    out_dir.mkdir(parents=True, exist_ok=True)
    screens = []
    for practice, page, number, variant, name, row in plan:
        target = out_dir / "pratiche" / practice / f"{name}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(practices_dir / row["Percorso"], target)
        screens.append([f"{practice}/{name}", practice, page, f"{number:02d}", variant,
                        f"pratiche/{practice}/{name}.png", row["SHA256 immagine"], row["Larghezza"], row["Altezza"]])
    shown = {row[0].split("/", 1)[0]: 0 for row in screens}
    for row in values:
        shown[row[0].split("/", 1)[0]] += 1
    counts = {practice: sum(1 for row in screens if row[1] == practice) for practice in shown}
    _write(out_dir / "schermate.csv", SCREENS_HEAD, screens)
    _write(out_dir / "valori.csv", VALUES_HEAD, values)
    _write(out_dir / "pratiche.csv", PRACTICES_HEAD,
           [[practice, roles[practice], str(counts[practice]), str(shown[practice])] for practice in sorted(shown)])
    return {"pratiche": len(shown), "schermate": len(screens), "valori": len(values)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--pratiche", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(build_dataset_archive(args.truth, args.pratiche, args.out))


if __name__ == "__main__":
    main()
