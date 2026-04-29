"""Firestore CRUD helpers for compliance filings."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import streamlit as st

from .firebase_client import get_db


# ── read ──────────────────────────────────────────────────────────────────────
# No @st.cache_data on get_filings — always fetch fresh so deletes / edits
# are reflected immediately without any cache invalidation race conditions.

def get_filings(category: str) -> list[dict]:
    """Return all filings for a category, sorted by year then due_date."""
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
    rows.sort(key=lambda r: (r.get("year") or 9999, r.get("due_date") or date.max))
    return rows


def get_all_filings() -> list[dict]:
    result = []
    for cat in ("quarterly", "annual", "one_time"):
        result.extend(get_filings(cat))
    return result


def get_filing_history(doc_id: str) -> list[dict]:
    """Return audit history for a filing, sorted oldest-first in Python
    (avoids the composite Firestore index required for where+order_by)."""
    db = get_db()
    docs = (
        db.collection("filing_history")
        .where("filing_id", "==", doc_id)
        .stream()
    )
    rows = []
    for doc in docs:
        d = doc.to_dict()
        rows.append(d)
    rows.sort(key=lambda h: h.get("changed_at") or datetime.min)
    return rows


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
    new_status = updates.get("status")
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
    """Add a new filing; returns the new document ID."""
    from firebase_admin import firestore as fs

    db = get_db()
    if "date_filed" in data:
        data["date_filed"] = _to_dt(data["date_filed"])
    if "due_date" in data:
        data["due_date"] = _to_dt(data["due_date"])

    data["created_at"] = fs.SERVER_TIMESTAMP
    data["updated_at"] = fs.SERVER_TIMESTAMP
    data["updated_by"] = user_email

    _, ref = db.collection("filings").add(data)
    return ref.id


def delete_filing(doc_id: str) -> None:
    db = get_db()
    db.collection("filings").document(doc_id).delete()
