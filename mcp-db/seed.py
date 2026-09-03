"""Create and populate mcp-db/data.db with synthetic Atlas Financial data.

Deterministic (random.seed(42)) so repeated runs reproduce the same DB byte-for-
byte in content. Run:  python seed.py

The data is deliberately PII-rich. Every PII column is shaped to match one of
Resolve's built-in redaction patterns (email, phone, date of birth, credit card
number, bank account, card expiration, SSN, EIN, IP address, US street address)
so that a query over the MCP integration returns values that are recognizably
sensitive. Everything is fabricated: names are drawn from generic pools, phone
numbers use the reserved 555-01xx fictional exchange, and card/routing numbers
are checksum-valid but not issued. No real person's data appears here.

Override the output path with SEED_DB_PATH (used to build a preview DB without
clobbering data.db).
"""

import os
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = Path(os.environ.get("SEED_DB_PATH", HERE / "data.db"))
SCHEMA_PATH = HERE / "schema.sql"

random.seed(42)

TODAY = date(2026, 8, 1)
N_CUSTOMERS = 60
N_BUSINESS = 8          # commercial policyholders (get an EIN, not an SSN)
N_INTERNAL = 4          # employee policyholders kept on @atlasfi.com

FIRST_NAMES = [
    "Sarah", "James", "Maria", "David", "Linda", "Robert", "Priya", "Michael",
    "Aisha", "Daniel", "Emily", "Carlos", "Nina", "Kevin", "Grace", "Omar",
    "Hannah", "Wei", "Laura", "Tomas", "Jasmine", "Andre", "Sofia", "Trevor",
    "Rachel", "Malik", "Elena", "Brandon", "Yuki", "Marcus",
]
LAST_NAMES = [
    "Chen", "Patel", "Garcia", "Nguyen", "Johnson", "Kim", "Rossi", "Brown",
    "Okafor", "Muller", "Silva", "Adams", "Haddad", "Novak", "Reyes", "Watson",
    "Delgado", "Whitfield", "Bautista", "Sorensen", "Ferreira", "Kowalski",
]

# Consumer mail providers, weighted the way a real book of business skews.
EMAIL_DOMAINS = (
    ["gmail.com"] * 9
    + ["yahoo.com"] * 4
    + ["outlook.com"] * 3
    + ["hotmail.com"] * 3
    + ["icloud.com"] * 3
    + ["aol.com"] * 2
    + ["proton.me"] * 1
)

# city, state, area code, zip pool, driver's-license format key
LOCATIONS = [
    ("Austin",    "TX", "512", ["78701", "78704", "78745", "78759"]),
    ("Denver",    "CO", "303", ["80202", "80205", "80211", "80220"]),
    ("Seattle",   "WA", "206", ["98101", "98103", "98115", "98122"]),
    ("Boston",    "MA", "617", ["02108", "02116", "02127", "02135"]),
    ("Miami",     "FL", "305", ["33125", "33131", "33137", "33186"]),
    ("Chicago",   "IL", "312", ["60601", "60614", "60622", "60647"]),
    ("Portland",  "OR", "503", ["97201", "97209", "97214", "97229"]),
    ("Atlanta",   "GA", "404", ["30303", "30305", "30312", "30318"]),
    ("Phoenix",   "AZ", "602", ["85004", "85016", "85032", "85048"]),
    ("Charlotte", "NC", "704", ["28202", "28203", "28209", "28277"]),
    ("Nashville", "TN", "615", ["37203", "37206", "37212", "37215"]),
    ("Columbus",  "OH", "614", ["43201", "43206", "43215", "43220"]),
]

STREET_NAMES = [
    "Windermere", "Crestview", "Larkspur", "Bramblewood", "Kingsley",
    "Ashford", "Cedar Hollow", "Fairmount", "Thornbury", "Marigold",
    "Silver Birch", "Rockridge", "Pinehurst", "Wyndham", "Old Mill",
    "Copper Beech", "Havenwood", "Sagebrush", "Whitcomb", "Ellerslie",
]
STREET_TYPES = ["St", "Ave", "Rd", "Ln", "Dr", "Ct", "Blvd", "Way", "Ter", "Pl"]
UNIT_FORMS = ["Apt {n}{a}", "Unit {n}", "#{n}"]          # residential
BIZ_UNIT_FORMS = ["Ste {n}", "Bldg {a}, Ste {n}", "Unit {n}"]  # commercial

