"""The LLM-authored practice set: 40 fictitious profiles that widen what the seed generator produces.

bper-emulator/profiles/generated-set-01.json joins the catalogue with --profiles. Its values are written in the
seed's vocabulary and display formats (bper_synthetic_db), so every check here compares it with the seed's own
tables, never with the real archive: load_profiles does that collision check and prints no value.
"""

from calendar import monthrange
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
import re

import pytest

from bper_profiles import PAGES, load_profiles
from bper_simulator_catalog import ensure_database, read_catalog
from bper_simulator_truth import LIST_FONT, REQUEST_NOTE_LINES
from bper_synthetic_db import (
    BANK, BRANCHES, CONS_KEY, CONS_PRODUCT, EMPTY_MONTH, FUND_KEY, FUND_NAME, FUND_NDG, MONTHS, MORTGAGE_KEY,
    OFFICE_CODE, OPERATORS, SCENARIOS, SCHEDA_TODAY, STAGES, _money, product_for, synthetic_practices,
    validation_age,
)

REPO = Path(__file__).resolve().parents[1]
ARCHIVE = REPO / "data" / "dataset"
PROFILES = REPO / "bper-emulator" / "profiles" / "generated-set-01.json"

FUND_ROLE = "Nuovo Garante/nuovo Datore Di Pegno"
ROLES = ("Richiedente", "Cointestatario", "Garante", FUND_ROLE)
SPESE = ("P. SPESE", "315014 - PRESTITO PER SPESE TECNICHE", None)
CREDIT_PRODUCTS = {s.product: (s.product, s.tooltip, CONS_KEY if s.product == CONS_PRODUCT else None)
                   for s in SCENARIOS} | {SPESE[0]: SPESE}
# description: (tooltip, tooltipField, share of the first credit line in percent)
GUARANTEES = {
    "CONSAP DR BIS": ("457-IMP. FID. F.DO 1 CASA DR SOSTEGNI BIS", FUND_KEY, 80),
    "IPOTECA I GR.": ("55-IPOTECA DI PRIMO GRADO", MORTGAGE_KEY, 150),
    "GAR. PERS.": ("901-FIDEIUSSIONE PERSONALE SPECIFICA", None, 20),
}
# The request note names the applicant's employment once, in this sentence, with one of these phrases (masculine or
# feminine); EMPLOYMENTS names each kind.
APPLICANT = re.compile(r"Richiedente di (\d{2}) anni, (pensionat[oa]|lavorat(?:ore|rice) autonom[oa]"
                       r"|dipendente a tempo indeterminato|dipendente a tempo determinato|senza datore di lavoro)\b")
EMPLOYMENTS = {"pensionata": "pensionato", "lavoratrice autonoma": "lavoratore autonomo"}
HEADER = re.compile(r"- Numero proposta DESK: (\d{7})\n- Valore immobile presunto: ([\d.]+,\d\d)\n"
                    r"- Dettaglio importi mutuo:\n {7}IMPORTO RICHIESTO : ([\d.]+,\d\d) €\n")
SELF_EMPLOYED = ("LIBERO PROFESSIONISTA", "ARTIGIANO", "COMMERCIANTE", "AGENTE DI COMMERCIO")
WITHOUT_EMPLOYER = ("BENESTANTE", "CASALINGA", "STUDENTE")
STAMP = re.compile(r"(\d\d/\d\d/\d{4}) (\d\d):(\d\d) \((.+ fa)\)")


@pytest.fixture(scope="module")
def profiles() -> list[dict]:
    return load_profiles(PROFILES, archive=ARCHIVE)


@pytest.fixture(scope="module")
def seed() -> list[dict]:
    return synthetic_practices()


def _cents(money: str) -> int:
    whole, _, fraction = money.partition(",")
    return int(whole.replace(".", "")) * 100 + int(fraction or 0)


def _day(display: str) -> date:
    return datetime.strptime(display, "%d/%m/%Y").date()


def _month(display: str) -> int:
    """A page month ('MAGGIO 2016') as a month index."""
    name, year = display.split()
    return int(year) * 12 + MONTHS.index(name.lower())


