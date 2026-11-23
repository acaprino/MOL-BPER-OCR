"""The second LLM-authored practice set: 40 fictitious profiles that move the catalogue toward the real archive.

bper-emulator/profiles/generated-set-02.json joins the catalogue with --profiles, beside the seed and
generated-set-01. Every value is invented. Its vocabulary (state, phase, evidence and type codes, subject roles,
credit and guarantee labels) and its proportions follow count-only statistics of the calibration fold (13
calibration practices plus the reference one, never the validation or test practices), hardcoded below. This
file never reads the archive: load_profiles does the collision check and prints no value.
"""

from calendar import monthrange
from collections import Counter
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
import re
import statistics

import pytest

from bper_profiles import PAGES, load_profiles
from bper_simulator_catalog import ensure_database, read_catalog
from bper_simulator_truth import LIST_FONT, REQUEST_NOTE_LINES, request_note_fits
from bper_synthetic_db import FUND_NAME, FUND_NDG, SCHEDA_TODAY, _money, synthetic_practices

REPO = Path(__file__).resolve().parents[1]
ARCHIVE = REPO / "data" / "dataset"
PROFILES = REPO / "bper-emulator" / "profiles" / "generated-set-02.json"
SET_01 = REPO / "bper-emulator" / "profiles" / "generated-set-01.json"

# ============================================================
# The calibration fold, as counts (practices per value; the list row of 12 practices, 2 have no list screen)
# ============================================================
REAL_STATES = {"APP": 4, "ABB": 6, "LAV": 2}
REAL_PHASES = {"IST": 6, "VEP": 1, "PRO": 1, "": 4}  # every APP practice has an empty phase
REAL_EVIDENCE = {"B": 4, "B V": 2, "BC": 2, "BM": 1, "": 3}
REAL_SUBJECTS = {1: 3, 2: 3, 3: 1, 4: 5}  # Elenco Soggetti rows (4: four or more)
REAL_NOTE_QUARTILES = (1005, 1507, 2207)  # characters of the 11 written notes, two of them partly transcribed
REAL_EMPTY_NOTES = 3 / 14  # no note text (and no note screen); the audit's 5 of 20 held-out practices is near it
REAL_PARTIAL_NOTES = 2 / 13  # note rows transcribed only in part: the note ran beyond the window
REAL_MONTHS_DUE = 6 / 13  # Scadenza shown as "NNN mesi" instead of a date
REAL_ROUND_AMOUNTS = 7 / 13  # whole thousands

ROLE_UP, ROLE_LOW = "Nuovo Garante/nuovo Datore Di Pegno", "Nuovo Garante/nuovo Datore di Pegno"
JOINT_ROLES = ("Cointestazione", "Cointestato")
BROKER_TYPE = "BPI Mutui / Med. Creditizi"
# (code, practice type, long name of the Tipo cell): only BMB's long name is transcribed; BMS's is the recording's
# (bper_synthetic_db); BMM's was never seen, so its cell has no long name.
TYPES = {("BMB", "BPI Mutui", "BPI Mutui Origination Bstore"), ("BMB", BROKER_TYPE, "BPI Mutui Origination Bstore"),
         ("BMS", "BPI Mutui", "BPI Mutui Standard"), ("BMM", BROKER_TYPE, "")}
# A credit or guarantee text (description, tooltip, operation) is the seed's own, or copied from the calibration fold
# only when at least 2 of its practices show it and it holds no name, NDG, amount or date; any other is a generic
# invention in the seed's style. COPIED_TEXTS records the count-only check (calibration practices showing each text,
# no subject or header name of theirs inside it) that chose them.
COPIED_TEXTS = {"M.FOND.PRIVATI": 6, "M.F. PF FONDO": 2, "FID LIM INATTO": 2,
                "49-FIDEJUSSIONE SOLIDALE LIMITATA IN ATTO": 2, "Nuova Finanza": 5, "Nuova": 2}
