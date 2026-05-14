"""Firestore CRUD helpers for compliance filings."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .firebase_client import get_db


# ── read ──────────────────────────────────────────────────────────────────────
# No @st.cache_data — always fetch fresh so edits/deletes reflect immediately.

def _normalize_assigned_to(value: Any) -> list[str]:
    """Coerce legacy str values to list[str]. New schema stores assigned_to as a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    s = str(value).strip()
    return [s] if s else []


def get_filings(category: str) -> list[dict]:
    """Return all filings for a category.

    Primary sort: the 'order' field (integer, set by the user via ↑/↓).
    Fallback for docs without 'order': year then due_date (natural order).
    """
    db = get_db()
    docs = (
        db.collection("filings")
        .where("category", "==", category)
        .stream()
    )
    rows = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        for field in ("due_date", "date_filed", "created_at", "updated_at"):
            v = d.get(field)
            if hasattr(v, "date"):
                d[field] = v.date()
            elif hasattr(v, "isoformat"):
                d[field] = v if isinstance(v, date) else v.date()
        d["assigned_to"] = _normalize_assigned_to(d.get("assigned_to"))
        rows.append(d)
    rows.sort(key=lambda r: (
        r.get("order") if r.get("order") is not None else 999999,
        r.get("year") or 9999,
        r.get("due_date") or date.max,
    ))
    return rows


def get_all_filings() -> list[dict]:
    result = []
    for cat in ("quarterly", "annual", "one_time"):
        result.extend(get_filings(cat))
    return result


def get_filing_history(doc_id: str) -> list[dict]:
    """History sorted in Python — avoids composite Firestore index requirement."""
    db = get_db()
    docs = (
        db.collection("filing_history")
        .where("filing_id", "==", doc_id)
        .stream()
    )
    rows = [doc.to_dict() for doc in docs]
    rows.sort(key=lambda h: h.get("changed_at") or datetime.min)
    return rows


# ── order management ──────────────────────────────────────────────────────────

def ensure_order(rows: list[dict]) -> None:
    """Lazy migration: assign sequential 'order' values to any docs missing it.

    Operates on the already-fetched rows list, modifying both the in-memory
    dicts and the Firestore documents in one pass.
    """
    missing = [r for r in rows if r.get("order") is None]
    if not missing:
        return
    db = get_db()
    # rows already sorted by the natural fallback order from get_filings
    for i, r in enumerate(rows):
        if r.get("order") is None:
            order_val = i + 1
            db.collection("filings").document(r["id"]).update({"order": order_val})
            r["order"] = order_val


def move_rows(from_seq: list[dict], to_seq: list[dict]) -> None:
    """Rotate order values so to_seq[i] receives from_seq[i]'s order.

    Typical call for move-up:
        move_rows([upper_neighbor] + group, group + [upper_neighbor])
    Typical call for move-down:
        move_rows(group + [lower_neighbor], [lower_neighbor] + group)
    Both lists must have the same length and contain the same rows.
    """
    orders = [r.get("order") for r in from_seq]
    db = get_db()
    for row, order_val in zip(to_seq, orders):
        db.collection("filings").document(row["id"]).update({"order": order_val})
        row["order"] = order_val


# ── write ─────────────────────────────────────────────────────────────────────

def _to_dt(v: date | datetime | None) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    return datetime(v.year, v.month, v.day)


def update_filing(doc_id: str, updates: dict[str, Any], user_email: str) -> None:
    from firebase_admin import firestore as fs

    db = get_db()
    ref = db.collection("filings").document(doc_id)
    old = ref.get().to_dict() or {}

    if "date_filed" in updates:
        updates["date_filed"] = _to_dt(updates["date_filed"])
    if "due_date" in updates:
        updates["due_date"] = _to_dt(updates["due_date"])
    if "assigned_to" in updates:
        updates["assigned_to"] = _normalize_assigned_to(updates["assigned_to"])

    updates["updated_at"] = fs.SERVER_TIMESTAMP
    updates["updated_by"] = user_email
    ref.update(updates)

    old_status = old.get("status")
    new_status  = updates.get("status")
    if new_status and new_status != old_status:
        db.collection("filing_history").add({
            "filing_id":  doc_id,
            "changed_by": user_email,
            "old_status": old_status,
            "new_status": new_status,
            "note":       updates.get("notes", ""),
            "changed_at": fs.SERVER_TIMESTAMP,
        })