def _ndg(value: str) -> str:
    return value.lstrip("0") or "0"


def _narrative(profile: dict) -> str:
    """The request note after its four header lines."""
    return HEADER.sub("", profile["notes"], count=1)


def _employment(profile: dict) -> tuple[int, str]:
    age, kind = APPLICANT.findall(profile["notes"])[0]
    return int(age), EMPLOYMENTS.get(kind, kind)


def _years(profile: dict, credit: dict) -> int:
    return _day(credit["due"]).year - _day(profile["created"]).year


def _list_width(name: str) -> float:
    advance, kerning = LIST_FONT["advance"], LIST_FONT["kerning"]
    return sum(advance[c] for c in name) + sum(kerning.get(a + b, 0.0) for a, b in zip(name, name[1:]))


# ============================================================
# Identity: keys, numbers, NDGs
# ============================================================
# Identifiers that must not repeat in the file nor reuse one of the seed: what each one reads and its format.
IDENTIFIERS: dict[str, tuple[Callable[[list[dict]], list[str]], str]] = {
    "practice number": (lambda ps: [p["number"] for p in ps], r"\d{8}"),
    "proposal number": (lambda ps: [HEADER.match(p["notes"])[1] for p in ps], r"\d{7}"),
    "scheda id": (lambda ps: [p["scheda"]["schedaId"] for p in ps if p["scheda"]], r"\d{11}"),
    "account": (lambda ps: [f["account"] for p in ps for f in p["fidi"]], r"034 9\d{3} 001[78] \d{8}"),
}


def test_the_file_holds_forty_practices_keyed_gen_001_to_gen_040(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles] == [f"gen-{n:03}" for n in range(1, 41)]


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
def test_identifiers_are_outside_the_seed_catalogue(profiles: list[dict], seed: list[dict], identifier: str) -> None:
    read = IDENTIFIERS[identifier][0]
    assert not set(read(profiles)) & set(read(seed))


def test_accounts_name_the_practice_branch(profiles: list[dict]) -> None:
    assert [f["account"] for p in profiles for f in p["fidi"] if f["account"].split()[1] != p["branch"]] == []


def test_each_person_ndg_is_eight_digits(profiles: list[dict]) -> None:
    assert [s["ndg"] for p in profiles for s in p["subjects"] if not re.fullmatch(r"\d{8}", s["ndg"])] == []


def test_each_person_ndg_appears_once_in_the_file(profiles: list[dict]) -> None:
    ndgs = [_ndg(s["ndg"]) for p in profiles for s in p["subjects"] if s["ndg"] != FUND_NDG]
    assert len(set(ndgs)) == len(ndgs)


def test_no_ndg_collides_with_the_seed_catalogue(profiles: list[dict], seed: list[dict]) -> None:
    def ndgs(practices: list[dict]) -> set[str]:
        found = {s["ndg"] for p in practices for s in p["subjects"]}
        found |= {p["scheda"]["details"]["employerNdg"] for p in practices if p["scheda"]}
        return {_ndg(n) for n in found if n.strip() and n != "0"} - {FUND_NDG}

    assert not ndgs(profiles) & ndgs(seed)


def test_employer_ndgs_are_not_person_ndgs(profiles: list[dict]) -> None:
    people = {_ndg(s["ndg"]) for p in profiles for s in p["subjects"]}
    employers = {_ndg(p["scheda"]["details"]["employerNdg"]) for p in profiles if p["scheda"]}
    assert not people & (employers - {"0"})


def test_the_fund_is_never_the_applicant(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if FUND_NDG in (p["ndg"], (p["scheda"] or {}).get("ndg"))] == []


def test_the_fund_subject_carries_the_fund_name_and_role(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles for s in p["subjects"]
            if s["ndg"] == FUND_NDG and s != {"ndg": FUND_NDG, "name": FUND_NAME, "role": FUND_ROLE}] == []


def test_the_fund_subject_gives_the_fund_guarantee_in_its_name(profiles: list[dict]) -> None:
    def fund_subjects(p: dict) -> list[str]:
        return [f"{s['ndg']} {s['name']}" for s in p["subjects"] if s["ndg"] == FUND_NDG]

    assert [p["key"] for p in profiles
            if fund_subjects(p) != [g["ndgName"] for g in p["guarantees"] if g["description"] == "CONSAP DR BIS"]] == []


