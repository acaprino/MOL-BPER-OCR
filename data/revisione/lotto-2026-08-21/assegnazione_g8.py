"""Assign the reviewed 2026-08-21 batch to the G8 groups (docs/next-ver-plan.md §5.4).

Run from the repository root:
    python data/revisione/lotto-2026-08-21/assegnazione_g8.py
It reads the reviewed workbook and correzioni.json next to this file and writes g8_assegnazione.json.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))
from extraction.normalization import normalize_ndg  # noqa: E402
from training.dataset import read_transcribed_truth  # noqa: E402

WORKBOOK = HERE / "Revisione_10_pratiche_agosto_v1.0.xlsx"
# The 15 fields without positive examples in the v3.1 validation and test splits (plan §1.3).
UNCOVERED = ["dal", "datore_di_lavoro_anagrafica", "di_cui_percepiscono_reddito", "importo_totale_annuo_nucleo",
             "note_scheda_privati", "nr_altri_componenti_nucleo", "numero_mensilita", "professione_principale",
             "rating_ufficiale", "retribuzione_annua_netta", "score_cgs", "tipo_contratto",
             "ultima_validazione_scheda", "tooltip_descrizione_m_consap", "tooltip_descrizione_consap_dr_bis"]
NEED = {"validazione_estesa": 1, "conferma": 2}
TIE_ORDER = ("conferma", "validazione_estesa")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_review() -> list[dict[str, Any]]:
    """The reviewed rows with the recorded corrections applied (the same reader the dataset builder uses)."""
    return read_transcribed_truth(WORKBOOK, HERE / "correzioni.json")


def screen_hashes(screen: str) -> dict[str, str]:
    """Hash the source bytes and the decoded RGB pixels, as build_dataset() does for v3.1."""
    practice, name = screen.split("__", 1)
    path = ROOT / "data" / "pratiche" / practice / f"{name}.png"
    with Image.open(path) as image:
        pixels = image.convert("RGB").tobytes()
    return {"path": path.relative_to(ROOT).as_posix(), "image_sha256": _sha256(path.read_bytes()),
            "pixel_sha256": _sha256(pixels)}


def main() -> None:
    rows = read_review()
    practices = sorted({row["practice"] for row in rows}, key=int)
    filled: dict[str, set[str]] = defaultdict(set)
    ndgs: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["value"] is not None:
            filled[row["practice"]].add(row["field"])
        if row["outcome"] == "TRASCRITTO" and (row["field"] == "ndg" or row["field"].startswith("ndg_")):
            if identity := normalize_ndg(row["value"]):
                ndgs[row["practice"]].add(identity)
    images = {screen: screen_hashes(screen) for screen in sorted({row["screen"] for row in rows})}

    # Isolation from the 12 v3.1 practices: the same identities audit_splits() compares.
    reference: dict[str, dict[str, str]] = {"pratica": {}, "NDG": {}, "immagine": {}, "pixel": {}}
    for example in json.loads((ROOT / "data/training/ground-truth-v3.1/examples.json").read_text(encoding="utf-8")):
        reference["pratica"][example["practice"]] = example["practice"]
        reference["immagine"][example["image_sha256"]] = example["id"]
        reference["pixel"][example["pixel_sha256"]] = example["id"]
        for key, value in example["values"].items():
            if (key == "ndg" or key.startswith("ndg_")) and value and normalize_ndg(value):
                reference["NDG"][normalize_ndg(value)] = example["id"]
    violations: dict[str, list[dict[str, str]]] = defaultdict(list)
    owners: dict[tuple[str, str], set[str]] = defaultdict(set)
    for practice in practices:
        identities = [("pratica", practice), *[("NDG", ndg) for ndg in sorted(ndgs[practice])]]
        for screen, hashes in images.items():
            if screen.startswith(f"{practice}__"):
                identities += [("immagine", hashes["image_sha256"]), ("pixel", hashes["pixel_sha256"])]
        for kind, identity in identities:
            owners[(kind, identity)].add(practice)
            if identity in reference[kind]:
                violations[practice].append({"tipo": kind, "valore": identity, "v3_1": reference[kind][identity]})

    need = {group: {field: count for field in UNCOVERED} for group, count in NEED.items()}
    decisions: list[dict[str, Any]] = []
    ties = 0
    for practice in practices:
        fields = sorted(filled[practice] & set(UNCOVERED))
        gain = {group: sum(1 for field in fields if need[group][field] > 0) for group in NEED}
        if gain["validazione_estesa"] != gain["conferma"]:
            group, reason = max(gain, key=gain.__getitem__), "riduce di più il fabbisogno scoperto"
        else:
            group, ties = TIE_ORDER[ties % 2], ties + 1
            reason = ("parità" if gain["conferma"] else "nessuna riduzione") + ", alternanza a partire dalla conferma"
        for field in fields:
            need[group][field] = max(0, need[group][field] - 1)
        decisions.append({"pratica": practice, "gruppo": group, "campi_scoperti": fields, "riduzione": gain,
                          "motivo": reason})
    group_of = {d["pratica"]: d["gruppo"] for d in decisions}
    crossing = [{"tipo": kind, "valore": identity, "pratiche": sorted(owner)}
                for (kind, identity), owner in owners.items()
                if len({group_of[p] for p in owner}) > 1]
    if crossing:
        raise ValueError(f"Identità in comune fra validazione estesa e conferma: {crossing}.")

    manifest = {
        "lotto": "lotto-2026-08-21",
        "regola": "docs/next-ver-plan.md §5.4, regole 2 e 3",
        "interpretazione": ("Fabbisogno sui 15 campi scoperti: 1 pratica per campo in validazione estesa, 2 in conferma. "
                            "Riduzione = numero di campi scoperti non vuoti della pratica il cui fabbisogno nel gruppo è "
                            "ancora positivo. A parità (anche zero) i casi di parità si alternano conferma, validazione "
                            "estesa, ... Nessuna pratica è esclusa: le identità in comune con v3.1 sono registrate in "
                            "isolamento_v3_1 (decisione del 2026-10-28). Identità NDG: ndg e ndg_1..4 "
                            "trascritti, normalizzati con normalize_ndg(), come audit_splits()."),
        "workbook": WORKBOOK.name,
        "workbook_sha256": _sha256(WORKBOOK.read_bytes()),
        "correzioni_sha256": _sha256((HERE / "correzioni.json").read_bytes()),
        "gruppi": {group: [d["pratica"] for d in decisions if d["gruppo"] == group] for group in NEED},
        "decisioni": decisions,
        "isolamento_v3_1": {"controlli": ["pratica", "NDG", "immagine", "pixel"], "esito": "registrato, non esclude",
                            "identita_in_comune": violations},
        "isolamento_fra_gruppi": "superato",
        "fabbisogno_residuo": {group: {f: n for f, n in counts.items() if n} for group, counts in need.items()},
        "ndg": {practice: sorted(ndgs[practice]) for practice in practices},
        "schermate": images,
        "sigillo": ("Le pratiche in conferma restano sigillate fino al congelamento del candidato: niente OCR, "
                    "metriche o ispezioni per lo sviluppo sulle loro schermate o sulla loro verità."),
    }
    (HERE / "g8_assegnazione.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                                               encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ("gruppi", "fabbisogno_residuo")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
