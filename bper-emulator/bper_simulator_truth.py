"""Ground truth for native, single-practice captures at the nine numbered site views."""
import csv
from io import StringIO
from pathlib import Path
from runpy import run_path


# The standalone simulator does not install the extraction or training packages.
# Resolve the project's stdlib-only reader without modifying the caller's sys.path.
_schema = Path(__file__).resolve().parents[1] / "src" / "training" / "schema.py"
CSV_LABELS = {key: label.strip() for label, key in run_path(str(_schema))["vocabulary"]()[1].items()}
FINANCIAL_TOOLTIPS = (
    "tooltip_descrizione_m_consap", "tooltip_descrizione_consap_dr_bis", "tooltip_descrizione_ipoteca",
)
CREDIT_FIELDS = {
    "n_fido": "id", "rapporto": "account", "descrizione": "description",
    "scadenza": "due", "importo_euro": "amount", "tipo_op": "operation",
}


def _tooltip_targets(practice: dict) -> dict[int, tuple[str | None, str]]:
    targets = {}
    evidence = practice["evidence"]
    text = practice["evidenceTooltip"]
    if evidence and text and text.strip():
        targets[3] = ("tooltip_evidenze_b" if evidence == "B" else None, text)
    for start, rows in ((6, practice["fidi"][:1]), (7, practice["guarantees"][:2])):
        for step, row in enumerate(rows, start):
            text = row.get("tooltip")
            if row.get("description") and text and text.strip():
                targets[step] = (row.get("tooltipField"), text)
    return targets


def available_steps(practice: dict) -> list[int]:
    """Canonical capture states actually reachable for this dossier."""
    return sorted([1, 2, 4, 5, 9, *_tooltip_targets(practice)])


def practice_truth_csv(practice: dict) -> str:
    """Return evaluator CSV for screen N.png at each available canonical state."""
    targets = _tooltip_targets(practice)
    identity = {"ndg": practice["ndg"], "denominazione": practice["name"]}
    list_fields = {**identity, "evidenze": practice["evidence"], "tooltip_evidenze_b": ""}
    detail = {
        **identity, "tipo": practice["type"],
        "filiale_relazione": " - ".join(part for part in (practice["branch"], practice["branchName"]) if part),
    }
    subjects = {}
    for index in range(4):
        row = practice["subjects"][index] if index < len(practice["subjects"]) else {}
        for field, prop in (("ndg", "ndg"), ("denominazione", "name"), ("ruolo", "role")):
            subjects[f"{field}_{index + 1}"] = row.get(prop, "")

    # The scalar credit contract uses FIDI row one, even on a multi-credit dossier.
    first = next(iter(practice["fidi"]), {})
    credit = {field: first.get(prop, "") for field, prop in CREDIT_FIELDS.items()}
    financial = {**detail, **credit, **dict.fromkeys(FINANCIAL_TOOLTIPS, "")}
    screens = {
        1: {**list_fields, "stato": practice["state"], "fase": practice["phase"], "creazione": practice["date"]},
        # At the middle scroll position the creation column is clipped behind the pinned name.
        2: list_fields,
        4: {**detail, **subjects},
        5: financial,
        9: {**detail, "note_della_richiesta": practice["notes"]},
    }
    for step, (field, text) in targets.items():
        # The far-right list view exposes only the end of the identity columns.
        values = {"evidenze": practice["evidence"], "tooltip_evidenze_b": ""} if step == 3 else financial.copy()
        if field is not None:
            values[field] = text
        screens[step] = values

    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("Fotogramma", "Denominazione da attribuire", "Valore rilevato"))
    for step, values in sorted(screens.items()):
        writer.writerows((f"screen {step}", CSV_LABELS[key], value) for key, value in values.items())
    return output.getvalue()
