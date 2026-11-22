"""Behavioral checks for strict evaluation of the reviewed training corpus."""

from typing import Any

import pytest

from training.evaluation import (
    classify_value,
    decode_fields,
    evaluate_field_values,
    evaluate_predictions,
    word_metrics,
)


def _word(text: str, x: int, y: int, row: int = 0) -> dict[str, Any]:
    return {"text": text, "bbox": [x, y, x + 30, y + 10], "row": row}


def _example(
    words: list[dict[str, Any]], labels: list[str], values: dict[str, str | None],
    split: str = "test", example_id: str = "screen",
) -> dict[str, Any]:
    return {
        "id": example_id, "practice": "practice", "split": split,
        "image_size": [1000, 1000], "words": words, "labels": labels,
        "values": values,
    }


@pytest.mark.parametrize("field", ["ndg", "ndg_4"])
def test_wrong_ndg_digit_is_wrong(field: str) -> None:
    assert classify_value(field, "21310900", "21310908") == "wrong"


def test_ndg_suffix_is_part_of_identity() -> None:
    assert classify_value("ndg", "12345/A", "12345/B") == "wrong"


def test_numeric_ndg_leading_zeros_do_not_change_identity() -> None:
    assert classify_value("ndg", "0012345", "12.345") == "correct"


def test_long_account_wrong_digit_is_wrong() -> None:
    assert classify_value("rapporto", "1234/123456789012345678", "1234/123456789012345679") == "wrong"


def test_loan_number_prefix_is_part_of_identity() -> None:
    assert classify_value("n_fido", "F1", "G1") == "wrong"


def test_visible_nd_literal_is_a_value() -> None:
    assert classify_value("rating_ufficiale", "N/D", None) == "missing"


def test_visible_nd_literal_is_correct_when_read() -> None:
    assert classify_value("rating_ufficiale", "N/D", "N/D") == "correct"


def test_empty_ground_truth_does_not_accept_visible_nd_literal() -> None:
    assert classify_value("rating_ufficiale", None, "N/D") == "hallucinated"


def test_italian_amount_preserves_thousands() -> None:
    assert classify_value("importo_euro", "18.000", "18000,00") == "correct"


def test_amount_sign_changes_the_value() -> None:
    assert classify_value("importo_euro", "-18.000", "18.000") == "wrong"


def test_names_accept_layout_whitespace() -> None:
    assert classify_value("denominazione", "ZHENG LINA", "zheng\nLINA") == "correct"


def test_long_name_does_not_get_fuzzy_credit() -> None:
    assert classify_value("denominazione", "HETTIARACHCHIGE MENISHA", "HETTIARACHCHIGE MENISKA") == "wrong"


@pytest.mark.parametrize(
    ("field", "expected", "predicted"),
    [
        ("filiale_relazione", "3281-X", "3281 - X"),
        ("tipo", "BPI/Mutui", "BPI / Mutui"),
        ("denominazione", "LUCIAC ...", "LUCIAC..."),
        ("denominazione", "ZHENG LINA,CHEN WEIHUA", "ZHENG LINA, CHEN WEIHUA"),
    ],
)
def test_spacing_next_to_existing_punctuation_is_equivalent(
    field: str, expected: str, predicted: str,
) -> None:
    assert classify_value(field, expected, predicted) == "correct"


def test_punctuation_normalization_does_not_merge_name_words() -> None:
    assert classify_value("denominazione", "KOLA ALTIN", "KOLAALTIN") == "wrong"


def test_missing_punctuation_is_not_spacing_equivalence() -> None:
    assert classify_value("filiale_relazione", "145 - PR S LAZZARO", "145 PR S LAZZARO") == "wrong"


def test_scalar_words_decode_in_visual_reading_order() -> None:
    example = _example(
        [_word("LINA", 70, 20), _word("ZHENG", 10, 20)],
        ["denominazione", "denominazione"], {"denominazione": "ZHENG LINA"},
    )
    assert decode_fields(example, example["labels"]) == {"denominazione": "ZHENG LINA"}


