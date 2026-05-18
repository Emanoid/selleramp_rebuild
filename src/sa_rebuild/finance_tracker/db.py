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


# ── access control ────────────────────────────────────────────────────────────
# Editors see and mutate only their own rows; admins see everything. The role
# comes from a verified Firebase custom claim (see sa_rebuild.auth).

def _is_admin(user: Optional[dict]) -> bool:
    return bool(user) and user.get("role") == "admin"


def _require_owner(ref, user: dict) -> None:
    """Raise PermissionError unless `user` is an admin or owns the document.

    Defence-in-depth: editors only ever see their own rows in the UI, but this
    guards the write path even if a foreign doc_id is somehow supplied.
    """
    if _is_admin(user):
        return
    snap = ref.get()
    if not snap.exists:
        raise PermissionError("Record not found.")
    if snap.to_dict().get("owner_uid") != user.get("uid"):
        raise PermissionError("You can only modify your own records.")


# Fields a UI form may write. Server-managed fields (owner_uid, order,
# created_at, updated_at, updated_by) are set by the writers below and are never
# accepted from a caller; any unknown key is dropped (fail-safe whitelist).
_EXPENSE_FIELDS = frozenset({
    "type", "item_description", "unit_price", "frequency",
    "start_date", "end_date", "receipt_filename", "notes",
})
_INCOME_FIELDS = frozenset({"date", "type", "amount", "notes"})
_SETTINGS_FIELDS = frozenset({
    "onedrive_receipts_path", "income_types", "members", "tax_rate", "reinvest_pct",
})


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
    data = {k: v for k, v in data.items() if k in _SETTINGS_FIELDS}
    get_db().collection("finance_settings").document(_SETTINGS_DOC).set(data)


# ── Expenses ──────────────────────────────────────────────────────────────────

def get_expenses(user: Optional[dict] = None) -> list[dict]:
    """Return expense rows.

    Admins (and `user=None`, used by scripts) see every row; editors see only
    rows they own. The owner filter is a Firestore equality query, so legacy
    docs without an `owner_uid` are simply invisible to editors.
    """
    db = get_db()
    col = db.collection("finance_expenses")
    cursor = (
        col.stream() if user is None or _is_admin(user)
        else col.where("owner_uid", "==", user.get("uid")).stream()
    )
    rows = []
    for doc in cursor:
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


def add_expense(data: dict[str, Any], user: dict) -> str:
    from firebase_admin import firestore as fs
    db = get_db()
    data = {k: v for k, v in data.items() if k in _EXPENSE_FIELDS}
    if "start_date" in data:
        data["start_date"] = _to_dt(data["start_date"])
    if "end_date" in data:
        data["end_date"] = _to_dt(data["end_date"])
    existing = list(db.collection("finance_expenses").stream())
    max_order = max((d.to_dict().get("order") or 0 for d in existing), default=0)
    data["order"] = max_order + 1
    data["owner_uid"] = user["uid"]
    data["created_at"] = fs.SERVER_TIMESTAMP
    data["updated_at"] = fs.SERVER_TIMESTAMP
    data["updated_by"] = user["email"]
    _, ref = db.collection("finance_expenses").add(data)
    return ref.id


def update_expense(doc_id: str, updates: dict[str, Any], user: dict) -> None:
    from firebase_admin import firestore as fs
    db = get_db()
    ref = db.collection("finance_expenses").document(doc_id)
    _require_owner(ref, user)
    # Whitelist: drops owner_uid, order, timestamps, and any unknown key.
    updates = {k: v for k, v in updates.items() if k in _EXPENSE_FIELDS}
    if "start_date" in updates:
        updates["start_date"] = _to_dt(updates["start_date"])
    if "end_date" in updates:
        updates["end_date"] = _to_dt(updates["end_date"])
    updates["updated_at"] = fs.SERVER_TIMESTAMP
    updates["updated_by"] = user["email"]
    ref.update(updates)


def delete_expense(doc_id: str, user: dict) -> None:
    ref = get_db().collection("finance_expenses").document(doc_id)
    _require_owner(ref, user)
    ref.delete()


# ── Income ────────────────────────────────────────────────────────────────────

def get_income(user: Optional[dict] = None) -> list[dict]:
    """Return income rows. Admins see all; editors see only rows they own."""
    db = get_db()
    col = db.collection("finance_income")
    cursor = (
        col.stream() if user is None or _is_admin(user)
        else col.where("owner_uid", "==", user.get("uid")).stream()
    )
    rows = []
    for doc in cursor:
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


def add_income(data: dict[str, Any], user: dict) -> str:
    from firebase_admin import firestore as fs
    db = get_db()
    data = {k: v for k, v in data.items() if k in _INCOME_FIELDS}
    if "date" in data:
        data["date"] = _to_dt(data["date"])
    existing = list(db.collection("finance_income").stream())
    max_order = max((d.to_dict().get("order") or 0 for d in existing), default=0)
    data["order"] = max_order + 1
    data["owner_uid"] = user["uid"]
    data["created_at"] = fs.SERVER_TIMESTAMP
    data["updated_at"] = fs.SERVER_TIMESTAMP
    data["updated_by"] = user["email"]
    _, ref = db.collection("finance_income").add(data)
    return ref.id


def update_income(doc_id: str, updates: dict[str, Any], user: dict) -> None:
    from firebase_admin import firestore as fs
    db = get_db()
    ref = db.collection("finance_income").document(doc_id)
    _require_owner(ref, user)
    updates = {k: v for k, v in updates.items() if k in _INCOME_FIELDS}
    if "date" in updates:
        updates["date"] = _to_dt(updates["date"])
    updates["updated_at"] = fs.SERVER_TIMESTAMP
    updates["updated_by"] = user["email"]
    ref.update(updates)


def delete_income(doc_id: str, user: dict) -> None:
    ref = get_db().collection("finance_income").document(doc_id)
    _require_owner(ref, user)
    ref.delete()
