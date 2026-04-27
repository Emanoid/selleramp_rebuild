"""Iterable processing pipeline shared by CLI and Streamlit UI.

Yields ProgressEvent objects after every row so callers can drive a progress
bar / log stream without blocking. The CLI consumes events synchronously; the
UI consumes them on a background thread.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional

from . import state as state_mod
from .cache import Cache
from .config import AppConfig
from .csv_io import InputRow, ReportWriter
from .keepa_client import CancelledByUser, KeepaClient, TokensExhausted
from .paths import cache_dir
from .report import build_row
from .token_bucket import TokenBucket

log = logging.getLogger("sa_rebuild")


@dataclass
class ProgressEvent:
    kind: str  # "start" | "row_done" | "row_error" | "paused" | "finished"
    rows_done: int
    rows_total: int
    tokens_left: int
    last_message: str
    last_row: Optional[Dict] = None  # the just-written report row (for live preview)
    # Per-row stats (populated for row_done / row_error)
    cache_hit: bool = False
    tokens_consumed: int = 0
    wait_seconds: float = 0.0
    row_seconds: float = 0.0
    # Refill rate from Keepa (tokens/min) so the UI can compute live token countup
    refill_rate_per_min: float = 1.0
    # Snapshot timestamp so the UI can extrapolate token count between events
    timestamp: float = 0.0


def build_keepa_client(cfg: AppConfig) -> tuple[KeepaClient, Cache, TokenBucket]:
    cache = Cache(cache_dir() / "keepa.sqlite")
    bucket = TokenBucket(refill_rate_per_min=1.0)
    return KeepaClient(cfg, cache, bucket), cache, bucket


def iter_process(
    cfg: AppConfig,
    rs: state_mod.RunState,
    inputs_by_row_id: Dict[int, InputRow],
    *,
    include_descriptions: bool = True,
    variations_fetch_max: int = 0,
    cancel_check: Optional[Callable[[], bool]] = None,
    is_resume: bool = False,
) -> Iterator[ProgressEvent]:
    """Drive the full run, yielding a ProgressEvent after each row.

    cancel_check: optional callable; when it returns True we checkpoint and exit
    (used by the UI's "Stop" button).
    """
    client, cache, bucket = build_keepa_client(cfg)
    fetch_asin = client.fetch_by_asin

    def _ev(kind: str, msg: str, last_row: Optional[Dict] = None,
            cache_hit: bool = False, tokens_consumed: int = 0,
            wait_seconds: float = 0.0, row_seconds: float = 0.0) -> ProgressEvent:
        return ProgressEvent(
            kind=kind,
            rows_done=rs.rows_done,
            rows_total=rs.rows_total,
            tokens_left=client.tokens_left(),
            last_message=msg,
            last_row=last_row,
            cache_hit=cache_hit,
            tokens_consumed=tokens_consumed,
            wait_seconds=wait_seconds,
            row_seconds=row_seconds,
            refill_rate_per_min=bucket.refill_rate_per_min,
            timestamp=time.time(),
        )

    try:
        with ReportWriter(rs.output_csv, include_descriptions=include_descriptions,
                          allow_resume=is_resume) as writer:
            yield _ev("start",
                      f"Run {rs.run_id} starting — {rs.rows_total - rs.rows_done} rows to process")
            remaining = list(rs.remaining_row_ids)
            already_done = set(rs.completed_row_ids)
            for idx, row_id in enumerate(remaining, start=1):
                if cancel_check and cancel_check():
                    yield _ev("paused", "Stopped by user. Resume any time.")
                    return
                # Defensive dedup: never re-process a row that's already in completed_row_ids.
                if row_id in already_done:
                    log.info("skipping row#%s — already in completed_row_ids", row_id)
                    if row_id in rs.remaining_row_ids:
                        rs.remaining_row_ids.remove(row_id)
                    state_mod.save(rs)
                    continue
                in_row = inputs_by_row_id.get(row_id)
                if not in_row:
                    state_mod.mark_error(rs, row_id, "?", "input", "missing input row")
                    yield _ev("row_error", f"row#{row_id} skipped — missing input")
                    continue

                key = in_row.lookup_key
                fetch_kind = "asin" if in_row.lookup_is_asin else "upc"
                row_t0 = time.time()
                try:
                    if in_row.lookup_is_asin:
                        product = client.fetch_by_asin(key, cancel_check=cancel_check)
                    else:
                        product = client.fetch_by_upc(key, cancel_check=cancel_check)
                except CancelledByUser:
                    yield _ev("paused", "Stopped by user mid-wait. Resume any time.")
                    return
                except TokensExhausted as e:
                    log.warning(str(e))
                    yield _ev("paused", str(e))
                    return
                except Exception as e:
                    log.exception("fetch failed %s=%s", fetch_kind, key)
                    state_mod.mark_error(rs, row_id, key, "fetch", repr(e))
                    yield _ev("row_error", f"row#{row_id} {fetch_kind}={key} fetch failed: {e}")
                    continue

                row = build_row(
                    in_row, product, cfg,
                    fetch_asin=fetch_asin,
                    variations_fetch_max=variations_fetch_max,
                )
                writer.write(row)
                state_mod.mark_done(rs, row_id, client.tokens_left())

                row_seconds = time.time() - row_t0
                cache_hit = client.last_was_cache_hit
                tokens_used = client.last_tokens_consumed
                waited = client.last_wait_seconds
                src = "💾 cache" if cache_hit else f"🌐 keepa ({tokens_used}t)"
                wait_str = f" ⏳{waited:.0f}s wait" if waited > 1 else ""
                msg = (
                    f"row#{row_id} {fetch_kind}={key} cost=${in_row.cost:.2f} "
                    f"→ {row.get('viability_label', '—')} "
                    f"[{src}{wait_str} ⏱{row_seconds:.1f}s]"
                )
                yield _ev("row_done", msg, last_row=row,
                          cache_hit=cache_hit, tokens_consumed=tokens_used,
                          wait_seconds=waited, row_seconds=row_seconds)
                time.sleep(0.05)
    finally:
        cache.close()
    yield _ev("finished", f"Run complete — {rs.rows_done}/{rs.rows_total} processed")
