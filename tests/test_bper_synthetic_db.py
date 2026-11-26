import csv
from contextlib import closing
from datetime import date, datetime
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import re
import sqlite3

import pytest

from bper_synthetic_db import (
    APPLICATION_ID, EMPLOYMENTS, FUND_NAME, PENSIONERS, SCHEDA_TODAY, build_database, set_aside_older,
    synthetic_practices, validation_age,
)
from bper_simulator_truth import NOTE_LINE_CHARS
from extraction.normalization import normalize_ndg

REPO = Path(__file__).resolve().parents[1]
MONTHS = ("GENNAIO", "FEBBRAIO", "MARZO", "APRILE", "MAGGIO", "GIUGNO", "LUGLIO", "AGOSTO",
          "SETTEMBRE", "OTTOBRE", "NOVEMBRE", "DICEMBRE")
EMPTY_MONTH = "--------- ----"


def cents(display: str) -> int:
    return int(100 * Decimal(display.replace(".", "").replace(",", ".")))


def euros(display: str) -> int:
    assert re.fullmatch(r"\d{1,3}(\.\d{3})*", display), display
    return int(display.replace(".", ""))


def day(display: str) -> date:
    return datetime.strptime(display, "%d/%m/%Y").date()


def month(display: str) -> tuple[int, int]:
    name, year = display.split(" ")
    return int(year), MONTHS.index(name) + 1


def scheda_field_keys() -> set[str]:
    """The 13 extracted fields whose source page is Scheda Privati, from the canonical definitions."""
    path = REPO / "src" / "extraction" / "field_definitions.py"
    # Load the file alone: importing the package would pull in the VLM runtime.
    spec = importlib.util.spec_from_file_location("scheda_field_definitions", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {key for key, value in module.CANONICAL_FIELD_DEFINITIONS.items() if value["page_key"] == "scheda_privati"}


def employment(profile: dict) -> str:
    return next(text for text in EMPLOYMENTS if text in profile["notes"])


def paragraphs(note: str) -> list[str]:
    return note.strip("\n").split("\n\n")


def applicant(profile: dict) -> tuple[int, str, int]:
    """Age and employment of the applicant and the loan term, as the request note states them."""
    age, work = re.search(r"Richiedente di (\d+) anni, ([^.]+)\. ", profile["notes"]).groups()
    years = re.search(r"linea principale in (\d+) anni", profile["notes"]).group(1)
    return int(age), work, int(years)


def older_database(path: Path, version: int = 1) -> bytes:
    """A database this simulator wrote at an earlier schema version."""
    with closing(sqlite3.connect(path)) as con:
        con.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        con.execute(f"PRAGMA user_version = {version}")
        con.execute("CREATE TABLE practice (key TEXT PRIMARY KEY)")
        con.execute("INSERT INTO practice VALUES ('pratica-locale')")
        con.commit()
    return path.read_bytes()


def test_catalog_has_reproducible_distinct_customer_identities() -> None:
    profiles = synthetic_practices()
    assert len(profiles) == 64
    assert len({row["ndg"] for row in profiles}) == len(profiles)
    assert len({row["number"] for row in profiles}) == len(profiles)
    assert profiles == synthetic_practices()
    assert len({row["scenario"] for row in profiles[:3]}) == 3
    assert {len(row["subjects"]) for row in profiles} == {1, 2, 3, 4}


def test_demo_deep_link_preserves_its_original_dossier() -> None:
    first = synthetic_practices()[0]
    assert (first["key"], first["ndg"], first["name"], first["number"]) == (
        "demo", "90000001", "ALBA MARTINA", "99000001"
    )
    assert [s["ndg"] for s in first["subjects"]] == ["90000001", "90000002"]
    # The last block changed on purpose: one leading zero and varied digits, as real accounts show (the old
    # "00000001" was misread by the live OCR; tests/test_bper_account_numbers.py).
    assert first["fidi"][0]["account"] == "034 9001 0017 02868929"
    assert first["creditTotal"] == "120.000"
    assert first["guaranteeTotal"] == "204.000"


def test_dossier_totals_and_notes_follow_the_booked_credit_amounts() -> None:
    profiles = synthetic_practices()
    assert any(len(p["fidi"]) > 1 for p in profiles)
    assert any(not p["guarantees"] for p in profiles)
    assert any("," in p["creditTotal"] for p in profiles)
    for row in profiles:
        assert cents(row["creditTotal"]) == sum(cents(c["amount"]) for c in row["fidi"])
        assert cents(row["guaranteeTotal"]) == sum(cents(g["amount"]) for g in row["guarantees"])
        assert (row["creditTotal"] if "," in row["creditTotal"] else row["creditTotal"] + ",00") in row["notes"]
        assert row["subjects"][0]["ndg"] == row["ndg"]
        assert {g["creditId"] for g in row["guarantees"]} <= {c["id"] for c in row["fidi"]}
        created = date.fromisoformat("-".join(reversed(row["created"].split("/"))))
        for credit in row["fidi"]:
            assert date.fromisoformat("-".join(reversed(credit["due"].split("/")))) > created


def test_disk_catalog_drives_the_same_profiles_as_the_default_seed(tmp_path: Path) -> None:
    path = tmp_path / "sim.sqlite"
    build_database(path)
    assert synthetic_practices(path) == synthetic_practices()
    with sqlite3.connect(path) as con:
        con.execute("UPDATE subject SET name='ALBA TEST' WHERE ndg='90000001'")
    build_database(path)
    assert synthetic_practices(path)[0]["name"] == "ALBA TEST"


def test_sqlite_rejects_a_guarantee_linked_to_another_practices_credit(tmp_path: Path) -> None:
    path = tmp_path / "local.sqlite"
    build_database(path)
    with sqlite3.connect(path) as con:
        con.execute("PRAGMA foreign_keys=ON")
        assert not con.execute("PRAGMA foreign_key_check").fetchall()
        assert con.execute("SELECT count(*) FROM credit WHERE credit_id='F2'").fetchone()[0] > 0
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE guarantee SET credit_id='F2' WHERE practice_key='demo' AND guarantee_id='G1'")


def test_build_keeps_existing_unrelated_files_intact(tmp_path: Path) -> None:
    path = tmp_path / "unrelated.sqlite"
    path.write_bytes(b"existing content")
    with pytest.raises((ValueError, sqlite3.DatabaseError, FileExistsError)):
        build_database(path)
    assert path.read_bytes() == b"existing content"


def test_concurrent_first_use_publishes_one_complete_seed(tmp_path: Path) -> None:
    path = tmp_path / "shared.sqlite"
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(build_database, [path] * 4))
    assert len(synthetic_practices(path)) == 64


