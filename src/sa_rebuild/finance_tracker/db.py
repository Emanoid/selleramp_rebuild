"""Firestore CRUD for Finance Tracker."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sa_rebuild.compliance.firebase_client import get_db

_SETTINGS_DOC = "finance_config"

_DEFAULTS: dict = {
    "onedrive_receipts_path": "",
    "income_types": ["Income after Fees", "Reimbursement", "Other"],
    "members": [
        {"name": "Kadiatu", "pct": 0.70},
        {"name": "Emmanuel", "pct": 0.30},
    ],
    "tax_rate": 0.35,
    "reinvest_pct": 0.50,
}


def _to_dt(v: date | datetime | None) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    return None


def _coerce_date(d: dict, field: str) -> None:
    v = d.get(field)
    if v is None:
        return
    if hasattr(v, "date"):
        d[field] = v.date()
    elif hasattr(v, "isoformat"):
        d[field] = v if isinstance(v, date) else v.date()
    elif isinstance(v, str):
        try:
            d[field] = date.fromisoformat(v)
        except ValueError:
            d[field] = None


# ── Settings ──────────────────────────────────────────────────────────────────

def get_settings() -> dict:
    db = get_db()
    doc = db.collection("finance_settings").document(_SETTINGS_DOC).get()
    data = doc.to_dict() or {}
    for k, v in _DEFAULTS.items():
        if k not in data:
            data[k] = v
    return data


def save_settings(data: dict) -> None:
    get_db().collection("finance_settings").document(_SETTINGS_DOC).set(data)


# ── Expenses ──────────────────────────────────────────────────────────────────

def get_expenses() -> list[dict]:
    db = get_db()
    rows = []
    for doc in db.collection("finance_expenses").stream():
        d = doc.to_dict()
        d["id"] = doc.id
        _coerce_date(d, "start_date")
        _coerce_date(d, "end_date")
        rows.append(d)
    rows.sort(key=lambda r: (
        r.get("order") if r.get("order") is not None else 999999,
        r.get("start_date") or date.max,
    ))
    return rows


def ensure_order_expenses(rows: list[dict]) -> None:
    missing = [r for r in rows if r.get("order") is None]
    if not missing:
        return
    db = get_db()
    for i, r in enumerate(rows):
        if r.get("order") is None:
            db.collection("finance_expenses").document(r["id"]).update({"order": i + 1})
            r["order"] = i + 1


def move_expense_rows(from_seq: list[dict], to_seq: list[dict]) -> None:
    orders = [r.get("order") for r in from_seq]
    db = get_db()
    for row, order_val in zip(to_seq, orders):
        db.collection("finance_expenses").document(row["id"]).update({"order": order_val})
        row["order"] = order_val


def add_expense(data: dict[str, Any], user_email: str) -> str:
    from firebase_admin import firestore as fs
    db = get_db()
    if "start_date" in data:
        data["start_date"] = _to_dt(data["start_date"])
    if "end_date" in data:
        data["end_date"] = _to_dt(data["end_date"])
    existing = list(db.collection("finance_expenses").stream())
    max_order = max((d.to_dict().get("order") or 0 for d in existing), default=0)
    data["order"] = max_order + 1
    data["created_at"] = fs.SERVER_TIMESTAMP
    data["updated_at"] = fs.SERVER_TIMESTAMP
    data["updated_by"] = user_email
    _, ref = db.collection("finance_expenses").add(data)
    return ref.id


def update_expense(doc_id: str, updates: dict[str, Any], user_email: str) -> None:
    from firebase_admin import firestore as fs
    db = get_db()
    if "start_date" in updates:
        updates["start_date"] = _to_dt(updates["start_date"])
    if "end_date" in updates:
        updates["end_date"] = _to_dt(updates["end_date"])
    updates["updated_at"] = fs.SERVER_TIMESTAMP
    updates["updated_by"] = user_email
    db.collection("finance_expenses").document(doc_id).update(updates)


def delete_expense(doc_id: str) -> None:
    get_db().collection("finance_expenses").document(doc_id).delete()


# ── Income ────────────────────────────────────────────────────────────────────

def get_income() -> list[dict]:
    db = get_db()
    rows = []
    for doc in db.collection("finance_income").stream():
        d = doc.to_dict()
        d["id"] = doc.id
        _coerce_date(d, "date")
        rows.append(d)
    rows.sort(key=lambda r: (
        r.get("order") if r.get("order") is not None else 999999,
        r.get("date") or date.max,
    ))
    return rows


def ensure_order_income(rows: list[dict]) -> None:
    missing = [r for r in rows if r.get("order") is None]
    if not missing:
        return
    db = get_db()
    for i, r in enumerate(rows):
        if r.get("order") is None:
            db.collection("finance_income").document(r["id"]).update({"order": i + 1})
            r["order"] = i + 1


def move_income_rows(from_seq: list[dict], to_seq: list[dict]) -> None:
    orders = [r.get("order") for r in from_seq]
    db = get_db()
    for row, order_val in zip(to_seq, orders):
        db.collection("finance_income").document(row["id"]).update({"order": order_val})
        row["order"] = order_val


def add_income(data: dict[str, Any], user_email: str) -> str:
    from firebase_admin import firestore as fs
    db = get_db()
    if "date" in data:
        data["date"] = _to_dt(data["date"])
    existing = list(db.collection("finance_income").stream())
    max_order = max((d.to_dict().get("order") or 0 for d in existing), default=0)
    data["order"] = max_order + 1
    data["created_at"] = fs.SERVER_TIMESTAMP
    data["updated_at"] = fs.SERVER_TIMESTAMP
    data["updated_by"] = user_email
    _, ref = db.collection("finance_income").add(data)
    return ref.id


def update_income(doc_id: str, updates: dict[str, Any], user_email: str) -> None:
    from firebase_admin import firestore as fs
    db = get_db()
    if "date" in updates:
        updates["date"] = _to_dt(updates["date"])
    updates["updated_at"] = fs.SERVER_TIMESTAMP
    updates["updated_by"] = user_email
    db.collection("finance_income").document(doc_id).update(updates)


def delete_income(doc_id: str) -> None:
    get_db().collection("finance_income").document(doc_id).delete()
