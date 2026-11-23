"""Read the practice and website images used by the simulator."""

import csv
from io import BytesIO
import json
import re
from pathlib import Path

from bper_simulator_truth import CSV_LABELS
from bper_synthetic_db import OPERATORS, product_for

FIELD_OF_LABEL = {label: key for key, label in CSV_LABELS.items()}


REFERENCE_CSV = Path(__file__).resolve().parents[1] / "tools" / "reference" / "dati.csv"
# Scheda Privati of practice 52062600, transcribed from its five repository screenshots.
REFERENCE_SCHEDA = Path(__file__).resolve().parent / "site" / "scheda" / "reference.json"
# The native website is 842 x 617 in every frame. Its position inside the
# recorded browser window varies by one pixel across screenshots.
SITE_ORIGINS = {
    1: (3, 59), 2: (3, 60), 3: (3, 60), 4: (3, 59), 5: (3, 60),
    6: (3, 60), 7: (3, 60), 8: (4, 60), 9: (4, 60),
}


def site_reference_png(step: int) -> bytes:
    """Return the original website pixels without window borders or browser controls."""
    from PIL import Image

    from tools.reference_screens import reference_screens

    left, top = SITE_ORIGINS[step]
    with Image.open(reference_screens()[f"screen {step}"]) as source:
        page = source.crop((left, top, left + 842, top + 617))
        output = BytesIO()
        page.save(output, format="PNG")
        return output.getvalue()


def reference_schede() -> dict[str, dict]:
    """Reference Scheda Privati pages keyed by NDG, the key of their real URL."""
    scheda = json.loads(REFERENCE_SCHEDA.read_text(encoding="utf-8"))
    return {scheda["ndg"]: scheda}


def _tooltip(fields: dict[str, str]) -> tuple[str, str, str | None]:
    """The description a tooltip belongs to, its text, and the extracted field its label names (or None)."""
    for label, text in fields.items():
        if label.startswith("tooltip su valore campo "):
            return label.partition(": ")[2], text, FIELD_OF_LABEL.get(label.strip())
    raise KeyError("Missing reference tooltip")


def _note_lines(note: str, name: str) -> str:
    # The CSV flattened bullets, indented amounts and the two closing paragraphs.
    note = re.sub(r" (?=- [A-Z][a-z])", "\n", note)
    note = note.replace(" IMPORTO ", "\n      IMPORTO ")
    note = note.replace("; RICHIESTA ", ";\nRICHIESTA ", 1)
    return note.replace(f". {name} ", f".\n{name} ", 1)


def reference_practice(path: Path = REFERENCE_CSV) -> dict[str, str | list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        screens: dict[str, dict[str, str]] = {}
        for row in csv.DictReader(source):
            screen = screens.setdefault(row["Fotogramma"], {})
            screen[row["Denominazione da attribuire"]] = row["Valore rilevato"]

    listing = screens["screen 1"]
    details = screens["screen 4"]
    loan = screens["screen 5"]
    subjects = [
        {"ndg": details[f"NDG {index}"], "name": details[f"DENOMINAZIONE {index}"],
         "role": details[f"RUOLO {index}"]}
        for index in range(1, 5) if details[f"NDG {index}"] or details[f"DENOMINAZIONE {index}"]
    ]
    branch, branch_name = details["Filiale relazione"].split(" - ", 1)
    credit = {
        "id": loan["n° FIDO"], "account": loan["Rapporto"], "description": loan["Descrizione"],
        "due": loan["Scadenza"], "amount": loan["Importo (€)"], "operation": loan["Tipo Op."],
        "tooltip": _tooltip(screens["screen 6"])[1], "tooltipField": _tooltip(screens["screen 6"])[2],
    }
    # The original guarantee table is visible in screen 5; only its tooltips are in the CSV.
    fund_display = f"{details['NDG 2']} {details['DENOMINAZIONE 2'][:10]}".strip()
    guarantees = []
    for step, row_id, amount, holder in (
        (7, "G1", "127.040", fund_display),
        (8, "G2", "285.840", ""),
    ):
        description, tooltip, field = _tooltip(screens[f"screen {step}"])
        guarantees.append({
            "id": row_id, "description": description, "creditId": credit["id"],
            "ndgName": holder, "amount": amount, "operation": "Nuova / In Lavoraz.",
            "tooltip": tooltip, "tooltipField": field,
        })

    assignee = "901500"
    # The list's Tipo cell: the archive has no code for this practice (out of view), so the catalogue's product.
    code, product = product_for(details["Tipo"], listing["Evidenze"]) or (None, None)
    return {
        "ndg": listing["NDG"], "name": listing["DENOMINAZIONE"], "number": "51350695",
        "operatorName": "Crut Radu Ionut", "operatorId": "U820797", "officeCode": "90901500",
        "noteAuthor": "Ruben Scioscia (25861)",
        # The list's Tipo and Assegnata cells use the synthetic catalogue's codes and names (None: unknown).
        "branch": branch, "branchName": branch_name, "type": details["Tipo"],
        "typeCode": code, "typeName": product,
        "assigneeName": {code: office for code, _, office in OPERATORS}.get(assignee),
        "created": listing["Creazione"], "date": listing["Creazione"], "state": listing["Stato"],
        "phase": listing["Fase"], "abi": "5387", "assignee": assignee, "evidence": listing["Evidenze"],
        "evidenceTooltip": _tooltip(screens["screen 3"])[1],
        "subjects": subjects, "fidi": [credit], "guarantees": guarantees,
        "notes": _note_lines(screens["screen 9"]["Note della richiesta"], listing["DENOMINAZIONE"]),
        "creditTotal": credit["amount"], "guaranteeTotal": "412.880",
    }
