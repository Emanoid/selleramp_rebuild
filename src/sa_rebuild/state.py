"""Durable per-row state — atomic writes so a crash mid-write never corrupts."""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


from .paths import state_dir as _state_dir

STATE_DIR = _state_dir()
LAST_RUN_POINTER = STATE_DIR / "last_run.json"


@dataclass
class RunError:
    upc: str
    stage: str
    message: str


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

    @classmethod
    def new(cls, input_csv: str, output_csv: str, row_ids: List[int], config_path: str = "config.yaml") -> "RunState":
        ts = time.strftime("%Y%m%dT%H%M%S")
        return cls(
            run_id=f"{ts}-{uuid.uuid4().hex[:6]}",
            input_csv=input_csv,
            output_csv=output_csv,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            rows_total=len(row_ids),
            remaining_row_ids=list(row_ids),
            config_path=config_path,
        )

    def path(self) -> Path:
        return STATE_DIR / f"run_{self.run_id}.json"


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def save(state: RunState) -> None:
    state.last_updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    payload = asdict(state)
    _atomic_write_json(state.path(), payload)
    _atomic_write_json(LAST_RUN_POINTER, payload)


def load(run_id: str) -> RunState:
    path = STATE_DIR / f"run_{run_id}.json"
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return RunState(**data)


def load_last() -> Optional[RunState]:
    if not LAST_RUN_POINTER.exists():
        return None
    with LAST_RUN_POINTER.open(encoding="utf-8") as f:
        data = json.load(f)
    return RunState(**data)


def mark_done(state: RunState, row_id: int, tokens_left: int) -> None:
    if row_id in state.remaining_row_ids:
        state.remaining_row_ids.remove(row_id)
    if row_id not in state.completed_row_ids:
        state.completed_row_ids.append(row_id)
    state.rows_done = len(state.completed_row_ids)
    state.tokens_left_snapshot = tokens_left
    save(state)


def mark_error(state: RunState, row_id: int, upc: str, stage: str, message: str) -> None:
    state.errors.append({"row_id": row_id, "upc": upc, "stage": stage, "message": message})
    save(state)