BUSINESS_SUFFIXES = ["LLC", "Inc", "Holdings LLC", "Group Inc", "& Sons LLC", "Co"]
BUSINESS_WORDS = [
    "Northgate Logistics", "Harbor Point Dental", "Sunbelt Roofing",
    "Riverstone Catering", "Precision Machining", "Lakeside Property Mgmt",
    "Copperfield Landscaping", "Ironwood Fabrication", "Bluecrest Trucking",
    "Meridian Auto Body",
]

# Internal staff: agents on policies, adjusters on claims. All @atlasfi.com.
AGENTS = [
    "Dana Whitcombe", "Paul Ferraro", "Renee Alvarado", "Stephen Ochoa",
    "Marla Devine", "Curtis Nakamura", "Bethany Kline", "Victor Amadi",
]
ADJUSTERS = [
    "Gordon Rhee", "Alicia Trent", "Neil Sandoval", "Wanda Piotrowski",
    "Desmond Vance", "Kayla Berg",
]

POLICY_TYPES = ["auto", "home", "life"]
POLICY_STATUS = ["active", "active", "active", "lapsed", "cancelled"]  # weighted active
CLAIM_STATUS = ["open", "approved", "denied", "paid"]
POLICY_CODE = {"auto": "AU", "home": "HO", "life": "LI", "commercial": "CM"}
# (description, min amount, max amount) - the loss type bounds the payout so a
# windshield chip never books at $27k. Life is special-cased against coverage.
CLAIM_DESCRIPTIONS = {
    "auto": [
        ("Rear-end collision at signalized intersection", 2500, 18000),
        ("Windshield crack from road debris", 350, 1200),
        ("Hail damage to hood and roof panels", 1800, 9000),
        ("Theft of vehicle from apartment lot", 8000, 42000),
        ("Single-vehicle skid, guardrail contact", 3000, 22000),
    ],
    "home": [
        ("Water damage from burst supply line", 3000, 45000),
        ("Roof damage from windstorm", 4000, 38000),
        ("Kitchen fire, smoke remediation", 12000, 120000),
        ("Burglary, forced entry through rear door", 1500, 25000),
        ("Sewer backup in finished basement", 5000, 40000),
    ],
    # Life amounts are derived from coverage, not these bounds.
    "life": [
        ("Beneficiary payout claim", 1.0, 1.0),
        ("Terminal illness rider claim", 0.25, 0.5),
        ("Accidental death rider claim", 1.0, 1.0),
    ],
    "commercial": [
        ("Fleet vehicle collision with property damage", 8000, 95000),
        ("Slip-and-fall general liability claim", 5000, 150000),
        ("Business interruption after power surge", 20000, 400000),
        ("Tools and equipment stolen from job site", 3000, 60000),
        ("Cargo loss in transit", 10000, 180000),
    ],
}

RELATIONSHIPS = ["spouse", "son", "daughter", "sister", "brother", "mother", "father"]

# Auto WMIs (world manufacturer identifiers) so VINs read as real makes.
VIN_WMI = ["1HG", "5YJ", "JTM", "1FT", "WBA", "3VW", "2T1", "5NP", "1G1", "JHM"]
VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"   # no I, O, Q
VIN_YEAR = "NPRSTVWXY"

# Consumer-ISP-looking /8s, plus some corporate NAT / VPN egress ranges.
IP_PREFIXES = [
    (73, None), (98, None), (24, None), (67, None), (174, None), (108, None),
    (71, None), (75, None), (47, None), (10, 0), (192, 168), (172, 18),
]