def test_synthetic_notes_include_household_capacity_and_repayment_horizon() -> None:
    profiles = synthetic_practices()
    assert all("mensil" in p["notes"].lower() and "anni" in p["notes"] for p in profiles)
    assert len({p["assignee"] for p in profiles}) > 1
    assert len({(p["operatorName"], p["operatorId"]) for p in profiles}) == 1


def test_every_practice_is_marked_as_synthetic_material() -> None:
    assert {p["role"] for p in synthetic_practices()} == {"sintetica"}


def test_every_practice_main_subject_has_a_scheda_with_the_13_extracted_fields() -> None:
    profiles = synthetic_practices()
    keys = scheda_field_keys()
    assert len(keys) == 13
    for p in profiles:
        assert set(p["scheda"]["fields"]) == keys, p["key"]
        assert (p["scheda"]["ndg"], p["scheda"]["name"]) == (p["ndg"], p["name"])
    assert len({p["scheda"]["schedaId"] for p in profiles}) == len(profiles)


def test_scheda_follows_the_structure_and_formats_of_the_reference_page() -> None:
    reference = json.loads((REPO / "bper-emulator" / "site" / "scheda" / "reference.json").read_text(encoding="utf-8"))
    for p in synthetic_practices():
        scheda = p["scheda"]
        assert set(scheda) == set(reference) - {"_comment"}
        for block in ("operator", "lastChange", "lastValidation", "details"):
            assert set(scheda[block]) == set(reference[block]), block
        f, d = scheda["fields"], scheda["details"]
        assert re.fullmatch(r"\d{11}", scheda["schedaId"])
        assert re.fullmatch(r"\d{6} - \d{5}", scheda["operator"]["code"])
        assert re.fullmatch(r"\d{5} [A-Z' ]+", scheda["lastChange"]["user"])
        assert re.fullmatch(r"\d{4}-0000-0000 [A-Z' ]+", scheda["lastChange"]["branch"])
        assert scheda["lastChange"]["bank"] == reference["lastChange"]["bank"]
        stamp = re.fullmatch(r"(\d\d/\d\d/\d{4}) \d\d:\d\d \((.+ fa)\)", f["ultima_validazione_scheda"])
        assert stamp and stamp[2] == validation_age((SCHEDA_TODAY - day(stamp[1])).days)
        for key in ("retribuzione_annua_netta", "importo_totale_annuo_nucleo"):
            euros(f[key])
        month(f["dal"])
        for value in (d["employerFrom"], d["employerTo"]):
            assert value == EMPTY_MONTH or month(value)
        assert f["numero_mensilita"] in {"12", "13", "14"}
        assert re.fullmatch(r"\d{4}", d["housingFrom"])
        assert isinstance(d["employerRegistered"], bool)


