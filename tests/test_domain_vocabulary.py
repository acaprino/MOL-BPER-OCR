"""The extraction catalogs must describe one complete field vocabulary."""

from collections import Counter

import extraction.config as config
from extraction.field_definitions import CANONICAL_FIELD_DEFINITIONS
from extraction.fields import CSV_TO_SCHEMA, FIELD_KEYS
from extraction.prompts import FIELD_RETRY_PROMPTS


def test_canonical_definitions_cover_the_field_vocabulary() -> None:
    assert set(CANONICAL_FIELD_DEFINITIONS) == set(FIELD_KEYS)


def test_csv_mappings_cover_the_field_vocabulary() -> None:
    assert set(CSV_TO_SCHEMA.values()) == set(FIELD_KEYS)


def test_every_field_has_exactly_one_retry_policy() -> None:
    assigned = Counter(
        field for fields in config.AREA_TO_FIELDS.values() for field in fields
    )
    assigned.update(getattr(config, "UNRETRIED_FIELDS", ()))

    assert assigned == Counter({field: 1 for field in FIELD_KEYS})


def test_only_the_five_tooltips_are_explicitly_unretried() -> None:
    assert getattr(config, "UNRETRIED_FIELDS", frozenset()) == frozenset({
        "tooltip_descrizione_bmb",
        "tooltip_evidenze_b",
        "tooltip_descrizione_m_consap",
        "tooltip_descrizione_consap_dr_bis",
        "tooltip_descrizione_ipoteca",
    })


def test_every_retry_area_has_an_image_crop() -> None:
    assert config.AREA_TO_FIELDS.keys() <= config.RETRY_AREAS.keys()


def test_every_retry_area_has_a_dedicated_prompt() -> None:
    assert config.AREA_TO_FIELDS.keys() <= FIELD_RETRY_PROMPTS.keys()
    for area in config.AREA_TO_FIELDS:
        assert FIELD_RETRY_PROMPTS[area].strip(), area
