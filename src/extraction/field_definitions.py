"""Canonical client field definitions and field-label resolution."""

from typing import Dict, Optional

CANONICAL_FIELD_DEFINITIONS: Dict[str, Dict[str, str]] = {
    "ndg": {
        "display_name": "NDG",
        "page_key": "risultato_ricerca",
    },
    "denominazione": {
        "display_name": "DENOMINAZIONE",
        "page_key": "risultato_ricerca",
    },
    "tipo": {
        "display_name": "Tipo",
        "page_key": "risultato_ricerca",
    },
    "stato": {
        "display_name": "Stato",
        "page_key": "risultato_ricerca",
    },
    "fase": {
        "display_name": "Fase",
        "page_key": "risultato_ricerca",
    },
    "creazione": {
        "display_name": "Creazione",
        "page_key": "risultato_ricerca",
    },
    "evidenze": {
        "display_name": "Evidenze",
        "page_key": "risultato_ricerca",
    },
    "filiale_relazione": {
        "display_name": "Filiale relazione",
        "page_key": "risultato_ricerca",
    },
    "n_fido": {
        "display_name": "n° FIDO",
        "page_key": "gestione_fidi_e_garanzie",
    },
    "rapporto": {
        "display_name": "Rapporto",
        "page_key": "gestione_fidi_e_garanzie",
    },
    "descrizione": {
        "display_name": "Descrizione",
        "page_key": "gestione_fidi_e_garanzie",
    },
    "scadenza": {
        "display_name": "Scadenza",
        "page_key": "gestione_fidi_e_garanzie",
    },
    "importo_euro": {
        "display_name": "Importo (€)",
        "page_key": "gestione_fidi_e_garanzie",
    },
    "tipo_op": {
        "display_name": "Tipo Op.",
        "page_key": "gestione_fidi_e_garanzie",
    },
    "note_della_richiesta": {
        "display_name": "Note della richiesta",
        "page_key": "note_da_richiesta",
    },
    "ndg_1": {
        "display_name": "NDG 1",
        "page_key": "elenco_soggetti",
    },
    "denominazione_1": {
        "display_name": "DENOMINAZIONE 1",
        "page_key": "elenco_soggetti",
    },
    "ruolo_1": {
        "display_name": "RUOLO 1",
        "page_key": "elenco_soggetti",
    },
    "ndg_2": {
        "display_name": "NDG 2",
        "page_key": "elenco_soggetti",
    },
    "denominazione_2": {
        "display_name": "DENOMINAZIONE 2",
        "page_key": "elenco_soggetti",
    },
    "ruolo_2": {
        "display_name": "RUOLO 2",
        "page_key": "elenco_soggetti",
    },
    "ndg_3": {
        "display_name": "NDG 3",
        "page_key": "elenco_soggetti",
    },
    "denominazione_3": {
        "display_name": "DENOMINAZIONE 3",
        "page_key": "elenco_soggetti",
    },
    "ruolo_3": {
        "display_name": "RUOLO 3",
        "page_key": "elenco_soggetti",
    },
    "ndg_4": {
        "display_name": "NDG 4",
        "page_key": "elenco_soggetti",
    },
    "denominazione_4": {
        "display_name": "DENOMINAZIONE 4",
        "page_key": "elenco_soggetti",
    },
    "ruolo_4": {
        "display_name": "RUOLO 4",
        "page_key": "elenco_soggetti",
    },
    "dal": {
        "display_name": "DAL",
        "page_key": "scheda_privati",
        "export_group_key": "note_da_richiesta",
    },
    "datore_di_lavoro_anagrafica": {
        "display_name": "DATORE DI LAVORO ANAGRAFICA",
        "page_key": "scheda_privati",
        "export_group_key": "note_da_richiesta",
    },
    "di_cui_percepiscono_reddito": {
        "display_name": "Di cui percepiscono reddito",
        "page_key": "scheda_privati",
        "export_group_key": "note_da_richiesta",
    },
    "importo_totale_annuo_nucleo": {
        "display_name": "Importo totale annuo altri componenti nucleo familiare",
        "page_key": "scheda_privati",
        "export_group_key": "note_da_richiesta",
    },
    "note_scheda_privati": {
        "display_name": "Note Scheda Privati",
        "page_key": "scheda_privati",
        "export_group_key": "note_da_richiesta",
    },
    "nr_altri_componenti_nucleo": {
        "display_name": "Nr altri componenti nucleo familiare",
        "page_key": "scheda_privati",
        "export_group_key": "note_da_richiesta",
    },
    "numero_mensilita": {
        "display_name": "Numero mensilità",
        "page_key": "scheda_privati",
        "export_group_key": "note_da_richiesta",
    },
    "professione_principale": {
        "display_name": "Professione principale",
        "page_key": "scheda_privati",
        "export_group_key": "note_da_richiesta",
    },
    "rating_ufficiale": {
        "display_name": "RATING UFFICIALE",
        "page_key": "scheda_privati",
        "export_group_key": "note_da_richiesta",
    },
    "retribuzione_annua_netta": {
        "display_name": "Retribuzione annua netta",
        "page_key": "scheda_privati",
        "export_group_key": "note_da_richiesta",
    },
    "score_cgs": {
        "display_name": "SCORE CGS",
        "page_key": "scheda_privati",
        "export_group_key": "note_da_richiesta",
    },
    "tipo_contratto": {
        "display_name": "Tipo contratto",
        "page_key": "scheda_privati",
        "export_group_key": "note_da_richiesta",
    },
    "ultima_validazione_scheda": {
        "display_name": "Ultima validazione scheda privati",
        "page_key": "scheda_privati",
        "export_group_key": "note_da_richiesta",
    },
    "tooltip_descrizione_bmb": {
        "display_name": "tooltip su valore campo Descrizione: BMB",
        "page_key": "gestione_fidi_e_garanzie",
    },
    "tooltip_evidenze_b": {
        "display_name": "tooltip su valore campo Evidenze: B",
        "page_key": "risultato_ricerca",
    },
    "tooltip_descrizione_m_consap": {
        "display_name": "tooltip su valore campo Descrizione (riga 1): M. CONSAP >= 80%",
        "page_key": "gestione_fidi_e_garanzie",
    },
    "tooltip_descrizione_consap_dr_bis": {
        "display_name": "tooltip su valore campo Descrizione (riga 1): CONSAP DR BIS",
        "page_key": "gestione_fidi_e_garanzie",
    },
    "tooltip_descrizione_ipoteca": {
        "display_name": "tooltip su valore campo Descrizione (riga 2): IPOTECA I GR.",
        "page_key": "gestione_fidi_e_garanzie",
    },
}

