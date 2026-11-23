"""Practices of the real archive (data/dataset) as emulator profiles, built in memory and never written.

Each of the 33 practices becomes the profile ``arch-<pratica>`` (format in bper_profiles) whose role is its Ruolo
in pratiche.csv. The test practices stay closed until a frozen candidate (ADR 0027): they are read only with
include_test, as training.dataset reads them, and the user asked to have them available, hence the explicit
double flag (--include-archive and --include-test) on serve, export and capture.

Values of the 45 extracted fields are the archive's own, never invented:
  - a value comes from the rows of valori.csv for its key, preferring TRASCRITTO, then DERIVATO, then PARZIALE;
    VUOTO, NON VISIBILE and NON LEGGIBILE rows give none, and a field without a value is shown empty;
  - a value the pages show differently comes from the page that shows it: the list (elenco) gives Stato, Fase,
    Creazione, Evidenze and the short Tipo code with its tooltip (tooltip_descrizione_bmb); the detail pages
    (soggetti, gestione-fidi, note) give the header, Tipo Pratica and Filiale relazione, then the list;
  - a note seen in several scrolled screens joins its fragments (merge_fragments). Text is only re-spaced: the
    Scheda Privati note is broken at spaces into lines that fit its box (the evaluator compares squashed text).
Values outside the 45 fields come from the archive when it has them (the guarantee table, the agent behind the
note, the description in a tooltip's label); the rest is empty, or a stand-in listed in provenance.filler.
A practice has the PEF pages it has screenshots of, and a Scheda Privati page only with scheda-privati screens.
"""

from collections import defaultdict
import csv
from pathlib import Path
import re
import textwrap
from typing import NamedTuple

from bper_profiles import ARCHIVE, PAGES, SCHEDA_FIELDS
from bper_simulator_truth import NOTE_LINE_CHARS
from bper_synthetic_db import BANK, EMPTY_MONTH, OFFICE_CODE, OPERATORS

RANK = {"TRASCRITTO": 0, "DERIVATO": 1, "PARZIALE": 2}
DETAIL = ("soggetti", "gestione-fidi", "note")
SCHEDA = "scheda-privati"
MIN_OVERLAP = 40  # characters two fragments of one note must share to be joined at their overlap
CREDIT_COLUMNS = {"n_fido": "id", "rapporto": "account", "descrizione": "description", "scadenza": "due",
                  "importo_euro": "amount", "tipo_op": "operation"}
GUARANTEE_COLUMNS = (("n", "id"), ("Descrizione", "description"), ("Fido", "creditId"), ("NDG", "ndg"),
                     ("Denominazione", "name"), ("Imp", "amount"), ("Tipo Op.", "operation"),
                     ("tooltip Descrizione", "tooltip"))
GUARANTEE_TOOLTIPS = ("tooltip_descrizione_consap_dr_bis", "tooltip_descrizione_ipoteca")


class Value(NamedTuple):
    page: str
    number: int
    label: str
    key: str
    text: str
    outcome: str


def _table(root: Path, name: str) -> list[dict[str, str]]:
    with (Path(root) / name).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter=";"))


def merge_fragments(fragments: list[str]) -> str:
    """One note from the fragments that scrolled screens show, in screen order: a fragment already contained
    adds nothing, one overlapping the end of the text adds its tail, and a disjoint one starts a paragraph."""
    merged = ""
    for fragment in (f.strip() for f in fragments):
        if not fragment or fragment in merged:
            continue
        if merged in fragment:
            merged = fragment
            continue
        overlap = max((n for n in range(MIN_OVERLAP, min(len(merged), len(fragment)) + 1)
                       if merged.endswith(fragment[:n])), default=0)
        merged = merged + fragment[overlap:] if overlap else merged + "\n\n" + fragment
    return merged


def _note_box(note: str) -> str:
    """The Scheda Privati note broken at spaces into lines of the box, with a blank first and last line."""
    if not note:
        return ""
    wrap = textwrap.TextWrapper(NOTE_LINE_CHARS, break_long_words=False, break_on_hyphens=False)
    return "\n" + "\n\n".join(wrap.fill(paragraph) for paragraph in note.split("\n\n")) + "\n"


