PRAGMA foreign_keys = ON;
PRAGMA application_id = 1112556883;
PRAGMA user_version = 1;

CREATE TABLE branch (
    code TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    city TEXT NOT NULL
);
CREATE TABLE operator (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL
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
    state TEXT NOT NULL,
    phase TEXT NOT NULL,
    created TEXT NOT NULL,
    assigned TEXT NOT NULL CHECK(assigned >= created),
    evidence TEXT NOT NULL,
    property_cents INTEGER NOT NULL CHECK(property_cents > 0),
    narrative TEXT NOT NULL
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
