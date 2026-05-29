"""
Accounting module — end-to-end test cases.

Covers every endpoint in app/routers/accounting.py:

  KPIs
  ├── TC-01  GET  /kpis  — returns required fields
  Chart of Accounts
  ├── TC-02  GET  /accounts  — seeded defaults present
  ├── TC-03  POST /accounts  — create a new account
  ├── TC-04  POST /accounts  — duplicate code returns 409
  ├── TC-05  POST /accounts  — missing name returns 422
  Journal Entries
  ├── TC-06  GET  /journal-entries  — returns list
  ├── TC-07  POST /journal-entries  — create draft entry
  ├── TC-08  POST /journal-entries  — missing description returns 422
  ├── TC-09  POST /journal-entries/{id}/post  — draft → posted
  ├── TC-10  POST /journal-entries/{id}/post  — posting again returns 409
  Bank Accounts
  ├── TC-11  GET  /bank-accounts  — seeded defaults present
  ├── TC-12  POST /bank-accounts/{id}/import  — CSV import
  ├── TC-13  POST /bank-accounts/{id}/import  — bad file returns 400
  ├── TC-14  GET  /bank-accounts/{id}/transactions  — lists imported txns
  ├── TC-15  POST /bank-accounts/{id}/reconcile  — marks txns reconciled
  Close Period
  ├── TC-16  GET  /close-period/preview  — returns preview data
  ├── TC-17  POST /close-period  — closes a period
  ├── TC-18  POST /close-period  — closing same period again returns 409
  Financial Reports
  ├── TC-19  GET  /reports/profit-loss
  ├── TC-20  GET  /reports/balance-sheet
  ├── TC-21  GET  /reports/trial-balance
  ├── TC-22  GET  /reports/cash-flow
  Auth guard
  └── TC-23  Any endpoint without token returns 401
"""

import io
import random
import pytest

# Unique per test run so re-runs against a shared DB don't collide
_RUN_ID   = random.randint(1000, 8999)
ACC_CODE  = str(_RUN_ID)       # e.g. "4721" — used for TC-03/TC-04
# Use a year far in the past that's very unlikely to already be closed
CLOSE_YEAR, CLOSE_MONTH = 2000 + (_RUN_ID % 20), (_RUN_ID % 12) + 1

ACC_URL = "/accounting"


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def make_csv(rows: list[dict]) -> bytes:
    """Build a minimal bank-statement CSV in memory."""
    lines = ["Date,Description,Amount"]
    for r in rows:
        lines.append(f"{r['date']},{r['desc']},{r['amount']}")
    return "\n".join(lines).encode()


# ─────────────────────────────────────────────
# TC-01  KPIs
# ─────────────────────────────────────────────

def test_tc01_kpis_returns_required_fields(client, auth):
    r = client.get(f"{ACC_URL}/kpis", headers=auth)
    assert r.status_code == 200
    data = r.json()
    for key in ("total_accounts", "active_accounts", "entries_this_month",
                "entries_total", "total_debits_posted", "total_credits_posted",
                "draft_entries", "posted_entries"):
        assert key in data, f"Missing KPI field: {key}"


# ─────────────────────────────────────────────
# TC-02  Chart of Accounts — seeded defaults
# ─────────────────────────────────────────────

