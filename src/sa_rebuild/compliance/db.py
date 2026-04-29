"""Firestore CRUD helpers for compliance filings."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import streamlit as st

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


def swap_order(row_a: dict, row_b: dict) -> None:
    """Swap the 'order' field between two filing rows (persists to Firestore)."""
    db = get_db()
    db.collection("filings").document(row_a["id"]).update({"order": row_b["order"]})
    db.collection("filings").document(row_b["id"]).update({"order": row_a["order"]})
    # Keep in-memory dicts consistent so callers can rely on them
    row_a["order"], row_b["order"] = row_b["order"], row_a["order"]


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
