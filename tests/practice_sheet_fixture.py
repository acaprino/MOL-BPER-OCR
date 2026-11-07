"""A workbook shaped like a lot delivered as one sheet per practice, shared by the suites that read one."""

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

FIDI_TOOLTIP = "tooltip su valore campo Descrizione (tabella Fidi): "
GARANZIE_TOOLTIP = "tooltip su valore campo Descrizione (tabella Garanzie):"
SHEET: list[tuple[object, object]] = [
    (" Elenco", None), ("CAMPO RILEVATO", "Valori"),
    ("NDG", 60000001), ("DENOMINAZIONE", "ROSSI MARIO…"), ("Tipo", "BMB"), ("Stato", "APP"), ("Fase", "vuoto"),
    ("Creazione", datetime(2026, 9, 15)), ("Evidenze", "BC "),
    (None, None),
    ("Soggetti", None), ("CAMPO RILEVATO", "Valori"),
    ("NDG 1", 60000001), ("DENOMINAZIONE 1", "ROSSI MARIO,\nBIANCHI ANNA"), ("RUOLO 1", "Richiedente"),
    (None, None),
    ("Gestione fidi e garanzie", None), ("CAMPO RILEVATO", "Valori"),
    ("n° Fido", "F1"), ("Rapporto", "034 0230 0017 05000000"), ("Descrizione", "M.CONSAP >=80%"),
    (FIDI_TOOLTIP, "340176 - MUTUO FOND  PRIV  CONSAP  >=80%"),
    ("Scadenza", datetime(2056, 10, 15)), ("Importo (€)", 125000), ("Tipo Op.", "Nuova Finanza"),
    ("n° Gar.", "G1"), ("Descrizione", "IPOTECA I GR"), ("Fido", "F1"), ("NDG", "6000002 \n6000003 "),
    ("Denominazione", "ROSSI MARI\nBIANCHI AN"), ("Imp (€)%", 225000), ("Tipo Op.", "Nuova"),
    (GARANZIE_TOOLTIP, "55-IPOTECA DI PRIMO GRADO"),
    ("n° Gar.", "G2"), ("Descrizione", "CONSAP DR BIS"), ("Fido", "F1"), ("NDG", 11153238),
    ("Denominazione", "FONDO DI G"), ("Imp (€)%", "80.00"), ("Tipo Op.", "Nuova"),
    (GARANZIE_TOOLTIP, "457-IMP. FID. F.DO 1 CASA DR SOSTEGNI BIS "),
    (None, None),
    ("CAMPO RILEVATO", "Esempio valori"),
    ("Note della richiesta", "Numero Finanziamento FICS: 017/5000000\nNumero proposta DESK: N.D."),
    ("Filiale", "230 - BO XXI APRIL"), ("Agente proponente", "Anna Verdi"),
]


def write_sheets(path: Path, practices: dict[str, list[tuple[object, object]]]) -> Path:
    """Save a workbook with the description sheet and one sheet per practice."""
    workbook = Workbook()
    workbook.active.title = "Descrizione"
    workbook.active.append(["Elenco", "Soggetti"])
    for practice, rows in practices.items():
        sheet = workbook.create_sheet(practice)
        for label, value in rows:
            sheet.append([None, label, value])
    workbook.save(path)
    return path