FIELD_LABEL_ALIASES: Dict[str, str] = {
    "ndg": "ndg",
    "denominazione": "denominazione",
    "tipo": "tipo",
    "stato": "stato",
    "fase": "fase",
    "creazione": "creazione",
    "evidenze": "evidenze",
    "filiale relazione": "filiale_relazione",
    "n° fido": "n_fido",
    "rapporto": "rapporto",
    "descrizione": "descrizione",
    "scadenza": "scadenza",
    "importo (€)": "importo_euro",
    "tipo op.": "tipo_op",
    "note della richiesta": "note_della_richiesta",
    "dal": "dal",
    "datore di lavoro anagrafica": "datore_di_lavoro_anagrafica",
    "di cui percepiscono reddito": "di_cui_percepiscono_reddito",
    "importo totale annuo altri componenti nucleo familiare": "importo_totale_annuo_nucleo",
    "note scheda privati": "note_scheda_privati",
    "nr altri componenti nucleo familiare": "nr_altri_componenti_nucleo",
    "numero mensilità": "numero_mensilita",
    "professione principale": "professione_principale",
    "rating ufficiale": "rating_ufficiale",
    "retribuzione annua netta": "retribuzione_annua_netta",
    "score cgs": "score_cgs",
    "tipo contratto": "tipo_contratto",
    "ultima validazione scheda privati": "ultima_validazione_scheda",
    "ndg 1": "ndg_1",
    "denominazione 1": "denominazione_1",
    "ruolo 1": "ruolo_1",
    "ndg 2": "ndg_2",
    "denominazione 2": "denominazione_2",
    "ruolo 2": "ruolo_2",
    "ndg 3": "ndg_3",
    "denominazione 3": "denominazione_3",
    "ruolo 3": "ruolo_3",
    "ndg 4": "ndg_4",
    "denominazione 4": "denominazione_4",
    "ruolo 4": "ruolo_4",
    "tooltip su valore campo descrizione: bmb": "tooltip_descrizione_bmb",
    "tooltip su valore campo evidenze: b": "tooltip_evidenze_b",
    "tooltip su valore campo descrizione (riga 1): m. consap >= 80%": "tooltip_descrizione_m_consap",
    "tooltip su valore campo descrizione (riga 1): consap dr bis": "tooltip_descrizione_consap_dr_bis",
    "tooltip su valore campo descrizione (riga 2): ipoteca i gr.": "tooltip_descrizione_ipoteca",
    "denom.": "denominazione",
}


def normalize_field_label(label: str) -> str:
    """Normalize external field labels for stable lookup."""
    return " ".join(str(label).strip().lower().split())


def resolve_schema_key(label: str) -> Optional[str]:
    """Resolve an external/raw field label to the internal schema key."""
    normalized = normalize_field_label(label)
    return FIELD_LABEL_ALIASES.get(normalized)


def resolve_display_name(schema_key: str) -> Optional[str]:
    """Resolve an internal schema key to the canonical client display name."""
    definition = CANONICAL_FIELD_DEFINITIONS.get(schema_key)
    if definition is None:
        return None
    return definition["display_name"]


def resolve_field_page_key(schema_key: str) -> Optional[str]:
    """Resolve an internal schema key to the canonical client page key."""
    definition = CANONICAL_FIELD_DEFINITIONS.get(schema_key)
    if definition is None:
        return None
    return definition["page_key"]


def resolve_field_export_group_key(schema_key: str) -> Optional[str]:
    """Return the spreadsheet group, which can differ from the source page."""
    definition = CANONICAL_FIELD_DEFINITIONS.get(schema_key)
    if definition is None:
        return None
    return definition.get("export_group_key", definition["page_key"])
