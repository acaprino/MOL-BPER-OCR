"""Reproducible Italian retail-credit dossiers for the local simulator."""

from calendar import monthrange
from contextlib import closing
from datetime import date, datetime, timedelta
from itertools import count
import os
from pathlib import Path
from random import Random
import sqlite3
from tempfile import NamedTemporaryFile
from typing import Any, NamedTuple


SCHEMA = Path(__file__).with_name("bper_synthetic_schema.sql")
APPLICATION_ID = 1112556883
# 2 added the Scheda Privati tables and the practice role; 3 the practice types, operator offices and income
# kinds; 4 the product table in place of the practice types. Any schema change bumps it, so an older file is
# refused (or, the default one, set aside and rebuilt).
SCHEMA_VERSION = 4
ROLE = "sintetica"
OFFICE_CODE = "09001"
BRANCHES = (
    ("9001", "FILIALE DI PROVA", "Modena"),
    ("9102", "BOLOGNA SARAGOZZA", "Bologna"), ("9103", "ROMA NOMENTANA", "Roma"),
    ("9104", "MODENA CENTRO", "Modena"), ("9105", "BRESCIA OVEST", "Brescia"),
    ("9106", "PESCARA PORTANUOVA", "Pescara"), ("9107", "CAGLIARI CENTRO", "Cagliari"),
    ("9108", "TORINO SAN PAOLO", "Torino"), ("9109", "FIRENZE RIFREDI", "Firenze"),
    ("9110", "CATANIA BORGO", "Catania"), ("9111", "PARMA OLTRETORRENTE", "Parma"),
    ("9112", "GENOVA LEVANTE", "Genova"),
)
# id, name, office. The list shows an operator's id as the practice's Assegnata code, with the office it
# names as tooltip; a recording shows 901500 = BPI MUTUI, the other offices are stand-ins. Practice i goes to
# OPERATORS[i % 6] and is a personal loan when i % 8 == 7, so personal loans reach only the odd entries: those
# are retail offices (PRIVATI), working mortgages too, and the even ones are mortgage offices (MUTUI).
OPERATORS = (
    ("901500", "Nora Bellariva", "BPI MUTUI"), ("903012", "Irene Vallescura", "BPI PRIVATI"),
    ("903024", "Stefano Montelago", "BPI MUTUI NORD"), ("903036", "Laura Costaferma", "BPI PRIVATI NORD"),
    ("903048", "Davide Roccaluce", "BPI MUTUI SUD"), ("903060", "Marta Fonteluna", "BPI PRIVATI SUD"),
)
# Products: the short code of the list's Tipo cell, the practice type of the detail header, whether it is the
# product of an Origination BSTORE practice (evidence B; None: either) and the long name of the cell's tooltip.
# From the archive's authored pairs (training and control practices only, ADR 0027): every practice with the B
# evidence shows BMB, "BPI Mutui Origination Bstore"; BMS goes only with "BPI Mutui", and BMS, "BPI Mutui
# Standard" is the pair a recording shows (without the B evidence the archive shows BMB as well: ambiguous).
# The personal-loan type, BPS (initials of its name, as BMS is) and its name are stand-ins.
PRODUCTS = (
    ("BMB", "BPI Mutui", True, "BPI Mutui Origination Bstore"),
    ("BMS", "BPI Mutui", False, "BPI Mutui Standard"),
    ("BPS", "BPI Privati", None, "BPI Privati Standard"),
)


def product_for(practice_type: str, evidence: str) -> tuple[str, str] | None:
    """(code, long name) of the product a practice of this type and evidence shows, or None."""
    bstore = "B" in evidence.split()
    return next(((code, name) for code, kind, origination, name in PRODUCTS
                 if kind == practice_type and origination in (None, bstore)), None)
SURNAMES = (
    "ALBAVALLE", "D'AMICO", "FERRANTI", "DELLA TORRE", "RIVA", "FIORAVANTI", "ORTOLANI",
    "BELLINI", "ROSSATO", "SERRAVALLE", "D'ANGELO", "PISANI", "PAGANINI", "PELLEGRINI",
    "MONTANARI", "D'URBINO", "COSTANTINI", "MARCHESI", "LO PRESTI", "DE LUCA", "FONTANESI",
    "GENTILI", "VENTURINI", "CASAGRANDE", "LICATA", "CARBONE", "MANFRINI", "DE SANTIS",
    "VIGANÒ", "FALCONE", "PIETRANGELI", "BELLUCCI",
)
NAMES = (
    "ELENA", "NICOLA", "GIULIA", "PIETRO", "CHIARA", "LUCA", "MARTA", "DAVIDE",
    "ROSSELLA", "ANDREA", "MARIA ELENA", "MARCO", "ISABELLA", "FRANCESCO", "FRANCESCA",
    "ALESSIO", "ANNA", "MASSIMO", "SOFIA", "GIUSEPPE", "EMANUELA", "FILIPPO",
    "DANIELA", "MATTIA", "GIORGIA", "ALESSANDRO", "SERENA", "GIAN PAOLO",
)
FUND_NDG = "99800000"
FUND_NAME = "FONDO DI GARANZIA PER LA PRIMA CASA"
CONS_PRODUCT = "M.CONSAP >=80%"
CONS_KEY = "tooltip_descrizione_m_consap"
FUND_KEY = "tooltip_descrizione_consap_dr_bis"
MORTGAGE_KEY = "tooltip_descrizione_ipoteca"


