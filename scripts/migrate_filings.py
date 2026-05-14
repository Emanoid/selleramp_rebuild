#!/usr/bin/env python3
# =============================================================================
# Filings migration script — one-shot data correction for Firestore `filings`.
#
# WHAT THIS DOES
#   1. Renames "NJ Sales Tax Return"  →  "NJ Sales Tax Return. ST-50"
#   2. Recomputes due dates for every quarterly filing based on the new pattern:
#        - ST-50            : 20th of the month after quarter end
#                              Q1 → Apr 20,  Q2 → Jul 20,  Q3 → Oct 20,  Q4 → Jan 20 of YEAR+1
#        - Federal 1040-ES  : Q1 → Apr 15,  Q2 → Jun 16,  Q3 → Sep 15,  Q4 → Jan 15 of YEAR+1
#        - NJ-1040-ES       : same as Federal 1040-ES
#   3. Updates due dates for annual filings:
#        - Federal Form 1065   → March 15 of YEAR+1
#        - NJ Form NJ-1065     → April 15 of YEAR+1
#        - Personal Form 1040  → April 15 of YEAR+1   (joint federal)
#        - Personal NJ-1040    → April 15 of YEAR+1   (joint NJ)
#        - NJ Annual Report    → April 30 of YEAR (no offset — renewal year)
#   4. Overwrites the `notes` field with a short where-to-file + calculation hint.
#   5. Merges duplicate joint filings (same filing_type + year + quarter, different
#      assigned_to) into a single row with `assigned_to = [name1, name2, ...]`.
#      Deletes the redundant duplicate documents.
#   6. Skips & logs anything it doesn't recognise so nothing is silently lost.
#
# OUTPUT
#   A timestamped log file is written next to this script:
#       scripts/migration_log_YYYYMMDD_HHMMSS.txt
#   Every action (or skip) is recorded there. Re-runnable.
#
# HOW TO RUN
#   1. cd into the repo root.
#   2. Activate the venv:                 source venv311/bin/activate
#   3. Ensure service_account.json exists in the repo root (Firebase admin key).
#   4. DRY RUN (default — prints + logs without writing):
#          python3 scripts/migrate_filings.py
#      Inspect the log file to confirm the proposed changes look right.
#   5. APPLY (writes to Firestore):
#          python3 scripts/migrate_filings.py --apply
#   6. Optional flags:
#          --service-account /path/to/sa.json     (default: ./service_account.json)
#          --log /path/to/log.txt                 (default: scripts/migration_log_<ts>.txt)
#
# SAFETY
#   - This is destructive (overwrites notes, merges duplicates). Always run --dry-run first.
#   - Tested filings (status="Done") are NOT touched: their due dates stay, only notes refresh.
#   - If a filing's name doesn't match any rule, it is skipped + logged. Nothing is deleted.
# =============================================================================
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional


# ── canonical migration rules ────────────────────────────────────────────────
#
# Keyed by lowercased filing_type for case-insensitive matching.
# Each rule may specify:
#   "rename_to"       — new filing_type
#   "category"        — expected category ("quarterly"|"annual")
#   "due_for_quarter" — callable(year, q_num:int) -> date   (quarterly only)
#   "due_for_year"    — callable(year:int)        -> date   (annual only)
#   "notes"           — new notes (overwritten)