def test_scheda_income_matches_the_monthly_income_quoted_in_the_practice_note() -> None:
    for p in synthetic_practices():
        basis, monthly = re.search(r"Reddito netto mensile (del richiedente|complessivo dei cointestatari) "
                                   r"di ([\d.]+),00 €", p["notes"]).groups()
        f = p["scheda"]["fields"]
        payments = int(f["numero_mensilita"])
        annual = euros(f["retribuzione_annua_netta"])
        assert annual % payments == 0, p["key"]
        if basis == "del richiedente":
            assert annual // payments == euros(monthly), p["key"]
        else:
            # The co-holder lives with the applicant and earns on 13 payments.
            assert int(f["di_cui_percepiscono_reddito"]) >= 1, p["key"]
            assert annual // payments + euros(f["importo_totale_annuo_nucleo"]) / 13 == euros(monthly), p["key"]


def test_household_earners_never_exceed_the_other_members() -> None:
    profiles = synthetic_practices()
    for p in profiles:
        f = p["scheda"]["fields"]
        others, earners = int(f["nr_altri_componenti_nucleo"]), int(f["di_cui_percepiscono_reddito"])
        assert 0 <= earners <= others, p["key"]
        assert (earners == 0) == (f["importo_totale_annuo_nucleo"] == "0"), p["key"]
    assert len({p["scheda"]["fields"]["nr_altri_componenti_nucleo"] for p in profiles}) >= 3


def test_scheda_note_quotes_the_booked_amount_and_duration_of_the_main_credit() -> None:
    for p in synthetic_practices():
        years = day(p["fidi"][0]["due"]).year - day(p["created"]).year
        request = paragraphs(p["scheda"]["fields"]["note_scheda_privati"])[0]
        assert f"€ {p['fidi'][0]['amount']}," in request, p["key"]
        assert f"durata {years} anni" in request, p["key"]
        # A second credit line is the technical-costs loan, quoted with its own amount.
        assert re.findall(r"€ ([\d.,]+?) per le spese tecniche", request) == [c["amount"] for c in p["fidi"][1:]]


def test_scheda_notes_have_one_to_four_paragraphs_of_one_line_each() -> None:
    notes = [p["scheda"]["fields"]["note_scheda_privati"] for p in synthetic_practices()]
    assert {len(paragraphs(note)) for note in notes} == {1, 2, 3, 4}
    for note in notes:
        # A blank first and last line: the line the note box cuts at its edges is always a blank one.
        assert note.startswith("\n") and not note.startswith("\n\n")
        assert note.endswith("\n") and not note.endswith("\n\n")
        for paragraph in paragraphs(note):
            assert paragraph and "\n" not in paragraph and len(paragraph) <= NOTE_LINE_CHARS, paragraph


def test_validation_age_counts_days_then_weeks_then_months() -> None:
    observed = {1: "un giorno fa", 5: "5 giorni fa", 6: "6 giorni fa", 8: "una settimana fa", 13: "2 settimane fa",
                27: "4 settimane fa"}
    inferred = {2: "2 giorni fa", 7: "una settimana fa", 10: "una settimana fa", 11: "2 settimane fa",
                25: "4 settimane fa", 31: "4 settimane fa", 32: "un mese fa", 61: "2 mesi fa"}
    assert {d: validation_age(d) for d in {**observed, **inferred}} == {**observed, **inferred}
    for days in (0, 335):
        with pytest.raises(ValueError):
            validation_age(days)


