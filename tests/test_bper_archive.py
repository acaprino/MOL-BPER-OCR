"""Practices of the real archive (data/dataset) as emulator profiles, built in memory.

Assertions compare counts and keys only: a failure must never print a real value. The test practices are
read here only in memory, as read_archive() reads them, to count and check them (ADR 0027).
"""

from collections import Counter, defaultdict
import csv
from io import StringIO
from pathlib import Path
import re

import pytest

from bper_archive import archive_profiles, merge_fragments
from bper_profiles import validate_profile
from bper_simulator_truth import (
    CSV_LABELS, NOTE_LINE_CHARS, available_steps, practice_truth_csv, practice_truth_record_csv,
)

ARCHIVE = Path(__file__).resolve().parents[1] / "data" / "dataset"
# What a value of the archive may be rendered from: read on screen, derived from another page, or partly read.
AUTHORED = ("TRASCRITTO", "DERIVATO", "PARZIALE")
NOTES = ("note_della_richiesta", "note_scheda_privati")
STEPS = {"elenco": {1, 2, 3}, "soggetti": {4}, "gestione-fidi": {5, 6, 7, 8}, "note": {9}}


def table(name: str) -> list[dict[str, str]]:
    with (ARCHIVE / name).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter=";"))


def squash(text: str) -> str:
    return " ".join(text.split()).lower()


@pytest.fixture(scope="module")
def everything() -> list[dict]:
    return archive_profiles(ARCHIVE, include_test=True)


@pytest.fixture(scope="module")
def authored() -> dict[tuple[str, str], list[str]]:
    """(practice, canonical key) -> the authored values of that key, whitespace-squashed."""
    values = defaultdict(list)
    for row in table("valori.csv"):
        if row["Chiave"] and row["Esito"] in AUTHORED and row["Valore"].strip():
            values[(row["Schermata"].split("/")[0], row["Chiave"])].append(squash(row["Valore"]))
    return values


def practice_id(profile: dict) -> str:
    return profile["key"].removeprefix("arch-")


def rendered(profile: dict) -> list[tuple[str, str]]:
    """(canonical key, value) of every value of the 45 fields the emulator pages show for this profile."""
    p = profile
    out = [("ndg", p["ndg"]), ("denominazione", p["name"]), ("tipo", p["type"]), ("tipo", p["typeCode"]),
           ("tooltip_descrizione_bmb", p["typeName"]), ("stato", p["state"]), ("fase", p["phase"]),
           ("creazione", p["created"]), ("creazione", p["date"]), ("evidenze", p["evidence"]),
           ("tooltip_evidenze_b", p["evidenceTooltip"]), ("note_della_richiesta", p["notes"]),
           ("filiale_relazione", " - ".join(part for part in (p["branch"], p["branchName"]) if part))]
    for n, s in enumerate(p["subjects"], 1):
        out += [(f"ndg_{n}", s["ndg"]), (f"denominazione_{n}", s["name"]), (f"ruolo_{n}", s["role"])]
    for row in p["fidi"][:1]:
        out += [("n_fido", row["id"]), ("rapporto", row["account"]), ("descrizione", row["description"]),
                ("scadenza", row["due"]), ("importo_euro", row["amount"]), ("tipo_op", row["operation"])]
    out += [(row["tooltipField"], row["tooltip"]) for row in p["fidi"] + p["guarantees"] if row["tooltipField"]]
    if p["scheda"]:
        out += [("ndg", p["scheda"]["ndg"]), ("denominazione", p["scheda"]["name"]), *p["scheda"]["fields"].items()]
    return out


