#!/usr/bin/env python3
"""
Wipe all Firestore compliance data and reseed from scratch.

No Excel file required — seeds the canonical NJ LLC filing schedule
for Central Line Group LLC (formed April 27, 2026).

Usage:
    python scripts/init_compliance.py
    python scripts/init_compliance.py --service-account /path/to/sa.json
    python scripts/init_compliance.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path


# ── canonical filing data ─────────────────────────────────────────────────────
# All assigned_to = "LLC". No personal names.

_QUARTERLY: list[dict] = [
    # NJ Sales Tax — first return covers May-Jun (partial Q2 after Apr 27 formation)
    {
        "filing_type": "NJ Sales Tax Return",
        "jurisdiction": "New Jersey",
        "year": 2026, "quarter": "Q2 (May-Jun)", "period": "Q2 (May-Jun) 2026",
        "due_date": date(2026, 7, 31), "status": "Pending",
    },
    {
        "filing_type": "NJ Sales Tax Return",
        "jurisdiction": "New Jersey",
        "year": 2026, "quarter": "Q3 (Jul-Sep)", "period": "Q3 (Jul-Sep) 2026",
        "due_date": date(2026, 10, 31), "status": "Pending",
    },
    {
        "filing_type": "NJ Sales Tax Return",
        "jurisdiction": "New Jersey",
        "year": 2026, "quarter": "Q4 (Oct-Dec)", "period": "Q4 (Oct-Dec) 2026",
        "due_date": date(2027, 1, 31), "status": "Pending",
    },
    # Federal Estimated Tax 1040-ES
    {
        "filing_type": "Federal Est. Tax 1040-ES",
        "jurisdiction": "Federal",
        "year": 2026, "quarter": "Q2 (Apr-Jun)", "period": "Q2 (Apr-Jun) 2026",
        "due_date": date(2026, 6, 16), "status": "Pending",
        "notes": "Pay at irs.gov/payments",
    },
    {
        "filing_type": "Federal Est. Tax 1040-ES",
        "jurisdiction": "Federal",
        "year": 2026, "quarter": "Q3 (Jul-Sep)", "period": "Q3 (Jul-Sep) 2026",
        "due_date": date(2026, 9, 15), "status": "Pending",
        "notes": "Pay at irs.gov/payments",
    },
    {
        "filing_type": "Federal Est. Tax 1040-ES",
        "jurisdiction": "Federal",
        "year": 2026, "quarter": "Q4 (Oct-Dec)", "period": "Q4 (Oct-Dec) 2026",
        "due_date": date(2027, 1, 15), "status": "Pending",
        "notes": "Pay at irs.gov/payments",
    },
    # NJ Estimated Tax NJ-1040-ES
    {
        "filing_type": "NJ Est. Tax NJ-1040-ES",
        "jurisdiction": "New Jersey",
        "year": 2026, "quarter": "Q2 (Apr-Jun)", "period": "Q2 (Apr-Jun) 2026",
        "due_date": date(2026, 6, 16), "status": "Pending",
        "notes": "Pay at nj.gov/taxation",
    },
    {
        "filing_type": "NJ Est. Tax NJ-1040-ES",
        "jurisdiction": "New Jersey",
        "year": 2026, "quarter": "Q3 (Jul-Sep)", "period": "Q3 (Jul-Sep) 2026",
        "due_date": date(2026, 9, 15), "status": "Pending",
        "notes": "Pay at nj.gov/taxation",
    },
    {
        "filing_type": "NJ Est. Tax NJ-1040-ES",
        "jurisdiction": "New Jersey",
        "year": 2026, "quarter": "Q4 (Oct-Dec)", "period": "Q4 (Oct-Dec) 2026",
        "due_date": date(2027, 1, 15), "status": "Pending",
        "notes": "Pay at nj.gov/taxation",
    },
]

_ANNUAL: list[dict] = [
    {
        "filing_type": "Federal Form 1065",
        "jurisdiction": "Federal",
        "year": 2026, "due_date": date(2027, 3, 15), "status": "Pending",
        "notes": "Partnership return + K-1s for each member",
    },
    {
        "filing_type": "NJ Form NJ-1065",
        "jurisdiction": "New Jersey",
        "year": 2026, "due_date": date(2027, 3, 15), "status": "Pending",
        "notes": "NJ partnership return — file at nj.gov/taxation",
    },
    {
        "filing_type": "Personal Form 1040",
        "jurisdiction": "Federal",
        "year": 2026, "due_date": date(2027, 4, 15), "status": "Pending",
        "notes": "Attach Schedule K-1 from Form 1065",
    },
    {
        "filing_type": "Personal NJ-1040",
        "jurisdiction": "New Jersey",
        "year": 2026, "due_date": date(2027, 4, 15), "status": "Pending",
        "notes": "NJ personal return — attach K-1 from NJ-1065",
    },
    {
        "filing_type": "NJ Annual Report ($75)",
        "jurisdiction": "New Jersey",
        "year": 2027, "due_date": date(2027, 4, 30), "status": "Pending",
        "notes": "File at njportal.com/DOR/annualreports — $75 fee",
    },
]

_ONE_TIME: list[dict] = [
    {
        "filing_type": "NJ LLC Formation",
        "jurisdiction": "New Jersey",
        "due_date": date(2026, 4, 27),
        "status": "Done",
        "date_filed": date(2026, 4, 27),
        "notes": "Certificate of Formation filed with NJ Division of Revenue",
    },
    {
        "filing_type": "FinCEN BOI Report",
        "jurisdiction": "Federal",
        "due_date": date(2026, 4, 27),
        "status": "Done",
        "date_filed": date(2026, 4, 27),
        "notes": "Beneficial Ownership Information report — boiefiling.fincen.gov",
    },
    {
        "filing_type": "Open Business Bank Account",
        "jurisdiction": "N/A",
        "due_date": date(2026, 5, 1),
        "status": "Pending",
        "notes": "Bring EIN + Certificate of Formation",
    },
    {
        "filing_type": "Amazon Seller Account Setup",
        "jurisdiction": "N/A",
        "due_date": date(2026, 6, 1),
        "status": "Pending",
        "notes": "Configure NJ 6.625% sales tax collection settings",
    },
    {
        "filing_type": "Obtain EIN",
        "jurisdiction": "Federal",
        "due_date": date(2026, 4, 27),
        "status": "Done",
        "date_filed": date(2026, 4, 27),
        "notes": "Employer Identification Number — irs.gov/businesses/small",
    },
]


# ── helpers ───────────────────────────────────────────────────────────────────

def _to_dt(d: date | None) -> datetime | None:
    if d is None:
        return None
    return datetime(d.year, d.month, d.day)


def _build_records() -> list[dict]:
    records = []
    for i, r in enumerate(_QUARTERLY, 1):
        records.append({
            "category": "quarterly",
            "filing_type": r["filing_type"],
            "jurisdiction": r["jurisdiction"],
            "year": r["year"],
            "quarter": r["quarter"],
            "period": r["period"],
            "due_date": r["due_date"],
            "status": r.get("status", "Pending"),
            "date_filed": r.get("date_filed"),
            "confirmation_number": None,
            "assigned_to": "LLC",
            "notes": r.get("notes", ""),
            "order": i,
        })
    for i, r in enumerate(_ANNUAL, 1):
        records.append({
            "category": "annual",
            "filing_type": r["filing_type"],
            "jurisdiction": r["jurisdiction"],
            "year": r["year"],
            "quarter": None,
            "period": str(r["year"]),
            "due_date": r["due_date"],
            "status": r.get("status", "Pending"),
            "date_filed": r.get("date_filed"),
            "confirmation_number": None,
            "assigned_to": "LLC",
            "notes": r.get("notes", ""),
            "order": i,
        })
    for i, r in enumerate(_ONE_TIME, 1):
        records.append({
            "category": "one_time",
            "filing_type": r["filing_type"],
            "jurisdiction": r["jurisdiction"],
            "year": None,
            "quarter": None,
            "period": "",
            "due_date": r["due_date"],
            "status": r.get("status", "Pending"),
            "date_filed": r.get("date_filed"),
            "confirmation_number": r.get("confirmation_number"),
            "assigned_to": "LLC",
            "notes": r.get("notes", ""),
            "order": i,
        })
    return records


def _wipe_collection(db, name: str) -> int:
    col = db.collection(name)
    deleted = 0
    while True:
        docs = list(col.limit(400).stream())
        if not docs:
            break
        for doc in docs:
            doc.reference.delete()
            deleted += 1
    return deleted


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wipe and reseed all Firestore compliance data"
    )
    parser.add_argument(
        "--service-account",
        default="service_account.json",
        help="Path to Firebase service account JSON (default: service_account.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without touching Firestore",
    )
    args = parser.parse_args()

    records = _build_records()
    q = sum(1 for r in records if r["category"] == "quarterly")
    a = sum(1 for r in records if r["category"] == "annual")
    ot = sum(1 for r in records if r["category"] == "one_time")
    print(f"Prepared {q} quarterly + {a} annual + {ot} one-time = {len(records)} total records")

    if args.dry_run:
        print("\n--- DRY RUN — no writes ---")
        for r in records:
            print(
                f"  [{r['category']:10s}] {r['filing_type']:<45}  "
                f"{r['status']:<10}  due:{r['due_date']}"
            )
        return

    sa_path = Path(args.service_account)
    if not sa_path.exists():
        sys.exit(f"Service account not found: {sa_path}")

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore as fs
    except ImportError:
        sys.exit("Install firebase-admin:  pip install firebase-admin")

    if not firebase_admin._apps:
        cred = credentials.Certificate(str(sa_path))
        firebase_admin.initialize_app(cred)
    db = fs.client()

    # Wipe all collections
    for col_name in ("filings", "filing_history", "members", "config"):
        n = _wipe_collection(db, col_name)
        print(f"Wiped {col_name}: {n} document(s) deleted")

    # Seed filings
    col = db.collection("filings")
    for rec in records:
        rec["due_date"] = _to_dt(rec["due_date"])
        rec["date_filed"] = _to_dt(rec.get("date_filed"))
        rec["created_at"] = fs.SERVER_TIMESTAMP
        rec["updated_at"] = fs.SERVER_TIMESTAMP
        rec["updated_by"] = "init_script"
        col.add(rec)

    print(f"\nSeeded {len(records)} filings — all assigned to 'LLC', no personal names.")
    print("Members collection is empty — add members via the Settings tab in the app.")


if __name__ == "__main__":
    main()