INVENTED_TEXTS = {"M. IPOTECARIO", "310910 - MUTUO FONDIARIO ABITAZIONE", "310920 - MUTUO IPOTECARIO NON FONDIARIO",
                  "310930 - MUTUO FONDIARIO CON GARANZIA DEL FONDO", "GAR. FONDO P.C.", "460-GARANZIA DEL FONDO PRIMA CASA"}
CREDIT_PRODUCTS = {
    "M.FOND.PRIVATI": ("310910 - MUTUO FONDIARIO ABITAZIONE", None),
    "M.CONSAP >=80%": ("340176 - MUTUO FOND PRIV CONSAP >=80%", "tooltip_descrizione_m_consap"),
    "M.F. PF FONDO": ("310930 - MUTUO FONDIARIO CON GARANZIA DEL FONDO", None),
    "M. IPOTECARIO": ("310920 - MUTUO IPOTECARIO NON FONDIARIO", None),
}
GUARANTEES = {
    "CONSAP DR BIS": ("457-IMP. FID. F.DO 1 CASA DR SOSTEGNI BIS", "tooltip_descrizione_consap_dr_bis"),
    "GAR. FONDO P.C.": ("460-GARANZIA DEL FONDO PRIMA CASA", None),
    "IPOTECA I GR.": ("55-IPOTECA DI PRIMO GRADO", "tooltip_descrizione_ipoteca"),
    "FID LIM INATTO": ("49-FIDEJUSSIONE SOLIDALE LIMITATA IN ATTO", None),
}
# The fund's guarantee, per product that carries it.
FUND_GUARANTEE = {"M.CONSAP >=80%": "CONSAP DR BIS", "M.F. PF FONDO": "GAR. FONDO P.C."}
HEADER = re.compile(r"- Numero proposta DESK: (\d{7})\n- Valore immobile presunto: ([\d.]+,\d\d)\n"
                    r"- Dettaglio importi mutuo:\n {7}IMPORTO RICHIESTO : ([\d.]+,\d\d) €\n")
PARTIAL_HEADER = re.compile(r"- Dettaglio importi mutuo:\n {7}IMPORTO RICHIESTO : ([\d.]+,\d\d) €\n")
MONTHS_DUE = re.compile(r"(\d{3}) mesi")


@pytest.fixture(scope="module")
def profiles() -> list[dict]:
    return load_profiles(PROFILES, archive=ARCHIVE)


@pytest.fixture(scope="module")
def others() -> list[dict]:
    """The seed catalogue and the first generated set."""
    return synthetic_practices() + load_profiles(SET_01, archive=None)


def _cents(money: str) -> int:
    whole, _, fraction = money.partition(",")
    return int(whole.replace(".", "")) * 100 + int(fraction or 0)


def _day(display: str) -> date:
    return datetime.strptime(display, "%d/%m/%Y").date()


def _ndg(value: str) -> str:
    return value.lstrip("0") or "0"


def _share(count: int, total: int) -> float:
    return count / total


def _written(profiles: list[dict]) -> list[dict]:
    return [p for p in profiles if p["notes"]]


def _has_fund(p: dict) -> bool:
    return any(s["ndg"] == FUND_NDG for s in p["subjects"])


def _guarantors(p: dict) -> list[dict]:
    return [s for s in p["subjects"][1:] if s["role"] in (ROLE_UP, ROLE_LOW) and s["ndg"] != FUND_NDG]


def _list_width(name: str) -> float:
    advance, kerning = LIST_FONT["advance"], LIST_FONT["kerning"]
    return sum(advance[c] for c in name) + sum(kerning.get(a + b, 0.0) for a, b in zip(name, name[1:]))