def add_filing(data: dict[str, Any], user_email: str) -> str:
    """Add a new filing; appends after the last row of the same category."""
    from firebase_admin import firestore as fs

    db = get_db()
    if "date_filed" in data:
        data["date_filed"] = _to_dt(data["date_filed"])
    if "due_date" in data:
        data["due_date"] = _to_dt(data["due_date"])
    if "assigned_to" in data:
        data["assigned_to"] = _normalize_assigned_to(data["assigned_to"])

    # Assign order = max existing order + 1 so new rows appear at the bottom
    category = data.get("category", "")
    existing = list(
        db.collection("filings").where("category", "==", category).stream()
    )
    max_order = max(
        (d.to_dict().get("order") or 0 for d in existing), default=0
    )
    data["order"] = max_order + 1

    data["created_at"] = fs.SERVER_TIMESTAMP
    data["updated_at"] = fs.SERVER_TIMESTAMP
    data["updated_by"] = user_email

    _, ref = db.collection("filings").add(data)
    return ref.id


def delete_filing(doc_id: str) -> None:
    db = get_db()
    db.collection("filings").document(doc_id).delete()


# ── config / members ──────────────────────────────────────────────────────────

def get_members() -> list[str]:
    """Return assignable names from the 'members' collection, always prepending 'LLC'."""
    db = get_db()
    docs = db.collection("members").stream()
    names = sorted(d.to_dict().get("name", "") for d in docs)
    names = [n for n in names if n]
    return ["LLC"] + names


def get_members_with_ids() -> list[dict]:
    """Return [{id, name}, ...] sorted by name — used by the Settings UI."""
    db = get_db()
    docs = db.collection("members").stream()
    rows = [{"id": d.id, "name": d.to_dict().get("name", "")} for d in docs]
    return sorted(rows, key=lambda r: r["name"])


def add_member(name: str) -> None:
    get_db().collection("members").add({"name": name.strip()})


def delete_member(doc_id: str) -> None:
    get_db().collection("members").document(doc_id).delete()


def count_filings_by_assignee(name: str) -> int:
    """Count filings where `name` appears in assigned_to (list or legacy str)."""
    db = get_db()
    count = 0
    for doc in db.collection("filings").stream():
        if name in _normalize_assigned_to(doc.to_dict().get("assigned_to")):
            count += 1
    return count


def reassign_filings(old_name: str, new_name: str) -> int:
    """Replace `old_name` with `new_name` inside every filing's assigned_to list.

    Removes `old_name`; adds `new_name` if not already present. Returns count touched.
    """
    db = get_db()
    touched = 0
    for doc in db.collection("filings").stream():
        names = _normalize_assigned_to(doc.to_dict().get("assigned_to"))
        if old_name not in names:
            continue
        names = [n for n in names if n != old_name]
        if new_name and new_name not in names:
            names.append(new_name)
        doc.reference.update({"assigned_to": names})
        touched += 1
    return touched


def get_company_info() -> dict:
    """Return the 'config/company' document (keys: name, formed, etc.)."""
    db = get_db()
    doc = db.collection("config").document("company").get()
    return doc.to_dict() or {}


def save_company_info(data: dict) -> None:
    """Create or overwrite the 'config/company' document."""
    get_db().collection("config").document("company").set(data)


# ── Quick Reference (dashboard) ──────────────────────────────────────────────
# Editable replacement for the old hard-coded _QUICK_REF tuples.
# Schema: filing, frequency, due_date_pattern, who_files, where_to_file, order