class Scenario(NamedTuple):
    label: str
    product: str
    tooltip: str
    min_euro: int
    max_euro: int
    years: tuple[int, ...]
    memo: str


SCENARIOS = (
    Scenario("Acquisto prima casa", "M. CASA", "310101 - MUTUO ACQUISTO ABITAZIONE", 90_000, 240_000,
             (20, 25, 30), "Preliminare sottoscritto, caparra già versata con mezzi propri."),
    Scenario("Surroga", "M. SURROGA", "310202 - MUTUO PER PORTABILITÀ", 65_000, 210_000,
             (10, 15, 20), "Portabilità del debito residuo. Acquisito il conteggio della banca originaria."),
    Scenario("Ristrutturazione", "M. RISTR.", "310303 - MUTUO RISTRUTTURAZIONE", 45_000, 145_000,
             (10, 15, 20), "Lavori su immobile di proprietà. Preventivo di impresa allegato, erogazione per SAL."),
    Scenario("Acquisto seconda casa", "M. II CASA", "310404 - MUTUO SECONDA ABITAZIONE", 85_000, 260_000,
             (15, 20, 25), "Acquisto seconda abitazione. Disponibilità liquide a copertura di anticipo e spese."),
    Scenario("Prima casa con garanzia pubblica", CONS_PRODUCT, "340176 - MUTUO FOND PRIV CONSAP >=80%",
             92_000, 215_000, (25, 30), "Richiesta di accesso al Fondo prima casa, acquisita attestazione ISEE."),
    Scenario("Acquisto con lavori", "M. ACQ. RISTR.", "310606 - ACQUISTO E RISTRUTTURAZIONE", 120_000,
             270_000, (20, 25), "Presentata proposta di acquisto con capitolato per il recupero dell'unità."),
    Scenario("Liquidità ipotecaria", "M. LIQUID.", "310707 - FINANZIAMENTO IPOTECARIO PER LIQUIDITÀ",
             40_000, 120_000, (10, 15), "Liquidità per esigenze familiari su immobile già di proprietà."),
    Scenario("Riqualificazione energetica", "P. ENERGIA", "310808 - PRESTITO EFFICIENTAMENTO ABITAZIONE",
             12_000, 38_000, (5, 7, 10), "Sostituzione degli infissi e della pompa di calore. Allegati i preventivi."),
)
STAGES = (("LAV", "VEP"), ("LAV", "IST"), ("LAV", "PRO"), ("SOSP", "IST"), ("LAV", "DEL"))
EMPLOYMENTS = (
    "rapporto di lavoro a tempo indeterminato nel settore metalmeccanico",
    "attività professionale in proprio con due dichiarazioni dei redditi acquisite",
    "impiego amministrativo presso un ente locale",
    "attività artigiana nel settore impiantistico",
    "rapporto a tempo indeterminato presso una società di logistica",
    "impiego nel comparto sanitario pubblico",
    "attività commerciale con anzianità superiore a cinque anni",
    "impiego nel settore informatico con contratto a tempo indeterminato",
    "pensionato, titolare di pensione diretta INPS",
)
# Applicant i has employment i % PENSION; the PENSIONERS take the pension instead. They are 62 or older, so
# only dossiers whose main loan ends by the applicant's 74th year at 62 qualify (a term of at most 12 years);
# none is named by the README, the tests or the capture examples, and each income stays a plausible pension.
PENSION = len(EMPLOYMENTS) - 1
PENSIONERS = frozenset({"sim-008", "sim-015", "sim-018", "sim-019", "sim-032", "sim-040", "sim-056"})

# ============================================================
# Scheda Privati. One real page is known (site/scheda/reference.json): it fixes the display formats and
# shows OPERAIO IMPRESE PRIVATE (INDUSTRIA), 13 payments, TEMPO INDETERMINATO, an employer typed in by
# hand (NDG 0, NON CENSITO), an empty employer box and N/D ratings. The other professions, the fixed-term
# contract, registered employers with a rating and the housing labels are plausible stand-ins.
# ============================================================
# The day the pages are seen from: "(N giorni fa)" counts from it.
SCHEDA_TODAY = date(2026, 11, 23)
BANK = "05387 BPER Banca"
EMPTY_MONTH = "--------- ----"
MONTHS = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
          "settembre", "ottobre", "novembre", "dicembre")