_NOTES = {
    "st_50": (
        "$0 owed — Amazon remits NJ sales tax as marketplace facilitator. "
        "File at taxportal.nj.gov. Line 1 = gross marketplace receipts; "
        "Line 2 = same amount (marketplace facilitator deduction); Line 3 = $0 taxable. "
        "Still must file every quarter even if $0."
    ),
    "fed_1040es": (
        "Federal estimated tax on LLC profit (filed jointly). "
        "Pay at irs.gov/payments → Direct Pay. "
        "Shortcut: quarterly net profit × 28% covers SE tax (12.4% SS + 2.9% Medicare on 92.35%) + income tax."
    ),
    "nj_1040es": (
        "NJ estimated income tax on LLC profit (filed jointly). "
        "Pay at NJ Individual Tax Portal (nj.gov/treasury/taxation). "
        "Shortcut: quarterly net profit × 7% (covers NJ graduated brackets for new sellers; no self-employment tax in NJ)."
    ),
    "fed_1065": (
        "Partnership return + Schedule K-1s for each member. "
        "File via TaxAct Business → e-file. Must be filed BEFORE NJ-1065 (NJ-1065 is built from it)."
    ),
    "nj_1065": (
        "NJ partnership return — built from federal 1065. "
        "File via TaxAct Business → e-file (same session as federal)."
    ),
    "fed_1040": (
        "Joint federal personal income tax return. Attach Schedule K-1 from Form 1065. "
        "File via TaxAct bundle → K-1 imports automatically from the business return."
    ),
    "nj_1040": (
        "Joint NJ personal income tax return. Attach NJ K-1 from NJ-1065. "
        "File via TaxAct bundle → e-file."
    ),
    "nj_annual_report": (
        "NJ LLC renewal — $75 fee. File at njportal.com/DOR/annualreports. "
        "Log in, search for entity ID, confirm members + address, pay $75."
    ),
}


def _st50_due(year: int, q: int) -> date:
    # 20th of month after quarter end
    return {1: date(year, 4, 20), 2: date(year, 7, 20),
            3: date(year, 10, 20), 4: date(year + 1, 1, 20)}[q]


def _est_tax_due(year: int, q: int) -> date:
    # Federal 1040-ES and NJ-1040-ES same dates per conversation
    return {1: date(year, 4, 15), 2: date(year, 6, 16),
            3: date(year, 9, 15), 4: date(year + 1, 1, 15)}[q]


