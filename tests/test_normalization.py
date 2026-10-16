"""Behavioral checks for identifier comparison during extraction evaluation."""

from typing import Any

import pytest

from extraction.normalization import classify_field, dataset_mismatch_guard


NDG_FIELDS = ("ndg", "ndg_1", "ndg_2", "ndg_3", "ndg_4")


@pytest.mark.parametrize("field_key", NDG_FIELDS)
@pytest.mark.parametrize(
    ("gt_value", "pred_value"),
    [
        ("12345", "12.345"),
        ("12345", "0012345"),
        ("12345/A", "12345a"),
    ],
)
def test_ndg_classification_accepts_equivalent_identifiers(
    field_key: str, gt_value: str, pred_value: str,
) -> None:
    assert classify_field(gt_value, pred_value, field_key)[0] == "OK"


@pytest.mark.parametrize("field_key", NDG_FIELDS)
@pytest.mark.parametrize(
    ("gt_value", "pred_value"),
    [
        ("12.345", "12.35"),
        ("12345/A", "12345"),
        ("12345/A", "12345/B"),
        ("0012345/A", "12345/A"),
        ("123456789012345678901234567890/A", "123456789012345678901234567890/B"),
    ],
)
def test_ndg_classification_rejects_distinct_identifiers(
    field_key: str, gt_value: str, pred_value: str,
) -> None:
    assert classify_field(gt_value, pred_value, field_key)[0] == "WRONG"


@pytest.mark.parametrize("field_key", NDG_FIELDS)
@pytest.mark.parametrize(
    ("gt_value", "pred_value", "status"),
    [
        (None, "n/d", "OK_NULL"),
        ("12345", "---", "MISSING"),
        ("nan", "12345/A", "HALLUCINATED"),
    ],
)
def test_ndg_classification_preserves_null_statuses(
    field_key: str, gt_value: Any, pred_value: Any, status: str,
) -> None:
    assert classify_field(gt_value, pred_value, field_key)[0] == status


@pytest.mark.parametrize(
    ("gt_value", "pred_value"),
    [
        ("12345", "12.345"),
        ("12345", "0012345"),
        ("12345/A", "12345a"),
    ],
)
def test_dataset_guard_accepts_equivalent_ndg_identifiers(
    gt_value: str, pred_value: str,
) -> None:
    pred = {"fields": {"ndg": {"value": pred_value}}}

    assert dataset_mismatch_guard({"NDG": gt_value}, pred) is False


@pytest.mark.parametrize(
    ("gt_value", "pred_value"),
    [
        ("12.345", "12.35"),
        ("12345/A", "12345"),
        ("12345/A", "12345/B"),
        ("0012345/A", "12345/A"),
    ],
)
def test_dataset_guard_rejects_distinct_ndg_identifiers(
    gt_value: str, pred_value: str,
) -> None:
    pred = {"fields": {"ndg": {"value": pred_value}}}

    assert dataset_mismatch_guard({"NDG": gt_value}, pred) is True


@pytest.mark.parametrize("pred_value", [None, "", "n/d", "---", "nan"])
def test_dataset_guard_does_not_treat_unread_ndg_as_a_mismatch(pred_value: Any) -> None:
    pred = {"fields": {"ndg": {"value": pred_value}}}

    assert dataset_mismatch_guard({"NDG": "12345"}, pred) is False


def test_dataset_guard_uses_subject_ndg_when_header_ndg_is_unread() -> None:
    pred = {"fields": {"ndg": {"value": None}}, "soggetti": [{"ndg": "12.345"}]}

    assert dataset_mismatch_guard({"ndg": "12345"}, pred) is False


def test_dataset_guard_preserves_denominazione_comparison() -> None:
    pred = {"fields": {"ndg": {"value": "12345"}, "denominazione": {"value": "BIANCHI"}}}

    assert dataset_mismatch_guard({"NDG": "12345", "DENOMINAZIONE": "ROSSI"}, pred) is True


@pytest.mark.parametrize("field_key", ["importo_euro", "n_fido"])
@pytest.mark.parametrize(
    ("gt_value", "pred_value", "status"),
    [
        ("36.177,00", "36177.00", "OK"),
        ("-36.177,00", "-36177.00", "OK"),
        ("123,45", "123,46", "WRONG"),
    ],
)
def test_quantity_classification_preserves_numeric_comparison(
    field_key: str, gt_value: str, pred_value: str, status: str,
) -> None:
    assert classify_field(gt_value, pred_value, field_key)[0] == status