# Kinds of income the REDDITI DA LAVORO / PENSIONE box can hold (table income_kind). The page shows one
# income entry of any kind; a further kind needs only its row.
INCOME_KINDS = (("DIPENDENTE", "Lavoro dipendente"), ("AUTONOMO", "Lavoro autonomo"), ("PENSIONE", "Pensione"))
# Per EMPLOYMENTS entry, in its order: income kind, profession, payments per year, employer kind (None: the
# employer box stays empty).
JOBS = (
    ("DIPENDENTE", "OPERAIO IMPRESE PRIVATE (INDUSTRIA)", (13, 14), "industria"),
    ("AUTONOMO", "LIBERO PROFESSIONISTA", (12,), None),
    ("DIPENDENTE", "IMPIEGATO PUBBLICA AMMINISTRAZIONE", (13,), "comune"),
    ("AUTONOMO", "ARTIGIANO", (12,), None),
    ("DIPENDENTE", "IMPIEGATO IMPRESE PRIVATE (SERVIZI)", (14, 13), "logistica"),
    ("DIPENDENTE", "IMPIEGATO PUBBLICA AMMINISTRAZIONE", (13,), "sanita"),
    ("AUTONOMO", "COMMERCIANTE", (12,), None),
    ("DIPENDENTE", "IMPIEGATO IMPRESE PRIVATE (SERVIZI)", (13, 14), "informatica"),
    # Assumption: no screenshot shows a pensioner's page. It is taken to fill the same box: the pension
    # category as profession, DAL the start of the pension, the 13 INPS instalments and the annual pension as
    # net pay, no contract and no employer (empty box, NON CENSITO).
    ("PENSIONE", "PENSIONATO", (13,), None),
)
# The document a note's update paragraph cites, per kind of income.
UPDATES = {"DIPENDENTE": "acquisita l'ultima busta paga", "AUTONOMO": "acquisita la situazione contabile aggiornata",
           "PENSIONE": "acquisito l'ultimo cedolino della pensione"}
# Self-employed EMPLOYMENTS entries: how the note describes the activity and the years it has lasted at
# least (two tax returns; "anzianità superiore a cinque anni").
ACTIVITIES = {
    1: ("Il cliente esercita la libera professione dal {year}, con studio a {city}.", 2),
    3: ("Il cliente è titolare di un'impresa artigiana nel settore impiantistico dal {year}.", 2),
    6: ("Il cliente è titolare di un'attività commerciale a {city}, avviata nel {year}.", 6),
}
# How a note names a public employer.
PUBLIC_BODIES = {"comune": "il Comune di {city}", "sanita": "l'Azienda sanitaria locale di {city}"}
CITIES = tuple(sorted({city for _, _, city in BRANCHES}))
# kind, name, NDG (None: not a bank customer, so typed by hand), rating, Cribis class.
EMPLOYERS = (
    ("industria", "OFFICINE MECCANICHE VALTRESA S.P.A.", "94000011", "4", "2"),
    ("industria", "FONDERIE ROCCABRUNA SRL", None, "N/D", "N/D"),
    ("industria", "MECCANICA PIANALTA S.R.L.", "94000021", "6", "3"),
    ("industria", "TORNERIA SAN VITALE SNC", None, "N/D", "N/D"),
    ("logistica", "TRASPORTI VALMORENA S.R.L.", "94000031", "5", "2"),
    ("logistica", "LOGISTICA PIANURA NORD SPA", None, "N/D", "N/D"),
    ("logistica", "SPEDIZIONI CORTEMARE SRL", None, "N/D", "N/D"),
    ("informatica", "LUMERA SISTEMI INFORMATICI S.R.L.", "94000041", "3", "1"),
    ("informatica", "DATAVALLE SOFTWARE SRL", None, "N/D", "N/D"),
    ("informatica", "RETICOLO DIGITALE S.P.A.", "94000051", "N/D", "N/D"),
    *(("comune", f"COMUNE DI {city.upper()}", str(94100001 + 10 * n), "N/D", "N/D") for n, city in enumerate(CITIES)),
    *(("sanita", f"AZIENDA SANITARIA LOCALE DI {city.upper()}", str(94200001 + 10 * n), "N/D", "N/D")
      for n, city in enumerate(CITIES)),
)
PURPOSES = {
    "Acquisto prima casa": "l'acquisto della prima casa",
    "Surroga": "la surroga del mutuo in essere presso altro istituto",
    "Ristrutturazione": "la ristrutturazione dell'abitazione di proprietà",
    "Acquisto seconda casa": "l'acquisto di una seconda abitazione",
    "Prima casa con garanzia pubblica": "l'acquisto della prima casa con garanzia del Fondo",
    "Acquisto con lavori": "l'acquisto e la ristrutturazione dell'immobile",
    "Liquidità ipotecaria": "esigenze di liquidità con ipoteca sull'abitazione",
    "Riqualificazione energetica": "l'efficientamento energetico dell'abitazione",
}
RENTERS = ("Acquisto prima casa", "Prima casa con garanzia pubblica", "Acquisto con lavori")


def _money(cents: int, *, decimals: bool = False) -> str:
    whole, fraction = divmod(cents, 100)
    value = f"{whole:,}".replace(",", ".")
    return f"{value},{fraction:02d}" if decimals or fraction else value


def _date(iso_date: str) -> str:
    return date.fromisoformat(iso_date).strftime("%d/%m/%Y")


def _name(index: int) -> str:
    return f"{SURNAMES[index % len(SURNAMES)]} {NAMES[(index * 9 + index // len(SURNAMES)) % len(NAMES)]}"


def _month_index(day: date) -> int:
    return day.year * 12 + day.month - 1


def _iso_month(index: int | None) -> str | None:
    return None if index is None else f"{index // 12:04d}-{index % 12 + 1:02d}"