def test_wrapped_subject_role_stays_with_its_subject() -> None:
    example = _example(
        [
            _word("101", 0, 10, 0), _word("ALFA", 50, 10, 0),
            _word("Richiedente", 200, 10, 0), _word("202", 0, 35, 1),
            _word("BETA", 50, 35, 1), _word("Nuovo", 200, 35, 1),
            _word("Garante", 200, 47, 2),
        ],
        ["sogg_ndg", "sogg_denominazione", "sogg_ruolo", "sogg_ndg",
         "sogg_denominazione", "sogg_ruolo", "sogg_ruolo"], {},
    )
    assert decode_fields(example, example["labels"]) == {
        "ndg_1": "101", "denominazione_1": "ALFA", "ruolo_1": "Richiedente",
        "ndg_2": "202", "denominazione_2": "BETA", "ruolo_2": "Nuovo Garante",
    }


def test_unpredicted_subject_identifiers_preserve_later_row_numbers() -> None:
    example = _example(
        [
            _word("108", 0, 10), _word("ALFA", 50, 10),
            _word("Richiedente", 200, 10), _word("208", 0, 40),
            _word("BETA", 50, 40), _word("Garante", 200, 40),
            _word("303", 0, 70), _word("GAMMA", 50, 70),
            _word("Garante", 200, 70),
        ],
        ["IGNORE", "sogg_denominazione", "sogg_ruolo", "O",
         "sogg_denominazione", "sogg_ruolo", "sogg_ndg",
         "sogg_denominazione", "sogg_ruolo"],
        {"ndg_1": "106", "ndg_2": "206", "ndg_3": "303"},
    )
    assert decode_fields(example, example["labels"]) == {
        "denominazione_1": "ALFA", "ruolo_1": "Richiedente",
        "denominazione_2": "BETA", "ruolo_2": "Garante",
        "ndg_3": "303", "denominazione_3": "GAMMA", "ruolo_3": "Garante",
    }


def test_wrapped_subject_name_stays_before_the_next_row_marker() -> None:
    example = _example(
        [
            _word("108", 0, 10), _word("ALFA", 50, 10),
            _word("Richiedente", 200, 10), _word("LUNGA", 50, 27),
            _word("202", 0, 40), _word("BETA", 50, 40),
            _word("Garante", 200, 40),
        ],
        ["O", "sogg_denominazione", "sogg_ruolo", "sogg_denominazione",
         "sogg_ndg", "sogg_denominazione", "sogg_ruolo"], {},
    )
    assert decode_fields(example, example["labels"])["denominazione_1"] == "ALFA LUNGA"


def test_first_line_of_a_wrapped_cell_stays_in_the_row_of_its_centered_identifier() -> None:
    example = _example(
        [
            _word("101", 0, 10), _word("ALFA", 50, 10), _word("Richiedente", 200, 10),
            _word("FONDO", 50, 24), _word("Nuovo", 200, 24), _word("202", 0, 30),
            _word("CASA", 50, 36), _word("Pegno", 200, 36),
        ],
        ["sogg_ndg", "sogg_denominazione", "sogg_ruolo", "sogg_denominazione", "sogg_ruolo",
         "sogg_ndg", "sogg_denominazione", "sogg_ruolo"], {},
    )
    assert decode_fields(example, example["labels"]) == {
        "ndg_1": "101", "denominazione_1": "ALFA", "ruolo_1": "Richiedente",
        "ndg_2": "202", "denominazione_2": "FONDO CASA", "ruolo_2": "Nuovo Pegno",
    }


def _header_example(line: list[tuple[str, int, str]]) -> dict[str, Any]:
    """A detail screen: the practice number and the proposer above, the header line below."""
    words = [_word("52032077", 300, 10), _word("SEBASTIANO", 400, 10)]
    words += [_word(word, x, 30) for word, x, _ in line]
    return _example(words, ["ndg", "denominazione", *[role for *_, role in line]], {})


def test_header_ndg_is_read_after_its_label() -> None:
    example = _header_example([("NDG:", 0, "O"), ("32661219", 40, "ndg"), ("-", 80, "O"), ("GRECO", 100, "O")])
    assert decode_fields(example, example["labels"])["ndg"] == "32661219"