# ============================================================
# Identity: keys, numbers, NDGs
# ============================================================
# Identifiers that must not repeat in the file nor reuse one of the seed or of the first set: reader and format.
IDENTIFIERS: dict[str, tuple[Callable[[list[dict]], list[str]], str]] = {
    "practice number": (lambda ps: [p["number"] for p in ps], r"\d{8}"),
    "proposal number": (lambda ps: [m[1] for p in ps if (m := re.search(r"DESK: (\d+)", p["notes"]))], r"\d{7}"),
    "account": (lambda ps: [f["account"] for p in ps for f in p["fidi"] if f["account"]], r"034 \d{4} 001[78] \d{8}"),
    "person ndg": (lambda ps: [_ndg(s["ndg"]) for p in ps for s in p["subjects"] if s["ndg"] != FUND_NDG], r"\d{7,8}"),
}


def test_the_file_holds_forty_practices_keyed_gen2_001_to_gen2_040(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles] == [f"gen2-{n:03}" for n in range(1, 41)]


def test_every_practice_is_synthetic(profiles: list[dict]) -> None:
    assert {p["role"] for p in profiles} == {"sintetica"}


def test_every_practice_is_marked_llm_generated(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["provenance"] != {"source": "llm-generated", "filler": [], "stated": None}] == []


@pytest.mark.parametrize("identifier", IDENTIFIERS)
def test_identifiers_have_the_seed_format(profiles: list[dict], identifier: str) -> None:
    read, pattern = IDENTIFIERS[identifier]
    assert [value for value in read(profiles) if not re.fullmatch(pattern, value)] == []


@pytest.mark.parametrize("identifier", IDENTIFIERS)
def test_identifiers_are_unique_in_the_file(profiles: list[dict], identifier: str) -> None:
    values = IDENTIFIERS[identifier][0](profiles)
    assert len(set(values)) == len(values)


@pytest.mark.parametrize("identifier", IDENTIFIERS)
def test_identifiers_are_outside_the_seed_and_the_first_set(profiles: list[dict], others: list[dict], identifier: str) -> None:
    read = IDENTIFIERS[identifier][0]
    assert not set(read(profiles)) & set(read(others))


def test_no_person_ndg_is_an_employer_ndg_of_the_seed_or_the_first_set(profiles: list[dict], others: list[dict]) -> None:
    employers = {_ndg(p["scheda"]["details"]["employerNdg"]) for p in others if p["scheda"]} - {"0"}
    assert not set(IDENTIFIERS["person ndg"][0](profiles)) & employers


def test_the_set_joins_the_catalogue_beside_the_seed_and_the_first_set(tmp_path: Path) -> None:
    ensure_database(tmp_path / "seed.sqlite3")
    catalog = read_catalog(tmp_path / "seed.sqlite3", False, profiles=[SET_01, PROFILES])
    assert [p["key"] for p in catalog["practices"]][-40:] == [f"gen2-{n:03}" for n in range(1, 41)]


def test_accounts_name_the_practice_branch(profiles: list[dict]) -> None:
    assert [f["account"] for p in profiles for f in p["fidi"]
            if f["account"] and f["account"].split()[1] != p["branch"].zfill(4)] == []


def test_the_fund_is_never_the_applicant(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["ndg"] == FUND_NDG] == []


def test_the_fund_subject_carries_the_fund_name_and_a_guarantor_role(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles for s in p["subjects"]
            if s["ndg"] == FUND_NDG and (s["name"], s["role"] in (ROLE_UP, ROLE_LOW)) != (FUND_NAME, True)] == []


# ============================================================
# The calibration fold's vocabulary, each code at least twice
# ============================================================
def test_states_are_the_real_ones(profiles: list[dict]) -> None:
    assert {p["state"] for p in profiles} == set(REAL_STATES)


@pytest.mark.parametrize("state", REAL_STATES)
def test_each_real_state_appears_at_least_twice(profiles: list[dict], state: str) -> None:
    assert sum(p["state"] == state for p in profiles) >= 2


def test_phases_are_the_real_ones(profiles: list[dict]) -> None:
    assert {p["phase"] for p in profiles} == set(REAL_PHASES)


@pytest.mark.parametrize("phase", REAL_PHASES)
def test_each_real_phase_appears_at_least_twice(profiles: list[dict], phase: str) -> None:
    assert sum(p["phase"] == phase for p in profiles) >= 2


