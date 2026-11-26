PRAGMA foreign_keys = ON;
PRAGMA application_id = 1112556883;
PRAGMA user_version = 7;

CREATE TABLE branch (
    code TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    city TEXT NOT NULL
);
-- The list shows an operator's id as the Assegnata code of its practices, with office as its tooltip.
CREATE TABLE operator (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    office TEXT NOT NULL UNIQUE
);
-- A product: the short code of the list's Tipo cell, the practice type the detail header shows for it and the
-- long name of the cell's tooltip.
CREATE TABLE product (
    code TEXT PRIMARY KEY NOT NULL,
    practice_type TEXT NOT NULL,
    name TEXT NOT NULL UNIQUE,
    UNIQUE (code, practice_type)
);
CREATE TABLE subject (
    ndg TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL
);
CREATE TABLE practice (
    key TEXT PRIMARY KEY NOT NULL,
    number TEXT NOT NULL UNIQUE,
    proposal TEXT NOT NULL UNIQUE,
    branch_code TEXT NOT NULL REFERENCES branch(code),
    operator_id TEXT NOT NULL REFERENCES operator(id),
    scenario TEXT NOT NULL,
    practice_type TEXT NOT NULL,
    product TEXT NOT NULL,
    state TEXT NOT NULL,
    phase TEXT NOT NULL,
    created TEXT NOT NULL,
    assigned TEXT NOT NULL CHECK(assigned >= created),
    evidence TEXT NOT NULL,
    property_cents INTEGER NOT NULL CHECK(property_cents > 0),
    narrative TEXT NOT NULL,
    -- What the dossier may be used for downstream, e.g. 'sintetica'; captures carry it in their manifest.
    role TEXT NOT NULL CHECK(role <> ''),
    -- The product shown in the list belongs to the practice type of the detail header.
    FOREIGN KEY (product, practice_type) REFERENCES product(code, practice_type)
);
CREATE TABLE participation (
    practice_key TEXT NOT NULL REFERENCES practice(key),
    position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 4),
    ndg TEXT NOT NULL REFERENCES subject(ndg),
    role TEXT NOT NULL,
    PRIMARY KEY (practice_key, position),
    UNIQUE (practice_key, ndg),
    CHECK(position != 1 OR role = 'Richiedente')
);
CREATE TABLE credit (
    practice_key TEXT NOT NULL REFERENCES practice(key),
    credit_id TEXT NOT NULL,
    account TEXT NOT NULL UNIQUE,
    product TEXT NOT NULL,
    due TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    operation TEXT NOT NULL,
    tooltip TEXT NOT NULL,
    tooltip_field TEXT,
    PRIMARY KEY(practice_key, credit_id)
);
CREATE TABLE guarantee (
    practice_key TEXT NOT NULL,
    guarantee_id TEXT NOT NULL,
    credit_id TEXT NOT NULL,
    holder_ndg TEXT,
    product TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    operation TEXT NOT NULL,
    tooltip TEXT NOT NULL,
    tooltip_field TEXT,
    PRIMARY KEY(practice_key, guarantee_id),
    FOREIGN KEY(practice_key, credit_id) REFERENCES credit(practice_key, credit_id),
    FOREIGN KEY(practice_key, holder_ndg) REFERENCES participation(practice_key, ndg)
);
-- An employer named in a Scheda Privati. NULL ndg: not a customer of the bank, shown as NDG 0 and
-- "NON CENSITO". Rating and score are display codes, N/D when not available.
CREATE TABLE employer (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    ndg TEXT UNIQUE,
    rating TEXT NOT NULL,
    score TEXT NOT NULL
);
-- What the income box REDDITI DA LAVORO / PENSIONE of a Scheda Privati holds: a job, an activity, a pension.
-- The page shows one entry of any kind, so a further kind needs only its row here.
CREATE TABLE income_kind (
    code TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL
);
-- The Scheda Privati of a customer. Months are YYYY-MM, amounts in cents, validated is YYYY-MM-DD HH:MM.
-- profession, job_from (DAL), payments and net_annual_cents describe the income of income_kind: a job, an
-- activity or a pension and its start. No employer_id: the employer box is empty. employer_to is the end of a
-- fixed-term contract. One income entry per customer: a second one (e.g. a pension and a job) needs a list.
CREATE TABLE scheda (
    ndg TEXT PRIMARY KEY NOT NULL REFERENCES subject(ndg),
    scheda_id TEXT NOT NULL UNIQUE,
    income_kind TEXT NOT NULL REFERENCES income_kind(code),
    profession TEXT NOT NULL,
    job_from TEXT NOT NULL CHECK(job_from GLOB '[12][0-9][0-9][0-9]-[01][0-9]'),
    payments INTEGER NOT NULL CHECK(payments BETWEEN 12 AND 14 OR (payments = 1 AND income_kind = 'AUTONOMO')),
    net_annual_cents INTEGER NOT NULL CHECK(net_annual_cents > 0),
    contract TEXT NOT NULL,
    employer_id INTEGER REFERENCES employer(id),
    employer_from TEXT CHECK(employer_from <= job_from),
    employer_to TEXT CHECK(employer_to > job_from),
    income_channeled TEXT NOT NULL CHECK(income_channeled IN ('SI', 'NO')),
    card_balance TEXT NOT NULL CHECK(card_balance IN ('SI', 'NO', 'NON SO')),
    housing TEXT NOT NULL,
    housing_from INTEGER NOT NULL,
    household_others INTEGER NOT NULL CHECK(household_others BETWEEN 0 AND 9),
    household_earners INTEGER NOT NULL CHECK(household_earners BETWEEN 0 AND household_others),
    household_income_cents INTEGER NOT NULL
        CHECK(household_income_cents >= 0 AND (household_earners = 0) = (household_income_cents = 0)),
    validated TEXT NOT NULL,
    validator_id TEXT NOT NULL REFERENCES operator(id),
    validator_branch TEXT NOT NULL REFERENCES branch(code),
    notes TEXT NOT NULL,
    CHECK((employer_id IS NULL) = (employer_from IS NULL)),
    CHECK(employer_id IS NOT NULL OR employer_to IS NULL),
    -- The self-employed have no employer and the autonomous contract, pensioners neither employer nor contract;
    -- other kinds stay open.
    CHECK(income_kind != 'AUTONOMO' OR (employer_id IS NULL AND contract = 'LAVORATORE AUTONOMO')),
    CHECK(income_kind != 'PENSIONE' OR (employer_id IS NULL AND contract = ''))
);