def test_scheda_dates_are_ordered_inside_the_practice_life() -> None:
    for p in synthetic_practices():
        scheda, f, d = p["scheda"], p["scheda"]["fields"], p["scheda"]["details"]
        created, assigned = day(p["created"]), day(p["assigned"])
        stamp, age = re.fullmatch(r"(\d\d/\d\d/\d{4}) \d\d:\d\d \((.+ fa)\)",
                                  f["ultima_validazione_scheda"]).groups()
        validated = day(stamp)
        assert assigned <= validated < SCHEDA_TODAY and validated.weekday() < 5, p["key"]
        assert 2 <= (SCHEDA_TODAY - validated).days <= 25 and age == validation_age((SCHEDA_TODAY - validated).days),             p["key"]
        assert scheda["lastChange"]["when"] == f["ultima_validazione_scheda"]
        assert month(f["dal"]) < (created.year, created.month), p["key"]
        if d["employerFrom"] != EMPTY_MONTH:
            assert month(d["employerFrom"]) <= month(f["dal"]), p["key"]
        if d["employerTo"] != EMPTY_MONTH:
            assert month(d["employerTo"]) > (created.year, created.month), p["key"]
        assert int(d["housingFrom"]) <= created.year, p["key"]


def test_employer_box_follows_the_employment_in_the_practice_note() -> None:
    profiles = synthetic_practices()
    states = set()
    for p in profiles:
        f, d = p["scheda"]["fields"], p["scheda"]["details"]
        text = employment(p)
        if text.startswith(("attività", "pensionato")):
            # Self-employed and pensioners: no employer, no contract; a pension is paid on 13 instalments.
            state = "pension" if text.startswith("pensionato") else "empty"
            assert (f["datore_di_lavoro_anagrafica"], d["employerNdg"], f["tipo_contratto"]) == ("", "", ""), p["key"]
            assert (d["employerFrom"], d["employerTo"]) == (EMPTY_MONTH, EMPTY_MONTH), p["key"]
            assert f["numero_mensilita"] == ("13" if state == "pension" else "12"), p["key"]
        else:
            assert f["datore_di_lavoro_anagrafica"], p["key"]
            assert f["tipo_contratto"] in {"TEMPO INDETERMINATO", "TEMPO DETERMINATO"}, p["key"]
            if "tempo indeterminato" in text:
                assert f["tipo_contratto"] == "TEMPO INDETERMINATO", p["key"]
            assert (f["tipo_contratto"] == "TEMPO DETERMINATO") == (d["employerTo"] != EMPTY_MONTH), p["key"]
            state = "registered" if d["employerRegistered"] else "not registered"
            if d["employerRegistered"]:
                assert re.fullmatch(r"[1-9]\d{7}", d["employerNdg"]), p["key"]
            else:
                assert d["employerNdg"] == "0", p["key"]
        if not d["employerRegistered"]:
            assert (f["rating_ufficiale"], f["score_cgs"]) == ("N/D", "N/D"), p["key"]
        states.add(state)
    assert states == {"empty", "pension", "registered", "not registered"}
    assert {p["scheda"]["fields"]["tipo_contratto"] for p in profiles} == {"TEMPO INDETERMINATO", "TEMPO DETERMINATO", ""}


def test_pensioners_are_a_few_practices_that_no_document_or_test_names() -> None:
    keys = [p["key"] for p in synthetic_practices()]
    assert len(keys) == 64
    assert PENSIONERS < set(keys) and 6 <= len(PENSIONERS) <= 8 and "demo" not in PENSIONERS
    # Examples and tests pin some practices by key; a pensioner must not silently change one of them.
    named = [REPO / "README.md", REPO / "bper-emulator" / "capture_bper_dataset.cjs",
             *(REPO / "tests").glob("*.py"), *(REPO / "tests" / "browser").glob("*.cjs")]
    text = "\n".join(path.read_text(encoding="utf-8") for path in named)
    assert sorted(key for key in PENSIONERS if re.search(rf"\b{key}\b", text)) == []


def test_pensioner_applicants_are_62_or_older_and_the_request_note_says_so() -> None:
    for p in synthetic_practices():
        age, work, years = applicant(p)
        assert work.startswith("pensionato") == (p["key"] in PENSIONERS), p["key"]
        if p["key"] in PENSIONERS:
            # The generator's rule for every applicant: at most 74 at the end of the main loan.
            assert 62 <= age <= 74 - years, p["key"]


