"""Field key definitions and CSV-to-schema mappings."""
from typing import Dict, List

# ============================================================
# Target fields
# ============================================================
FIELD_KEYS: List[str] = [
    "ndg",
    "denominazione",
    "tipo",
    "stato",
    "fase",
    "creazione",
    "evidenze",
    "filiale_relazione",
    "n_fido",
    "rapporto",
    "descrizione",
    "scadenza",
    "importo_euro",
    "tipo_op",
    "note_della_richiesta",
    "tooltip_descrizione_bmb",
    "tooltip_evidenze_b",
    "tooltip_descrizione_m_consap",
    "tooltip_descrizione_consap_dr_bis",
    "tooltip_descrizione_ipoteca",
]

CSV_TO_SCHEMA: Dict[str, str] = {
    "NDG": "ndg",
    "Denom.": "denominazione",
    "Tipo": "tipo",
    "Stato": "stato",
    "Fase": "fase",
    "Creazione": "creazione",
    "Evidenze": "evidenze",
    "Evidenze ": "evidenze",
    "Filiale relazione": "filiale_relazione",
    "n° FIDO": "n_fido",
    "Rapporto": "rapporto",
    "Descrizione": "descrizione",
    "Scadenza": "scadenza",
    "Importo (€)": "importo_euro",
    "Tipo Op.": "tipo_op",
    "Note della richiesta": "note_della_richiesta",
    "tooltip su valore campo Descrizione: BMB": "tooltip_descrizione_bmb",
    "tooltip su valore campo Evidenze: B": "tooltip_evidenze_b",
    "tooltip su valore campo Descrizione (riga 1): M. CONSAP >= 80%": "tooltip_descrizione_m_consap",
    "tooltip su valore campo Descrizione (riga 1): CONSAP DR BIS": "tooltip_descrizione_consap_dr_bis",
    "tooltip su valore campo Descrizione (riga 2): IPOTECA I GR.": "tooltip_descrizione_ipoteca",
}

_SOGGETTI_KEY_MAP: Dict[str, str] = {
    "NDG": "ndg",
    "DENOMINAZIONE": "denominazione",
    "RUOLO": "ruolo"
}

_GARANZIE_KEY_MAP: Dict[str, str] = {
    "N° GAR": "n_gar",
    "DESCRIZIONE": "descrizione",
    "FIDO": "fido",
    "NDG": "ndg",
    "DENOMINAZIONE": "denominazione",
    "IMP. (€)/%": "importo_percentuale",
    "TIPO OP.": "tipo_op"
}
