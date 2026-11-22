"""Reproducible Italian retail-credit dossiers for the local simulator."""

from calendar import monthrange
from contextlib import closing
from datetime import date, timedelta
import os
from pathlib import Path
from random import Random
import sqlite3
from tempfile import NamedTemporaryFile
from typing import Any, NamedTuple


SCHEMA = Path(__file__).with_name("bper_synthetic_schema.sql")
APPLICATION_ID = 1112556883
BRANCHES = (
    ("9001", "FILIALE DI PROVA", "Modena"),
    ("9102", "BOLOGNA SARAGOZZA", "Bologna"), ("9103", "ROMA NOMENTANA", "Roma"),
    ("9104", "MODENA CENTRO", "Modena"), ("9105", "BRESCIA OVEST", "Brescia"),
    ("9106", "PESCARA PORTANUOVA", "Pescara"), ("9107", "CAGLIARI CENTRO", "Cagliari"),
    ("9108", "TORINO SAN PAOLO", "Torino"), ("9109", "FIRENZE RIFREDI", "Firenze"),
    ("9110", "CATANIA BORGO", "Catania"), ("9111", "PARMA OLTRETORRENTE", "Parma"),
    ("9112", "GENOVA LEVANTE", "Genova"),
)
OPERATORS = (
    ("901500", "Nora Bellariva"), ("903012", "Irene Vallescura"),
    ("903024", "Stefano Montelago"), ("903036", "Laura Costaferma"),
    ("903048", "Davide Roccaluce"), ("903060", "Marta Fonteluna"),
)
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
)


def _money(cents: int, *, decimals: bool = False) -> str:
    whole, fraction = divmod(cents, 100)
    value = f"{whole:,}".replace(",", ".")
    return f"{value},{fraction:02d}" if decimals or fraction else value


def _date(iso_date: str) -> str:
    return date.fromisoformat(iso_date).strftime("%d/%m/%Y")


def _name(index: int) -> str:
    return f"{SURNAMES[index % len(SURNAMES)]} {NAMES[(index * 9 + index // len(SURNAMES)) % len(NAMES)]}"


def _seed(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.executemany("INSERT INTO branch VALUES (?, ?, ?)", BRANCHES)
    con.executemany("INSERT INTO operator VALUES (?, ?)", OPERATORS)
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
    other_installment = rng.choice((0, 0, 0, 155, 190, 215))
    # Derive a plausible income band from principal, term and outstanding debt.
    # This is fixture generation, not an affordability assessment.
    monthly_band = (principal // (years * 12 * 100) + ancillary // (5 * 12 * 100)) * 4 + 3 * other_installment
    net_income = max(1_550, monthly_band // 50 * 50) + rng.randrange(2, 16) * 50
    joint = any(role == "Cointestatario" for _, _, role in members)
    if joint:
        net_income = max(2_750, net_income)
    note += f"\nRichiedente di {age} anni, {EMPLOYMENTS[i % len(EMPLOYMENTS)]}. "
    income_basis = "complessivo dei cointestatari" if joint else "del richiedente"
    note += f"Reddito netto mensile {income_basis} di {_money(net_income * 100, decimals=True)} €. "
    note += f"Piano di rimborso della linea principale in {years} anni. "
    note += (f"Altra rata in corso di {other_installment},00 € mensili."
             if other_installment else "Non risultano altre rate in corso.")
    con.execute(
        "INSERT INTO practice VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (key, number, str(9900001 + i), branch, operator_id, scenario.label,
         "BPI Privati" if scenario.product == "P. ENERGIA" else "BPI Mutui",
         state, phase, created.isoformat(), assigned.isoformat(), evidence, appraisal, note),
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


def _open_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def _check_schema(con: sqlite3.Connection) -> None:
    if (con.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID or
            con.execute("PRAGMA user_version").fetchone()[0] != 1):
        raise ValueError("Archivio SQLite non riconosciuto dal simulatore BPER.")


def build_database(path: Path) -> None:
    """Publish a complete seed atomically. Preserve an existing simulator database."""
    path = Path(path)
    if path.exists():
        with closing(_open_readonly(path)) as existing:
            _check_schema(existing)
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
                _check_schema(existing)
    finally:
        staging.unlink(missing_ok=True)


def synthetic_practices(path: Path | None = None) -> list[dict[str, Any]]:
    """Read the relational catalog, using the built-in seed when no file is supplied."""
    with closing(_open_readonly(Path(path)) if path is not None else sqlite3.connect(":memory:")) as con:
        if path is None:
            _seed(con)
        _check_schema(con)
        con.row_factory = sqlite3.Row
        con.execute("BEGIN")  # All related tables must come from the same read snapshot.
        query = """
            SELECT p.*, b.name AS branch_name, o.name AS operator_name, s.ndg, s.name
            FROM practice p JOIN branch b ON b.code = p.branch_code
            JOIN operator o ON o.id = p.operator_id
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
        "abi": "5387", "assignee": row["operator_id"], "operatorId": OPERATORS[0][0],
        "operatorName": OPERATORS[0][1], "officeCode": "09001", "noteAuthor": row["operator_name"],
        "type": row["practice_type"], "state": row["state"], "phase": row["phase"],
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
    }