def test_evidence_codes_are_the_real_ones(profiles: list[dict]) -> None:
    assert {p["evidence"] for p in profiles} == set(REAL_EVIDENCE)


@pytest.mark.parametrize("evidence", REAL_EVIDENCE)
def test_each_real_evidence_code_appears_at_least_twice(profiles: list[dict], evidence: str) -> None:
    assert sum(p["evidence"] == evidence for p in profiles) >= 2


def test_states_keep_the_real_proportions(profiles: list[dict]) -> None:
    real = sum(REAL_STATES.values())
    assert [s for s, n in REAL_STATES.items()
            if abs(_share(sum(p["state"] == s for p in profiles), len(profiles)) - n / real) > 0.10] == []


def test_an_approved_practice_has_no_phase(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if (p["state"] == "APP") != (p["phase"] == "")] == []


def test_an_abandoned_practice_stopped_in_istruttoria(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["state"] == "ABB" and p["phase"] != "IST"] == []


def test_the_b_tooltip_goes_with_a_separate_b_code(profiles: list[dict]) -> None:
    # The truth fills tooltip_evidenze_b only for a B standing alone ("B", "B V"); BC and BM show no tooltip.
    assert [p["key"] for p in profiles
            if p["evidenceTooltip"] != ("Origination BSTORE" if "B" in p["evidence"].split() else "")] == []


def test_type_codes_and_names_come_from_the_real_table(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if (p["typeCode"], p["type"], p["typeName"]) not in TYPES] == []


def test_the_bstore_code_goes_with_an_evidence(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if (p["typeCode"] == "BMB") != bool(p["evidence"])] == []


def test_the_broker_evidence_goes_with_the_broker_type(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["typeCode"] == "BMB" and (p["evidence"] == "BM") != (p["type"] == BROKER_TYPE)] == []


@pytest.mark.parametrize("code", ["BMB", "BMS", "BMM"])
def test_each_real_type_code_appears_at_least_twice(profiles: list[dict], code: str) -> None:
    assert sum(p["typeCode"] == code for p in profiles) >= 2


def test_subject_roles_come_from_the_real_vocabulary(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles
            if any(s["role"] not in (ROLE_UP, ROLE_LOW, *JOINT_ROLES) for s in p["subjects"][1:])] == []


def test_a_practice_spells_the_guarantor_role_one_way(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if len({s["role"] for s in p["subjects"]} & {ROLE_UP, ROLE_LOW}) > 1] == []


@pytest.mark.parametrize("role", [ROLE_UP, ROLE_LOW, *JOINT_ROLES])
def test_each_real_subject_role_appears_in_at_least_two_practices(profiles: list[dict], role: str) -> None:
    assert sum(any(s["role"] == role for s in p["subjects"]) for p in profiles) >= 2


def test_the_number_of_subjects_follows_the_real_distribution(profiles: list[dict]) -> None:
    real = sum(REAL_SUBJECTS.values())
    counts = Counter(len(p["subjects"]) for p in profiles)
    assert {n: abs(_share(counts[n], len(profiles)) - r / real) <= 0.10 for n, r in REAL_SUBJECTS.items()} == \
        dict.fromkeys(REAL_SUBJECTS, True)


# ============================================================
# Credit line and guarantees
# ============================================================
def test_a_practice_has_one_credit_line(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if [f["id"] for f in p["fidi"]] != ["F1"]] == []


def test_credit_lines_use_the_set_products_with_their_tooltips(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles for f in p["fidi"]
            if CREDIT_PRODUCTS.get(f["description"]) != (f["tooltip"], f["tooltipField"])] == []


def _texts(practices: list[dict]) -> set[str]:
    rows = [r for p in practices for r in (*p["fidi"], *p["guarantees"])]
    return {t for r in rows for t in (r["description"], r["tooltip"], r["operation"]) if t}