def test_header_name_is_read_after_the_dash_of_its_line() -> None:
    example = _header_example([("NDG:", 0, "O"), ("32661219", 40, "ndg"), ("-", 80, "O"), ("GRECO", 100, "O"),
                               ("ALESSANDRO", 140, "O")])
    assert decode_fields(example, example["labels"])["denominazione"] == "GRECO ALESSANDRO"


def test_header_line_without_a_dash_keeps_the_predicted_name() -> None:
    example = _header_example([("NDG:", 0, "O"), ("32661219", 40, "ndg")])
    assert decode_fields(example, example["labels"])["denominazione"] == "SEBASTIANO"


def test_words_above_the_first_subject_row_stay_out() -> None:
    example = _example(
        [_word("ANDREA", 50, 0), _word("101", 0, 30), _word("ALFA", 50, 30)],
        ["sogg_denominazione", "sogg_ndg", "sogg_denominazione"], {},
    )
    assert decode_fields(example, example["labels"])["denominazione_1"] == "ALFA"


def test_header_name_without_a_predicted_ndg_keeps_its_words() -> None:
    example = _example(
        [_word("LODI", 300, 10), _word("ROSSI", 100, 30)], ["denominazione", "denominazione"], {},
    )
    assert decode_fields(example, example["labels"])["denominazione"] == "LODI ROSSI"


def test_subject_rows_decode_without_any_predicted_identifier() -> None:
    example = _example(
        [_word("ALFA", 50, 10), _word("Richiedente", 200, 10),
         _word("BETA", 50, 40), _word("Garante", 200, 40)],
        ["sogg_denominazione", "sogg_ruolo", "sogg_denominazione", "sogg_ruolo"], {},
    )
    assert decode_fields(example, example["labels"]) == {
        "denominazione_1": "ALFA", "ruolo_1": "Richiedente",
        "denominazione_2": "BETA", "ruolo_2": "Garante",
    }


FIDI_HEADER = (("N\u00ba", 10), ("Fido", 45), ("Rapporto", 90), ("Descrizione", 190), ("Scadenza", 290),
               ("Importo(\u20ac)", 390), ("Tipo", 490), ("Op.", 525), ("N\u00ba", 600), ("Fido", 635))


def _fidi_example(row: list[tuple[str, int, int, str]], header: tuple[tuple[str, int], ...] = FIDI_HEADER) -> dict[str, Any]:
    """The header of the two tables side by side, and the words of a row with their predicted roles."""
    words = [_word(word, x, 100) for word, x in header] + [_word(word, x, y) for word, x, y, _ in row]
    return _example(words, ["O"] * len(header) + [role for *_, role in row], {})


def _decoded_row(row: list[tuple[str, int, int, str]]) -> dict[str, str]:
    example = _fidi_example([("F1", 10, 130, "n_fido"), *row])
    return decode_fields(example, example["labels"])


def test_fidi_word_takes_the_role_of_the_column_it_stands_in() -> None:
    fields = _decoded_row([("15/10/2056", 290, 130, "importo_euro"), ("129.000", 390, 130, "importo_euro")])
    assert (fields["scadenza"], fields["importo_euro"]) == ("15/10/2056", "129.000")


def test_wrapped_fidi_cell_keeps_the_words_predicted_elsewhere() -> None:
    fields = _decoded_row([("M.F.", 170, 125, "descrizione"), ("PF", 205, 125, "tipo_op"), ("FONDO", 190, 135, "O")])
    assert fields["descrizione"] == "M.F. PF FONDO"


def test_fidi_word_of_the_table_on_the_right_stays_out() -> None:
    fields = _decoded_row([("Nuova", 490, 130, "tipo_op"), ("F9", 600, 130, "tipo_op")])
    assert fields["tipo_op"] == "Nuova"


def test_empty_fidi_cell_stays_empty() -> None:
    fields = _decoded_row([("Nuova", 490, 130, "rapporto")])
    assert "rapporto" not in fields


def test_tooltip_under_a_fidi_row_stays_out_of_its_cells() -> None:
    fields = _decoded_row([("Nuova", 490, 130, "tipo_op"), ("MUTUO", 490, 145, "tipo_op")])
    assert fields["tipo_op"] == "Nuova"