def invented(profile: dict, values: list[tuple[str, str]], authored: dict) -> list[str]:
    """Keys whose non-empty value is not one of the practice's authored values (notes: not covered by them)."""
    bad = []
    for key, value in values:
        if not value.strip():
            continue
        known = authored.get((practice_id(profile), key), [])
        if key in NOTES:
            # Every 40-character window of every paragraph lies in one authored fragment.
            for paragraph in re.split(r"\n\s*\n", value):
                text = squash(paragraph)
                windows = [text[i:i + 40] for i in range(0, max(1, len(text) - 39), 20)]
                if not all(any(window in fragment for fragment in known) for window in windows):
                    bad.append(key)
                    break
        elif squash(value) not in known:
            bad.append(key)
    return bad


def test_all_33_practices_load_with_their_archive_roles(everything: list[dict]) -> None:
    roles = {row["Pratica"]: row["Ruolo"] for row in table("pratiche.csv")}
    assert {p["key"]: p["role"] for p in everything} == {f"arch-{n}": role for n, role in roles.items()}
    assert Counter(p["role"] for p in everything) == {"addestramento": 18, "controllo": 2, "test": 13}


def test_test_practices_are_read_only_with_include_test() -> None:
    assert Counter(p["role"] for p in archive_profiles(ARCHIVE)) == {"addestramento": 18, "controllo": 2}


def test_every_archive_practice_is_a_valid_profile(everything: list[dict]) -> None:
    assert [p["key"] for p in everything if validate_profile(p)] == []


def test_the_pages_show_only_authored_values_of_the_45_fields(everything: list[dict], authored: dict) -> None:
    bad = {p["key"]: invented(p, rendered(p), authored) for p in everything}
    assert {key: fields for key, fields in bad.items() if fields} == {}


def test_the_truth_asserts_only_authored_values(everything: list[dict], authored: dict) -> None:
    keys = {label: key for key, label in CSV_LABELS.items()}
    bad = {}
    for p in everything:
        rows = list(csv.reader(StringIO(practice_truth_csv(p), newline="")))[1:]
        bad[p["key"]] = invented(p, [(keys[label], value) for _, label, value in rows], authored)
    assert {key: fields for key, fields in bad.items() if fields} == {}


def test_practice_truth_states_the_fields_the_archive_has_with_authored_values(everything: list[dict],
                                                                             authored: dict) -> None:
    stated = defaultdict(set)
    for row in table("valori.csv"):
        if row["Chiave"] and row["Esito"] in (*AUTHORED, "VUOTO"):
            stated[row["Schermata"].split("/")[0]].add(row["Chiave"])
    wrong_keys, bad = {}, {}
    for p in everything:
        rows = list(csv.DictReader(StringIO(practice_truth_record_csv(p), newline=""), delimiter=";"))
        if {row["Chiave"] for row in rows} != stated[practice_id(p)]:
            wrong_keys[p["key"]] = sorted({row["Chiave"] for row in rows} ^ stated[practice_id(p)])
        bad[p["key"]] = invented(p, [(row["Chiave"], row["Valore"]) for row in rows], authored)
    assert wrong_keys == {}
    assert {key: fields for key, fields in bad.items() if fields} == {}


def test_values_outside_the_45_fields_are_empty_or_marked_as_filler(everything: list[dict]) -> None:
    outside = ("abi", "assignee", "assigneeName", "operatorId", "operatorName", "officeCode", "assigned",
               "creditTotal", "guaranteeTotal", "scenario")
    unmarked = {p["key"]: [k for k in outside if p[k] and k not in p["provenance"]["filler"]] for p in everything}
    assert {key: found for key, found in unmarked.items() if found} == {}


def test_no_filler_stands_where_one_of_the_45_fields_is_shown(everything: list[dict]) -> None:
    fields = ("ndg", "name", "type", "typeCode", "typeName", "state", "phase", "created", "date", "evidence",
              "evidenceTooltip", "branch", "branchName", "notes", "subjects", "fidi", "scheda.ndg", "scheda.name",
              "scheda.fields")
    bad = {}
    for p in everything:
        for path in p["provenance"]["filler"]:
            if path.split(".")[0] in fields or ".".join(path.split(".")[:2]) in fields:
                bad.setdefault(p["key"], []).append(path)
            elif path.startswith("guarantees."):
                row = p["guarantees"][int(path.split(".")[1])]
                if row["tooltipField"] or row["tooltip"]:
                    bad.setdefault(p["key"], []).append(path)
    assert bad == {}