def test_credit_and_guarantee_texts_come_from_the_seed_the_calibration_fold_or_a_generic_invention(profiles: list[dict]) -> None:
    seed = _texts(synthetic_practices())
    assert sorted(_texts(profiles) - seed - set(COPIED_TEXTS) - INVENTED_TEXTS) == []


def test_every_copied_text_appears_in_at_least_two_calibration_practices() -> None:
    assert [text for text, practices in COPIED_TEXTS.items() if practices < 2] == []


def test_no_credit_or_guarantee_text_looks_like_an_ndg_an_amount_or_a_date(profiles: list[dict]) -> None:
    pattern = re.compile(r"\b\d{8}\b|\b\d{1,3}(?:\.\d{3})+(?:,\d\d)?\b|\b\d\d/\d\d/\d{4}\b")
    assert sorted(t for t in _texts(profiles) if pattern.search(t)) == []


@pytest.mark.parametrize("product", CREDIT_PRODUCTS)
def test_each_product_appears_at_least_twice(profiles: list[dict], product: str) -> None:
    assert sum(p["fidi"][0]["description"] == product for p in profiles) >= 2


def test_the_public_guarantee_product_always_has_the_fund(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["fidi"][0]["description"] == "M.CONSAP >=80%" and not _has_fund(p)] == []


def test_only_a_fund_product_has_the_fund(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if _has_fund(p) and p["fidi"][0]["description"] not in FUND_GUARANTEE] == []


def test_the_operation_follows_the_state(profiles: list[dict]) -> None:
    def expected(p: dict) -> str:
        return "Nuova Finanza" if p["state"] == "APP" or p["phase"] == "PRO" else "In Lavoraz."

    assert [p["key"] for p in profiles if p["fidi"][0]["operation"] not in (expected(p), "")] == []


@pytest.mark.parametrize("cell", ["account", "operation"])
def test_a_credit_cell_is_rarely_empty(profiles: list[dict], cell: str) -> None:
    assert 1 <= sum(not p["fidi"][0][cell] for p in profiles) <= 3


@pytest.mark.parametrize("cell", ["account", "operation"])
def test_a_credit_cell_is_empty_only_on_an_abandoned_practice(profiles: list[dict], cell: str) -> None:
    assert {p["state"] for p in profiles if not p["fidi"][0][cell]} <= {"ABB"}


def test_the_due_cell_is_a_month_end_date_or_a_number_of_months(profiles: list[dict]) -> None:
    def ok(p: dict) -> bool:
        due = p["fidi"][0]["due"]
        if months := MONTHS_DUE.fullmatch(due):
            return 120 <= int(months[1]) <= 361
        day, created = _day(due), _day(p["created"])
        return day.month == created.month and day.day == monthrange(day.year, day.month)[1] and day.year - created.year >= 10

    assert [p["key"] for p in profiles if not ok(p)] == []


def test_an_approved_practice_shows_its_duration_in_months(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["state"] == "APP" and not MONTHS_DUE.fullmatch(p["fidi"][0]["due"])] == []


def test_the_share_of_durations_in_months_is_near_the_real_one(profiles: list[dict]) -> None:
    share = _share(sum(bool(MONTHS_DUE.fullmatch(p["fidi"][0]["due"])) for p in profiles), len(profiles))
    assert abs(share - REAL_MONTHS_DUE) <= 0.15


def test_amounts_are_whole_euros_in_the_seed_money_format(profiles: list[dict]) -> None:
    amounts = [a for p in profiles for a in (p["creditTotal"], p["guaranteeTotal"],
                                             *(f["amount"] for f in p["fidi"]), *(g["amount"] for g in p["guarantees"]))]
    assert [a for a in amounts if _money(_cents(a)) != a or _cents(a) % 100] == []


def test_the_share_of_round_thousands_is_near_the_real_one(profiles: list[dict]) -> None:
    share = _share(sum(_cents(p["fidi"][0]["amount"]) % 100_000 == 0 for p in profiles), len(profiles))
    assert abs(share - REAL_ROUND_AMOUNTS) <= 0.15