def test_next_fidi_row_stays_out_of_the_cells() -> None:
    fields = _decoded_row([("100", 390, 130, "importo_euro"), ("F2", 10, 141, "n_fido"), ("200", 390, 141, "importo_euro")])
    assert fields["importo_euro"] == "100"


def test_account_wider_than_its_header_keeps_its_first_word() -> None:
    fields = _decoded_row([("034", 50, 130, "rapporto"), ("0017", 90, 130, "rapporto")])
    assert fields["rapporto"] == "034 0017"


def test_tooltip_close_under_a_fidi_row_stays_out_of_its_cells() -> None:
    fields = _decoded_row([("Nuova", 490, 130, "tipo_op"), ("MUTUO", 490, 142, "tipo_op")])
    assert fields["tipo_op"] == "Nuova"


def _misread(*changes: tuple[str, str]) -> tuple[tuple[str, int], ...]:
    names = dict(changes)
    return tuple((names.get(word, word), x) for word, x in FIDI_HEADER)


@pytest.mark.parametrize("change", [("Descrizione", "Deacrizione"), ("Tipo", "T\u00edpo"), ("Scadenza", "Scadeuza")])
def test_header_word_misread_by_the_ocr_still_names_its_column(change: tuple[str, str]) -> None:
    example = _fidi_example([("F1", 10, 130, "n_fido"), ("15/10/2056", 290, 130, "importo_euro")], _misread(change))
    assert decode_fields(example, example["labels"])["scadenza"] == "15/10/2056"


def test_misread_label_of_the_last_header_does_not_narrow_its_column() -> None:
    example = _fidi_example([("F1", 10, 130, "n_fido"), ("Finanza", 530, 130, "tipo_op")], _misread(("Op.", "0p.")))
    assert decode_fields(example, example["labels"])["tipo_op"] == "Finanza"


def test_fidi_roles_stand_without_the_header_of_the_table_on_the_right() -> None:
    header = tuple(item for item in FIDI_HEADER if item[1] < 600)
    example = _fidi_example([("F1", 10, 130, "n_fido"), ("15/10/2056", 290, 130, "importo_euro")], header)
    assert decode_fields(example, example["labels"])["importo_euro"] == "15/10/2056"


def test_fido_number_of_the_guarantee_table_reads_no_cells() -> None:
    example = _fidi_example([("F1", 240, 130, "n_fido"), ("15/10/2056", 290, 130, "importo_euro")])
    assert decode_fields(example, example["labels"])["importo_euro"] == "15/10/2056"


def test_fidi_roles_stand_when_the_header_was_not_read_whole() -> None:
    header = tuple(item for item in FIDI_HEADER if item[0] != "Scadenza")
    example = _fidi_example([("F1", 10, 130, "n_fido"), ("15/10/2056", 290, 130, "importo_euro")], header)
    assert decode_fields(example, example["labels"])["importo_euro"] == "15/10/2056"


def test_fidi_fields_decode_from_the_first_table_row_only() -> None:
    example = _example(
        [_word("F1", 0, 40), _word("159.431", 200, 40),
         _word("F2", 0, 72), _word("70.000", 200, 72)],
        ["n_fido", "importo_euro", "n_fido", "importo_euro"], {},
    )
    assert decode_fields(example, example["labels"]) == {"n_fido": "F1", "importo_euro": "159.431"}


def test_wrapped_fidi_cell_stays_with_its_row() -> None:
    example = _example(
        [_word("F1", 0, 40), _word("034", 50, 34), _word("05518084", 50, 48),
         _word("F2", 0, 72), _word("034", 50, 66), _word("05672856", 50, 80)],
        ["n_fido", "rapporto", "rapporto", "n_fido", "rapporto", "rapporto"], {},
    )
    assert decode_fields(example, example["labels"])["rapporto"] == "034 05518084"