# ============================================================
# Vocabulary of the seed generator
# ============================================================
def test_product_codes_come_from_the_seed_product_table(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles
            if (p["typeCode"], p["typeName"]) != product_for(p["type"], p["evidence"])] == []


def test_states_and_phases_come_from_the_seed_stages(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if (p["state"], p["phase"]) not in STAGES] == []


def test_evidence_is_b_with_its_tooltip_or_empty_without(profiles: list[dict]) -> None:
    assert {(p["evidence"], p["evidenceTooltip"]) for p in profiles} <= {("B", "Origination BSTORE"), ("", "")}


def test_branches_come_from_the_seed_branch_table(profiles: list[dict]) -> None:
    branches = {code: name for code, name, _ in BRANCHES}
    assert [p["key"] for p in profiles if branches.get(p["branch"]) != p["branchName"]] == []


def test_each_practice_is_assigned_to_a_seed_operator_who_writes_its_note(profiles: list[dict]) -> None:
    operators = {code: (office, name) for code, name, office in OPERATORS}
    assert [p["key"] for p in profiles
            if operators.get(p["assignee"]) != (p["assigneeName"], p["noteAuthor"])] == []


def test_the_logged_in_user_is_the_seed_one(profiles: list[dict]) -> None:
    assert {(p["abi"], p["operatorId"], p["operatorName"], p["officeCode"]) for p in profiles} == {
        ("5387", OPERATORS[0][0], OPERATORS[0][1], OFFICE_CODE)}


def test_personal_loans_go_to_retail_offices(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["type"] == "BPI Privati" and "PRIVATI" not in p["assigneeName"]] == []


def test_the_scenario_is_a_seed_scenario_naming_the_first_credit_line(profiles: list[dict]) -> None:
    scenarios = {s.label: s.product for s in SCENARIOS}
    assert [p["key"] for p in profiles if scenarios.get(p["scenario"]) != p["fidi"][0]["description"]] == []


def test_the_personal_loan_type_goes_with_the_energy_product(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles
            if (p["type"] == "BPI Privati") != (p["fidi"][0]["description"] == "P. ENERGIA")] == []


def test_credit_lines_use_the_seed_products_with_their_tooltips(profiles: list[dict]) -> None:
    assert [(p["key"], f["id"]) for p in profiles for f in p["fidi"]
            if CREDIT_PRODUCTS.get(f["description"]) != (f["description"], f["tooltip"], f["tooltipField"])] == []


def test_credit_lines_are_being_worked(profiles: list[dict]) -> None:
    assert {f["operation"] for p in profiles for f in p["fidi"]} == {"In Lavoraz."}


def test_a_practice_has_one_or_two_credit_lines_numbered_in_order(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if [f["id"] for f in p["fidi"]] not in (["F1"], ["F1", "F2"])] == []


def test_guarantees_use_the_seed_kinds_with_their_tooltips(profiles: list[dict]) -> None:
    assert [(p["key"], g["id"]) for p in profiles for g in p["guarantees"]
            if GUARANTEES.get(g["description"], (None, None, 0))[:2] != (g["tooltip"], g["tooltipField"])] == []


def test_guarantees_are_new_and_being_worked(profiles: list[dict]) -> None:
    assert {g["operation"] for p in profiles for g in p["guarantees"]} <= {"Nuova / In Lavoraz."}