def test_guarantees_use_the_set_kinds_with_their_tooltips(profiles: list[dict]) -> None:
    assert [(p["key"], g["id"]) for p in profiles for g in p["guarantees"]
            if GUARANTEES.get(g["description"]) != (g["tooltip"], g["tooltipField"])] == []


def test_every_practice_has_one_first_degree_mortgage_without_holder(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles
            if [g["ndgName"] for g in p["guarantees"] if g["description"] == "IPOTECA I GR."] != [""]] == []


def test_the_fund_gives_its_product_guarantee_in_its_name(profiles: list[dict]) -> None:
    def fund_rows(p: dict) -> list[tuple[str, str]]:
        return [(g["description"], g["ndgName"]) for g in p["guarantees"] if g["description"] in FUND_GUARANTEE.values()]

    expected = {p["key"]: [(FUND_GUARANTEE[p["fidi"][0]["description"]], f"{FUND_NDG} {FUND_NAME}")] if _has_fund(p) else []
                for p in profiles}
    assert {p["key"]: fund_rows(p) for p in profiles} == expected


def test_personal_guarantors_give_one_limited_guarantee_in_the_name_of_one_of_them(profiles: list[dict]) -> None:
    def ok(p: dict) -> bool:
        rows = [g["ndgName"] for g in p["guarantees"] if g["description"] == "FID LIM INATTO"]
        names = {f"{s['ndg']} {s['name']}" for s in _guarantors(p)}
        return len(rows) == 1 and rows[0] in names if names else rows == []

    assert [p["key"] for p in profiles if not ok(p)] == []


def test_the_guarantee_operation_follows_the_state(profiles: list[dict]) -> None:
    assert [(p["key"], g["id"]) for p in profiles for g in p["guarantees"]
            if g["operation"] != ("Nuova" if p["state"] == "APP" else "Nuova / In Lavoraz.")] == []


@pytest.mark.parametrize("field", ["tooltip_descrizione_m_consap", "tooltip_descrizione_consap_dr_bis"])
def test_each_public_guarantee_tooltip_is_reachable_in_at_least_two_practices(profiles: list[dict], field: str) -> None:
    # The truth reads tooltips from the first credit line and the first two guarantees (capture states 6-8).
    assert sum(any(r["tooltipField"] == field for r in (*p["fidi"][:1], *p["guarantees"][:2])) for p in profiles) >= 2


def test_the_mortgage_tooltip_is_reachable_in_every_practice(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if not any(g["tooltipField"] == "tooltip_descrizione_ipoteca" for g in p["guarantees"][:2])] == []


# ============================================================
# Internal coherence
# ============================================================
def test_the_credit_total_is_the_credit_line(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["creditTotal"] != p["fidi"][0]["amount"]] == []


def test_the_guarantee_total_is_the_sum_of_the_guarantees(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles
            if p["guaranteeTotal"] != _money(sum(_cents(g["amount"]) for g in p["guarantees"]))] == []


def test_every_guarantee_belongs_to_the_credit_line(profiles: list[dict]) -> None:
    assert [(p["key"], g["id"]) for p in profiles for g in p["guarantees"] if g["creditId"] != "F1"] == []


def test_guarantees_are_numbered_in_order(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles
            if [g["id"] for g in p["guarantees"]] != [f"G{n}" for n in range(1, len(p["guarantees"]) + 1)]] == []


def test_the_list_date_is_the_creation_date(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["date"] != p["created"]] == []


def test_a_practice_is_assigned_within_days_of_its_creation_before_the_viewing_day(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if not _day(p["created"]) <= _day(p["assigned"]) < SCHEDA_TODAY
            or (_day(p["assigned"]) - _day(p["created"])).days > 5] == []


def test_practices_are_created_and_assigned_on_working_days(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if max(_day(p["created"]).weekday(), _day(p["assigned"]).weekday()) > 4] == []


def test_the_main_ndg_is_the_first_subject_as_applicant(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if (p["subjects"][0]["ndg"], p["subjects"][0]["role"]) != (p["ndg"], "Richiedente")] == []