def test_fidi_row_ends_at_an_unpredicted_next_fido_number() -> None:
    example = _example(
        [_word("F1", 0, 40), _word("159.431", 200, 40),
         _word("F2", 0, 72), _word("70.000", 200, 72)],
        ["n_fido", "importo_euro", "O", "importo_euro"], {},
    )
    assert decode_fields(example, example["labels"])["importo_euro"] == "159.431"


def test_missing_subject_four_is_correctly_empty() -> None:
    example = _example(
        [_word("21310900", 0, 10)], ["sogg_ndg"],
        {"ndg_1": "21310900", "ndg_4": None},
    )
    report = evaluate_predictions([example], {"screen": {"pred": example["labels"]}})
    assert report["by_field"]["ndg_4"]["counts"] == {"correct_null": 1}


def test_prediction_for_reviewed_blank_is_hallucinated() -> None:
    example = _example([_word("P", 0, 10)], ["O"], {"evidenze": None})
    report = evaluate_predictions([example], {"screen": {"pred": ["evidenze"]}})
    assert report["by_field"]["evidenze"]["counts"] == {"hallucinated": 1}


def test_only_reviewed_fields_enter_the_field_denominator() -> None:
    example = _example([_word("101", 0, 10)], ["ndg"], {"ndg": "101"})
    report = evaluate_predictions([example], {"screen": {"pred": ["ndg"]}})
    assert report["overall"]["total"] == 1


def test_unavailable_ocr_value_remains_in_end_to_end_denominator() -> None:
    example = _example([_word("108", 0, 10)], ["IGNORE"], {"ndg": "106"})
    example["field_alignment"] = {"ndg": {"status": "ocr_mismatch"}}
    report = evaluate_predictions([example], {"screen": {"pred": ["ndg"]}})
    assert report["overall"]["counts"] == {"wrong": 1}


def test_field_without_heldout_examples_reports_zero_coverage() -> None:
    example = _example([_word("13", 0, 10)], ["numero_mensilita"], {"numero_mensilita": "13"}, split="train")
    report = evaluate_predictions([example], {"screen": {"pred": ["numero_mensilita"]}})
    assert report["by_split"]["test"]["by_field"]["numero_mensilita"]["total"] == 0
    assert report["by_split"]["test"]["by_field"]["numero_mensilita"]["accuracy"] is None


def test_role_without_heldout_examples_reports_zero_support() -> None:
    example = _example([_word("13", 0, 10)], ["numero_mensilita"], {"numero_mensilita": "13"}, split="train")
    report = evaluate_predictions([example], {"screen": {"pred": ["numero_mensilita"]}})
    score = report["by_split"]["test"]["word_metrics"]["by_role"]["numero_mensilita"]
    assert score["support"] == 0
    assert score["f1"] is None


def test_content_ceiling_separates_blank_fields_from_missing_ocr() -> None:
    example = _example([_word("108", 0, 10)], ["IGNORE"], {"ndg": "106", "ndg_4": None})
    example["field_alignment"] = {"ndg": {"status": "ocr_mismatch"}}
    report = evaluate_predictions([example], {"screen": {"pred": ["ndg"]}})
    availability = report["overall"]["content_availability"]
    assert availability["rate"] == 0.5
    assert availability["non_null_rate"] == 0.0


def test_fuzzy_location_does_not_count_as_available_content() -> None:
    example = _example([_word("108", 0, 10)], ["IGNORE"], {"ndg": "106"})
    example["field_alignment"] = {"ndg": {"status": "aligned", "exact_text": False}}
    report = evaluate_predictions([example], {"screen": {"pred": ["ndg"]}})
    assert report["overall"]["content_availability"]["non_null_rate"] == 0.0


def test_missing_screen_prediction_counts_as_missing_values() -> None:
    example = _example([_word("101", 0, 10)], ["ndg"], {"ndg": "101"})
    report = evaluate_predictions([example], {})
    assert report["overall"]["counts"] == {"missing": 1}
    assert report["missing_predictions"] == ["screen"]


def test_word_f1_ignores_uncertain_words() -> None:
    example = _example(
        [_word("101", 0, 0), _word("106", 40, 0), _word("Label", 80, 0)],
        ["ndg", "IGNORE", "O"], {"ndg": "101"},
    )
    result = word_metrics([example], {"screen": {"pred": ["ndg", "denominazione", "O"]}})
    assert result["micro"]["f1"] == 1.0
    assert result["ignored_words"] == 1


