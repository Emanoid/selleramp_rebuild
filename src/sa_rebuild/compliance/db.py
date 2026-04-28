"""Firestore CRUD helpers for compliance filings."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import streamlit as st

from .firebase_client import get_db


# ── read ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner=False)
def get_filings(category: str) -> list[dict]:
    """Return all filings for a category, sorted by due_date."""
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
        # Convert Firestore timestamps → Python date for DataFrame compatibility
        for field in ("due_date", "date_filed", "created_at", "updated_at"):
            v = d.get(field)
            if hasattr(v, "date"):       # Firestore DatetimeWithNanoseconds
                d[field] = v.date()
            elif hasattr(v, "isoformat"):  # already date/datetime
                d[field] = v if isinstance(v, date) else v.date()
        rows.append(d)
    rows.sort(key=lambda r: (r.get("year") or 9999, r.get("due_date") or date.max))
    return rows


def get_all_filings() -> list[dict]:
    """Return every filing across all categories (used by Dashboard)."""
    result = []
    for cat in ("quarterly", "annual", "one_time"):
        result.extend(get_filings(cat))
    return result


@st.cache_data(ttl=60, show_spinner=False)
def get_filing_history(doc_id: str) -> list[dict]:
    db = get_db()
    docs = (
        db.collection("filing_history")
        .where("filing_id", "==", doc_id)
        .order_by("changed_at")
        .stream()
    )
    rows = []
    for doc in docs:
        d = doc.to_dict()
        ts = d.get("changed_at")
        if hasattr(ts, "isoformat"):
            d["changed_at"] = ts
        rows.append(d)
    return rows


# ── write ─────────────────────────────────────────────────────────────────────

def _to_dt(v: date | datetime | None) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    return datetime(v.year, v.month, v.day)


def update_filing(doc_id: str, updates: dict[str, Any], user_email: str) -> None:
    """Update a filing document and append to history if status changed."""
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

    # Audit trail only on status changes
    old_status = old.get("status")
    new_status = updates.get("status")
    if new_status and new_status != old_status:
        db.collection("filing_history").add({
            "filing_id": doc_id,
            "changed_by": user_email,
            "old_status": old_status,
            "new_status": new_status,
            "note": updates.get("notes", ""),
            "changed_at": fs.SERVER_TIMESTAMP,
        })

    _invalidate_cache()


def add_filing(data: dict[str, Any], user_email: str) -> str:
    """Add a new filing document; returns the new document ID."""
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
    _invalidate_cache()
    return ref.id


def delete_filing(doc_id: str) -> None:
    db = get_db()
    db.collection("filings").document(doc_id).delete()
    _invalidate_cache()


def _invalidate_cache() -> None:
    get_filings.clear()
    get_all_filings.cache_clear() if hasattr(get_all_filings, "cache_clear") else None