_QUICK_REF_SEED: list[dict] = [
    {"filing": "NJ Sales Tax Return. ST-50",   "frequency": "Quarterly", "due_date_pattern": "Jul 20 / Oct 20 / Jan 20 / Apr 20", "who_files": "LLC",            "where_to_file": "taxportal.nj.gov"},
    {"filing": "Federal Est. Tax 1040-ES",     "frequency": "Quarterly", "due_date_pattern": "Apr 15 / Jun 16 / Sep 15 / Jan 15", "who_files": "Members (joint)", "where_to_file": "irs.gov/payments"},
    {"filing": "NJ Est. Tax NJ-1040-ES",       "frequency": "Quarterly", "due_date_pattern": "Apr 15 / Jun 16 / Sep 15 / Jan 15", "who_files": "Members (joint)", "where_to_file": "NJ Individual Tax Portal"},
    {"filing": "Federal Form 1065",            "frequency": "Annual",    "due_date_pattern": "March 15",                          "who_files": "LLC",            "where_to_file": "TaxAct Business → e-file"},
    {"filing": "NJ Form NJ-1065",              "frequency": "Annual",    "due_date_pattern": "April 15",                          "who_files": "LLC",            "where_to_file": "TaxAct Business → e-file"},
    {"filing": "Joint Federal 1040",           "frequency": "Annual",    "due_date_pattern": "April 15",                          "who_files": "Members (joint)", "where_to_file": "TaxAct bundle → e-file"},
    {"filing": "Joint NJ-1040",                "frequency": "Annual",    "due_date_pattern": "April 15",                          "who_files": "Members (joint)", "where_to_file": "TaxAct bundle → e-file"},
    {"filing": "NJ Annual Report ($75)",       "frequency": "Annual",    "due_date_pattern": "April 30",                          "who_files": "LLC",            "where_to_file": "njportal.com/DOR/annualreports"},
    {"filing": "FinCEN BOI Report",            "frequency": "One-time",  "due_date_pattern": "Filed Apr 27, 2026",                "who_files": "LLC",            "where_to_file": "boiefiling.fincen.gov"},
    {"filing": "NJ LLC Formation",             "frequency": "One-time",  "due_date_pattern": "Filed Apr 27, 2026",                "who_files": "LLC",            "where_to_file": "njportal.com"},
]


def _seed_if_empty(collection: str, seed: list[dict]) -> None:
    db = get_db()
    col = db.collection(collection)
    existing = list(col.limit(1).stream())
    if existing:
        return
    for i, row in enumerate(seed, 1):
        col.add({**row, "order": i})


def get_quick_reference() -> list[dict]:
    db = get_db()
    _seed_if_empty("quick_reference", _QUICK_REF_SEED)
    rows = []
    for doc in db.collection("quick_reference").stream():
        d = doc.to_dict()
        d["id"] = doc.id
        rows.append(d)
    rows.sort(key=lambda r: r.get("order") if r.get("order") is not None else 999999)
    return rows


def ensure_order_quick_reference(rows: list[dict]) -> None:
    if all(r.get("order") is not None for r in rows):
        return
    db = get_db()
    for i, r in enumerate(rows):
        if r.get("order") is None:
            db.collection("quick_reference").document(r["id"]).update({"order": i + 1})
            r["order"] = i + 1


def add_quick_reference(data: dict, user_email: str) -> str:
    from firebase_admin import firestore as fs
    db = get_db()
    existing = list(db.collection("quick_reference").stream())
    max_order = max((d.to_dict().get("order") or 0 for d in existing), default=0)
    data["order"] = max_order + 1
    data["created_at"] = fs.SERVER_TIMESTAMP
    data["updated_at"] = fs.SERVER_TIMESTAMP
    data["updated_by"] = user_email
    _, ref = db.collection("quick_reference").add(data)
    return ref.id


def update_quick_reference(doc_id: str, updates: dict, user_email: str) -> None:
    from firebase_admin import firestore as fs
    updates["updated_at"] = fs.SERVER_TIMESTAMP
    updates["updated_by"] = user_email
    get_db().collection("quick_reference").document(doc_id).update(updates)


def delete_quick_reference(doc_id: str) -> None:
    get_db().collection("quick_reference").document(doc_id).delete()


