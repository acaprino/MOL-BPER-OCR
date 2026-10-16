"""Actual source pages stay distinct from the legacy spreadsheet groups."""

import pytest

from extraction.canonical_mapping import build_canonical_field_entries
from extraction.fields import FIELD_KEYS, get_canonical_field_metadata
from extraction.page_definitions import resolve_page_key, resolve_page_name


PRIVATI_FIELDS = (
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
)


@pytest.mark.parametrize("schema_key", PRIVATI_FIELDS)
def test_privati_metadata_reports_its_actual_source_page(schema_key: str) -> None:
    metadata = get_canonical_field_metadata(schema_key)

    assert metadata["page_key"] == "scheda_privati"
    assert metadata["page_name"] == "Scheda Privati"


@pytest.mark.parametrize("schema_key", PRIVATI_FIELDS)
def test_privati_canonical_output_reports_its_actual_source_page(schema_key: str) -> None:
    entries = build_canonical_field_entries({
        schema_key: {"value": "letto", "confidence": 0.9}
    })

    assert entries[0]["page_key"] == "scheda_privati"
    assert entries[0]["page_name"] == "Scheda Privati"
    assert entries[0]["value"] == "letto"


def test_only_privati_fields_belong_to_the_privati_source_page() -> None:
    entries = build_canonical_field_entries({key: {} for key in FIELD_KEYS})

    assert {
        entry["schema_key"] for entry in entries if entry["page_key"] == "scheda_privati"
    } == set(PRIVATI_FIELDS)


@pytest.mark.parametrize("label", ["Scheda Privati", "scheda_privati", "  SCHEDA   PRIVATI "])
def test_privati_page_labels_resolve_to_the_actual_page(label: str) -> None:
    assert resolve_page_key(label) == "scheda_privati"
    assert resolve_page_name(label) == "Scheda Privati"


def test_request_notes_keep_their_own_source_page() -> None:
    metadata = get_canonical_field_metadata("note_della_richiesta")

    assert metadata["page_key"] == "note_da_richiesta"
    assert metadata["page_name"] == "Note da Richiesta"


def test_canonical_order_stays_compatible_when_source_pages_differ() -> None:
    entries = build_canonical_field_entries({
        "professione_principale": {}, "note_della_richiesta": {}, "ndg": {}, "dal": {}
    })

    assert [entry["schema_key"] for entry in entries] == [
        "ndg", "dal", "note_della_richiesta", "professione_principale"
    ]
