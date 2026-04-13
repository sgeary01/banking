"""
Seed script — creates realistic banking data:
  - 10 customers with auth accounts
  - 2-3 accounts per customer (checking, savings, sometimes credit)
  - Historical transactions (deposits, withdrawals, transfers)
  - A few high-value transactions to seed fraud alerts
"""

import httpx
import os
import random
import time
from datetime import datetime

AUTH_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")
CUSTOMER_URL = os.getenv("CUSTOMER_SERVICE_URL", "http://localhost:8002")
ACCOUNT_URL = os.getenv("ACCOUNT_SERVICE_URL", "http://localhost:8003")
TX_URL = os.getenv("TRANSACTION_SERVICE_URL", "http://localhost:8004")

CUSTOMERS = [
    {"first_name": "Alice",   "last_name": "Johnson",  "email": "alice@example.com",   "phone": "555-0101", "address": "123 Main St, Springfield"},
    {"first_name": "Bob",     "last_name": "Williams",  "email": "bob@example.com",     "phone": "555-0102", "address": "456 Oak Ave, Shelbyville"},
    {"first_name": "Carol",   "last_name": "Martinez",  "email": "carol@example.com",   "phone": "555-0103", "address": "789 Pine Rd, Capital City"},
    {"first_name": "David",   "last_name": "Brown",     "email": "david@example.com",   "phone": "555-0104", "address": "321 Elm St, Ogdenville"},
    {"first_name": "Eve",     "last_name": "Davis",     "email": "eve@example.com",     "phone": "555-0105", "address": "654 Maple Dr, North Haverbrook"},
    {"first_name": "Frank",   "last_name": "Wilson",    "email": "frank@example.com",   "phone": "555-0106", "address": "987 Cedar Ln, Brockway"},
    {"first_name": "Grace",   "last_name": "Anderson",  "email": "grace@example.com",   "phone": "555-0107", "address": "147 Birch Blvd, Springfield"},
    {"first_name": "Henry",   "last_name": "Taylor",    "email": "henry@example.com",   "phone": "555-0108", "address": "258 Walnut Way, Shelbyville"},
    {"first_name": "Iris",    "last_name": "Thomas",    "email": "iris@example.com",    "phone": "555-0109", "address": "369 Spruce St, Capital City"},
    {"first_name": "Jack",    "last_name": "Jackson",   "email": "jack@example.com",    "phone": "555-0110", "address": "741 Ash Ave, Ogdenville"},
]

PASSWORD = "password123"


def wait_for_services():
    print("Waiting for services to be ready…")
    for url, name in [(AUTH_URL, "auth"), (CUSTOMER_URL, "customer"), (ACCOUNT_URL, "account"), (TX_URL, "transaction")]:
        for attempt in range(30):
            try:
                r = httpx.get(f"{url}/health", timeout=3)
                if r.status_code == 200:
                    print(f"  ✓ {name}-service ready")
                    break
            except Exception:
                pass
            time.sleep(2)
        else:
            print(f"  ✗ {name}-service not ready after 60s — continuing anyway")


def create_customer_and_accounts(client_data: dict) -> tuple[str, list[str]]:
    """Returns (customer_id, [account_ids])"""

    # 1. Create customer profile
    r = httpx.post(f"{CUSTOMER_URL}/customers", json=client_data, timeout=10)
    if r.status_code == 409:
        # Already exists — fetch by listing (simple approach for idempotency)
        print(f"  Customer {client_data['email']} already exists, skipping")
        return None, []

    r.raise_for_status()
    customer_id = r.json()["id"]

    # 2. Register auth account
    httpx.post(f"{AUTH_URL}/auth/register", json={
        "email": client_data["email"],
        "password": PASSWORD,
        "customer_id": customer_id,
    }, timeout=10)  # May 409 if re-seeding, that's fine

    # 3. Create accounts
    account_ids = []

    # Checking account — everyone gets one
    r = httpx.post(f"{ACCOUNT_URL}/accounts", json={
        "customer_id": customer_id,
        "account_type": "checking",
        "initial_balance": round(random.uniform(500, 5000), 2),
    }, timeout=10)
    r.raise_for_status()
    account_ids.append(r.json()["id"])

    # Savings account — 80% of customers
    if random.random() < 0.8:
        r = httpx.post(f"{ACCOUNT_URL}/accounts", json={
            "customer_id": customer_id,
            "account_type": "savings",
            "initial_balance": round(random.uniform(2000, 25000), 2),
        }, timeout=10)
        r.raise_for_status()
        account_ids.append(r.json()["id"])

    # Credit account — 40% of customers
    if random.random() < 0.4:
        r = httpx.post(f"{ACCOUNT_URL}/accounts", json={
            "customer_id": customer_id,
            "account_type": "credit",
            "initial_balance": 0.0,
        }, timeout=10)
        r.raise_for_status()
        account_ids.append(r.json()["id"])

    return customer_id, account_ids