def move_quick_reference_rows(from_seq: list[dict], to_seq: list[dict]) -> None:
    orders = [r.get("order") for r in from_seq]
    db = get_db()
    for row, order_val in zip(to_seq, orders):
        db.collection("quick_reference").document(row["id"]).update({"order": order_val})
        row["order"] = order_val


# ── Key Websites (dashboard) ─────────────────────────────────────────────────
# Editable replacement for the old hard-coded _KEY_SITES tuples.
# Schema: name, url, note, order

_KEY_SITES_SEED: list[dict] = [
    {"name": "IRS Direct Pay",          "url": "irs.gov/payments",                "note": "Federal est. tax (1040-ES) payments"},
    {"name": "NJ Sales Tax Portal",     "url": "taxportal.nj.gov",                "note": "ST-50 quarterly sales tax returns"},
    {"name": "NJ Individual Tax Portal","url": "nj.gov/treasury/taxation/",       "note": "NJ-1040-ES estimated tax payments"},
    {"name": "NJ Taxation Portal",      "url": "nj.gov/taxation",                 "note": "NJ-1065 partnership return"},
    {"name": "NJ Annual Report",        "url": "njportal.com/DOR/annualreports", "note": "LLC renewal — $75/yr"},
    {"name": "FinCEN BOI Filing",       "url": "boiefiling.fincen.gov",          "note": "Beneficial ownership report"},
    {"name": "TaxAct Business",         "url": "taxact.com/business-taxes",      "note": "1065 + NJ-1065 e-file"},
    {"name": "TaxAct (personal bundle)","url": "taxact.com",                     "note": "Joint 1040 + NJ-1040 with K-1 import"},
]


def get_key_websites() -> list[dict]:
    db = get_db()
    _seed_if_empty("key_websites", _KEY_SITES_SEED)
    rows = []
    for doc in db.collection("key_websites").stream():
        d = doc.to_dict()
        d["id"] = doc.id
        rows.append(d)
    rows.sort(key=lambda r: r.get("order") if r.get("order") is not None else 999999)
    return rows


def ensure_order_key_websites(rows: list[dict]) -> None:
    if all(r.get("order") is not None for r in rows):
        return
    db = get_db()
    for i, r in enumerate(rows):
        if r.get("order") is None:
            db.collection("key_websites").document(r["id"]).update({"order": i + 1})
            r["order"] = i + 1


def add_key_website(data: dict, user_email: str) -> str:
    from firebase_admin import firestore as fs
    db = get_db()
    existing = list(db.collection("key_websites").stream())
    max_order = max((d.to_dict().get("order") or 0 for d in existing), default=0)
    data["order"] = max_order + 1
    data["created_at"] = fs.SERVER_TIMESTAMP
    data["updated_at"] = fs.SERVER_TIMESTAMP
    data["updated_by"] = user_email
    _, ref = db.collection("key_websites").add(data)
    return ref.id


def update_key_website(doc_id: str, updates: dict, user_email: str) -> None:
    from firebase_admin import firestore as fs
    updates["updated_at"] = fs.SERVER_TIMESTAMP
    updates["updated_by"] = user_email
    get_db().collection("key_websites").document(doc_id).update(updates)


def delete_key_website(doc_id: str) -> None:
    get_db().collection("key_websites").document(doc_id).delete()


def move_key_website_rows(from_seq: list[dict], to_seq: list[dict]) -> None:
    orders = [r.get("order") for r in from_seq]
    db = get_db()
    for row, order_val in zip(to_seq, orders):
        db.collection("key_websites").document(row["id"]).update({"order": order_val})
        row["order"] = order_val


def sync_members_from_filings() -> int:
    """Add any assigned_to value from filings that isn't already in members. Returns count added."""
    db = get_db()
    existing = {d.to_dict().get("name", "") for d in db.collection("members").stream()}
    assigned: set[str] = set()
    for d in db.collection("filings").stream():
        for name in _normalize_assigned_to(d.to_dict().get("assigned_to")):
            assigned.add(name)
    to_add = sorted(n for n in assigned if n and n != "LLC" and n not in existing)
    for name in to_add:
        db.collection("members").add({"name": name})
    return len(to_add)
