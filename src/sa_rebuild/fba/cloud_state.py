"""Firestore-backed run state for Streamlit Cloud deployments.

Collections (all prefixed fba_ — wiped cleanly by clear_all_fba_data):
  fba_runs/{run_id}             — run metadata + serialised input rows
  fba_output/{run_id}__{row_id} — one doc per completed report row
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ..compliance.firebase_client import get_db

RUNS_COL = "fba_runs"
OUTPUT_COL = "fba_output"
_SEP = "__"
HEARTBEAT_STALE_S = 30   # running run considered orphaned after this many seconds of silence
_PENDING_STALE_S  = 120  # pending run with no heartbeat considered orphaned after this


@dataclass
class RunState:
    run_id: str
    input_csv: str
    output_csv: str
    started_at: str
    last_updated_at: str = ""
    rows_total: int = 0
    rows_done: int = 0
    remaining_row_ids: List[int] = field(default_factory=list)
    tokens_left_snapshot: int = 0
    completed_row_ids: List[int] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    config_path: str = "config.yaml"
    status: str = "pending"
    last_heartbeat: float = 0.0
    last_message: str = ""
    input_rows: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def new(
        cls,
        input_csv: str,
        output_csv: str,
        row_ids: List[int],
        input_rows: Optional[List[Dict[str, Any]]] = None,
        config_path: str = "config.yaml",
    ) -> "RunState":
        ts = time.strftime("%Y%m%dT%H%M%S")
        return cls(
            run_id=f"{ts}-{uuid.uuid4().hex[:6]}",
            input_csv=input_csv,
            output_csv=output_csv,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            rows_total=len(row_ids),
            remaining_row_ids=list(row_ids),
            config_path=config_path,
            status="pending",
            input_rows=input_rows or [],
        )

    def path(self):
        return None

    @property
    def is_orphaned(self) -> bool:
        """Worker crashed or server restarted — run needs recovery."""
        if self.status == "running":
            return (
                self.last_heartbeat > 0
                and (time.time() - self.last_heartbeat) > HEARTBEAT_STALE_S
            )
        if self.status == "pending":
            # Worker crashed before first heartbeat — detect by run age
            try:
                from datetime import datetime
                age_s = (datetime.now() - datetime.fromisoformat(self.started_at)).total_seconds()
                return age_s > _PENDING_STALE_S
            except Exception:
                return True
        return False

    @property
    def is_resumable(self) -> bool:
        return self.status == "paused" or self.is_orphaned


def save(state: RunState) -> None:
    """Full document write — used for new runs and initial state creation."""
    state.last_updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    get_db().collection(RUNS_COL).document(state.run_id).set(asdict(state))


def _partial_update(run_id: str, fields: dict) -> None:
    fields["last_updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    get_db().collection(RUNS_COL).document(run_id).update(fields)


def load(run_id: str) -> RunState:
    doc = get_db().collection(RUNS_COL).document(run_id).get()
    if not doc.exists:
        raise KeyError(f"Run {run_id} not found in Firestore")
    return RunState(**doc.to_dict())


def list_all_runs(limit: int = 50) -> List[RunState]:
    docs = (
        get_db().collection(RUNS_COL)
        .order_by("started_at", direction="DESCENDING")
        .limit(limit)
        .stream()
    )
    return [RunState(**d.to_dict()) for d in docs]


def load_last() -> Optional[RunState]:
    """Return the most recent resumable run, or the most recent run overall."""
    runs = list_all_runs(limit=20)
    for r in runs:
        if r.is_resumable and r.remaining_row_ids:
            return r
    return runs[0] if runs else None


def mark_done(state: RunState, row_id: int, tokens_left: int) -> None:
    if row_id in state.remaining_row_ids:
        state.remaining_row_ids.remove(row_id)
    if row_id not in state.completed_row_ids:
        state.completed_row_ids.append(row_id)
    state.rows_done = len(state.completed_row_ids)
    state.tokens_left_snapshot = tokens_left
    state.status = "running"
    _partial_update(state.run_id, {
        "remaining_row_ids": state.remaining_row_ids,
        "completed_row_ids": state.completed_row_ids,
        "rows_done": state.rows_done,
        "tokens_left_snapshot": tokens_left,
        "status": "running",
    })


def mark_error(state: RunState, row_id: int, upc: str, stage: str, message: str) -> None:
    state.errors.append({"row_id": row_id, "upc": upc, "stage": stage, "message": message})
    _partial_update(state.run_id, {"errors": state.errors})


def set_status(state: RunState, status: str) -> None:
    state.status = status
    _partial_update(state.run_id, {"status": status})


def write_heartbeat(run_id: str, rows_done: int, tokens_left: int,
                    last_message: str = "") -> None:
    update: Dict[str, Any] = {
        "last_heartbeat": time.time(),
        "rows_done": rows_done,
        "tokens_left_snapshot": tokens_left,
        "status": "running",
        "last_updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if last_message:
        update["last_message"] = last_message
    get_db().collection(RUNS_COL).document(run_id).update(update)


def is_cancelled(run_id: str) -> bool:
    doc = get_db().collection(RUNS_COL).document(run_id).get(field_paths=["status"])
    return doc.exists and doc.to_dict().get("status") == "cancelled"


def cancel_run(run_id: str) -> None:
    get_db().collection(RUNS_COL).document(run_id).update({"status": "cancelled"})


def delete_run(run_id: str) -> None:
    db = get_db()
    db.collection(RUNS_COL).document(run_id).delete()
    for doc in db.collection(OUTPUT_COL).where("run_id", "==", run_id).stream():
        doc.reference.delete()


def save_output_row(run_id: str, row_id: int, row: Dict[str, Any]) -> None:
    doc_id = f"{run_id}{_SEP}{row_id}"
    get_db().collection(OUTPUT_COL).document(doc_id).set(
        {"run_id": run_id, "row_id": row_id, **row}
    )


def get_output_rows(run_id: str) -> List[Dict[str, Any]]:
    docs = get_db().collection(OUTPUT_COL).where("run_id", "==", run_id).stream()
    rows = [d.to_dict() for d in docs]
    rows.sort(key=lambda r: r.get("row_id", 0))
    return rows


def build_output_csv(run_id: str, include_descriptions: bool = True) -> str:
    """Assemble all completed rows for a run into a CSV string."""
    import csv
    import io
    from .csv_io import COLUMN_DESCRIPTIONS, REPORT_COLUMNS

    rows = get_output_rows(run_id)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    if include_descriptions and rows:
        writer.writerow({c: COLUMN_DESCRIPTIONS.get(c, "") for c in REPORT_COLUMNS})
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def clear_all_fba_data() -> int:
    """Delete all fba_runs and fba_output documents. Returns total docs deleted."""
    db = get_db()
    total = 0
    for col in (RUNS_COL, OUTPUT_COL):
        for doc in db.collection(col).stream():
            doc.reference.delete()
            total += 1
    return total
