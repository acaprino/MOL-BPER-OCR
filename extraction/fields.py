"""Field key definitions and CSV-to-schema mappings."""

from typing import Dict, List

# ============================================================
# Target fields
# ============================================================

FIELD_KEYS: List[str] = [
    "ndg",
    "denominazione",
    "tipo",
    "evidenze",
    "filiale_relazione",
    "ultima_validazione",
    "professione_principale",
    "numero_mensilita",
    "retribuzione_annua_netta",
    "tipo_contratto",
    "anagrafica",
    "dal",
    "rating_ufficiale",
    "score_cgs",
    "nr_altri_componenti_nucleo_familiare",
    "di_cui_percepiscono_reddito",
    "importo_totale_annuo_altri_componenti",
    "note",
]

CSV_TO_SCHEMA: Dict[str, str] = {
    "NDG": "ndg",
    "DENOMINAZIONE": "denominazione",
    "Tipo": "tipo",
    "Evidenze": "evidenze",
    "Filiale relazione": "filiale_relazione",
    "Ultima validazione": "ultima_validazione",
    "Professione principale": "professione_principale",
    "Numero mensilità": "numero_mensilita",
    "Retribuzione annua netta": "retribuzione_annua_netta",
    "Tipo contratto": "tipo_contratto",
    "ANAGRAFICA": "anagrafica",
    "DAL": "dal",
    "RATING UFFICIALE": "rating_ufficiale",
    "SCORE CGS": "score_cgs",
    "Nr altri componenti nucleo familiare": "nr_altri_componenti_nucleo_familiare",
    "Di cui percepiscono reddito": "di_cui_percepiscono_reddito",
    "Importo totale annuo altri componenti nucleo familiare": "importo_totale_annuo_altri_componenti",
    "Note": "note",
}

_SOGGETTI_KEY_MAP: Dict[str, str] = {
    "NDG": "ndg",
    "DENOMINAZIONE": "denominazione",
    "RUOLO": "ruolo",
}
