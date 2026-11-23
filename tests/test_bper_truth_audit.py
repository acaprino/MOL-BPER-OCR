"""The comparison rules of bper-emulator/audit_truth.cjs, without a browser: what the page shows against a state's truth.

The browser half (reading each data-field element and judging it visible, clipped or invisible) runs in
tests/browser/bper_truth_audit.cjs where Playwright exists.
"""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

AUDIT = Path(__file__).resolve().parents[1] / "bper-emulator" / "audit_truth.cjs"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")


def node(expression: str, payload: object) -> object:
    script = f"const audit = require({json.dumps(str(AUDIT))}); const input = {json.dumps(payload)};" \
             f"process.stdout.write(JSON.stringify({expression}));"
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def compare(elements: list[dict], truth: dict[str, str]) -> list[tuple[str, str, str]]:
    found = node("audit.compare(input.elements, input.truth)", {"elements": elements, "truth": truth})
    return [(v["rule"], v["reason"], v["field"]) for v in found]


def shown(field: str, text: str, status: str = "visible", row: int = 0) -> dict:
    return {"field": field, "row": row, "status": status, "text": text}


def test_a_visible_field_in_the_truth_with_the_same_text_passes() -> None:
    assert compare([shown("ndg", " 90000001\n")], {"ndg": "90000001"}) == []


def test_a_visible_field_missing_from_the_truth_breaks_rule_i() -> None:
    assert compare([shown("creazione", "10/02/2025")], {}) == [("i", "shown, not in truth", "creazione")]


def test_a_visible_field_with_other_text_in_the_truth_breaks_both_rules() -> None:
    assert compare([shown("stato", "LAV")], {"stato": "SOSP"}) == [
        ("i", "text differs", "stato"), ("ii", "text differs", "stato")]


@pytest.mark.parametrize("status", ["clipped", "invisible"])
def test_a_truth_row_for_a_field_the_page_does_not_fully_show_breaks_rule_ii(status: str) -> None:
    assert compare([shown("note_della_richiesta", "Nota", status)], {"note_della_richiesta": "Nota"}) == [
        ("ii", status, "note_della_richiesta")]


def test_a_truth_row_without_any_element_breaks_rule_ii() -> None:
    assert compare([], {"tooltip_descrizione_ipoteca": "55-IPOTECA"}) == [
        ("ii", "no element", "tooltip_descrizione_ipoteca")]


def test_an_empty_truth_row_asserts_nothing_shown() -> None:
    assert compare([shown("ndg_4", "", "invisible")], {"ndg_4": "", "tooltip_evidenze_b": ""}) == []


def test_later_rows_of_a_table_do_not_count_for_its_scalar_fields() -> None:
    elements = [shown("n_fido", "F1", row=1), shown("n_fido", "F2", row=2)]
    assert compare(elements, {"n_fido": "F1"}) == []


def test_truth_rows_are_read_by_state_and_field_from_the_evaluator_csv() -> None:
    csv = '﻿Fotogramma,Denominazione da attribuire,Valore rilevato\r\nscreen 9,Note,"Riga uno\r\n""due"""\r\n'
    states = node("audit.truthByState(input.csv, input.labels)",
                  {"csv": csv, "labels": {"note_della_richiesta": "Note"}})
    assert states == {"screen 9": {"note_della_richiesta": 'Riga uno\r\n"due"'}}