class _Practice:
    def __init__(self, values: list[Value]) -> None:
        self.values = [v for v in values if v.outcome in RANK and v.text.strip()]
        self.stated = [v for v in values if v.outcome in (*RANK, "VUOTO")]

    def found(self, *, key: str | None = None, label: str | None = None, pages: tuple[str, ...] = ()) -> list[Value]:
        hits = [v for v in self.values if (key is None or v.key == key) and (label is None or v.label == label)
                and (not pages or v.page in pages)]
        return sorted(hits, key=lambda v: (RANK[v.outcome], pages.index(v.page) if pages else 0, v.number))

    def first(self, key: str, pages: tuple[str, ...] = (), then: tuple[str, ...] = ()) -> str:
        """The best value of the pages; only without one, of the fallback pages (then)."""
        hits = self.found(key=key, pages=pages) or (self.found(key=key, pages=then) if then else [])
        return hits[0].text.strip() if hits else ""

    def note(self, key: str, page: str) -> str:
        hits = self.found(key=key, pages=(page,))
        best = [v for v in hits if RANK[v.outcome] == RANK[hits[0].outcome]] if hits else []
        return merge_fragments([v.text for v in sorted(best, key=lambda v: v.number)])


def _row_of(label: str) -> int:
    match = re.search(r"\(riga (\d+)\)", label)
    return int(match.group(1)) if match else 1


def _guarantees(practice: _Practice) -> tuple[list[dict], list[str]]:
    table: dict[int, dict[str, str]] = defaultdict(dict)
    for value in practice.found(pages=("gestione-fidi",)):
        match = re.fullmatch(r"Garanzia (\d+): (.+)", value.label)
        if match and not value.key:
            column = next((name for prefix, name in GUARANTEE_COLUMNS if match.group(2).startswith(prefix)), None)
            if column:
                table[int(match.group(1))].setdefault(column, value.text.strip())
    for key in GUARANTEE_TOOLTIPS:
        for value in practice.found(key=key):
            row = table[_row_of(value.label)]
            if row.get("tooltipField"):
                continue  # one extracted field per description, its best transcription
            # The extracted field's own transcription wins over the table's copy of the same tooltip.
            row.update(tooltip=value.text.strip(), tooltipField=key)
            # The label names the description the tooltip belongs to: "... (riga 2): IPOTECA I GR.".
            row.setdefault("description", value.label.partition(": ")[2].strip())
    rows, filler = [], []
    for n in range(1, max(table, default=0) + 1):
        cells = table.get(n, {})
        if not cells:
            filler.append(f"guarantees.{n - 1}")  # an empty row before a known one
        rows.append({"id": cells.get("id", ""), "creditId": cells.get("creditId", ""),
                     "description": cells.get("description", ""),
                     "ndgName": " ".join(part for part in (cells.get("ndg"), cells.get("name")) if part),
                     "amount": cells.get("amount", ""), "operation": cells.get("operation", ""),
                     "tooltip": cells.get("tooltip", ""), "tooltipField": cells.get("tooltipField")})
    return rows, filler


def _credits(practice: _Practice) -> list[dict]:
    row = {name: practice.first(key, ("gestione-fidi",)) for key, name in CREDIT_COLUMNS.items()}
    if not any(row.values()):
        return []
    keyed = practice.found(key="tooltip_descrizione_m_consap")
    plain = practice.found(label="Fido: tooltip Descrizione", pages=("gestione-fidi",))
    row["tooltip"] = (keyed or plain)[0].text.strip() if keyed or plain else ""
    row["tooltipField"] = "tooltip_descrizione_m_consap" if keyed else None
    return [row]


def _subjects(practice: _Practice) -> list[dict]:
    slots = [{"ndg": practice.first(f"ndg_{n}", ("soggetti",)), "name": practice.first(f"denominazione_{n}", ("soggetti",)),
              "role": practice.first(f"ruolo_{n}", ("soggetti",))} for n in range(1, 5)]
    while slots and not any(slots[-1].values()):
        slots.pop()
    return slots


