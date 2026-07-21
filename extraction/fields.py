"""Field key definitions and CSV-to-schema mappings."""
from typing import Dict, List, Optional
from extraction.field_definitions import (
    resolve_display_name,
    resolve_field_page_key,
)
from extraction.page_definitions import get_canonical_page_name

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

    # Soggetti piatti (per compatibilità CSV screen 2)
    "ndg_1", "denominazione_1", "ruolo_1",
    "ndg_2", "denominazione_2", "ruolo_2",
    "ndg_3", "denominazione_3", "ruolo_3",
    "ndg_4", "denominazione_4", "ruolo_4",

    # Nuovi campi screen 4 e 5
    "dal",
    "datore_di_lavoro_anagrafica",
    "di_cui_percepiscono_reddito",
    "importo_totale_annuo_nucleo",
    "note_scheda_privati",
    "nr_altri_componenti_nucleo",
    "numero_mensilita",
    "professione_principale",
    "rating_ufficiale",
    "retribuzione_annua_netta",
    "score_cgs",
    "tipo_contratto",
    "ultima_validazione_scheda",
]

CSV_TO_SCHEMA: Dict[str, str] = {
    "NDG": "ndg",
    "Denom.": "denominazione",
    "DENOMINAZIONE": "denominazione",
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

    # Mapping soggetti piatti
    "NDG 1": "ndg_1", "DENOMINAZIONE 1": "denominazione_1", "RUOLO 1": "ruolo_1",
    "NDG 2": "ndg_2", "DENOMINAZIONE 2": "denominazione_2", "RUOLO 2": "ruolo_2",
    "NDG 3": "ndg_3", "DENOMINAZIONE 3": "denominazione_3", "RUOLO 3": "ruolo_3",
    "NDG 4": "ndg_4", "DENOMINAZIONE 4": "denominazione_4", "RUOLO 4": "ruolo_4",

    # Mapping nuovi campi
    "DAL": "dal",
    "DATORE DI LAVORO ANAGRAFICA": "datore_di_lavoro_anagrafica",
    "Di cui percepiscono reddito": "di_cui_percepiscono_reddito",
    "Importo totale annuo altri componenti nucleo familiare": "importo_totale_annuo_nucleo",
    "Note Scheda Privati": "note_scheda_privati",
    "Nr altri componenti nucleo familiare": "nr_altri_componenti_nucleo",
    "Numero mensilità": "numero_mensilita",
    "Professione principale": "professione_principale",
    "RATING UFFICIALE": "rating_ufficiale",
    "Retribuzione annua netta": "retribuzione_annua_netta",
    "SCORE CGS": "score_cgs",
    "Tipo contratto": "tipo_contratto",
    "Ultima validazione scheda privati": "ultima_validazione_scheda",
}

def get_canonical_field_display_name(schema_key: str) -> str:
    """Return the canonical client display name for a schema key."""
    resolved = resolve_display_name(schema_key)
    return resolved or schema_key


def get_canonical_field_page_key(schema_key: str) -> Optional[str]:
    """Return the canonical client page key for a schema key, if known."""
    return resolve_field_page_key(schema_key)

def get_canonical_field_metadata(schema_key: str) -> Dict[str, Optional[str]]:
    """Return canonical backend metadata for a schema key."""
    display_name = get_canonical_field_display_name(schema_key)
    page_key = get_canonical_field_page_key(schema_key)
    page_name = get_canonical_page_name(page_key) if page_key else None
    return {
        "schema_key": schema_key,
        "display_name": display_name,
        "page_key": page_key,
        "page_name": page_name,
    }