def test_the_applicant_row_shows_the_header_name_or_a_joint_heading_starting_with_it(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles
            if p["subjects"][0]["name"] != p["name"] and not p["subjects"][0]["name"].startswith(p["name"] + ", ")] == []


def test_some_applicant_rows_show_a_joint_heading(profiles: list[dict]) -> None:
    # 3 of the 12 real Soggetti tables name the applicant row with a comma while the header has none.
    assert sum(p["subjects"][0]["name"] != p["name"] for p in profiles) >= 3


def test_no_ndg_repeats_inside_a_practice(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if len({_ndg(s["ndg"]) for s in p["subjects"]}) != len(p["subjects"])] == []


def test_every_practice_shows_the_four_pef_pages(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["pages"] != list(PAGES)] == []


def test_no_practice_has_a_scheda(profiles: list[dict]) -> None:
    # No calibration practice has a Scheda Privati screen: the set adds none.
    assert [p["key"] for p in profiles if p["scheda"] is not None] == []


def test_list_names_are_clear_of_the_list_cell_edge(profiles: list[dict]) -> None:
    # Within 2 px of the 127 px cell the truth's width estimate may disagree with Chrome (list_name_fits).
    assert [p["key"] for p in profiles if abs(_list_width(p["name"]) - LIST_FONT["innerWidth"]) <= 2] == []


def test_applicant_names_are_at_most_twenty_five_characters(profiles: list[dict]) -> None:
    # The real header names have 6 to 20 characters.
    assert [p["key"] for p in profiles if len(p["name"]) > 25] == []


def test_at_least_eight_applicant_names_are_short(profiles: list[dict]) -> None:
    # 6 of the 14 real header names have at most 10 characters.
    assert sum(len(p["name"]) <= 10 for p in profiles) >= 8


# ============================================================
# Branches and operators
# ============================================================
def test_branch_codes_have_two_three_and_four_digits(profiles: list[dict]) -> None:
    assert {len(p["branch"]) for p in profiles if p["branch"].isdigit()} == {2, 3, 4}


def test_at_least_fifteen_branches_are_present(profiles: list[dict]) -> None:
    assert len({p["branch"] for p in profiles}) >= 15


def test_a_branch_keeps_one_name(profiles: list[dict]) -> None:
    pairs = {(p["branch"], p["branchName"]) for p in profiles}
    assert len(pairs) == len({code for code, _ in pairs})


def test_at_least_six_operators_are_present(profiles: list[dict]) -> None:
    assert len({p["assignee"] for p in profiles}) >= 6


@pytest.mark.parametrize("office", ["assigneeName", "officeCode"])
def test_at_least_six_offices_are_present(profiles: list[dict], office: str) -> None:
    assert len({p[office] for p in profiles}) >= 6


def test_the_logged_in_user_is_the_assigned_operator_who_writes_the_note(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if (p["operatorId"], p["operatorName"]) != (p["assignee"], p["noteAuthor"])] == []


def test_the_abi_stays_bper(profiles: list[dict]) -> None:
    # valori.csv has no ABI column, so no other ABI is evidenced; Ricerca Pratica offers 05387 only (search.js).
    assert {p["abi"] for p in profiles} == {"5387"}


# ============================================================
# The request note
# ============================================================
def test_about_a_quarter_of_the_request_notes_are_empty(profiles: list[dict]) -> None:
    assert abs(_share(sum(not p["notes"] for p in profiles), len(profiles)) - REAL_EMPTY_NOTES) <= 0.06


def test_written_note_length_quartiles_are_near_the_real_ones(profiles: list[dict]) -> None:
    quartiles = statistics.quantiles([len(p["notes"]) for p in _written(profiles)], n=4)
    assert [abs(q - r) / r <= 0.15 for q, r in zip(quartiles, REAL_NOTE_QUARTILES)] == [True] * 3