def _spoken(index: int) -> str:
    """A month as a note writes it: 'luglio 2026'."""
    return f"{MONTHS[index % 12]} {index // 12}"


def _since(index: int) -> str:
    """The start of something in a note: 'dal luglio 2026', 'dall'aprile 2025'."""
    month = _spoken(index)
    return ("dall'" if month[0] in "aeiou" else "dal ") + month


def _at(index: int) -> str:
    """A deadline in a note: 'a luglio 2026', 'ad aprile 2025'."""
    month = _spoken(index)
    return ("ad " if month[0] == "a" else "a ") + month


def _month(iso: str | None) -> str:
    """A month as the page shows it: 'LUGLIO 2026', or the empty mask."""
    if iso is None:
        return EMPTY_MONTH
    year, month = iso.split("-")
    return f"{MONTHS[int(month) - 1].upper()} {year}"


def _seed(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.executemany("INSERT INTO branch VALUES (?, ?, ?)", BRANCHES)
    con.executemany("INSERT INTO operator VALUES (?, ?, ?)", OPERATORS)
    con.executemany("INSERT INTO product VALUES (?, ?, ?)", [(code, kind, name) for code, kind, _, name in PRODUCTS])
    con.executemany("INSERT INTO income_kind VALUES (?, ?)", INCOME_KINDS)
    con.executemany("INSERT INTO employer VALUES (?, ?, ?, ?, ?)",
                    [(n, name, ndg, rating, score) for n, (_, name, ndg, rating, score) in enumerate(EMPLOYERS, 1)])
    con.execute("INSERT INTO subject VALUES (?, ?)", (FUND_NDG, FUND_NAME))
    for index in range(64):
        _seed_case(con, index)
    con.commit()


def _seed_case(con: sqlite3.Connection, i: int) -> None:
    rng = Random(20261122 + i)
    demo = i == 0
    key = "demo" if demo else f"sim-{i + 1:03}"
    number = str(99000001 + i)
    scenario = SCENARIOS[i % len(SCENARIOS)]
    branch, _, city = BRANCHES[0 if demo else 1 + (i - 1) % (len(BRANCHES) - 1)]
    operator_id = OPERATORS[i % len(OPERATORS)][0]
    created = date(2026, 11, 12) if demo else date(2025, 9, 1) + timedelta(days=rng.randrange(428))
    if created.weekday() > 4:
        created += timedelta(days=7 - created.weekday())
    assigned = created + timedelta(days=0 if demo else rng.randrange(4))
    if assigned.weekday() > 4:
        assigned += timedelta(days=7 - assigned.weekday())
    state, phase = ("LAV", "IST") if demo else STAGES[i % len(STAGES)]
    evidence = "" if i % 7 == 6 else "B"
    primary = "90000001" if demo else (f"09{i:06}" if i % 13 == 0 else str(91000000 + i * 10))
    name = "ALBA MARTINA" if demo else _name(i)
    members = [(primary, name, "Richiedente")]
    if demo:
        members.append(("90000002", "ALBA LUCA", "Garante"))
    else:
        if i % 3 != 1:
            members.append((str(92000001 + 10 * i), _name(140 + i), "Cointestatario"))
        if scenario.product == CONS_PRODUCT:
            members.append((FUND_NDG, FUND_NAME, "Nuovo Garante/nuovo Datore Di Pegno"))
        if i % 4 == 0 and scenario.product != "P. ENERGIA":
            members.append((str(93000001 + 10 * i), _name(290 + i), "Garante"))

    years = 20 if demo else rng.choice(scenario.years)
    due_year = created.year + years
    due = date(due_year, created.month, monthrange(due_year, created.month)[1])
    principal = rng.randrange(scenario.min_euro // 1000, scenario.max_euro // 1000 + 1) * 100_000
    if demo:
        principal = 12_000_000
    elif scenario.product == "M. SURROGA":
        principal += rng.randrange(1, 100_000)  # The payoff statement includes accrued cents.
    ancillary = rng.randrange(45, 116) * 10_000 if scenario.product == "M. ACQ. RISTR." else 0
    ltv = 88 if scenario.product == CONS_PRODUCT else rng.randrange(55, 79)
    appraisal = ((principal + ancillary) * 100 // ltv + 99_999) // 100_000 * 100_000
    if demo:
        appraisal = 18_000_000
    elif scenario.product == "P. ENERGIA":
        appraisal = rng.randrange(140, 310) * 100_000
    note = f"{scenario.memo} Immobile nel comune di {city}."
    if ancillary:
        note += " Prevista una linea separata per le spese tecniche di avvio cantiere."
    if state == "SOSP":
        note += " Istruttoria sospesa in attesa di integrazione documentale."
    elif phase == "DEL":
        note += " Fascicolo completo, proposta trasmessa per delibera."
    elif phase == "VEP":
        note += " In corso la verifica preliminare della documentazione di reddito."
    age = rng.randint(25, 35 if scenario.product == CONS_PRODUCT else 74 - years)
    job = PENSION if key in PENSIONERS else i % PENSION
    if job == PENSION:
        # Its own stream: the dossier's later draws, and so the rest of its note, stay as they were.
        age = Random(60261122 + i).randint(62, 74 - years)
    other_installment = rng.choice((0, 0, 0, 155, 190, 215))
    # Derive a plausible income band from principal, term and outstanding debt.
    # This is fixture generation, not an affordability assessment.
    monthly_band = (principal // (years * 12 * 100) + ancillary // (5 * 12 * 100)) * 4 + 3 * other_installment
    net_income = max(1_550, monthly_band // 50 * 50) + rng.randrange(2, 16) * 50
    joint = any(role == "Cointestatario" for _, _, role in members)
    if joint:
        net_income = max(2_750, net_income)
    note += f"\nRichiedente di {age} anni, {EMPLOYMENTS[job]}. "
    income_basis = "complessivo dei cointestatari" if joint else "del richiedente"
    note += f"Reddito netto mensile {income_basis} di {_money(net_income * 100, decimals=True)} €. "
    note += f"Piano di rimborso della linea principale in {years} anni. "
    note += (f"Altra rata in corso di {other_installment},00 € mensili."
             if other_installment else "Non risultano altre rate in corso.")
    practice_type = "BPI Privati" if scenario.product == "P. ENERGIA" else "BPI Mutui"
    con.execute(
        "INSERT INTO practice VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (key, number, str(9900001 + i), branch, operator_id, scenario.label, practice_type,
         product_for(practice_type, evidence)[0], state, phase, created.isoformat(), assigned.isoformat(), evidence,
         appraisal, note, ROLE),
    )
    for pos, (ndg, full_name, role) in enumerate(members, 1):
        if ndg != FUND_NDG:
            con.execute("INSERT INTO subject VALUES (?, ?)", (ndg, full_name))
        con.execute("INSERT INTO participation VALUES (?, ?, ?, ?)", (key, pos, ndg, role))

    account = f"034 {branch} 0017 {i * 2 + 1:08d}"
    con.execute("INSERT INTO credit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
        key, "F1", account, scenario.product, due.isoformat(), principal, "In Lavoraz.",
        "900001 - MUTUO ABITAZIONE DI PROVA" if demo else scenario.tooltip,
        CONS_KEY if scenario.product == CONS_PRODUCT else None,
    ))
    if ancillary:
        short_due = date(created.year + 5, created.month, monthrange(created.year + 5, created.month)[1])
        con.execute("INSERT INTO credit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            key, "F2", f"034 {branch} 0018 {i * 2 + 2:08d}", "P. SPESE", short_due.isoformat(),
            ancillary, "In Lavoraz.", "315014 - PRESTITO PER SPESE TECNICHE", None,
        ))
    guarantees = []
    for ndg, _, role in members:
        if ndg == FUND_NDG:
            guarantees.append((ndg, "CONSAP DR BIS", principal * 80 // 100,
                               "457-IMP. FID. F.DO 1 CASA DR SOSTEGNI BIS", FUND_KEY))
        elif role == "Garante":
            guarantees.append((ndg, "GAR. PERS.", principal // 5,
                               "901-GARANZIA PERSONALE DI PROVA" if demo else "901-FIDEIUSSIONE PERSONALE SPECIFICA", None))
    if scenario.product != "P. ENERGIA":
        mortgage = (None, "IPOTECA I GR.", principal * 150 // 100, "55-IPOTECA DI PRIMO GRADO", MORTGAGE_KEY)
        guarantees.insert(min(1, len(guarantees)), mortgage)
    for n, (holder, label, amount, tip, field) in enumerate(guarantees, 1):
        con.execute("INSERT INTO guarantee VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            key, f"G{n}", "F1", holder, label, amount, "Nuova / In Lavoraz.", tip, field,
        ))
    _seed_scheda(con, i, job, ndg=primary, created=created, assigned=assigned, operator_id=operator_id,
                 branch=branch, city=city, scenario=scenario, principal=principal, ancillary=ancillary,
                 years=years, age=age, other_installment=other_installment, net_income=net_income, joint=joint)


def _seed_scheda(con: sqlite3.Connection, i: int, job: int, *, ndg: str, created: date, assigned: date,
                 operator_id: str, branch: str, city: str, scenario: Scenario, principal: int, ancillary: int,
                 years: int, age: int, other_installment: int, net_income: int, joint: bool) -> None:
    """The applicant's Scheda Privati, agreeing with the dossier and with its PEF note.

    The PEF note states the applicant's age, employment and monthly net income (the co-holders' total for a
    joint loan); this page splits that income, dates the job inside the applicant's working life and quotes
    the booked amount and term. Every note paragraph is one line of the note box (NOTE_LINE_CHARS), between
    blank lines.
    """
    rng = Random(40261122 + i)  # its own stream: the dossier's draws stay as they were
    income_kind, profession, payment_options, kind = JOBS[job]
    payments = rng.choice(payment_options)
    now = _month_index(created)
    adult = (created.year - age + 19) * 12  # January of the year the applicant turned 19
    employer = employer_from = employer_to = None
    contract = ""
    if income_kind == "PENSIONE":
        # Retired at 61 or later, at least two months before the practice.
        start = now - rng.randrange(2, max(3, (age - 61) * 12))
        retired_at = age - (now - start) // 12
        pension = "di vecchiaia" if retired_at >= 67 else "anticipata"
        work = f"Il cliente percepisce {_since(start)} una pensione {pension} erogata dall'INPS."
    elif kind is None:
        sentence, min_years = ACTIVITIES[job]
        start = now - rng.randrange(min_years * 12 + 1, max(min_years * 12 + 2, now - adult))
        work = sentence.format(year=start // 12, city=city)
    else:
        fixed_term = kind in PUBLIC_BODIES and rng.random() < 0.3
        start = now - (rng.randrange(6, 37) if fixed_term else rng.randrange(6, max(7, min(now - adult, 25 * 12))))
        if kind in PUBLIC_BODIES:
            employer = next(n for n, row in enumerate(EMPLOYERS, 1) if row[0] == kind and row[1].endswith(city.upper()))
            label = PUBLIC_BODIES[kind].format(city=city)
        else:
            employer = rng.choice([n for n, row in enumerate(EMPLOYERS, 1) if row[0] == kind])
            label = EMPLOYERS[employer - 1][1]
        employer_from = start
        if fixed_term:
            contract = "TEMPO DETERMINATO"
            employer_to = now + rng.randrange(6, 19)
            work = (f"Il cliente lavora presso {label} {_since(start)} con contratto a tempo determinato "
                    f"in scadenza {_at(employer_to)}.")
        else:
            contract = "TEMPO INDETERMINATO"
            if rng.random() < 0.25 and start - adult > 6:
                # A fixed-term contract at the same employer before the permanent one, as on the real page.
                employer_from = start - rng.randrange(6, min(31, start - adult))
                work = (f"Assunto presso {label} a tempo determinato da {_spoken(employer_from)}, "
                        f"a tempo indeterminato da {_spoken(start)}.")
            else:
                work = f"Il cliente è assunto presso {label} {_since(start)} con contratto a tempo indeterminato."

    applicant, partner = net_income, 0
    others, earners, household = rng.choice((0, 0, 1, 2, 3)), 0, 0
    if joint:
        applicant = net_income * rng.choice((50, 55, 60, 65)) // 100 // 50 * 50
        partner = net_income - applicant
        # The co-holder lives with the applicant and earns on 13 payments.
        others, earners, household = 1 + rng.choice((0, 0, 1, 1, 2)), 1, partner * 13
    elif others:
        earners = rng.choice((0, 1))
        household = earners * rng.randrange(12, 29) * 1000
    renting = scenario.label in RENTERS
    housing_from = max(adult // 12, created.year - rng.randrange(0 if renting else 2, 9 if renting else 16))
    rent = rng.randrange(45, 96) * 10
    new_customer = scenario.product == "M. SURROGA" or rng.random() < 0.3
    since = rng.randrange(adult // 12, created.year)
    first = max(assigned, SCHEDA_TODAY - timedelta(days=25))
    validated = rng.choice([day for day in (first + timedelta(days=n) for n in range((SCHEDA_TODAY - first).days - 1))
                            if day.weekday() < 5])
    minute = rng.randrange(8 * 60 + 30, 18 * 60)

    loan = "prestito" if scenario.product == "P. ENERGIA" else "mutuo cointestato" if joint else "mutuo"
    request = f"Richiesta di {loan} per {PURPOSES[scenario.label]} di € {_money(principal)}, durata {years} anni"
    request += f", oltre a € {_money(ancillary)} per le spese tecniche." if ancillary else "."
    customer = ("Nuovo cliente della scrivente Filiale, redditi non ancora canalizzati presso la banca."
                if new_customer else f"Cliente della scrivente Filiale dal {since}, con redditi canalizzati sul conto.")
    monthly = f"€ {_money(applicant * 100)} mensili per {payments} mensilità."
    income = {
        "DIPENDENTE": f"Reddito netto desunto dalle ultime buste paga e dalla CU {created.year} (anno d'imposta "
                      f"{created.year - 1}): {monthly}",
        "AUTONOMO": f"Reddito desunto dalle dichiarazioni {created.year - 2} e {created.year - 1}: "
                    f"€ {_money(applicant * 1200)} netti annui.",
        "PENSIONE": f"Reddito desunto dal cedolino della pensione e dalla CU {created.year} (anno d'imposta "
                    f"{created.year - 1}): {monthly}",
    }[income_kind]
    partner_line = (f"Il cointestatario, convivente del cliente, percepisce un reddito netto di "
                    f"€ {_money(partner * 100)} mensili.")
    if renting:
        housing = (f"Il nucleo vive in un immobile condotto in locazione dal {housing_from}, con canone mensile "
                   f"di € {rent}." if others else
                   f"Il cliente vive da solo in un immobile in locazione dal {housing_from}, canone mensile € {rent}.")
    else:
        housing = ("Il cliente risiede con il proprio nucleo familiare nell'immobile di proprietà dal "
                   f"{housing_from}." if others else f"Il cliente vive da solo nell'immobile di proprietà dal {housing_from}.")
    crif = (f"Da CRIF risulta un finanziamento in corso con rata mensile di € {other_installment}, regolarmente "
            "rimborsato." if other_installment else
            "Posizione CRIF regolare; il cliente dichiara di non avere altri finanziamenti in corso.")
    update = (f"Aggiornamento del {validated:%d/%m}: {UPDATES[income_kind]}, confermati i dati reddituali "
              "indicati in scheda.")
    optional = [customer, work, income, *([partner_line] if joint else []), housing, crif,
                *([update] if validated > assigned + timedelta(days=7) else [])]
    chosen = sorted(rng.sample(range(len(optional)), rng.choice((1, 2, 2, 3, 3, 4, 4)) - 1))
    # A blank first and last line, as on the real page: the line the box cuts at an edge is then blank.
    notes = "\n" + "\n\n".join([request, *(optional[n] for n in chosen)]) + "\n"

    con.execute(f"INSERT INTO scheda VALUES ({', '.join('?' * 22)})", (
        ndg, f"{88000001 + i:011d}", income_kind, profession, _iso_month(start), payments, applicant * payments * 100,
        contract,
        employer, _iso_month(employer_from), _iso_month(employer_to), "NO" if new_customer else "SI",
        rng.choice(("SI", "NO", "NON SO")), "AFFITTO" if renting else "PROPRIETA'", housing_from,
        others, earners, household * 100, f"{validated.isoformat()} {minute // 60:02d}:{minute % 60:02d}",
        operator_id, branch, notes,
    ))


def _open_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def _check_schema(con: sqlite3.Connection, path: Path | None = None) -> None:
    version = con.execute("PRAGMA user_version").fetchone()[0]
    if con.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID or not 0 < version <= SCHEMA_VERSION:
        raise ValueError("Archivio SQLite non riconosciuto dal simulatore BPER.")
    if version < SCHEMA_VERSION:
        raise ValueError(f"L'archivio {path} è di una versione precedente del simulatore BPER (schema {version}, "
                         f"atteso {SCHEMA_VERSION}): eliminalo per rigenerarlo, oppure indica un altro file con --db.")


def set_aside_older(path: Path) -> Path | None:
    """Rename a database this simulator wrote at an older version to <stem>.v<N>.bak<suffix> beside it.

    Returns the new name, or None when the file is missing, current or not the simulator's. The first free
    name is taken (<stem>.v<N>.bak-2<suffix>, ...), so nothing is deleted or overwritten. The caller then
    rebuilds the file: this is for the launcher's default database only, never for a file the user names.
    """
    path = Path(path)
    if not path.exists():
        return None
    with closing(_open_readonly(path)) as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        owned = con.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
    if not owned or not 0 < version < SCHEMA_VERSION:
        return None
    for n in count(1):
        target = path.with_name(f"{path.stem}.v{version}.bak{'' if n == 1 else f'-{n}'}{path.suffix}")
        try:
            # Neither call replaces an existing target (see build_database).
            if os.name == "nt":
                os.rename(path, target)
            else:
                os.link(path, target)
                path.unlink()
            return target
        except FileExistsError:
            continue


def build_database(path: Path) -> None:
    """Publish a complete seed atomically. Preserve an existing simulator database."""
    path = Path(path)
    if path.exists():
        with closing(_open_readonly(path)) as existing:
            _check_schema(existing, path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, prefix=".bper-", suffix=".sqlite", delete=False) as tmp:
        staging = Path(tmp.name)
    try:
        with closing(sqlite3.connect(staging)) as con:
            _seed(con)
        try:
            # Windows rename rejects existing targets. POSIX rename would replace them.
            if os.name == "nt":
                os.rename(staging, path)
            else:
                os.link(staging, path)
        except FileExistsError:
            # A concurrent startup published first.
            with closing(_open_readonly(path)) as existing:
                _check_schema(existing, path)
    finally:
        staging.unlink(missing_ok=True)


def synthetic_practices(path: Path | None = None) -> list[dict[str, Any]]:
    """Read the relational catalog, using the built-in seed when no file is supplied."""
    with closing(_open_readonly(Path(path)) if path is not None else sqlite3.connect(":memory:")) as con:
        if path is None:
            _seed(con)
        _check_schema(con, path)
        con.row_factory = sqlite3.Row
        con.execute("BEGIN")  # All related tables must come from the same read snapshot.
        query = """
            SELECT p.*, b.name AS branch_name, o.name AS operator_name, o.office, pr.name AS product_name,
                   s.ndg, s.name
            FROM practice p JOIN branch b ON b.code = p.branch_code
            JOIN operator o ON o.id = p.operator_id JOIN product pr ON pr.code = p.product
            JOIN participation m ON m.practice_key = p.key AND m.position = 1
            JOIN subject s ON s.ndg = m.ndg ORDER BY p.number
        """
        return [_profile(con, row) for row in con.execute(query)]


def _profile(con: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    key = row["key"]
    members = [dict(m) for m in con.execute("""
        SELECT m.ndg, s.name, m.role FROM participation m JOIN subject s ON m.ndg = s.ndg
        WHERE practice_key=? ORDER BY position
    """, (key,))]
    credits = con.execute("SELECT * FROM credit WHERE practice_key=? ORDER BY credit_id", (key,)).fetchall()
    guarantees = con.execute("""
        SELECT g.*, s.name AS holder FROM guarantee g LEFT JOIN subject s ON s.ndg = g.holder_ndg
        WHERE practice_key=? ORDER BY guarantee_id
    """, (key,)).fetchall()
    total = sum(c["amount_cents"] for c in credits)
    notes = (
        f"- Numero proposta DESK: {row['proposal']}\n"
        f"- Valore immobile presunto: {_money(row['property_cents'], decimals=True)}\n"
        f"- Dettaglio importi mutuo:\n       IMPORTO RICHIESTO : {_money(total, decimals=True)} €\n"
        f"{row['name']} — {row['scenario'].upper()}. {row['narrative']}"
    )
    return {
        "key": key, "ndg": row["ndg"], "name": row["name"], "number": row["number"],
        "scenario": row["scenario"], "branch": row["branch_code"], "branchName": row["branch_name"],
        "abi": "5387", "assignee": row["operator_id"], "assigneeName": row["office"], "operatorId": OPERATORS[0][0],
        "operatorName": OPERATORS[0][1], "officeCode": OFFICE_CODE, "noteAuthor": row["operator_name"],
        "type": row["practice_type"], "typeCode": row["product"], "typeName": row["product_name"],
        "state": row["state"], "phase": row["phase"],
        "date": _date(row["created"]), "created": _date(row["created"]), "assigned": _date(row["assigned"]),
        "evidence": row["evidence"], "evidenceTooltip": "Origination BSTORE" if row["evidence"] == "B" else "",
        "subjects": members, "notes": notes, "creditTotal": _money(total),
        "guaranteeTotal": _money(sum(g["amount_cents"] for g in guarantees)),
        "fidi": [{"id": c["credit_id"], "account": c["account"], "description": c["product"],
                  "due": _date(c["due"]), "amount": _money(c["amount_cents"]), "operation": c["operation"],
                  "tooltip": c["tooltip"], "tooltipField": c["tooltip_field"]} for c in credits],
        "guarantees": [{"id": g["guarantee_id"], "creditId": g["credit_id"], "description": g["product"],
                        "ndgName": f"{g['holder_ndg']} {g['holder']}" if g["holder_ndg"] else "",
                        "amount": _money(g["amount_cents"]), "operation": g["operation"],
                        "tooltip": g["tooltip"], "tooltipField": g["tooltip_field"]} for g in guarantees],
        "role": row["role"], "scheda": _scheda(con, row["ndg"], row["name"]),
        # Profile format (bper_profiles): every PEF page, and all values are this seed's own.
        "pages": ["elenco", "soggetti", "gestione-fidi", "note"], "provenance": {"source": "sqlite", "filler": [], "stated": None},
    }


def _scheda(con: sqlite3.Connection, ndg: str, name: str) -> dict[str, Any] | None:
    """The Scheda Privati page of a customer, in the display schema of site/scheda/scheda.js."""
    s = con.execute("""
        SELECT c.*, e.name AS employer_name, e.ndg AS employer_ndg, e.rating, e.score,
               o.name AS validator_name, b.name AS branch_name
        FROM scheda c JOIN operator o ON o.id = c.validator_id JOIN branch b ON b.code = c.validator_branch
        LEFT JOIN employer e ON e.id = c.employer_id WHERE c.ndg = ?
    """, (ndg,)).fetchone()
    if s is None:
        return None
    validated = datetime.strptime(s["validated"], "%Y-%m-%d %H:%M")
    stamp = f"{validated:%d/%m/%Y %H:%M} ({(SCHEDA_TODAY - validated.date()).days} giorni fa)"
    staff = {"user": f"{s['validator_id'][-5:]} {s['validator_name'].upper()}",
             "branch": f"{s['validator_branch']}-0000-0000 {s['branch_name']}", "bank": BANK}
    employed = s["employer_id"] is not None
    return {
        "ndg": ndg, "schedaId": s["scheda_id"], "name": name,
        "operator": {"code": f"{OPERATORS[0][0]} - {OFFICE_CODE}", "name": OPERATORS[0][1]},
        "lastChange": {"when": stamp, **staff}, "lastValidation": staff,
        "fields": {
            "professione_principale": s["profession"], "dal": _month(s["job_from"]),
            "numero_mensilita": str(s["payments"]), "retribuzione_annua_netta": _money(s["net_annual_cents"]),
            "tipo_contratto": s["contract"], "datore_di_lavoro_anagrafica": s["employer_name"] or "",
            "rating_ufficiale": s["rating"] or "N/D", "score_cgs": s["score"] or "N/D",
            "nr_altri_componenti_nucleo": str(s["household_others"]),
            "di_cui_percepiscono_reddito": str(s["household_earners"]),
            "importo_totale_annuo_nucleo": _money(s["household_income_cents"]),
            "note_scheda_privati": s["notes"], "ultima_validazione_scheda": stamp,
        },
        "details": {
            # A customer's employer has its NDG; one typed in by hand shows 0 and "NON CENSITO".
            "employerNdg": (s["employer_ndg"] or "0") if employed else "",
            "employerFrom": _month(s["employer_from"]), "employerTo": _month(s["employer_to"]),
            "employerRegistered": s["employer_ndg"] is not None,
            "incomeChanneled": s["income_channeled"], "creditCardBalance": s["card_balance"],
            "housing": s["housing"], "housingFrom": str(s["housing_from"]),
        },
    }
