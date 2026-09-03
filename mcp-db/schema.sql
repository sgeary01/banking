-- Atlas Financial - standalone analytics DB for the MCP server.
-- Read-only from the MCP server's perspective; populated by seed.py.
-- Deliberately separate from the per-service SQLite DBs the lab runs.
--
-- This DB is the deliberately UN-REDACTED baseline surface for the MCP
-- integration demo: every column below is synthetic, but the PII columns are
-- shaped to match Resolve's built-in redaction patterns (email, phone, DOB,
-- credit card, bank account, card expiration, SSN, EIN, IP address, US street
-- address) so a query result is visibly recognizable as sensitive data.
-- All values are fabricated. No real person's data appears here.

DROP TABLE IF EXISTS claims;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS policies;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id     INTEGER PRIMARY KEY,
    first_name      TEXT    NOT NULL,
    last_name       TEXT    NOT NULL,
    customer_type   TEXT    NOT NULL,   -- individual | business
    business_name   TEXT,               -- business customers only
    email           TEXT    NOT NULL UNIQUE,  -- consumer domains; a few @atlasfi.com internal
    phone           TEXT    NOT NULL,   -- (305) 555-0148
    ssn             TEXT,               -- 123-45-6789   (individual policyholders)
    ein             TEXT,               -- 47-3820194    (business policyholders only)
    date_of_birth   TEXT,               -- 1978-04-12    (individual policyholders)
    drivers_license TEXT,               -- state-formatted
    street_address  TEXT    NOT NULL,   -- 4821 Windermere Ln, Apt 3B
    city            TEXT    NOT NULL,
    state           TEXT    NOT NULL,
    zip             TEXT    NOT NULL,
    last_login_ip   TEXT    NOT NULL,   -- 73.118.204.37
    join_date       TEXT    NOT NULL    -- ISO date
);

CREATE TABLE policies (
    policy_id            INTEGER PRIMARY KEY,
    customer_id          INTEGER NOT NULL REFERENCES customers(customer_id),
    policy_number        TEXT    NOT NULL UNIQUE,  -- ATL-AU-2024-118437
    policy_type          TEXT    NOT NULL,   -- auto | home | life | commercial
    status               TEXT    NOT NULL,   -- active | lapsed | cancelled
    premium_monthly      REAL    NOT NULL,
    coverage_amount      REAL    NOT NULL,
    deductible           REAL    NOT NULL,
    beneficiary          TEXT,              -- life policies only: "Maria Chen (spouse)"
    assigned_agent       TEXT    NOT NULL,
    assigned_agent_email TEXT    NOT NULL,  -- @atlasfi.com (internal)
    start_date           TEXT    NOT NULL,
    renewal_date         TEXT    NOT NULL
);

CREATE TABLE claims (
    claim_id        INTEGER PRIMARY KEY,
    policy_id       INTEGER NOT NULL REFERENCES policies(policy_id),
    claim_number    TEXT    NOT NULL UNIQUE,  -- CLM-2025-0041827
    claim_date      TEXT    NOT NULL,
    amount          REAL    NOT NULL,
    status          TEXT    NOT NULL,       -- open | approved | denied | paid
    description     TEXT    NOT NULL,
    vin             TEXT,                   -- auto policies only (17 chars)
    adjuster_name   TEXT    NOT NULL,
    adjuster_email  TEXT    NOT NULL        -- @atlasfi.com (internal)
);

CREATE TABLE payments (
    payment_id         INTEGER PRIMARY KEY,
    policy_id          INTEGER NOT NULL REFERENCES policies(policy_id),
    payment_date       TEXT    NOT NULL,
    amount             REAL    NOT NULL,
    method             TEXT    NOT NULL,   -- ach | card | check
    card_brand         TEXT,               -- card only: visa | mastercard | amex | discover
    credit_card_number TEXT,               -- card only: 4539-1488-0343-6467 (Luhn-valid)
    card_expiration    TEXT,               -- card only: 07/29
    bank_account       TEXT,               -- ach only:  000183947261
    routing_number     TEXT,               -- ach only:  021000021 (ABA-valid)
    check_number       TEXT                -- check only
);

CREATE INDEX idx_policies_customer ON policies(customer_id);
CREATE INDEX idx_claims_policy     ON claims(policy_id);
CREATE INDEX idx_payments_policy   ON payments(policy_id);