DL_FORMATS = {
    "TX": "DDDDDDDD",
    "FL": "LDDDDDDDDDDDD",
    "CA": "LDDDDDDD",
    "WA": "LLLLLDDDLD",
    "MA": "SDDDDDDDD",
    "IL": "LDDDDDDDDDDD",
    "CO": "DDDDDDDDD",
    "OR": "DDDDDDD",
    "GA": "DDDDDDDDD",
    "AZ": "LDDDDDDDD",
    "NC": "DDDDDDDDDDDD",
    "TN": "DDDDDDDDD",
    "OH": "LLDDDDDD",
}


def iso(d: date) -> str:
    return d.isoformat()


def digits(n: int) -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(n))


def luhn_check_digit(payload: str) -> str:
    """Check digit that makes payload + digit pass the Luhn test."""
    total = 0
    for i, ch in enumerate(reversed(payload)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def make_card() -> tuple[str, str]:
    """Return (brand, formatted Luhn-valid card number)."""
    brand = random.choices(
        ["visa", "mastercard", "amex", "discover"], weights=[5, 4, 2, 1]
    )[0]
    if brand == "visa":
        payload = "4" + digits(14)
    elif brand == "mastercard":
        payload = str(random.randint(51, 55)) + digits(13)
    elif brand == "discover":
        payload = "6011" + digits(11)
    else:  # amex: 15 digits
        payload = random.choice(["34", "37"]) + digits(12)
    num = payload + luhn_check_digit(payload)
    if brand == "amex":
        formatted = f"{num[:4]}-{num[4:10]}-{num[10:]}"
    else:
        formatted = "-".join(num[i:i + 4] for i in range(0, 16, 4))
    return brand, formatted


def make_card_expiration() -> str:
    """MM/YY, still valid relative to TODAY."""
    year = random.randint(TODAY.year, TODAY.year + 4)
    month = random.randint(1, 12)
    if year == TODAY.year:
        month = random.randint(TODAY.month, 12)
    return f"{month:02d}/{year % 100:02d}"


def make_routing_number() -> str:
    """9-digit ABA number whose checksum validates."""
    prefix = random.choice(
        ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12",
         "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32"]
    )
    d = [int(c) for c in prefix + digits(6)]
    checksum = 3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + d[2] + d[5]
    return "".join(str(x) for x in d) + str((10 - checksum % 10) % 10)


def make_bank_account() -> str:
    return digits(random.choice([8, 9, 10, 11, 12]))


def make_ssn() -> str:
    """Fabricated but well-formed: no 000/666/9xx area, no 00 group, no 0000 serial."""
    area = random.choice([n for n in range(101, 900) if n != 666])
    return f"{area:03d}-{random.randint(1, 99):02d}-{random.randint(1, 9999):04d}"


def make_ein() -> str:
    prefix = random.choice([20, 26, 27, 45, 46, 47, 81, 82, 83, 84, 85, 87, 88])
    return f"{prefix}-{random.randint(1000000, 9999999)}"


def make_phone(area: str) -> str:
    """Reserved 555-01xx fictional exchange, real area code for the city."""
    return f"({area}) 555-{random.randint(100, 199):04d}"


def make_ip() -> str:
    a, b = random.choice(IP_PREFIXES)
    if b is None:
        return f"{a}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
    return f"{a}.{b}.{random.randint(0, 255)}.{random.randint(1, 254)}"


def make_street_address(business: bool = False) -> str:
    base = (
        f"{random.randint(12, 9899)} {random.choice(STREET_NAMES)} "
        f"{random.choice(STREET_TYPES)}"
    )
    forms, odds = (BIZ_UNIT_FORMS, 0.6) if business else (UNIT_FORMS, 0.3)
    if random.random() < odds:
        unit = random.choice(forms).format(
            n=random.randint(1, 480), a=random.choice("ABCDEF")
        )
        return f"{base}, {unit}"
    return base


def make_dob() -> str:
    return iso(date(random.randint(1945, 2004), random.randint(1, 12), random.randint(1, 28)))


