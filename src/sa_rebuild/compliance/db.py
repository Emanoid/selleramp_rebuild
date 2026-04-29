"""Firestore CRUD helpers for compliance filings."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .firebase_client import get_db


# ── read ──────────────────────────────────────────────────────────────────────
# No @st.cache_data — always fetch fresh so edits/deletes reflect immediately.

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
    db = get_db()
    return len(list(db.collection("filings").where("assigned_to", "==", name).stream()))


def reassign_filings(old_name: str, new_name: str) -> int:
    """Update every filing assigned to old_name → new_name. Returns count updated."""
    db = get_db()
    docs = list(db.collection("filings").where("assigned_to", "==", old_name).stream())
    for doc in docs:
        doc.reference.update({"assigned_to": new_name})
    return len(docs)


def get_company_info() -> dict:
    """Return the 'config/company' document (keys: name, formed, etc.)."""
    db = get_db()
    doc = db.collection("config").document("company").get()
    return doc.to_dict() or {}


def save_company_info(data: dict) -> None:
    """Create or overwrite the 'config/company' document."""
    get_db().collection("config").document("company").set(data)


def sync_members_from_filings() -> int:
    """Add any assigned_to value from filings that isn't already in members. Returns count added."""
    db = get_db()
    existing = {d.to_dict().get("name", "") for d in db.collection("members").stream()}
    assigned = {
        d.to_dict().get("assigned_to", "")
        for d in db.collection("filings").stream()
    }
    to_add = sorted(n for n in assigned if n and n != "LLC" and n not in existing)
    for name in to_add:
        db.collection("members").add({"name": name})
    return len(to_add)
