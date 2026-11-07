"""Assigning reviewed practices to the G8 groups (docs/next-ver-plan.md §5.4, rules 2 and 3)."""

import pytest

from training.g8_assignment import assign_lot, assign_practices

NEED = {"validazione_estesa": {"a": 1}, "conferma": {"b": 1}}
FUND_NDG = "11153238"
CLIENT_NDG = "36303133"


def _record(practice: str, field: str | None, value: str | None, outcome: str = "TRASCRITTO") -> dict:
    return {"practice": practice, "field": field, "value": value, "outcome": outcome}


def _truth(practice: str, group: str, ndg: str) -> dict:
    return {"Denominazione da attribuire": "NDG 2", "Valore rilevato": ndg, "Esito": "TRASCRITTO",
            "Pratica": practice, "Gruppo": group}


def _assign_subject_practice(earlier_group: str, ndg: str = CLIENT_NDG) -> dict:
    """A practice whose field the confirmation group needs, sharing a subject NDG with an earlier practice."""
    records = [_record("1", "ndg_2", ndg), _record("1", "b", "x")]
    return assign_lot(records, {}, [_truth("5", earlier_group, ndg)], [], NEED)


def _groups(result: dict) -> dict[str, str]:
    return {decision["pratica"]: decision["gruppo"] for decision in result["decisioni"]}


def test_practice_goes_to_the_group_whose_need_it_reduces_most() -> None:
    result = assign_practices({"1": {"b"}}, {"1": set()}, NEED)
    assert _groups(result) == {"1": "conferma"}


def test_practices_without_a_reduction_alternate_starting_from_confirmation() -> None:
    result = assign_practices({"1": set(), "2": set(), "3": set()}, {"1": set(), "2": set(), "3": set()}, NEED)
    assert _groups(result) == {"1": "conferma", "2": "validazione_estesa", "3": "conferma"}


def test_practices_are_examined_by_increasing_number() -> None:
    result = assign_practices({"10": set(), "9": set()}, {"10": set(), "9": set()}, NEED)
    assert [decision["pratica"] for decision in result["decisioni"]] == ["9", "10"]


def test_equal_reduction_is_a_tie() -> None:
    result = assign_practices({"1": {"a", "b"}}, {"1": set()}, NEED)
    assert _groups(result) == {"1": "conferma"}


def test_reduced_need_no_longer_attracts_the_next_practice() -> None:
    result = assign_practices({"1": {"b"}, "2": {"b"}}, {"1": set(), "2": set()}, NEED)
    assert result["fabbisogno_residuo"]["conferma"] == {}
    assert _groups(result)["2"] == "conferma"


def test_identity_of_an_earlier_group_binds_the_practice_to_that_group() -> None:
    identity = ("NDG", "7")
    result = assign_practices({"1": {"b"}}, {"1": {identity}}, NEED, {identity: "validazione_estesa"})
    assert _groups(result) == {"1": "validazione_estesa"}


def test_identity_shared_inside_the_lot_binds_the_later_practice() -> None:
    identity = ("NDG", "7")
    result = assign_practices({"1": {"b"}, "2": {"a"}}, {"1": {identity}, "2": {identity}}, NEED)
    assert _groups(result) == {"1": "conferma", "2": "conferma"}


def test_bound_practice_does_not_consume_a_tie() -> None:
    identity = ("NDG", "7")
    result = assign_practices({"1": set(), "2": set()}, {"1": {identity}, "2": set()}, NEED, {identity: "validazione_estesa"})
    assert _groups(result)["2"] == "conferma"


def test_refuses_practice_bound_to_both_groups() -> None:
    first, second = ("NDG", "7"), ("NDG", "8")
    with pytest.raises(ValueError, match="1"):
        assign_practices({"1": set()}, {"1": {first, second}}, NEED, {first: "validazione_estesa", second: "conferma"})


def test_given_need_is_not_modified() -> None:
    need = {"validazione_estesa": {"a": 1}, "conferma": {"b": 1}}
    assign_practices({"1": {"b"}}, {"1": set()}, need)
    assert need["conferma"] == {"b": 1}


def test_ndg_of_the_extended_validation_binds_the_practice() -> None:
    assert _groups(_assign_subject_practice("val_ext")) == {"1": "validazione_estesa"}


def test_guarantee_fund_does_not_bind_the_practice() -> None:
    assert _groups(_assign_subject_practice("val_ext", FUND_NDG)) == {"1": "conferma"}


def test_guarantee_fund_shared_inside_the_lot_does_not_bind_the_practices() -> None:
    records = [_record("1", "ndg_2", FUND_NDG), _record("1", "b", "x"), _record("2", "ndg_2", FUND_NDG), _record("2", "a", "x")]
    assert _groups(assign_lot(records, {}, [], [], NEED)) == {"1": "conferma", "2": "validazione_estesa"}


def test_guarantee_fund_is_not_recorded_as_shared_with_a_training_practice() -> None:
    assert _assign_subject_practice("train", FUND_NDG)["isolamento_v3_1"]["identita_in_comune"] == {}


def test_practices_with_the_guarantee_fund_are_listed() -> None:
    assert _assign_subject_practice("val_ext", FUND_NDG)["ndg_istituzionali"] == {FUND_NDG: ["1"]}


def test_ndg_of_a_training_practice_does_not_bind_the_practice() -> None:
    assert _groups(_assign_subject_practice("train")) == {"1": "conferma"}


def test_ndg_of_a_training_practice_is_recorded() -> None:
    recorded = _assign_subject_practice("train")["isolamento_v3_1"]["identita_in_comune"]
    assert recorded == {"1": [{"tipo": "NDG", "valore": CLIENT_NDG, "v3_1": "5"}]}


def test_value_outside_the_vocabulary_is_not_an_identity() -> None:
    records = [_record("1", None, CLIENT_NDG), _record("1", "b", "x")]
    assert _groups(assign_lot(records, {}, [_truth("5", "val_ext", CLIENT_NDG)], [], NEED)) == {"1": "conferma"}


def test_image_of_the_extended_validation_binds_the_practice() -> None:
    screens = {"1__Elenco": {"image_sha256": "same", "pixel_sha256": "other"}}
    rows = [{"Pratica": "5", "Gruppo": "val_ext", "SHA256 immagine": "same", "SHA256 pixel": "another"}]
    result = assign_lot([_record("1", "b", "x")], screens, [], rows, NEED)
    assert _groups(result) == {"1": "validazione_estesa"}


def test_empty_value_does_not_reduce_the_need() -> None:
    result = assign_lot([_record("1", "b", None, "VUOTO")], {}, [], [], NEED)
    assert result["fabbisogno_residuo"]["conferma"] == {"b": 1}