def test_the_header_takes_the_detail_pages_value_before_the_lists_cut_one() -> None:
    # The list cuts long names ("NAME..."): a detail page's value, even derived, is the header's.
    detail = defaultdict(list)
    for row in table("valori.csv"):
        page = row["Schermata"].split("/")[1].rpartition("-")[0]
        if row["Chiave"] == "denominazione" and page in ("soggetti", "gestione-fidi", "note") \
                and row["Esito"] in AUTHORED and row["Valore"].strip():
            detail[row["Schermata"].split("/")[0]].append(squash(row["Valore"]))
    checked = [p for p in archive_profiles(ARCHIVE) if detail[practice_id(p)]]
    not_from_detail = sum(squash(p["name"]) not in detail[practice_id(p)] for p in checked)
    assert len(checked) > 0  # counts only: a failure must not print a profile
    assert not_from_detail == 0


def test_only_practices_with_scheda_privati_screens_have_a_scheda(everything: list[dict]) -> None:
    with_scheda = {row["Pratica"] for row in table("schermate.csv") if row["Pagina"] == "scheda-privati"}
    assert {practice_id(p) for p in everything if p["scheda"]} == with_scheda


def test_a_scheda_belongs_to_the_customer_its_own_screens_name(everything: list[dict], authored: dict) -> None:
    on_scheda = defaultdict(set)
    for row in table("valori.csv"):
        page = row["Schermata"].split("/")[1]
        if page.startswith("scheda-privati-") and row["Chiave"] in ("ndg", "denominazione") and row["Valore"]:
            on_scheda[(row["Schermata"].split("/")[0], row["Chiave"])].add(squash(row["Valore"]))
    for p in (p for p in everything if p["scheda"]):
        # Booleans, so that a failure does not print the values.
        own_ndg = squash(p["scheda"]["ndg"]) in on_scheda[(practice_id(p), "ndg")]
        own_name = squash(p["scheda"]["name"]) in on_scheda[(practice_id(p), "denominazione")]
        assert own_ndg and own_name, p["key"]


def test_a_scheda_note_line_fits_one_line_of_the_note_box(everything: list[dict]) -> None:
    lines = [line for p in everything if p["scheda"] for line in p["scheda"]["fields"]["note_scheda_privati"].split("\n")]
    assert lines and max(map(len, lines)) <= NOTE_LINE_CHARS


def test_pages_and_capture_steps_follow_the_screens_of_the_archive(everything: list[dict]) -> None:
    pages = defaultdict(set)
    for row in table("schermate.csv"):
        if row["Pagina"] in STEPS:
            pages[row["Pratica"]].add(row["Pagina"])
    for p in everything:
        assert set(p["pages"]) == pages[practice_id(p)], p["key"]
        allowed = set().union(*(STEPS[page] for page in p["pages"]))
        assert set(available_steps(p)) <= allowed, p["key"]
        screens = {row[0] for row in csv.reader(StringIO(practice_truth_csv(p), newline=""))}
        assert {s for s in screens if s.startswith("screen ")} == {f"screen {n}" for n in available_steps(p)}, p["key"]


def test_overlapping_note_fragments_join_once() -> None:
    first = "Primo blocco della nota con una frase abbastanza lunga da sovrapporsi al secondo."
    second = "una frase abbastanza lunga da sovrapporsi al secondo. Poi il seguito della nota."
    assert merge_fragments([first, second]) == first + " Poi il seguito della nota."