def test_word_f1_counts_false_positive_on_background() -> None:
    example = _example([_word("Label", 0, 0)], ["O"], {})
    result = word_metrics([example], {"screen": {"pred": ["ndg"]}})
    assert result["by_role"]["ndg"]["fp"] == 1


def test_prediction_length_mismatch_is_rejected() -> None:
    example = _example([_word("101", 0, 0)], ["ndg"], {"ndg": "101"})
    with pytest.raises(ValueError, match="length"):
        decode_fields(example, [])


def test_missing_screen_role_prediction_marks_report_incomplete() -> None:
    example = _example([_word("101", 0, 10)], ["ndg"], {"ndg": "101"})
    assert evaluate_predictions([example], {})["complete"] is False


def test_role_predictions_for_every_screen_mark_report_complete() -> None:
    example = _example([_word("101", 0, 10)], ["ndg"], {"ndg": "101"})
    assert evaluate_predictions([example], {"screen": {"pred": ["ndg"]}})["complete"] is True


def test_field_values_use_the_strict_comparator() -> None:
    example = _example(
        [_word("3281", 0, 10), _word("21310908", 0, 40)], ["O", "O"],
        {"filiale_relazione": "3281-X", "ndg": "21310900"},
    )
    report = evaluate_field_values(
        [example], {"screen": {"fields": {"filiale_relazione": "3281 - X", "ndg": "21310908"}}},
    )
    assert report["overall"]["counts"] == {"correct": 1, "wrong": 1}


def test_field_values_score_like_the_same_fields_decoded_from_roles() -> None:
    example = _example(
        [_word("101", 0, 10), _word("ALFA", 50, 10), _word("Richiedente", 200, 10),
         _word("202", 0, 40), _word("BETA", 50, 40), _word("Garante", 200, 40)],
        ["sogg_ndg", "sogg_denominazione", "sogg_ruolo", "sogg_ndg", "sogg_denominazione", "sogg_ruolo"],
        {"ndg_1": "101", "denominazione_1": "ALFA", "ruolo_1": "Garante",
         "ndg_2": "202", "denominazione_2": "BETA", "ruolo_2": "Garante", "ndg_3": None},
    )
    by_roles = evaluate_predictions([example], {"screen": {"pred": example["labels"]}})
    by_fields = evaluate_field_values([example], {"screen": {"fields": {
        "ndg_1": "101", "denominazione_1": "ALFA", "ruolo_1": "Richiedente",
        "ndg_2": "202", "denominazione_2": "BETA", "ruolo_2": "Garante",
    }}})
    assert by_fields["overall"]["counts"] == {"correct": 5, "wrong": 1, "correct_null": 1}
    assert by_fields["by_field"] == by_roles["by_field"]


def test_field_value_report_lists_every_screen_without_an_outcome() -> None:
    first = _example([_word("101", 0, 10)], ["ndg"], {"ndg": "101"}, example_id="a")
    second = _example([_word("202", 0, 10)], ["ndg"], {"ndg": "202"}, example_id="b")
    report = evaluate_field_values([first, second], {"a": {"fields": {"ndg": "101"}}})
    assert report["complete"] is False
    assert report["missing_predictions"] == ["b"]
    assert report["overall"]["counts"] == {"correct": 1, "missing": 1}


def test_field_values_for_every_screen_mark_report_complete() -> None:
    example = _example([_word("101", 0, 10)], ["ndg"], {"ndg": "101"})
    assert evaluate_field_values([example], {"screen": {"fields": {}}})["complete"] is True


def test_abstained_field_scores_as_absent() -> None:
    example = _example([_word("101", 0, 10)], ["ndg"], {"ndg": "101", "evidenze": None})
    report = evaluate_field_values([example], {"screen": {"fields": {}, "abstained": ["ndg", "evidenze"]}})
    assert report["overall"]["counts"] == {"missing": 1, "correct_null": 1}