def test_each_guarantee_amount_is_the_seed_share_of_the_first_line(profiles: list[dict]) -> None:
    assert [(p["key"], g["id"]) for p in profiles for g in p["guarantees"]
            if _cents(g["amount"]) != _cents(p["fidi"][0]["amount"]) * GUARANTEES[g["description"]][2] // 100] == []


def test_guarantees_are_numbered_in_order(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles
            if [g["id"] for g in p["guarantees"]] != [f"G{n}" for n in range(1, len(p["guarantees"]) + 1)]] == []


def test_a_mortgage_has_one_first_degree_mortgage(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["type"] == "BPI Mutui"
            and sum(g["description"] == "IPOTECA I GR." for g in p["guarantees"]) != 1] == []


def test_a_personal_loan_has_no_guarantee(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["type"] == "BPI Privati" and p["guarantees"]] == []


def test_each_guarantor_gives_one_personal_guarantee_in_its_name(profiles: list[dict]) -> None:
    wrong = [p["key"] for p in profiles
             if sorted(f"{s['ndg']} {s['name']}" for s in p["subjects"] if s["role"] == "Garante")
             != sorted(g["ndgName"] for g in p["guarantees"] if g["description"] == "GAR. PERS.")]
    assert wrong == []


def test_the_mortgage_has_no_holder(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles for g in p["guarantees"] if g["description"] == "IPOTECA I GR." and g["ndgName"]] == []


def test_the_mortgage_comes_second_after_another_guarantee(profiles: list[dict]) -> None:
    # The seed lists the fund and the guarantors in subject order and inserts the mortgage at position 2.
    def position(p: dict) -> int:
        return [g["description"] for g in p["guarantees"]].index("IPOTECA I GR.")

    assert [p["key"] for p in profiles if p["type"] == "BPI Mutui"
            and position(p) != min(1, len(p["guarantees"]) - 1)] == []


def test_only_the_public_guarantee_scenario_has_the_fund(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if any(s["ndg"] == FUND_NDG for s in p["subjects"])
            != (p["fidi"][0]["description"] == CONS_PRODUCT)] == []


# ============================================================
# Internal coherence
# ============================================================
def test_the_credit_total_is_the_sum_of_the_credit_lines(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["creditTotal"] != _money(sum(_cents(f["amount"]) for f in p["fidi"]))] == []


def test_the_guarantee_total_is_the_sum_of_the_guarantees(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles
            if p["guaranteeTotal"] != _money(sum(_cents(g["amount"]) for g in p["guarantees"]))] == []


def test_amounts_are_in_the_seed_money_format(profiles: list[dict]) -> None:
    amounts = [a for p in profiles for a in (p["creditTotal"], p["guaranteeTotal"],
                                             *(f["amount"] for f in p["fidi"]), *(g["amount"] for g in p["guarantees"]))]
    assert [a for a in amounts if _money(_cents(a)) != a] == []


def test_every_guarantee_belongs_to_a_credit_line_of_its_practice(profiles: list[dict]) -> None:
    assert [(p["key"], g["id"]) for p in profiles for g in p["guarantees"]
            if g["creditId"] not in {f["id"] for f in p["fidi"]}] == []


def test_the_list_date_is_the_creation_date(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["date"] != p["created"]] == []


def test_a_practice_is_assigned_within_days_of_its_creation_before_the_viewing_day(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if not date(2025, 9, 1) <= _day(p["created"]) <= _day(p["assigned"]) < SCHEDA_TODAY
            or (_day(p["assigned"]) - _day(p["created"])).days > 5] == []


def test_practices_are_created_and_assigned_on_working_days(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if max(_day(p["created"]).weekday(), _day(p["assigned"]).weekday()) > 4] == []


def test_due_dates_end_the_month_of_creation_after_whole_years(profiles: list[dict]) -> None:
    wrong = []
    for p in profiles:
        created = _day(p["created"])
        for f in p["fidi"]:
            due = _day(f["due"])
            if due.month != created.month or due.day != monthrange(due.year, due.month)[1] or _years(p, f) < 5:
                wrong.append((p["key"], f["id"]))
    assert wrong == []


def test_the_main_ndg_is_the_first_subject_as_applicant(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles
            if p["subjects"][0] != {"ndg": p["ndg"], "name": p["name"], "role": "Richiedente"}] == []


def test_a_practice_has_one_to_four_subjects(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if not 1 <= len(p["subjects"]) <= 4] == []


def test_no_ndg_repeats_inside_a_practice(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if len({_ndg(s["ndg"]) for s in p["subjects"]}) != len(p["subjects"])] == []


def test_subject_roles_come_from_the_seed_and_only_the_first_applies(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles
            if any(s["role"] not in ROLES[1:] for s in p["subjects"][1:])] == []


def test_every_practice_shows_the_four_pages_of_its_content(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["pages"] != list(PAGES)
            or not (p["subjects"] and p["fidi"] and p["notes"].strip())] == []


def test_the_scheda_belongs_to_the_applicant(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if p["scheda"] and (p["scheda"]["ndg"], p["scheda"]["name"]) != (p["ndg"], p["name"])] == []


def test_the_set_joins_the_catalogue_beside_the_seed(tmp_path: Path) -> None:
    ensure_database(tmp_path / "seed.sqlite3")
    catalog = read_catalog(tmp_path / "seed.sqlite3", False, profiles=[PROFILES])
    assert [p["key"] for p in catalog["practices"]][-40:] == [f"gen-{n:03}" for n in range(1, 41)]


# ============================================================
# The request note
# ============================================================
def test_the_note_header_quotes_the_total_of_the_credit_lines(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if not HEADER.match(p["notes"])
            or HEADER.match(p["notes"])[3] != _money(_cents(p["creditTotal"]), decimals=True)] == []


def test_the_note_has_one_to_four_paragraphs(profiles: list[dict]) -> None:
    def paragraphs(p: dict) -> list[str]:
        return _narrative(p).split("\n")

    assert [p["key"] for p in profiles if not 1 <= len(paragraphs(p)) <= 4 or not all(x.strip() for x in paragraphs(p))] == []


def test_the_note_quotes_each_credit_line_amount(profiles: list[dict]) -> None:
    assert [(p["key"], f["id"]) for p in profiles for f in p["fidi"] if f"€ {f['amount']}" not in _narrative(p)] == []


def test_the_note_quotes_each_credit_line_duration(profiles: list[dict]) -> None:
    assert [(p["key"], f["id"]) for p in profiles for f in p["fidi"] if f"{_years(p, f)} anni" not in _narrative(p)] == []


def test_the_note_names_the_applicant_employment_once(profiles: list[dict]) -> None:
    assert [p["key"] for p in profiles if len(APPLICANT.findall(p["notes"])) != 1] == []


def test_the_applicant_age_fits_the_loan(profiles: list[dict]) -> None:
    wrong = []
    for p in profiles:
        age, kind = _employment(p)
        if not 20 <= age <= 75 or age + _years(p, p["fidi"][0]) > 80 or (kind == "pensionato" and age < 60) \
                or (p["fidi"][0]["description"] == CONS_PRODUCT and age >= 36):
            wrong.append(p["key"])
    assert wrong == []


def test_the_property_value_covers_the_mortgage(profiles: list[dict]) -> None:
    def ratio(p: dict) -> float:
        return _cents(p["creditTotal"]) / _cents(HEADER.match(p["notes"])[2])

    limit = {CONS_PRODUCT: 0.90, "P. ENERGIA": 0.40}
    assert [p["key"] for p in profiles if ratio(p) > limit.get(p["fidi"][0]["description"], 0.80)] == []


def test_the_request_note_is_clearly_inside_or_beyond_the_window_of_screen_9(profiles: list[dict]) -> None:
    def lines(note: str, width: int) -> int:
        return sum(max(1, -(-len(line) // width)) for line in note.split("\n"))

    # The page wraps 120 to 152 characters per line; the truth estimates 135 (bper_simulator_truth).
    assert [p["key"] for p in profiles
            if not (lines(p["notes"], 120) <= REQUEST_NOTE_LINES or lines(p["notes"], 152) > REQUEST_NOTE_LINES)] == []


def test_list_names_are_clear_of_the_list_cell_edge(profiles: list[dict]) -> None:
    # Within 2 px of the 127 px cell the truth's width estimate may disagree with Chrome (list_name_fits).
    assert [p["key"] for p in profiles if abs(_list_width(p["name"]) - LIST_FONT["innerWidth"]) <= 2] == []


# ============================================================
# Scheda Privati
# ============================================================
def _schede(profiles: list[dict]) -> list[tuple[dict, dict]]:
    return [(p, p["scheda"]) for p in profiles if p["scheda"]]


def test_the_scheda_fields_agree_with_the_applicant_employment(profiles: list[dict]) -> None:
    wrong = []
    for p, s in _schede(profiles):
        f, d = s["fields"], s["details"]
        boxless = f["datore_di_lavoro_anagrafica"] == d["employerNdg"] == "" and not d["employerRegistered"] \
            and d["employerFrom"] == d["employerTo"] == EMPTY_MONTH
        employed = f["datore_di_lavoro_anagrafica"] != "" and d["employerNdg"] != "" and d["employerFrom"] != EMPTY_MONTH
        ok = {
            "pensionato": boxless and f["tipo_contratto"] == "" and f["professione_principale"] == "PENSIONATO"
                          and f["numero_mensilita"] == "13",
            "lavoratore autonomo": boxless and f["tipo_contratto"] == "LAVORATORE AUTONOMO"
                                   and f["professione_principale"] in SELF_EMPLOYED and f["numero_mensilita"] == "1",
            "senza datore di lavoro": boxless and f["tipo_contratto"] == "" and f["professione_principale"] in WITHOUT_EMPLOYER,
            "dipendente a tempo indeterminato": employed and f["tipo_contratto"] == "TEMPO INDETERMINATO"
                                                and d["employerTo"] == EMPTY_MONTH,
            "dipendente a tempo determinato": employed and f["tipo_contratto"] == "TEMPO DETERMINATO"
                                              and d["employerTo"] != EMPTY_MONTH,
        }[_employment(p)[1]]
        if not ok:
            wrong.append(p["key"])
    assert wrong == []


def test_scheda_payments_are_one_for_the_self_employed_else_twelve_to_fourteen(profiles: list[dict]) -> None:
    def allowed(p: dict) -> tuple[str, ...]:
        return ("1",) if _employment(p)[1] == "lavoratore autonomo" else ("12", "13", "14")

    assert [p["key"] for p, s in _schede(profiles) if s["fields"]["numero_mensilita"] not in allowed(p)] == []


def test_scheda_net_pay_is_a_plausible_amount_in_the_seed_format(profiles: list[dict]) -> None:
    def pay(s: dict) -> str:
        return s["fields"]["retribuzione_annua_netta"]

    assert [p["key"] for p, s in _schede(profiles)
            if not 9_000_00 <= _cents(pay(s)) <= 120_000_00 or _money(_cents(pay(s))) != pay(s)] == []


def test_household_earners_do_not_exceed_its_other_members(profiles: list[dict]) -> None:
    assert [p["key"] for p, s in _schede(profiles)
            if int(s["fields"]["di_cui_percepiscono_reddito"]) > int(s["fields"]["nr_altri_componenti_nucleo"])] == []


def test_household_income_is_there_exactly_when_someone_earns_it(profiles: list[dict]) -> None:
    def income(s: dict) -> str:
        return s["fields"]["importo_totale_annuo_nucleo"]

    assert [p["key"] for p, s in _schede(profiles) if _money(_cents(income(s))) != income(s)
            or (s["fields"]["di_cui_percepiscono_reddito"] == "0") != (_cents(income(s)) == 0)] == []


def test_a_co_holder_lives_in_the_applicants_household(profiles: list[dict]) -> None:
    assert [p["key"] for p, s in _schede(profiles) if any(x["role"] == "Cointestatario" for x in p["subjects"])
            and int(s["fields"]["nr_altri_componenti_nucleo"]) < 1] == []


def test_the_scheda_job_starts_in_the_applicants_working_life(profiles: list[dict]) -> None:
    def bounds(p: dict) -> tuple[int, int]:
        created = _day(p["created"])
        return (created.year - _employment(p)[0] + 16) * 12, created.year * 12 + created.month - 1

    assert [p["key"] for p, s in _schede(profiles)
            if not bounds(p)[0] <= _month(s["fields"]["dal"]) <= bounds(p)[1]] == []


def test_the_scheda_housing_starts_after_the_applicant_came_of_age(profiles: list[dict]) -> None:
    def born(p: dict) -> int:
        return _day(p["created"]).year - _employment(p)[0]

    assert [p["key"] for p, s in _schede(profiles)
            if not born(p) + 18 <= int(s["details"]["housingFrom"]) <= _day(p["created"]).year] == []


def test_the_employment_with_the_employer_starts_no_later_than_the_job(profiles: list[dict]) -> None:
    assert [p["key"] for p, s in _schede(profiles) if s["details"]["employerFrom"] != EMPTY_MONTH
            and _month(s["details"]["employerFrom"]) > _month(s["fields"]["dal"])] == []


def test_a_fixed_term_contract_ends_after_the_practice_is_created(profiles: list[dict]) -> None:
    def created(p: dict) -> int:
        return _day(p["created"]).year * 12 + _day(p["created"]).month - 1

    assert [p["key"] for p, s in _schede(profiles) if s["details"]["employerTo"] != EMPTY_MONTH
            and _month(s["details"]["employerTo"]) <= created(p)] == []


def test_the_scheda_was_validated_on_a_working_day_after_the_assignment(profiles: list[dict]) -> None:
    wrong = []
    for p, s in _schede(profiles):
        match = STAMP.fullmatch(s["fields"]["ultima_validazione_scheda"])
        day = _day(match[1]) if match else None
        if day is None or not _day(p["assigned"]) <= day < SCHEDA_TODAY or day.weekday() > 4 \
                or not "08" <= match[2] <= "18":
            wrong.append(p["key"])
    assert wrong == []


def test_the_validation_stamp_counts_the_days_to_the_viewing_day(profiles: list[dict]) -> None:
    def stamp(s: dict) -> re.Match:
        return STAMP.fullmatch(s["fields"]["ultima_validazione_scheda"])

    assert [p["key"] for p, s in _schede(profiles)
            if stamp(s)[4] != validation_age((SCHEDA_TODAY - _day(stamp(s)[1])).days)] == []


def test_the_last_change_is_the_last_validation(profiles: list[dict]) -> None:
    assert [p["key"] for p, s in _schede(profiles) if s["lastChange"]["when"] != s["fields"]["ultima_validazione_scheda"]] == []


def test_the_scheda_staff_is_the_practice_operator_at_its_branch(profiles: list[dict]) -> None:
    def staff(p: dict) -> dict:
        return {"user": f"{p['assignee'][-5:]} {p['noteAuthor'].upper()}",
                "branch": f"{p['branch']}-0000-0000 {p['branchName']}", "bank": BANK}

    assert [p["key"] for p, s in _schede(profiles) if s["lastValidation"] != staff(p)
            or {k: v for k, v in s["lastChange"].items() if k != "when"} != staff(p)] == []


def test_the_scheda_user_is_the_seed_logged_in_user(profiles: list[dict]) -> None:
    assert [p["key"] for p, s in _schede(profiles)
            if s["operator"] != {"code": f"{OPERATORS[0][0]} - {OFFICE_CODE}", "name": OPERATORS[0][1]}] == []


def test_employer_details_follow_its_registration(profiles: list[dict]) -> None:
    wrong = []
    for p, s in _schede(profiles):
        f, d = s["fields"], s["details"]
        if d["employerRegistered"]:
            ok = re.fullmatch(r"\d{8}", d["employerNdg"]) and f["rating_ufficiale"] != "" and f["score_cgs"] != ""
        else:
            ok = d["employerNdg"] in ("0", "") and (f["rating_ufficiale"], f["score_cgs"]) == ("N/D", "N/D")
        if not ok:
            wrong.append(p["key"])
    assert wrong == []


def test_scheda_details_use_the_seed_choices(profiles: list[dict]) -> None:
    assert [p["key"] for p, s in _schede(profiles)
            if s["details"]["incomeChanneled"] not in ("SI", "NO") or s["details"]["housing"] not in ("AFFITTO", "PROPRIETA'")
            or s["details"]["creditCardBalance"] not in ("SI", "NO", "NON SO")] == []


def test_an_employer_keeps_one_ndg_across_the_set(profiles: list[dict]) -> None:
    pairs = {(s["fields"]["datore_di_lavoro_anagrafica"], s["details"]["employerNdg"]) for _, s in _schede(profiles)
             if s["details"]["employerRegistered"]}
    assert len({name for name, _ in pairs}) == len(pairs) == len({ndg for _, ndg in pairs})


def test_the_scheda_note_is_one_line_paragraphs_between_blank_lines(profiles: list[dict]) -> None:
    def well_formed(note: str) -> bool:
        lines = note.split("\n")
        return (note.startswith("\n") and note.endswith("\n") and len(lines) % 2 == 1
                and all(line == "" for line in lines[0::2]) and all(0 < len(line) <= 150 for line in lines[1::2]))

    assert [p["key"] for p, s in _schede(profiles) if not well_formed(s["fields"]["note_scheda_privati"])] == []


def test_the_scheda_note_quotes_the_main_credit_line_amount(profiles: list[dict]) -> None:
    assert [p["key"] for p, s in _schede(profiles)
            if f"€ {p['fidi'][0]['amount']}" not in s["fields"]["note_scheda_privati"]] == []


def test_the_scheda_note_quotes_the_main_credit_line_duration(profiles: list[dict]) -> None:
    assert [p["key"] for p, s in _schede(profiles)
            if f"{_years(p, p['fidi'][0])} anni" not in s["fields"]["note_scheda_privati"]] == []


# ============================================================
# Coverage: what the set adds to the seed
# ============================================================
@pytest.mark.parametrize(("employment", "minimum"), [
    ("pensionato", 10), ("lavoratore autonomo", 8), ("dipendente a tempo indeterminato", 10),
    ("dipendente a tempo determinato", 4), ("senza datore di lavoro", 4),
])
def test_the_set_covers_each_kind_of_applicant(profiles: list[dict], employment: str, minimum: int) -> None:
    assert sum(_employment(p)[1] == employment for p in profiles) >= minimum


def test_the_applicants_without_employer_all_show_their_scheda(profiles: list[dict]) -> None:
    assert all(p["scheda"] for p in profiles if _employment(p)[1] == "senza datore di lavoro")


def test_at_least_six_practices_are_joint(profiles: list[dict]) -> None:
    assert sum(any(s["role"] == "Cointestatario" for s in p["subjects"]) for p in profiles) >= 6


def test_some_practices_have_a_personal_guarantor(profiles: list[dict]) -> None:
    assert sum(any(s["role"] == "Garante" for s in p["subjects"]) for p in profiles) >= 4


def test_some_practice_fills_all_four_subject_rows(profiles: list[dict]) -> None:
    assert any(len(p["subjects"]) == 4 for p in profiles)


def test_at_least_eight_practices_have_two_credit_lines(profiles: list[dict]) -> None:
    assert sum(len(p["fidi"]) == 2 for p in profiles) >= 8


def test_at_least_eight_practices_have_no_guarantee(profiles: list[dict]) -> None:
    assert sum(not p["guarantees"] for p in profiles) >= 8


def test_at_least_eight_practices_have_two_guarantees(profiles: list[dict]) -> None:
    assert sum(len(p["guarantees"]) == 2 for p in profiles) >= 8


def test_both_working_and_suspended_practices_are_present(profiles: list[dict]) -> None:
    assert {p["state"] for p in profiles} == {"LAV", "SOSP"}


def test_at_least_four_phases_are_present(profiles: list[dict]) -> None:
    assert len({p["phase"] for p in profiles}) >= 4


def test_at_least_six_branches_are_present(profiles: list[dict]) -> None:
    assert len({p["branch"] for p in profiles}) >= 6


def test_at_least_four_operators_are_present(profiles: list[dict]) -> None:
    assert len({p["assignee"] for p in profiles}) >= 4


def test_at_least_three_request_notes_are_very_long(profiles: list[dict]) -> None:
    assert sum(len(p["notes"]) > 3000 for p in profiles) >= 3


def test_at_least_six_applicant_names_are_long(profiles: list[dict]) -> None:
    assert sum(len(p["name"]) > 30 for p in profiles) >= 6


def test_at_least_three_applicant_names_are_short(profiles: list[dict]) -> None:
    assert sum(len(p["name"]) <= 10 for p in profiles) >= 3


def test_six_practices_have_no_scheda(profiles: list[dict]) -> None:
    assert sum(p["scheda"] is None for p in profiles) == 6
