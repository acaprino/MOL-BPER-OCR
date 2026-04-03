"""Canonical client page definitions and page-label resolution."""

from typing import Dict, Optional

CANONICAL_PAGE_NAMES: Dict[str, str] = {
    "risultato_ricerca": "Risultato ricerca",
    "elenco_soggetti": "Elenco Soggetti",
    "gestione_fidi_e_garanzie": "Gestione Fidi e Garanzie",
    "note_da_richiesta": "Note da Richiesta",
}

PAGE_NAME_ALIASES: Dict[str, str] = {
    "risultato ricerca": "risultato_ricerca",
    "risultato_ricerca": "risultato_ricerca",
    "elenco soggetti": "elenco_soggetti",
    "elenco_soggetti": "elenco_soggetti",
    "gestione fidi e garanzie": "gestione_fidi_e_garanzie",
    "gestione_fidi_e_garanzie": "gestione_fidi_e_garanzie",
    "note da richiesta": "note_da_richiesta",
    "note_da_richiesta": "note_da_richiesta",
}

PAGE_SHEET_ORDER = (
    "risultato_ricerca",
    "elenco_soggetti",
    "gestione_fidi_e_garanzie",
    "note_da_richiesta",
)


def normalize_page_label(label: str) -> str:
    """Normalize external page labels for stable lookup."""
    return " ".join(str(label).strip().lower().replace("_", " ").split())


def resolve_page_key(label: str) -> Optional[str]:
    """Resolve an external/raw page label to the internal canonical page key."""
    normalized = normalize_page_label(label)
    return PAGE_NAME_ALIASES.get(normalized)


def resolve_page_name(label: str) -> Optional[str]:
    """Resolve an external/raw page label to the canonical display name."""
    page_key = resolve_page_key(label)
    if page_key is None:
        return None
    return CANONICAL_PAGE_NAMES[page_key]

def get_canonical_page_name(page_key: str) -> Optional[str]:
    """Return the canonical client page display name for a page key."""
    return CANONICAL_PAGE_NAMES.get(page_key)