def generate_transactions(all_account_ids: list[str]):
    """Generate realistic transaction history."""
    print("\nGenerating transaction history…")

    # Regular deposits (payroll, etc.)
    payroll_amounts = [2500, 3200, 4100, 2800, 5000, 3750]
    for account_id in all_account_ids:
        for i in range(random.randint(3, 6)):
            amount = random.choice(payroll_amounts) + random.uniform(-50, 50)
            r = httpx.post(f"{TX_URL}/transactions/deposit", json={
                "account_id": account_id,
                "amount": round(amount, 2),
                "description": random.choice(["Payroll deposit", "Direct deposit", "ACH transfer in"]),
            }, timeout=15)
            if r.status_code == 201:
                print(f"  + Deposit ${amount:.0f} → {account_id[:8]}…")
            time.sleep(0.05)

    # Regular withdrawals / bills
    bill_descriptions = ["Electric bill", "Internet service", "Grocery store", "Gas station", "Restaurant", "Online shopping", "Streaming service"]
    for account_id in all_account_ids:
        for i in range(random.randint(4, 8)):
            amount = round(random.uniform(15, 350), 2)
            r = httpx.post(f"{TX_URL}/transactions/withdraw", json={
                "account_id": account_id,
                "amount": amount,
                "description": random.choice(bill_descriptions),
            }, timeout=15)
            if r.status_code == 201:
                print(f"  - Withdrawal ${amount:.0f} ← {account_id[:8]}…")
            time.sleep(0.05)

    # Transfers between accounts
    if len(all_account_ids) >= 2:
        for _ in range(8):
            src, dst = random.sample(all_account_ids, 2)
            amount = round(random.uniform(50, 800), 2)
            r = httpx.post(f"{TX_URL}/transactions/transfer", json={
                "source_account_id": src,
                "destination_account_id": dst,
                "amount": amount,
                "description": random.choice(["Transfer to savings", "Move funds", "Account transfer"]),
            }, timeout=15)
            if r.status_code == 201:
                print(f"  ↔ Transfer ${amount:.0f} {src[:8]}… → {dst[:8]}…")
            time.sleep(0.05)

    # High-value transactions — will trigger fraud alerts
    print("\nGenerating fraud-triggering transactions…")
    fraud_accounts = random.sample(all_account_ids, min(3, len(all_account_ids)))
    for account_id in fraud_accounts:
        amount = round(random.uniform(6000, 14000), 2)
        r = httpx.post(f"{TX_URL}/transactions/deposit", json={
            "account_id": account_id,
            "amount": amount,
            "description": "Large wire transfer",
        }, timeout=15)
        if r.status_code == 201:
            print(f"  ⚠ High-value deposit ${amount:.0f} → {account_id[:8]}… (fraud alert expected)")
        time.sleep(0.1)


def main():
    wait_for_services()
    print(f"\nSeeding {len(CUSTOMERS)} customers…\n")

    all_account_ids = []

    for cdata in CUSTOMERS:
        print(f"Creating {cdata['first_name']} {cdata['last_name']} ({cdata['email']})…")
        customer_id, account_ids = create_customer_and_accounts(cdata)
        if customer_id:
            print(f"  customer_id={customer_id}, accounts={len(account_ids)}")
            all_account_ids.extend(account_ids)

    print(f"\nCreated {len(all_account_ids)} accounts total")
    generate_transactions(all_account_ids)

    print("\n✓ Seed complete!")
    print(f"  Login with any seed user, e.g. alice@example.com / {PASSWORD}")


if __name__ == "__main__":
    main()