def test_a_pensioner_scheda_shows_the_pension_from_its_start() -> None:
    pensions = [p for p in synthetic_practices() if p["key"] in PENSIONERS]
    for p in pensions:
        f = p["scheda"]["fields"]
        age = applicant(p)[0]
        created = day(p["created"])
        assert f["professione_principale"] == "PENSIONATO", p["key"]
        assert not p["scheda"]["details"]["employerRegistered"], p["key"]
        # Retired at 60 or later, before the practice was opened.
        assert (created.year - age + 60, 1) <= month(f["dal"]) < (created.year, created.month), p["key"]
        # The note never describes a job or an activity.
        assert not re.search(r"assunt|lavora presso|busta paga|dichiarazioni|professione|impresa|attività",
                             f["note_scheda_privati"]), p["key"]
    assert any("pensione" in p["scheda"]["fields"]["note_scheda_privati"] for p in pensions)


def test_sqlite_records_the_income_kind_behind_each_scheda(tmp_path: Path) -> None:
    path = tmp_path / "kinds.sqlite3"
    build_database(path)
    applicants = {p["ndg"]: p for p in synthetic_practices()}
    with closing(sqlite3.connect(path)) as con:
        con.execute("PRAGMA foreign_keys=ON")
        kinds = dict(con.execute("SELECT ndg, income_kind FROM scheda"))
        assert kinds.keys() == applicants.keys()
        for ndg, kind in kinds.items():
            work = employment(applicants[ndg])
            expected = "PENSIONE" if work.startswith("pensionato") else "AUTONOMO" if work.startswith("attività") \
                else "DIPENDENTE"
            assert kind == expected, applicants[ndg]["key"]
        pensioner = next(ndg for ndg, kind in kinds.items() if kind == "PENSIONE")
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE scheda SET employer_id = 1, employer_from = job_from WHERE ndg = ?", (pensioner,))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE scheda SET income_kind = 'SCONOSCIUTO' WHERE ndg = ?", (pensioner,))
        # A further kind needs only its row: the page shows any kind as one income entry.
        con.execute("INSERT INTO income_kind VALUES ('ALTRO', 'Altro reddito continuativo')")
        con.execute("UPDATE scheda SET income_kind = 'ALTRO' WHERE ndg = ?", (pensioner,))


def test_list_tooltips_name_the_long_practice_type_and_the_assigned_office() -> None:
    profiles = synthetic_practices()
    offices: dict[str, set[str]] = {}
    for p in profiles:
        assert p["typeName"].startswith(p["type"] + " ") and p["typeName"] != p["type"], p["key"]
        assert p["assigneeName"] == p["assigneeName"].upper() and p["assigneeName"].strip(), p["key"]
        offices.setdefault(p["assignee"], set()).add(p["assigneeName"])
        # A mortgage office never works a personal loan; every personal loan sits with a retail office.
        if "MUTUI" in p["assigneeName"]:
            assert p["type"] == "BPI Mutui", p["key"]
        if p["type"] == "BPI Privati":
            assert "PRIVATI" in p["assigneeName"], p["key"]
    assert all(len(names) == 1 for names in offices.values())
    assert len({name for names in offices.values() for name in names}) == len(offices) > 1
    # The pair seen in the recorded session.
    assert offices["901500"] == {"BPI MUTUI"}
    assert {p["typeName"] for p in profiles if p["type"] == "BPI Mutui"} == {"BPI Mutui Standard",
                                                                          "BPI Mutui Origination Bstore"}


def test_list_type_cell_shows_the_product_code_of_each_practice() -> None:
    # Decided with the lead: the codes follow the archive's authored pairs. Every training or control practice
    # with the B evidence (Origination BSTORE) shows BMB, "BPI Mutui Origination Bstore"; BMS, "BPI Mutui
    # Standard" is the pair a recording shows; the personal-loan code is a stand-in.
    expected = {("BPI Mutui", True): ("BMB", "BPI Mutui Origination Bstore"),
                ("BPI Mutui", False): ("BMS", "BPI Mutui Standard"),
                ("BPI Privati", True): ("BPS", "BPI Privati Standard"),
                ("BPI Privati", False): ("BPS", "BPI Privati Standard")}
    shown = {(p["type"], p["evidence"] == "B"): (p["typeCode"], p["typeName"]) for p in synthetic_practices()}
    assert shown == expected


def test_each_mortgage_product_pair_is_one_the_archive_authored() -> None:
    from bper_archive import archive_profiles
    authored = {(p["typeCode"], p["type"]) for p in archive_profiles() if p["typeCode"] and p["type"]}
    pairs = {(p["typeCode"], p["type"]) for p in synthetic_practices() if p["type"] == "BPI Mutui"}
    assert pairs <= authored and len(pairs) == 2