def test_abstentions_are_counted_per_field() -> None:
    example = _example([_word("101", 0, 10)], ["ndg"], {"ndg": "101", "evidenze": None})
    report = evaluate_field_values([example], {"screen": {"fields": {}, "abstained": ["ndg"]}})
    assert report["by_field"]["ndg"]["abstained"] == 1
    assert report["by_field"]["evidenze"]["abstained"] == 0


def test_ocr_availability_ignores_the_predicted_field_values() -> None:
    example = _example([_word("108", 0, 10)], ["IGNORE"], {"ndg": "106"})
    example["field_alignment"] = {"ndg": {"status": "ocr_mismatch"}}
    report = evaluate_field_values([example], {"screen": {"fields": {"ndg": "106"}}})
    assert report["overall"]["counts"] == {"correct": 1}
    assert report["overall"]["content_availability"]["non_null_available"] == 0


def test_word_metrics_are_not_reported_for_field_values() -> None:
    example = _example([_word("101", 0, 10)], ["ndg"], {"ndg": "101"})
    report = evaluate_field_values([example], {"screen": {"fields": {"ndg": "101"}}})
    assert report["word_metrics"] is None
    assert report["by_split"]["test"]["word_metrics"] is None


@pytest.mark.parametrize(
    ("predictions", "message"),
    [
        ({"other": {"fields": {}}}, "unknown screen"),
        ({"screen": {"ndg": "101"}}, "fields"),
        ({"screen": {"fields": {"ndg": ""}}}, "empty"),
        ({"screen": {"fields": {"ndg": 101}}}, "string or None"),
        ({"screen": {"fields": {"codice_inventato": "1"}}}, "unknown field"),
        ({"screen": {"fields": {"ndg": "101"}, "abstained": ["ndg"]}}, "abstained"),
        ({"screen": {"fields": {}, "abstained": ["codice_inventato"]}}, "unknown field"),
        ({"screen": {"fields": {}, "notes": "x"}}, "unexpected key"),
    ],
)
def test_malformed_field_predictions_are_rejected(predictions: dict[str, Any], message: str) -> None:
    example = _example([_word("101", 0, 10)], ["ndg"], {"ndg": "101"})
    with pytest.raises(ValueError, match=message):
        evaluate_field_values([example], predictions)


# ============================================================
# The Soggetti table read by column
# ============================================================

SUBJECT_HEADER = (("NDG", 0), ("Denominazione", 50), ("Ruolo", 200), ("Fase", 350))


def _subject_table(row: list[tuple[str, int, int, str]], header: tuple[tuple[str, int], ...] = SUBJECT_HEADER) -> dict[str, str]:
    """Decode a page with the table header at y=100 and the given words with their predicted roles."""
    words = [_word(word, x, 100) for word, x in header] + [_word(word, x, y) for word, x, y, _ in row]
    example = _example(words, ["O"] * len(header) + [role for *_, role in row], {})
    return decode_fields(example, example["labels"])


def test_subject_cell_is_read_under_its_header_whatever_role_the_model_gave() -> None:
    fields = _subject_table([("101", 0, 130, "sogg_ndg"), ("ALFA", 50, 130, "sogg_denominazione"), ("Cointestato", 200, 130, "O")])
    assert fields["ruolo_1"] == "Cointestato"


def test_subject_word_in_the_wrong_column_takes_the_column_of_its_position() -> None:
    fields = _subject_table([("101", 0, 130, "sogg_ndg"), ("ALFA", 50, 130, "sogg_ruolo"), ("Garante", 200, 130, "sogg_denominazione")])
    assert (fields["denominazione_1"], fields["ruolo_1"]) == ("ALFA", "Garante")


def test_word_left_of_the_subject_table_stays_out() -> None:
    fields = _subject_table([("DANIELE", -100, 130, "sogg_denominazione"), ("101", 0, 130, "sogg_ndg"), ("ALFA", 50, 130, "sogg_denominazione")])
    assert fields["denominazione_1"] == "ALFA"