def _scheda(practice: _Practice, number: str) -> tuple[dict, list[str]]:
    fields = {key: practice.first(key, (SCHEDA,)) for key in SCHEDA_FIELDS}
    fields["note_scheda_privati"] = _note_box(practice.note("note_scheda_privati", SCHEDA))
    staff = {"user": "", "branch": "", "bank": BANK}
    scheda = {
        # The customer of the page: in a joint practice, one holder, not the practice's own NDG.
        "ndg": practice.first("ndg", (SCHEDA,)), "schedaId": f"{int(number):011d}",
        "name": practice.first("denominazione", (SCHEDA,)),
        "operator": {"code": f"{OPERATORS[0][0]} - {OFFICE_CODE}", "name": OPERATORS[0][1]},
        "lastChange": {"when": fields["ultima_validazione_scheda"], **staff}, "lastValidation": staff,
        "fields": fields,
        "details": {"employerNdg": "", "employerFrom": EMPTY_MONTH, "employerTo": EMPTY_MONTH,
                    "employerRegistered": True, "incomeChanneled": "", "creditCardBalance": "", "housing": "",
                    "housingFrom": ""},
    }
    return scheda, ["scheda.schedaId", "scheda.operator", "scheda.lastChange", "scheda.lastValidation",
                    "scheda.details"]


def _profile(number: str, role: str, pages: set[str], practice: _Practice) -> dict:
    filiale = practice.first("filiale_relazione", DETAIL)
    branch, separator, branch_name = filiale.partition(" - ")
    if not separator:
        branch, branch_name = "", filiale
    fidi = _credits(practice)
    guarantees, filler = _guarantees(practice)
    created = practice.first("creazione", ("elenco",))
    author = practice.found(label="Agente proponente", pages=("note",))
    scheda, scheda_filler = _scheda(practice, number) if SCHEDA in pages else (None, [])
    profile = {
        "key": f"arch-{number}", "role": role, "number": number,
        # The detail pages before the list, whatever their outcome: the list cuts long names ("NAME...").
        "ndg": practice.first("ndg", DETAIL, then=("elenco",)),
        "name": practice.first("denominazione", DETAIL, then=("elenco",)),
        "type": practice.first("tipo", DETAIL), "typeCode": practice.first("tipo", ("elenco",)),
        "typeName": practice.first("tooltip_descrizione_bmb"),
        "state": practice.first("stato", ("elenco",)), "phase": practice.first("fase", ("elenco",)),
        "date": created, "created": created, "assigned": "",
        "evidence": practice.first("evidenze", ("elenco",)), "evidenceTooltip": practice.first("tooltip_evidenze_b"),
        "branch": branch, "branchName": branch_name,
        # The operator signed in is the viewer of the emulator, not part of the practice.
        "abi": "5387", "assignee": "", "assigneeName": "", "operatorId": OPERATORS[0][0],
        "operatorName": OPERATORS[0][1], "officeCode": OFFICE_CODE,
        "noteAuthor": author[0].text.strip() if author else "", "scenario": "",
        "subjects": _subjects(practice), "fidi": fidi, "guarantees": guarantees,
        "creditTotal": fidi[0]["amount"] if fidi else "", "guaranteeTotal": "",
        "notes": practice.note("note_della_richiesta", "note"),
        "pages": [page for page in PAGES if page in pages], "scheda": scheda,
    }
    filler += ["abi", "operatorId", "operatorName", "officeCode", *scheda_filler]
    if fidi:
        filler.append("creditTotal")  # the list's Importo: the first credit line's amount
    # The fields a screenshot showed, empty ones included: the others are unknown, not empty.
    stated = sorted({v.key for v in practice.stated if v.key})
    profile["provenance"] = {"source": "archivio", "filler": filler, "stated": stated}
    return profile


def archive_profiles(root: Path = ARCHIVE, *, include_test: bool = False) -> list[dict]:
    """The archive's practices as profiles, in practice order; the test ones only with include_test."""
    roles = {row["Pratica"]: row["Ruolo"] for row in _table(root, "pratiche.csv")}
    pages: dict[str, set[str]] = defaultdict(set)
    for row in _table(root, "schermate.csv"):
        pages[row["Pratica"]].add(row["Pagina"])
    values: dict[str, list[Value]] = defaultdict(list)
    for row in _table(root, "valori.csv"):
        number, screen = row["Schermata"].split("/")
        page, _, n = screen.rpartition("-")
        values[number].append(Value(page, int(n), row["Campo"], row["Chiave"], row["Valore"], row["Esito"]))
    return [_profile(number, role, pages[number], _Practice(values[number]))
            for number, role in sorted(roles.items()) if include_test or role != "test"]