def test_scheda_staff_are_the_operators_of_the_practice() -> None:
    for p in synthetic_practices():
        scheda = p["scheda"]
        assert scheda["operator"] == {"code": f"{p['operatorId']} - {p['officeCode']}", "name": p["operatorName"]}
        validator = scheda["lastChange"]["user"]
        assert validator.endswith(" " + p["noteAuthor"].upper()), p["key"]
        assert scheda["lastValidation"]["user"] == validator
        assert scheda["lastChange"]["branch"] == f"{p['branch']}-0000-0000 {p['branchName']}"


def test_synthetic_identities_never_equal_one_of_the_real_archive() -> None:
    with (REPO / "data" / "dataset" / "valori.csv").open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source, delimiter=";"))
    real_ndgs = {normalize_ndg(r["Valore"]) for r in rows if r["Chiave"].startswith("ndg") and r["Valore"].strip()}
    real_names = {" ".join(r["Valore"].upper().split()) for r in rows
                  if r["Chiave"].startswith(("denominazione", "datore_di_lavoro")) and r["Valore"].strip()}
    assert real_ndgs and real_names
    ndgs, names = set(), set()
    for p in synthetic_practices():
        scheda = p["scheda"]
        ndgs |= {s["ndg"] for s in p["subjects"]} | {scheda["schedaId"], scheda["details"]["employerNdg"]}
        names |= {s["name"] for s in p["subjects"]} | {scheda["fields"]["datore_di_lavoro_anagrafica"],
                                                       scheda["operator"]["name"], scheda["lastChange"]["user"]}
    # The guarantee fund is an institution present in real practices, not a customer.
    names.discard(FUND_NAME)
    # Counts only: a failure must not print the real values.
    ndg_collisions = len({normalize_ndg(n) for n in ndgs if n not in ("", "0")} & real_ndgs)
    name_collisions = len({" ".join(n.upper().split()) for n in names if n} & real_names)
    assert (ndg_collisions, name_collisions) == (0, 0)


# 1: before the Scheda Privati. 2: without practice types, offices and income kinds. 3: without the product table.
OLDER_VERSIONS = (1, 2, 3)


@pytest.mark.parametrize("version", OLDER_VERSIONS)
def test_an_archive_of_the_previous_format_is_refused_with_its_regeneration_hint(tmp_path: Path, version: int) -> None:
    path = tmp_path / "vecchio.sqlite3"
    contents = older_database(path, version)
    with pytest.raises(ValueError, match=r"vecchio\.sqlite3.*elimin"):
        build_database(path)
    assert path.read_bytes() == contents


@pytest.mark.parametrize("version", OLDER_VERSIONS)
def test_an_older_simulator_database_is_renamed_beside_itself(tmp_path: Path, version: int) -> None:
    path = tmp_path / "bper-synthetic.sqlite3"
    contents = older_database(path, version)
    backup = set_aside_older(path)
    assert backup == tmp_path / f"bper-synthetic.v{version}.bak.sqlite3"
    assert backup.read_bytes() == contents and not path.exists()


@pytest.mark.parametrize("version", OLDER_VERSIONS)
def test_setting_aside_never_overwrites_an_earlier_backup(tmp_path: Path, version: int) -> None:
    path = tmp_path / "bper-synthetic.sqlite3"
    earlier = tmp_path / f"bper-synthetic.v{version}.bak.sqlite3"
    earlier.write_bytes(b"backup precedente")
    contents = older_database(path, version)
    backup = set_aside_older(path)
    assert backup not in (earlier, path) and backup.parent == tmp_path
    assert backup.read_bytes() == contents and earlier.read_bytes() == b"backup precedente"


@pytest.mark.parametrize("kind", ["current", "foreign", "missing"])
def test_only_an_older_database_of_this_simulator_is_set_aside(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "bper-synthetic.sqlite3"
    if kind == "current":
        build_database(path)
    elif kind == "foreign":
        with closing(sqlite3.connect(path)) as con:
            con.execute("PRAGMA user_version = 1")
            con.execute("CREATE TABLE altro (x)")
    contents = path.read_bytes() if path.exists() else None
    assert set_aside_older(path) is None
    assert (path.read_bytes() if path.exists() else None) == contents
    assert sorted(p.name for p in tmp_path.iterdir()) == ([path.name] if contents is not None else [])