def test_wrapped_subject_cells_keep_both_lines_in_their_row() -> None:
    fields = _subject_table([("101", 0, 130, "sogg_ndg"), ("ALFA", 50, 130, "sogg_denominazione"),
                             ("FONDO", 50, 150, "sogg_denominazione"), ("Nuovo", 200, 150, "sogg_ruolo"), ("202", 0, 156, "sogg_ndg"),
                             ("CASA", 50, 162, "sogg_denominazione"), ("Pegno", 200, 162, "sogg_ruolo")])
    assert (fields["denominazione_2"], fields["ruolo_2"]) == ("FONDO CASA", "Nuovo Pegno")


def test_identifier_the_model_missed_still_opens_its_row() -> None:
    fields = _subject_table([("101", 0, 130, "sogg_ndg"), ("ALFA", 50, 130, "sogg_denominazione"), ("202", 0, 155, "O"), ("BETA", 50, 155, "O")])
    assert (fields["ndg_2"], fields["denominazione_2"]) == ("202", "BETA")


def test_button_under_the_subject_table_stays_out() -> None:
    fields = _subject_table([("101", 0, 130, "sogg_ndg"), ("Garante", 200, 130, "sogg_ruolo"), ("Avvia", 200, 170, "sogg_ruolo")])
    assert fields["ruolo_1"] == "Garante"


def test_page_where_the_model_sees_no_subject_has_none() -> None:
    assert _subject_table([("101", 0, 130, "O"), ("ALFA", 50, 130, "O")]) == {}


def test_subject_roles_stand_when_the_table_header_was_not_read_whole() -> None:
    fields = _subject_table([("101", 0, 130, "sogg_ndg"), ("ALFA", 50, 130, "sogg_denominazione")],
                            tuple(item for item in SUBJECT_HEADER if item[0] != "Ruolo"))
    assert fields == {"ndg_1": "101", "denominazione_1": "ALFA"}


# ============================================================
# The Elenco table: a word stays in the column of its role
# ============================================================

LIST_HEADER = (("ABI", 0), ("NDG", 60), ("Denom.", 120), ("Tipo", 250), ("Importo", 300), ("Stato", 350), ("Fase", 450),
               ("Creazione", 550), ("D.R.", 700), ("Evidenze", 800))


def _list_row(row: list[tuple[str, int, str]], header: tuple[tuple[str, int], ...] = LIST_HEADER) -> dict[str, str]:
    words = [_word(word, x, 100) for word, x in header] + [_word(word, x, 125) for word, x, _ in row]
    example = _example(words, ["O"] * len(header) + [role for *_, role in row], {})
    return decode_fields(example, example["labels"])


def test_list_word_under_another_column_leaves_the_role() -> None:
    assert _list_row([("IB", 250, "fase"), ("IST", 450, "fase")])["fase"] == "IST"


def test_list_word_far_from_its_column_leaves_the_role() -> None:
    assert _list_row([("B", -50, "evidenze"), ("BC", 800, "evidenze")])["evidenze"] == "BC"


def test_list_role_scrolled_away_stays_empty_under_another_header() -> None:
    header = tuple(item for item in LIST_HEADER if item[0] != "Tipo")
    assert "tipo" not in _list_row([("BPM-SI", 700, "tipo")], header)


def test_list_role_keeps_its_word_when_its_header_was_misread() -> None:
    header = tuple(("ip", x) if word == "Tipo" else (word, x) for word, x in LIST_HEADER)
    assert _list_row([("BMB", 250, "tipo")], header)["tipo"] == "BMB"


def test_amount_header_is_not_taken_for_the_type_column() -> None:
    header = tuple(item for item in LIST_HEADER if item[0] != "Tipo")
    assert "tipo" not in _list_row([("BMB", 300, "tipo")], header)


def test_column_rule_is_not_applied_outside_the_list_table() -> None:
    header = tuple(item for item in LIST_HEADER if item[0] != "ABI")
    assert _list_row([("IB", 250, "fase")], header)["fase"] == "IB"


def test_evidence_column_pinned_on_the_right_keeps_its_word_when_its_header_was_misread() -> None:
    header = tuple(item for item in LIST_HEADER if item[0] != "Evidenze")
    assert _list_row([("BC", 700, "evidenze")], header)["evidenze"] == "BC"