def make_drivers_license(state: str) -> str:
    fmt = DL_FORMATS.get(state, "LDDDDDDD")
    out = []
    for ch in fmt:
        if ch == "D":
            out.append(str(random.randint(0, 9)))
        elif ch == "L":
            out.append(random.choice("ABCDEFGHJKLMNPRSTUVWXYZ"))
        else:  # S: MA-style leading letter
            out.append("S")
    return "".join(out)


def make_vin() -> str:
    wmi = random.choice(VIN_WMI)
    vds = "".join(random.choice(VIN_CHARS) for _ in range(5))
    check = random.choice("0123456789X")
    year = random.choice(VIN_YEAR)
    plant = random.choice("ABCDEFGHJKLMNPRSTUVWXYZ")
    serial = digits(6)
    return f"{wmi}{vds}{check}{year}{plant}{serial}"


def make_email(fn: str, ln: str, taken: set, internal: bool) -> str:
    domain = "atlasfi.com" if internal else random.choice(EMAIL_DOMAINS)
    f, l = fn.lower(), ln.lower()
    forms = [
        f"{f}.{l}", f"{f}{l}", f"{f[0]}{l}", f"{f}_{l}", f"{f}.{l[0]}",
        f"{f}{l}{random.randint(1, 99)}", f"{f}.{l}{random.randint(60, 99)}",
        f"{l}.{f}",
    ]
    for local in random.sample(forms, len(forms)):
        candidate = f"{local}@{domain}"
        if candidate not in taken:
            taken.add(candidate)
            return candidate
    candidate = f"{f}.{l}.{random.randint(1000, 9999)}@{domain}"
    taken.add(candidate)
    return candidate


def agent_email(name: str) -> str:
    f, l = name.lower().split(" ", 1)
    return f"{f}.{l.replace(' ', '')}@atlasfi.com"


