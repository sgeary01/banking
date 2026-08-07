"""Create and populate mcp-db/data.db with synthetic Atlas Financial data.

Deterministic (fixed random seed) so repeated runs reproduce the same DB.
Run:  python seed.py
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "data.db"
SCHEMA_PATH = HERE / "schema.sql"

random.seed(42)

FIRST_NAMES = [
    "Sarah", "James", "Maria", "David", "Linda", "Robert", "Priya", "Michael",
    "Aisha", "Daniel", "Emily", "Carlos", "Nina", "Kevin", "Grace", "Omar",
    "Hannah", "Wei", "Laura", "Tomas",
]
LAST_NAMES = [
    "Chen", "Patel", "Garcia", "Nguyen", "Johnson", "Kim", "Rossi", "Brown",
    "Okafor", "Muller", "Silva", "Adams", "Haddad", "Novak", "Reyes", "Watson",
]
CITIES = [
    ("Austin", "TX"), ("Denver", "CO"), ("Seattle", "WA"), ("Boston", "MA"),
    ("Miami", "FL"), ("Chicago", "IL"), ("Portland", "OR"), ("Atlanta", "GA"),
]
POLICY_TYPES = ["auto", "home", "life"]
POLICY_STATUS = ["active", "active", "active", "lapsed", "cancelled"]  # weighted active
CLAIM_STATUS = ["open", "approved", "denied", "paid"]
PAY_METHODS = ["ach", "ach", "card", "check"]
CLAIM_DESCRIPTIONS = {
    "auto": ["Rear-end collision", "Windshield crack", "Hail damage", "Theft of vehicle"],
    "home": ["Water damage from burst pipe", "Roof damage from storm", "Kitchen fire", "Burglary"],
    "life": ["Beneficiary payout claim", "Terminal illness rider claim"],
}

TODAY = date(2026, 8, 1)


def iso(d: date) -> str:
    return d.isoformat()


def build():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text())

    customers = []
    for cid in range(1, 51):  # 50 customers
        fn = random.choice(FIRST_NAMES)
        ln = random.choice(LAST_NAMES)
        city, state = random.choice(CITIES)
        email = f"{fn.lower()}.{ln.lower()}{cid}@atlasfi.com"
        join = TODAY - timedelta(days=random.randint(90, 2000))
        customers.append((cid, fn, ln, email, city, state, iso(join)))
    conn.executemany(
        "INSERT INTO customers VALUES (?,?,?,?,?,?,?)", customers
    )

    policies = []
    pid = 1
    for cid in range(1, 51):
        for _ in range(random.randint(1, 3)):  # 1-3 policies each
            ptype = random.choice(POLICY_TYPES)
            status = random.choice(POLICY_STATUS)
            premium = round(random.uniform(35, 320), 2)
            coverage = {
                "auto": random.choice([25000, 50000, 100000]),
                "home": random.choice([150000, 300000, 500000]),
                "life": random.choice([100000, 250000, 500000, 1000000]),
            }[ptype]
            start = TODAY - timedelta(days=random.randint(30, 1800))
            policies.append((pid, cid, ptype, status, premium, float(coverage), iso(start)))
            pid += 1
    conn.executemany(
        "INSERT INTO policies VALUES (?,?,?,?,?,?,?)", policies
    )

    claims = []
    clid = 1
    for pol in policies:
        p_id, _, ptype, status = pol[0], pol[1], pol[2], pol[3]
        if status == "cancelled":
            continue
        for _ in range(random.choices([0, 1, 2], weights=[6, 3, 1])[0]):
            cdate = TODAY - timedelta(days=random.randint(1, 700))
            amount = round(random.uniform(500, 40000), 2)
            claims.append((
                clid, p_id, iso(cdate), amount,
                random.choice(CLAIM_STATUS),
                random.choice(CLAIM_DESCRIPTIONS[ptype]),
            ))
            clid += 1
    conn.executemany(
        "INSERT INTO claims VALUES (?,?,?,?,?,?)", claims
    )

    payments = []
    payid = 1
    for pol in policies:
        p_id, premium, status = pol[0], pol[4], pol[3]
        # active policies pay ~ every month since start; lapsed pay a few then stop
        months = random.randint(6, 24) if status == "active" else random.randint(1, 4)
        for m in range(months):
            pdate = TODAY - timedelta(days=30 * m + random.randint(0, 5))
            payments.append((
                payid, p_id, iso(pdate), premium, random.choice(PAY_METHODS)
            ))
            payid += 1
    conn.executemany(
        "INSERT INTO payments VALUES (?,?,?,?,?)", payments
    )

    conn.commit()
    counts = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("customers", "policies", "claims", "payments")
    }
    conn.close()
    print(f"Wrote {DB_PATH}")
    for t, n in counts.items():
        print(f"  {t}: {n}")


if __name__ == "__main__":
    build()
