"""Read a lot delivered as one sheet per practice (lotto-2026-11-05 onwards).

The reviewer lists the values of each practice page by page: there is no row per screenshot and no outcome
column. A sheet also holds values outside the canonical vocabulary (the guarantee table, the proposing agent):
they stay in the truth with no field key, so nothing is lost and nothing becomes a target.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from training.schema import vocabulary

DESCRIPTION_SHEET = "Descrizione"
PRACTICE_SHEET = re.compile(r"\d{8}")
SECTION_HEADER = "CAMPO RILEVATO"
SECTION_TITLES = {"Elenco": "Elenco", "Soggetti": "Soggetti", "Gestione fidi e garanzie": "GestioneFidi"}
# The note section is the only one without a title.
NOTE_PAGE = "Note"
PAGES = ("Elenco", "Soggetti", "GestioneFidi", NOTE_PAGE)
EMPTY_VALUE = "vuoto"

ELENCO_LABELS = ("NDG", "DENOMINAZIONE", "Tipo", "Stato", "Fase", "Creazione", "Evidenze")
SUBJECT_LABEL = re.compile(r"(?:NDG|DENOMINAZIONE|RUOLO) [1-4]")
SUBJECT_DISPLAYS = tuple(f"{name} {slot}" for slot in range(1, 5) for name in ("NDG", "DENOMINAZIONE", "RUOLO"))
LOAN_LABELS = {"n° Fido": "n° FIDO", "Rapporto": "Rapporto", "Descrizione": "Descrizione", "Scadenza": "Scadenza",
               "Importo (€)": "Importo (€)", "Tipo Op.": "Tipo Op."}
NOTE_LABELS = {"Note della richiesta": "Note della richiesta", "Filiale": "Filiale relazione",
               "Agente proponente": "Agente proponente"}
GUARANTEE_START = "n° Gar."
GUARANTEE_LABELS = {GUARANTEE_START, "Descrizione", "Fido", "NDG", "Denominazione", "Imp (€)%", "Tipo Op."}
AMOUNT_LABELS = {"Importo (€)", "Imp (€)%"}

LOAN_TOOLTIP = "tooltip su valore campo Descrizione (tabella Fidi):"
GUARANTEE_TOOLTIP = "tooltip su valore campo Descrizione (tabella Garanzie):"
M_CONSAP_TOOLTIP = "tooltip su valore campo Descrizione (riga 1): M. CONSAP >= 80%"
DR_BIS_TOOLTIP = "tooltip su valore campo Descrizione (riga 1): CONSAP DR BIS"
MORTGAGE_TOOLTIP = "tooltip su valore campo Descrizione (riga 2): IPOTECA I GR."
TOOLTIP_DISPLAYS = (M_CONSAP_TOOLTIP, DR_BIS_TOOLTIP, MORTGAGE_TOOLTIP)
# A tooltip starts with the product code: only these codes have a field among the 45.
LOAN_TOOLTIP_CODES = {"340176": M_CONSAP_TOOLTIP}
GUARANTEE_TOOLTIP_CODES = {"55": MORTGAGE_TOOLTIP, "457": DR_BIS_TOOLTIP}
NOTE_LABEL = "Note della richiesta"
# The list lines the application writes at the top of a note: on screen they start with a dash.
NOTE_LIST_LINES = ("Numero Finanziamento FICS:", "Numero proposta DESK:", "Importo perizia:", "Valore immobile presunto:",
                   "Immobile da ipotecare", "Dettaglio importi mutuo:", "Codice immobile:", "Sono presenti le garanzie")
NOTE_MARK = re.compile(r"^(?:[•·]|-(?!-))\s*")
# Who is on the header of a detail screen, as the other pages say: the reviewer does not list it there.
HEADER_FROM = {"NDG": "NDG", "DENOMINAZIONE": "DENOMINAZIONE 1", "Filiale relazione": "Filiale relazione"}
DELIVERED_FILE = re.compile(r"(elenco|soggetti|gestionefidi|note)(\d*)\.png", re.IGNORECASE)
DELIVERED_PAGES = {"elenco": "Elenco", "soggetti": "Soggetti", "gestionefidi": "GestioneFidi", "note": "Note"}


def screen_name(file_name: str) -> str:
    """The screen a delivered file becomes, from its name alone: the first of a page takes the page name."""
    match = DELIVERED_FILE.fullmatch(file_name)
    if match is None:
        raise ValueError(f"File non riconosciuto: {file_name}.")
    page, number = DELIVERED_PAGES[match.group(1).casefold()], match.group(2)
    return page if number in ("", "1") else f"{page}{number}"


def _text(label: str, value: Any, where: str) -> str | None:
    """The value as the screen shows it, None for the literal marking an empty field."""
    if isinstance(value, (datetime, date)):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, (int, float)):
        if value != int(value):
            raise ValueError(f"Numero non intero in {where}: {value}.")
        return f"{int(value):,}".replace(",", ".") if label in AMOUNT_LABELS else str(int(value))
    text = " ".join(str(value).split())
    return None if text.casefold() == EMPTY_VALUE else text


def _note_text(value: Any) -> str:
    """The note as the screen shows it: pasting through Word turned the dash of its list lines into a bullet, or dropped it."""
    lines: list[str] = []
    among_guarantees = False
    for line in str(value).splitlines():
        stripped = line.strip()
        bare = NOTE_MARK.sub("", stripped)
        guarantee = among_guarantees and bare.startswith("Garanzia ")
        listed = bare != stripped or guarantee or bare.startswith(NOTE_LIST_LINES)
        among_guarantees = guarantee or bare.startswith("Sono presenti le garanzie")
        lines.append(f"- {bare}" if listed else stripped)
    return "\n".join(lines)


def _tooltip_display(value: str | None, codes: Mapping[str, str], outside: str) -> str:
    code = re.match(r"\d+", value or "")
    return codes.get(code.group(), outside) if code else outside


def _display(page: str, label: str, guarantee: int, value: str | None) -> str | None:
    """The name of a value in the truth: a CSV_TO_SCHEMA key, a name outside the vocabulary, None if unknown."""
    if page == "Elenco":
        return label if label in ELENCO_LABELS else None
    if page == "Soggetti":
        return label if SUBJECT_LABEL.fullmatch(label) else None
    if page == NOTE_PAGE:
        return NOTE_LABELS.get(label)
    if guarantee == 0:
        if label == LOAN_TOOLTIP:
            return _tooltip_display(value, LOAN_TOOLTIP_CODES, "Fido: tooltip Descrizione")
        return LOAN_LABELS.get(label)
    if label == GUARANTEE_TOOLTIP:
        return _tooltip_display(value, GUARANTEE_TOOLTIP_CODES, f"Garanzia {guarantee}: tooltip Descrizione")
    return f"Garanzia {guarantee}: {label}" if label in GUARANTEE_LABELS else None


def _record(practice: str, page: str, display: str, value: str | None, mapping: Mapping[str, str],
            excel_row: str | None) -> dict[str, Any]:
    outcome = "TRASCRITTO" if value is not None else "VUOTO"
    return {"screen": f"{practice}__{page}", "practice": practice, "page": page, "display_name": display,
            "field": mapping.get(display), "value": value, "outcome": outcome, "reviewer_status": outcome,
            "excel_row": excel_row, "correction": None}


def _read_sheet(sheet: Any, mapping: Mapping[str, str]) -> list[dict[str, Any]]:
    practice = sheet.title
    records: dict[str, dict[str, Any]] = {}
    pages: list[str] = []
    page = title = None
    guarantee = 0
    for number, (label_cell, value_cell) in enumerate(sheet.iter_rows(min_col=2, max_col=3), 1):
        where = f"{practice}!{number}"
        label = " ".join(str(label_cell.value or "").split())
        if not label:
            if value_cell.value is not None:
                raise ValueError(f"Valore senza campo in {where}.")
            continue
        if label in SECTION_TITLES and value_cell.value is None:
            title = SECTION_TITLES[label]
            continue
        if label == SECTION_HEADER:
            page, title = title or NOTE_PAGE, None
            pages.append(page)
            continue
        if page is None:
            raise ValueError(f"Campo non riconosciuto in {where}: {label}.")
        if value_cell.data_type == "f":
            raise ValueError(f"Il ground truth contiene una formula in {where}.")
        if value_cell.value is None or not str(value_cell.value).strip():
            raise ValueError(f"Campo senza valore in {where}: {label}.")
        value = _text(label, _note_text(value_cell.value) if label == NOTE_LABEL else value_cell.value, where)
        if page == "GestioneFidi" and label == GUARANTEE_START:
            guarantee += 1
        display = _display(page, label, guarantee, value)
        if display is None:
            raise ValueError(f"Campo non riconosciuto in {where}: {label}.")
        if display in records:
            raise ValueError(f"Campo doppio in {where}: {label}.")
        records[display] = _record(practice, page, display, value, mapping, where)
    if sorted(pages) != sorted(PAGES):
        raise ValueError(f"Le pagine del foglio {practice} non sono {PAGES}: {pages}.")
    required = [*ELENCO_LABELS, *LOAN_LABELS.values(), *NOTE_LABELS.values()]
    missing = [display for display in required if display not in records]
    if missing:
        raise ValueError(f"Mancano dei campi nel foglio {practice}: {missing}.")
    # What the sheet does not list is not on the page: a subject row the table lacks, a tooltip with no code of ours.
    for page_name, displays in (("Soggetti", SUBJECT_DISPLAYS), ("GestioneFidi", TOOLTIP_DISPLAYS)):
        for display in displays:
            if display not in records:
                records[display] = _record(practice, page_name, display, None, mapping, None)
    return list(records.values())


def _apply_corrections(records: list[dict[str, Any]], corrections: list[dict[str, Any]]) -> None:
    """Replace the values checked against the screen; each record keeps what the sheet said."""
    by_row = {record["excel_row"]: record for record in records if record["excel_row"]}
    for fix in corrections:
        record = by_row.get(fix["riga_excel"])
        if record is None:
            raise ValueError(f"Correzione senza riga nel workbook: {fix['riga_excel']}.")
        reviewed = fix["revisione"]
        if (record["display_name"], record["outcome"], record["value"]) != (fix["campo"], reviewed["esito"],
                                                                            reviewed["trascrizione"]):
            raise ValueError(f"La correzione della riga {fix['riga_excel']} non corrisponde al foglio.")
        corrected = fix["corretto"]
        record.update(value=corrected["trascrizione"], outcome=corrected["esito"],
                      reviewer_status=corrected["esito"], correction=fix)


def _page_of(screen: str) -> str:
    page = screen.rstrip("0123456789")
    if page not in PAGES:
        raise ValueError(f"Schermata di una pagina sconosciuta: {screen}.")
    return page


def _on_screens(practice: str, records: list[dict[str, Any]], screens: Mapping[str, Mapping[str, Any]],
                tipo: str | None, mapping: Mapping[str, str]) -> list[dict[str, Any]]:
    """The values of the pages as rows of each screen, following what was checked on that screen.

    A field of the page is on all its screens unless hidden there; a tooltip only on the screen that shows it.
    What is outside the vocabulary stays on the first screen of the page: it is kept, not looked for.
    The header of a detail screen is not listed by the reviewer: its rows are derived from the other pages, and teach
    the model without being measured. A screen hiding its branch is scrolled past the header and has none.
    """
    missing = [page for page in PAGES if page not in screens]
    if missing:
        raise ValueError(f"Manca la prima schermata delle pagine {missing} nella pratica {practice}.")
    reviewed = {record["display_name"]: record["value"] for record in records}
    header = {display: reviewed.get(source) for display, source in HEADER_FROM.items()}
    header["Tipo"] = tipo
    rows: list[dict[str, Any]] = []
    shown: set[str] = set()
    for name, view in screens.items():
        page = _page_of(name)
        values = [record for record in records if record["page"] == page]
        available = {record["display_name"] for record in values if record["value"] is not None}
        hidden, partial = set(view.get("non_visibili", ())), set(view.get("parziali", ()))
        tooltip = view.get("tooltip")
        unknown = sorted((hidden | partial | ({tooltip} if tooltip else set())) - available
                         - {record["display_name"] for record in values if record["display_name"] != tooltip})
        if unknown:
            raise ValueError(f"Campi senza valore nel foglio {practice} per la schermata {name}: {unknown}.")
        if tooltip:
            shown.add(tooltip)
        for record in values:
            display = record["display_name"]
            if not record["field"]:
                keep = name == page
            elif display in TOOLTIP_DISPLAYS:
                keep = display == tooltip
            else:
                keep = True
            if not keep:
                continue
            row = dict(record, screen=f"{practice}__{name}")
            if display in hidden:
                row.update(value=None, outcome="NON VISIBILE", reviewer_status="NON VISIBILE")
            elif display in partial:
                row.update(outcome="PARZIALE", reviewer_status="PARZIALE")
            rows.append(row)
        if page == "Elenco" or "Filiale relazione" in hidden:
            continue
        on_page = {record["display_name"] for record in values}
        for display, value in header.items():
            if value is not None and display not in on_page:
                rows.append(dict(_record(practice, page, display, value, mapping, None), screen=f"{practice}__{name}",
                                 outcome="DERIVATO", reviewer_status="DERIVATO"))
    lost = [record["display_name"] for record in records if record["display_name"] in TOOLTIP_DISPLAYS
            and record["value"] is not None and record["display_name"] not in shown]
    if lost:
        raise ValueError(f"Tooltip senza schermata nel foglio {practice}: {lost}.")
    return rows


def read_practice_sheets(path: Path, corrections_path: Path | None = None) -> list[dict[str, Any]]:
    """Read every practice sheet, refusing formulas, unknown labels and incomplete sheets.

    The corrections file holds what was checked against the screens: the corrected values, and for each practice
    whose screens may be looked at what every screen shows. A practice without screens there (a sealed one) keeps
    its values on the first screen of each page.
    """
    screens: Mapping[str, Mapping[str, Any]] = {}
    corrections: list[dict[str, Any]] = []
    tipos: Mapping[str, str] = {}
    if corrections_path is not None:
        recorded = json.loads(corrections_path.read_text(encoding="utf-8"))
        if recorded["workbook_sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError("Le correzioni si riferiscono a un altro workbook.")
        screens, corrections = recorded.get("schermate", {}), recorded.get("correzioni", [])
        tipos = recorded.get("tipo_pratica", {})
    mapping = vocabulary()[1]
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        records: list[dict[str, Any]] = []
        for sheet in workbook.worksheets:
            if sheet.title == DESCRIPTION_SHEET:
                continue
            if not PRACTICE_SHEET.fullmatch(sheet.title):
                raise ValueError(f"Foglio non riconosciuto: {sheet.title}.")
            records += _read_sheet(sheet, mapping)
    finally:
        workbook.close()
    if not records:
        raise ValueError("Il lotto non contiene pratiche.")
    _apply_corrections(records, corrections)
    result: list[dict[str, Any]] = []
    for practice in dict.fromkeys(record["practice"] for record in records):
        own = [record for record in records if record["practice"] == practice]
        result += (_on_screens(practice, own, screens[practice], tipos.get(practice), mapping)
                   if screens.get(practice) else own)
    return result