def build():
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text())

    # ── customers ────────────────────────────────────────────────
    ids = list(range(1, N_CUSTOMERS + 1))
    business_ids = set(random.sample(ids, N_BUSINESS))
    internal_ids = set(random.sample([i for i in ids if i not in business_ids], N_INTERNAL))

    customers = []
    instruments = {}   # customer_id -> payment instrument reused across payments
    cust_meta = {}     # customer_id -> (type, name, state)
    taken_emails: set = set()
    biz_names = random.sample(BUSINESS_WORDS, N_BUSINESS)

    for cid in ids:
        fn = random.choice(FIRST_NAMES)
        ln = random.choice(LAST_NAMES)
        city, state, area, zips = random.choice(LOCATIONS)
        is_business = cid in business_ids
        is_internal = cid in internal_ids

        if is_business:
            ctype = "business"
            business_name = f"{biz_names.pop()} {random.choice(BUSINESS_SUFFIXES)}"
            ssn = None
            ein = make_ein()
            dob = None
        else:
            ctype = "individual"
            business_name = None
            ssn = make_ssn()
            ein = None
            dob = make_dob()

        customers.append((
            cid, fn, ln, ctype, business_name,
            make_email(fn, ln, taken_emails, is_internal),
            make_phone(area), ssn, ein, dob,
            make_drivers_license(state),
            make_street_address(is_business), city, state, random.choice(zips),
            make_ip(),
            iso(TODAY - timedelta(days=random.randint(90, 2600))),
        ))

        brand, card = make_card()
        instruments[cid] = {
            "card_brand": brand,
            "card_number": card,
            "card_expiration": make_card_expiration(),
            "bank_account": make_bank_account(),
            "routing_number": make_routing_number(),
        }
        cust_meta[cid] = (ctype, f"{fn} {ln}", state)

    conn.executemany(
        "INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", customers
    )

    # ── policies ─────────────────────────────────────────────────
    policies = []
    pid = 1
    for cid in ids:
        ctype, cname, _ = cust_meta[cid]
        for _ in range(random.randint(1, 3)):
            if ctype == "business":
                ptype = random.choices(["commercial", "auto"], weights=[7, 3])[0]
            else:
                ptype = random.choice(POLICY_TYPES)
            status = random.choice(POLICY_STATUS)
            premium = round(random.uniform(35, 320) * (3.5 if ptype == "commercial" else 1), 2)
            coverage = {
                "auto": random.choice([25000, 50000, 100000]),
                "home": random.choice([150000, 300000, 500000]),
                "life": random.choice([100000, 250000, 500000, 1000000]),
                "commercial": random.choice([500000, 1000000, 2000000, 5000000]),
            }[ptype]
            deductible = {
                "auto": random.choice([250, 500, 1000]),
                "home": random.choice([1000, 2500, 5000]),
                "life": 0,
                "commercial": random.choice([2500, 5000, 10000, 25000]),
            }[ptype]
            start = TODAY - timedelta(days=random.randint(30, 2200))
            renewal = start + timedelta(days=365 * (1 + (TODAY - start).days // 365))
            beneficiary = None
            if ptype == "life":
                beneficiary = (
                    f"{random.choice(FIRST_NAMES)} {cname.split()[1]} "
                    f"({random.choice(RELATIONSHIPS)})"
                )
            agent = random.choice(AGENTS)
            policy_number = (
                f"ATL-{POLICY_CODE[ptype]}-{start.year}-{random.randint(100000, 999999)}"
            )
            policies.append((
                pid, cid, policy_number, ptype, status, premium, float(coverage),
                float(deductible), beneficiary, agent, agent_email(agent),
                iso(start), iso(renewal),
            ))
            pid += 1
    conn.executemany(
        "INSERT INTO policies VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", policies
    )

    # ── claims ───────────────────────────────────────────────────
    claims = []
    clid = 1
    for pol in policies:
        p_id, ptype, status, coverage = pol[0], pol[3], pol[4], pol[6]
        if status == "cancelled":
            continue
        for _ in range(random.choices([0, 1, 2], weights=[5, 3, 2])[0]):
            cdate = TODAY - timedelta(days=random.randint(1, 700))
            desc, lo, hi = random.choice(CLAIM_DESCRIPTIONS[ptype])
            if ptype == "life":
                amount = round(coverage * random.uniform(lo, hi), 2)
            else:
                amount = round(min(random.uniform(lo, hi), coverage), 2)
            adjuster = random.choice(ADJUSTERS)
            claims.append((
                clid, p_id,
                f"CLM-{cdate.year}-{random.randint(100000, 999999)}",
                iso(cdate), amount,
                random.choice(CLAIM_STATUS),
                desc,
                make_vin() if ptype == "auto" else None,
                adjuster, agent_email(adjuster),
            ))
            clid += 1
    conn.executemany(
        "INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?)", claims
    )

    # ── payments ─────────────────────────────────────────────────
    # Each policy has a primary payment method; the customer's instrument is
    # reused across payments so the same card / account recurs as it would in
    # a real billing table.
    payments = []
    payid = 1
    for pol in policies:
        p_id, cid, premium, status = pol[0], pol[1], pol[5], pol[4]
        inst = instruments[cid]
        primary = random.choices(["ach", "card", "check"], weights=[5, 4, 1])[0]
        months = random.randint(6, 24) if status == "active" else random.randint(1, 4)
        for m in range(months):
            pdate = TODAY - timedelta(days=30 * m + random.randint(0, 5))
            method = primary if random.random() > 0.08 else random.choice(["ach", "card", "check"])
            card_brand = card_number = card_exp = None
            bank_account = routing = check_number = None
            if method == "card":
                card_brand = inst["card_brand"]
                card_number = inst["card_number"]
                card_exp = inst["card_expiration"]
            elif method == "ach":
                bank_account = inst["bank_account"]
                routing = inst["routing_number"]
            else:
                check_number = str(random.randint(1000, 9999))
            payments.append((
                payid, p_id, iso(pdate), premium, method,
                card_brand, card_number, card_exp,
                bank_account, routing, check_number,
            ))
            payid += 1
    conn.executemany(
        "INSERT INTO payments VALUES (?,?,?,?,?,?,?,?,?,?,?)", payments
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
