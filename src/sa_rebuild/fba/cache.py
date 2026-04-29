"""SQLite-backed key/value cache with TTL — saves Keepa tokens across runs."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional


class Cache:
    def __init__(self, path: Path | str = "cache/keepa.sqlite"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            "  k TEXT PRIMARY KEY,"
            "  v TEXT NOT NULL,"
            "  expires_at REAL NOT NULL"
            ")"
        )
        self._conn.commit()

    def get(self, key: str) -> Optional[Any]:
        row = self._conn.execute(
            "SELECT v, expires_at FROM kv WHERE k = ?", (key,)
        ).fetchone()
        if not row:
            return None
        v, expires_at = row
        if expires_at and expires_at < time.time():
            self._conn.execute("DELETE FROM kv WHERE k = ?", (key,))
            self._conn.commit()
            return None
        return json.loads(v)

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        expires_at = time.time() + ttl_seconds
        self._conn.execute(
            "INSERT OR REPLACE INTO kv (k, v, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, default=str), expires_at),
        )
        self._conn.commit()

    def clear_older_than(self, seconds: float) -> int:
        cutoff = time.time() - seconds
        cur = self._conn.execute(
            "DELETE FROM kv WHERE expires_at < ?", (cutoff,)
        )
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
