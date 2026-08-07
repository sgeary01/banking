-- Atlas Financial - standalone analytics DB for the MCP server.
-- Read-only from the MCP server's perspective; populated by seed.py.
-- Deliberately separate from the per-service SQLite DBs the lab runs.

DROP TABLE IF EXISTS claims;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS policies;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    first_name    TEXT    NOT NULL,
    last_name     TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    city          TEXT    NOT NULL,
    state         TEXT    NOT NULL,
    join_date     TEXT    NOT NULL   -- ISO date
);

CREATE TABLE policies (
    policy_id        INTEGER PRIMARY KEY,
    customer_id      INTEGER NOT NULL REFERENCES customers(customer_id),
    policy_type      TEXT    NOT NULL,   -- auto | home | life
    status           TEXT    NOT NULL,   -- active | lapsed | cancelled
    premium_monthly  REAL    NOT NULL,
    coverage_amount  REAL    NOT NULL,
    start_date       TEXT    NOT NULL
);

CREATE TABLE claims (
    claim_id     INTEGER PRIMARY KEY,
    policy_id    INTEGER NOT NULL REFERENCES policies(policy_id),
    claim_date   TEXT    NOT NULL,
    amount       REAL    NOT NULL,
    status       TEXT    NOT NULL,       -- open | approved | denied | paid
    description  TEXT    NOT NULL
);

CREATE TABLE payments (
    payment_id   INTEGER PRIMARY KEY,
    policy_id    INTEGER NOT NULL REFERENCES policies(policy_id),
    payment_date TEXT    NOT NULL,
    amount       REAL    NOT NULL,
    method       TEXT    NOT NULL        -- ach | card | check
);

CREATE INDEX idx_policies_customer ON policies(customer_id);
CREATE INDEX idx_claims_policy     ON claims(policy_id);
CREATE INDEX idx_payments_policy   ON payments(policy_id);
