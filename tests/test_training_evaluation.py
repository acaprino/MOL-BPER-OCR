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