def test_written_notes_span_the_real_range_of_lengths(profiles: list[dict]) -> None:
    lengths = [len(p["notes"]) for p in _written(profiles)]
    assert min(lengths) <= 400 and max(lengths) >= 2500


# 7 of 11 real notes carry the four header lines, 1 only the amount lines, 3 none.
def test_most_written_notes_open_with_the_desk_header(profiles: list[dict]) -> None:
    written = _written(profiles)
    assert 0.5 <= _share(sum(bool(HEADER.match(p["notes"])) for p in written), len(written)) <= 0.75


def test_some_written_notes_open_with_the_amount_lines_only(profiles: list[dict]) -> None:
    assert sum(bool(PARTIAL_HEADER.match(p["notes"])) for p in _written(profiles)) >= 2


def test_some_written_notes_have_no_header(profiles: list[dict]) -> None:
    assert sum(not (HEADER.match(p["notes"]) or PARTIAL_HEADER.match(p["notes"])) for p in _written(profiles)) >= 5


def test_the_header_quotes_the_requested_amount(profiles: list[dict]) -> None:
    def quoted(p: dict) -> str | None:
        match = HEADER.match(p["notes"]) or PARTIAL_HEADER.match(p["notes"])
        return match and match[match.lastindex]

    assert [p["key"] for p in profiles if p["notes"] and quoted(p) not in (None, _money(_cents(p["creditTotal"]), decimals=True))] == []


def test_the_property_value_covers_the_mortgage(profiles: list[dict]) -> None:
    # A fondiario stays within 80% of the value; the CONSAP and non-fondiario products go beyond, never past it.
    limit = {"M.CONSAP >=80%": 0.96, "M. IPOTECARIO": 0.96}
    assert [p["key"] for p in profiles if (m := HEADER.match(p["notes"]))
            and _cents(p["creditTotal"]) / _cents(m[2]) > limit.get(p["fidi"][0]["description"], 0.80)] == []


def test_the_note_quotes_the_credit_amount(profiles: list[dict]) -> None:
    assert [p["key"] for p in _written(profiles) if f"€ {p['creditTotal']}" not in p["notes"]] == []


def test_some_notes_are_written_in_capitals(profiles: list[dict]) -> None:
    # 3 of 11 real notes are mostly upper case.
    assert sum(_capitals(p["notes"]) for p in _written(profiles)) >= 6


def _lines(note: str, width: int) -> int:
    return sum(max(1, -(-len(line) // width)) for line in note.split("\n"))


def _capitals(note: str) -> bool:
    letters = [c for c in note if c.isalpha()]
    return sum(c.isupper() for c in letters) > len(letters) / 2


def _inside(note: str) -> bool:
    # The archive's notes render 120-152 characters per line; capitals are wider, so they get 100.
    return _lines(note, 100 if _capitals(note) else 120) <= REQUEST_NOTE_LINES


def _beyond(note: str) -> bool:
    # This set's lower-case prose reached about 160 per line: a note of 27 lines at 152 showed whole in Chrome.
    return _lines(note, 175) > REQUEST_NOTE_LINES


def test_the_request_note_is_clearly_inside_or_beyond_the_window_of_screen_9(profiles: list[dict]) -> None:
    # The truth estimates 135 characters per line (bper_simulator_truth) and asserts only a note it judges whole.
    assert [p["key"] for p in profiles if not (_inside(p["notes"]) or _beyond(p["notes"]))] == []


def test_long_written_notes_still_fit_on_screen_9(profiles: list[dict]) -> None:
    # The calibration's notes of 2,733 and 2,977 characters were transcribed whole.
    assert sum(len(p["notes"]) > 2000 and _inside(p["notes"]) and request_note_fits(p["notes"]) for p in profiles) >= 5


def test_only_a_few_written_notes_run_beyond_screen_9(profiles: list[dict]) -> None:
    beyond = sum(_beyond(p["notes"]) for p in _written(profiles))
    assert 2 <= beyond <= round(len(_written(profiles)) * REAL_PARTIAL_NOTES) + 2