def test_tc02_accounts_seeded_defaults(client, auth):
    r = client.get(f"{ACC_URL}/accounts", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert data["total"] >= 10, "Expected at least 10 seeded accounts"
    codes = {a["code"] for a in data["items"]}
    for expected in ("1000", "1200", "2000", "4000", "5000"):
        assert expected in codes, f"Seeded account code {expected} missing"


# ─────────────────────────────────────────────
# TC-03  Create a new account
# ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def created_account(client, auth):
    r = client.post(f"{ACC_URL}/accounts", headers=auth, json={
        "code":         ACC_CODE,
        "name":         "Test Suspense Account",
        "account_type": "Asset",
        "description":  "Created by automated test",
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_tc03_create_account(created_account):
    acc = created_account
    assert acc["code"] == ACC_CODE
    assert acc["name"] == "Test Suspense Account"
    assert acc["account_type"] == "Asset"
    assert acc["is_active"] is True


# ─────────────────────────────────────────────
# TC-04  Duplicate account code → 409
# ─────────────────────────────────────────────

def test_tc04_duplicate_account_code(client, auth, created_account):
    r = client.post(f"{ACC_URL}/accounts", headers=auth, json={
        "code":         ACC_CODE,
        "name":         "Duplicate",
        "account_type": "Liability",
    })
    assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"


# ─────────────────────────────────────────────
# TC-05  Missing required field → 422
# ─────────────────────────────────────────────

def test_tc05_create_account_missing_name(client, auth):
    r = client.post(f"{ACC_URL}/accounts", headers=auth, json={
        "code":         "8888",
        "account_type": "asset",
    })
    assert r.status_code == 422


# ─────────────────────────────────────────────
# TC-06  Journal Entries list
# ─────────────────────────────────────────────

def test_tc06_journal_entries_list(client, auth):
    r = client.get(f"{ACC_URL}/journal-entries", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert isinstance(data["items"], list)


# ─────────────────────────────────────────────
# TC-07  Create a journal entry
# ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def created_entry(client, auth):
    r = client.post(f"{ACC_URL}/journal-entries", headers=auth, json={
        "entry_date":   "2026-05-01",
        "description":  "Test utility payment",
        "debit_amount": 500.00,
        "credit_amount": 0,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_tc07_create_journal_entry(created_entry):
    e = created_entry
    assert e["description"] == "Test utility payment"
    assert e["debit_amount"] == 500.0
    assert e["status"] == "draft"
    assert e["reference"].startswith("JE-")


# ─────────────────────────────────────────────
# TC-08  Missing description → 422
# ─────────────────────────────────────────────

def test_tc08_create_entry_missing_description(client, auth):
    r = client.post(f"{ACC_URL}/journal-entries", headers=auth, json={
        "entry_date":   "2026-05-01",
        "debit_amount": 100.00,
        "credit_amount": 0,
    })
    assert r.status_code == 422


# ─────────────────────────────────────────────
# TC-09  Post a journal entry (draft → posted)
# ─────────────────────────────────────────────

def test_tc09_post_journal_entry(client, auth, created_entry):
    entry_id = created_entry["id"]
    r = client.post(f"{ACC_URL}/journal-entries/{entry_id}/post", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "posted"


# ─────────────────────────────────────────────
# TC-10  Posting already-posted entry → 409
# ─────────────────────────────────────────────

def test_tc10_post_already_posted_entry(client, auth, created_entry):
    entry_id = created_entry["id"]
    r = client.post(f"{ACC_URL}/journal-entries/{entry_id}/post", headers=auth)
    assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"


# ─────────────────────────────────────────────
# TC-11  Bank accounts — seeded defaults
# ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def bank_accounts(client, auth):
    r = client.get(f"{ACC_URL}/bank-accounts", headers=auth)
    assert r.status_code == 200, r.text
    accounts = r.json()
    assert len(accounts) >= 1, "Expected at least 1 seeded bank account"
    return accounts


def test_tc11_bank_accounts_seeded(bank_accounts):
    names = {b["name"] for b in bank_accounts}
    assert "Main Checking" in names


# ─────────────────────────────────────────────
# TC-12  Import CSV bank statement
# ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def bank_id(bank_accounts):
    return bank_accounts[0]["id"]


@pytest.fixture(scope="module")
def imported_statement(client, auth, bank_id):
    csv_bytes = make_csv([
        {"date": "2026-05-01", "desc": "Office supplies",  "amount": "-250.00"},
        {"date": "2026-05-03", "desc": "Client payment",   "amount": "5000.00"},
        {"date": "2026-05-10", "desc": "Utility bill",     "amount": "-180.50"},
    ])
    r = client.post(
        f"{ACC_URL}/bank-accounts/{bank_id}/import",
        headers={"Authorization": auth["Authorization"]},
        files={"file": ("statement.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_tc12_csv_import(imported_statement):
    data = imported_statement
    assert "imported" in data
    assert data["imported"] == 3
    assert "bank_account" in data


# ─────────────────────────────────────────────
# TC-13  Import bad file → 400
# ─────────────────────────────────────────────

def test_tc13_import_bad_csv(client, auth, bank_id):
    garbage = b"this is not a csv at all!!!"
    r = client.post(
        f"{ACC_URL}/bank-accounts/{bank_id}/import",
        headers={"Authorization": auth["Authorization"]},
        files={"file": ("bad.csv", io.BytesIO(garbage), "text/csv")},
    )
    assert r.status_code in (400, 422), f"Expected 400/422, got {r.status_code}: {r.text}"


# ─────────────────────────────────────────────
# TC-14  List bank transactions after import
# ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def transactions(client, auth, bank_id, imported_statement):
    r = client.get(f"{ACC_URL}/bank-accounts/{bank_id}/transactions", headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def test_tc14_list_transactions(transactions):
    data = transactions
    assert "items" in data
    assert len(data["items"]) >= 3


# ─────────────────────────────────────────────
# TC-15  Reconcile transactions
# ─────────────────────────────────────────────

def test_tc15_reconcile_transactions(client, auth, bank_id, transactions):
    unreconciled_ids = [t["id"] for t in transactions["items"] if not t["is_reconciled"]]
    assert len(unreconciled_ids) > 0, "No unreconciled transactions to reconcile"

    r = client.post(f"{ACC_URL}/bank-accounts/{bank_id}/reconcile", headers=auth, json={
        "transaction_ids": unreconciled_ids,
    })
    assert r.status_code == 200, r.text
    assert r.json()["reconciled"] == len(unreconciled_ids)


# ─────────────────────────────────────────────
# TC-16  Close Period — preview
# ─────────────────────────────────────────────

def test_tc16_close_period_preview(client, auth):
    r = client.get(f"{ACC_URL}/close-period/preview?year={CLOSE_YEAR}&month={CLOSE_MONTH}", headers=auth)
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("year", "month", "posted_entries", "draft_entries",
                "unreconciled_transactions", "net_balance", "already_closed"):
        assert key in data, f"Missing preview field: {key}"


# ─────────────────────────────────────────────
# TC-17  Close Period
# ─────────────────────────────────────────────

def test_tc17_close_period(client, auth):
    r = client.post(f"{ACC_URL}/close-period", headers=auth, json={
        "year":  CLOSE_YEAR,
        "month": CLOSE_MONTH,
        "notes": "Closed by automated test",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["year"] == CLOSE_YEAR
    assert data["month"] == CLOSE_MONTH


# ─────────────────────────────────────────────
# TC-18  Close same period again → 409
# ─────────────────────────────────────────────

def test_tc18_close_period_duplicate(client, auth):
    r = client.post(f"{ACC_URL}/close-period", headers=auth, json={
        "year":  CLOSE_YEAR,
        "month": CLOSE_MONTH,
    })
    assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"


# ─────────────────────────────────────────────
# TC-19 to TC-22  Financial Reports
# ─────────────────────────────────────────────

@pytest.mark.parametrize("endpoint,required_keys", [
    ("profit-loss",   ["period_label", "total_revenue", "total_expenses", "net_income"]),
    ("balance-sheet", ["as_of", "total_assets", "total_liabilities", "total_equity"]),
    ("trial-balance", ["as_of", "total_debits", "total_credits", "is_balanced"]),
    ("cash-flow",     ["period_label", "total_inflows", "total_outflows", "net_cash_flow"]),
])
def test_financial_reports(client, auth, endpoint, required_keys):
    r = client.get(f"{ACC_URL}/reports/{endpoint}", headers=auth)
    assert r.status_code == 200, f"{endpoint} failed: {r.text}"
    data = r.json()
    for key in required_keys:
        assert key in data, f"Report '{endpoint}' missing field: {key}"


# ─────────────────────────────────────────────
# TC-23  No token → 401 on every endpoint
# ─────────────────────────────────────────────

@pytest.mark.parametrize("method,path", [
    ("GET",  "/accounting/kpis"),
    ("GET",  "/accounting/accounts"),
    ("GET",  "/accounting/journal-entries"),
    ("GET",  "/accounting/bank-accounts"),
    ("GET",  "/accounting/reports/profit-loss"),
])
def test_tc23_unauthenticated_returns_401(client, method, path):
    r = client.request(method, path)
    assert r.status_code == 401, f"{method} {path} expected 401, got {r.status_code}"