_RULES: dict[str, dict] = {
    "nj sales tax return": {
        "rename_to": "NJ Sales Tax Return. ST-50",
        "category": "quarterly",
        "due_for_quarter": _st50_due,
        "notes": _NOTES["st_50"],
    },
    "nj sales tax return. st-50": {
        "category": "quarterly",
        "due_for_quarter": _st50_due,
        "notes": _NOTES["st_50"],
    },
    "federal est. tax 1040-es": {
        "category": "quarterly",
        "due_for_quarter": _est_tax_due,
        "notes": _NOTES["fed_1040es"],
    },
    "nj est. tax nj-1040-es": {
        "category": "quarterly",
        "due_for_quarter": _est_tax_due,
        "notes": _NOTES["nj_1040es"],
    },
    "federal form 1065": {
        "category": "annual",
        "due_for_year": lambda y: date(y + 1, 3, 15),
        "notes": _NOTES["fed_1065"],
    },
    "nj form nj-1065": {
        "category": "annual",
        "due_for_year": lambda y: date(y + 1, 4, 15),
        "notes": _NOTES["nj_1065"],
    },
    "personal form 1040": {
        "category": "annual",
        "due_for_year": lambda y: date(y + 1, 4, 15),
        "notes": _NOTES["fed_1040"],
    },
    "personal nj-1040": {
        "category": "annual",
        "due_for_year": lambda y: date(y + 1, 4, 15),
        "notes": _NOTES["nj_1040"],
    },
    "nj annual report ($75)": {
        "category": "annual",
        "due_for_year": lambda y: date(y, 4, 30),  # no +1 — renewal year
        "notes": _NOTES["nj_annual_report"],
    },
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _to_dt(d: Optional[date]) -> Optional[datetime]:
    if d is None:
        return None
    return datetime(d.year, d.month, d.day)


def _quarter_num(q: str | None) -> Optional[int]:
    """Parse 'Q2 (Apr-Jun)' → 2."""
    if not q:
        return None
    s = str(q).strip().upper()
    for n in (1, 2, 3, 4):
        if s.startswith(f"Q{n}"):
            return n
    return None


def _normalise_assigned_to(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v).strip()
    return [s] if s else []


def _existing_date(v) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    return None


# ── core migration ───────────────────────────────────────────────────────────

def _plan_changes(filings: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (updates, merges, skipped). Pure function — no Firestore writes.

    - updates: [{id, current, new_fields}] — per-doc field updates
    - merges:  [{keeper_id, drop_ids, merged_assigned_to, merged_filing_type, ...}]
    - skipped: [{id, reason, current_filing_type}]
    """
    updates: list[dict] = []
    skipped: list[dict] = []

    # Group by (canonical_filing_type, year, quarter) for duplicate detection
    groups: dict[tuple, list[dict]] = {}

    for f in filings:
        current_name = (f.get("filing_type") or "").strip()
        key = current_name.lower()
        rule = _RULES.get(key)
        if not rule:
            skipped.append({
                "id": f.get("id"),
                "current_filing_type": current_name,
                "reason": f"No migration rule for '{current_name}' (category={f.get('category')})",
            })
            continue

        new_fields: dict = {}
        new_name = rule.get("rename_to") or current_name
        if new_name != current_name:
            new_fields["filing_type"] = new_name

        # Due date recomputation — but only for Pending/Overdue filings (skip Done)
        status = (f.get("status") or "").strip()
        year = f.get("year")
        if status != "Done":
            try:
                if "due_for_quarter" in rule:
                    q = _quarter_num(f.get("quarter"))
                    if q is None or not year:
                        skipped.append({
                            "id": f.get("id"),
                            "current_filing_type": current_name,
                            "reason": f"Cannot compute due date — missing quarter or year (q={f.get('quarter')}, year={year})",
                        })
                        continue
                    new_due = rule["due_for_quarter"](int(year), q)
                elif "due_for_year" in rule:
                    if not year:
                        skipped.append({
                            "id": f.get("id"),
                            "current_filing_type": current_name,
                            "reason": f"Cannot compute due date — missing year",
                        })
                        continue
                    new_due = rule["due_for_year"](int(year))
                else:
                    new_due = None

                if new_due:
                    old_due = _existing_date(f.get("due_date"))
                    if old_due != new_due:
                        new_fields["due_date"] = new_due
            except Exception as exc:
                skipped.append({
                    "id": f.get("id"),
                    "current_filing_type": current_name,
                    "reason": f"Due date calc error: {exc}",
                })
                continue

        # Notes overwrite
        new_notes = rule.get("notes")
        if new_notes and (f.get("notes") or "") != new_notes:
            new_fields["notes"] = new_notes

        # Stage for merge grouping
        # Use canonical (post-rename) name as the merge key
        merge_key = (new_name, year, f.get("quarter"))
        groups.setdefault(merge_key, []).append({**f, "_new_fields": new_fields})

        if new_fields:
            updates.append({
                "id": f.get("id"),
                "current": {"filing_type": current_name, "due_date": f.get("due_date")},
                "new_fields": new_fields,
            })

    # Detect duplicates within groups: same merge_key, different assigned_to
    merges: list[dict] = []
    for key, docs in groups.items():
        if len(docs) <= 1:
            continue
        # Sort: keep doc with earliest 'order' as the keeper
        docs_sorted = sorted(docs, key=lambda d: d.get("order") or 999999)
        keeper = docs_sorted[0]
        drops  = docs_sorted[1:]
        union: list[str] = []
        for d in docs_sorted:
            for name in _normalise_assigned_to(d.get("assigned_to")):
                if name not in union:
                    union.append(name)
        merges.append({
            "keeper_id": keeper.get("id"),
            "drop_ids":  [d.get("id") for d in drops],
            "merged_assigned_to": union,
            "filing_type": keeper.get("_new_fields", {}).get("filing_type") or keeper.get("filing_type"),
            "year":       keeper.get("year"),
            "quarter":    keeper.get("quarter"),
        })

    return updates, merges, skipped


def _apply_changes(db, updates: list[dict], merges: list[dict], log) -> None:
    """Write the planned changes to Firestore."""
    from firebase_admin import firestore as fs

    col = db.collection("filings")

    # 1. Apply field updates
    for u in updates:
        fields = dict(u["new_fields"])
        if "due_date" in fields:
            fields["due_date"] = _to_dt(fields["due_date"])
        fields["updated_at"] = fs.SERVER_TIMESTAMP
        fields["updated_by"] = "migrate_filings.py"
        col.document(u["id"]).update(fields)
        log.write(f"UPDATED {u['id']}: {u['new_fields']}\n")

    # 2. Apply merges
    for m in merges:
        col.document(m["keeper_id"]).update({
            "assigned_to": m["merged_assigned_to"],
            "updated_at": fs.SERVER_TIMESTAMP,
            "updated_by": "migrate_filings.py",
        })
        log.write(
            f"MERGED keeper={m['keeper_id']} ({m['filing_type']}, year={m['year']}, q={m['quarter']}) "
            f"→ assigned_to={m['merged_assigned_to']}\n"
        )
        for did in m["drop_ids"]:
            col.document(did).delete()
            log.write(f"DELETED duplicate {did}\n")


def _load_filings(db) -> list[dict]:
    rows = []
    for doc in db.collection("filings").stream():
        d = doc.to_dict()
        d["id"] = doc.id
        rows.append(d)
    return rows


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate filings to new names / due dates / notes.")
    parser.add_argument("--apply", action="store_true",
                        help="Actually write to Firestore. Default is dry-run.")
    parser.add_argument("--service-account", default="service_account.json",
                        help="Path to Firebase service account JSON.")
    parser.add_argument("--log", default=None,
                        help="Path to log file. Default: scripts/migration_log_<timestamp>.txt")
    args = parser.parse_args()

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

    filings = _load_filings(db)
    updates, merges, skipped = _plan_changes(filings)

    log_path = Path(args.log) if args.log else Path("scripts") / f"migration_log_{datetime.now():%Y%m%d_%H%M%S}.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("w") as log:
        mode = "APPLY" if args.apply else "DRY-RUN"
        log.write(f"=== migrate_filings.py — {mode} — {datetime.now().isoformat()} ===\n")
        log.write(f"Loaded {len(filings)} filings.\n\n")

        log.write(f"--- Planned updates ({len(updates)}) ---\n")
        for u in updates:
            log.write(f"  {u['id']}  current={u['current']}\n      → {u['new_fields']}\n")
        log.write("\n")

        log.write(f"--- Planned merges ({len(merges)}) ---\n")
        for m in merges:
            log.write(
                f"  keeper={m['keeper_id']}  drops={m['drop_ids']}  "
                f"({m['filing_type']}, year={m['year']}, q={m['quarter']}) "
                f"→ assigned_to={m['merged_assigned_to']}\n"
            )
        log.write("\n")

        log.write(f"--- Skipped ({len(skipped)}) ---\n")
        for s in skipped:
            log.write(f"  {s['id']}  '{s['current_filing_type']}'  — {s['reason']}\n")
        log.write("\n")

        if args.apply:
            log.write("=== APPLYING CHANGES ===\n")
            _apply_changes(db, updates, merges, log)
            log.write("=== DONE ===\n")
        else:
            log.write("=== DRY RUN — no writes performed. Re-run with --apply to commit. ===\n")

    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"Filings loaded: {len(filings)}")
    print(f"Planned updates: {len(updates)}")
    print(f"Planned merges:  {len(merges)}")
    print(f"Skipped:         {len(skipped)}")
    print(f"Log written to:  {log_path}")
    if skipped:
        print("\n⚠️  Review the 'Skipped' section in the log — these filings were NOT touched.")


if __name__ == "__main__":
    main()