def test_a_note_fragment_already_contained_adds_nothing() -> None:
    assert merge_fragments(["Inizio. Centro. Fine.", "Centro."]) == "Inizio. Centro. Fine."
    assert merge_fragments(["Centro.", "Inizio. Centro. Fine."]) == "Inizio. Centro. Fine."


def test_disjoint_note_fragments_become_paragraphs() -> None:
    assert merge_fragments(["Primo paragrafo.", "Secondo paragrafo."]) == "Primo paragrafo.\n\nSecondo paragrafo."


# ---- the row of a guarantee's description tooltip (calibration screenshots: the tooltip boxes over the GARANZIE
# table, and the table rows the archive transcribes). Invented values in a one-practice archive. ----

IPOTECA = "tooltip_descrizione_ipoteca"
CONSAP = "tooltip_descrizione_consap_dr_bis"


def _one_practice(tmp_path: Path, rows: list[tuple[str, str, str, str]]) -> dict:
    """The profile of an invented practice whose gestione-fidi screens carry these (screen, Campo, Chiave, Valore)."""
    number = "90000001"
    screens = sorted({screen for screen, *_ in rows})
    (tmp_path / "pratiche.csv").write_text(f"Pratica;Ruolo;Schermate;Valori\n{number};addestramento;{len(screens)};{len(rows)}\n",
                                           encoding="utf-8")
    (tmp_path / "schermate.csv").write_text(
        "Schermata;Pratica;Pagina;Numero;Variante;File;SHA256;Larghezza;Altezza\n"
        + "".join(f"{number}/{screen};{number};gestione-fidi;{screen[-2:]};;;;;\n" for screen in screens), encoding="utf-8")
    (tmp_path / "valori.csv").write_text(
        "Schermata;Campo;Chiave;Valore;Esito\n"
        + "".join(f"{number}/{screen};{label};{key};{value};TRASCRITTO\n" for screen, label, key, value in rows),
        encoding="utf-8")
    return archive_profiles(tmp_path)[0]


def _tip(n: int, description: str) -> str:
    return f"tooltip su valore campo Descrizione (riga {n}): {description}"


def test_a_guarantee_tooltip_sits_on_the_table_row_showing_its_description(tmp_path: Path) -> None:
    profile = _one_practice(tmp_path, [
        ("gestione-fidi-01", "Garanzia 1: Descrizione", "", "IPOTECA I GR."),
        ("gestione-fidi-01", "Garanzia 2: Descrizione", "", "FID LIM INATTO"),
        ("gestione-fidi-02", _tip(2, "IPOTECA I GR."), IPOTECA, "55-IPOTECA FITTIZIA"),
    ])
    assert [row["tooltipField"] for row in profile["guarantees"]] == [IPOTECA, None]


@pytest.mark.parametrize("first, second", [(IPOTECA, CONSAP), (CONSAP, IPOTECA)])
def test_without_the_table_guarantee_tooltips_take_the_rows_in_the_order_of_their_screens(
        tmp_path: Path, first: str, second: str) -> None:
    labels = {IPOTECA: _tip(2, "IPOTECA I GR."), CONSAP: _tip(1, "CONSAP DR BIS")}
    profile = _one_practice(tmp_path, [("gestione-fidi-03", labels[first], first, "PRIMA FITTIZIA"),
                                       ("gestione-fidi-04", labels[second], second, "SECONDA FITTIZIA")])
    assert [row["tooltipField"] for row in profile["guarantees"]] == [first, second]


def test_a_lone_guarantee_tooltip_without_the_table_takes_the_first_row_of_the_rows_its_label_counts(
        tmp_path: Path) -> None:
    profile = _one_practice(tmp_path, [("gestione-fidi-02", _tip(2, "IPOTECA I GR."), IPOTECA, "55-IPOTECA FITTIZIA")])
    assert [row["tooltipField"] for row in profile["guarantees"]] == [IPOTECA, None]
    assert "guarantees.1" in profile["provenance"]["filler"]
