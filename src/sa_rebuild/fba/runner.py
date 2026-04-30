"""Iterable processing pipeline shared by CLI and Streamlit UI.

Yields ProgressEvent after every meaningful event — row start, wait ticks (every
30 s during token sleeps, 15 s during retries), row completion, errors — so the
UI log shows live activity even during long token-refill waits.

Cloud mode: pass state_mod=cloud_state and save_output_row_fn to persist to
Firestore instead of disk. CLI uses defaults (disk state, CSV output).

Retry strategy (the run NEVER pauses for token or network reasons):
  NOT_ENOUGH_TOKEN drift  → exponential backoff 60 s → 120 s → … cap 15 min, up to 10x
  Token wait > limit      → sleep the exact required seconds, yield tick every 30 s, retry
  Network / Keepa error   → backoff 30 s → 60 s → …, yield tick every 15 s, up to 5x per row
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Dict, Generator, Iterator, Optional, Tuple

from . import state as _disk_state_mod
from .cache import Cache
from ..config import AppConfig
from .csv_io import InputRow, ReportWriter
from .keepa_client import CancelledByUser, KeepaClient, TokensExhausted
from ..paths import cache_dir
from .report import build_row
from .token_bucket import TokenBucket

log = logging.getLogger("sa_rebuild")

_MAX_DRIFT_RETRIES = 10
_DRIFT_BASE_SLEEP_S = 60.0
_DRIFT_MAX_SLEEP_S = 900.0       # cap at 15 min per drift retry
_MAX_NET_RETRIES = 5
_NET_BASE_SLEEP_S = 30.0
_NET_MAX_SLEEP_S = 300.0         # cap at 5 min per network retry
_HEARTBEAT_INTERVAL_S = 10.0
_TOKEN_TICK_INTERVAL_S = 30.0    # how often to log progress during long token sleeps
_RETRY_TICK_INTERVAL_S = 15.0    # how often to log progress during retry backoffs


@dataclass
class ProgressEvent:
    kind: str   # "start" | "row_done" | "row_error" | "paused" | "finished"
    rows_done: int
    rows_total: int
    tokens_left: int
    last_message: str
    last_row: Optional[Dict] = None
    cache_hit: bool = False
    tokens_consumed: int = 0
    wait_seconds: float = 0.0
    row_seconds: float = 0.0
    refill_rate_per_min: float = 1.0
    timestamp: float = 0.0


class _NullWriter:
    def write(self, row): pass
    def __enter__(self): return self
    def __exit__(self, *exc): pass


def _fmt_s(seconds: float) -> str:
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def _interruptible_wait(
    seconds: float,
    cancel_check,
    tick_interval: float = 30.0,
) -> Generator[Tuple[bool, float, float], None, None]:
    """Interruptible sleep that yields progress ticks.

    Yields (cancelled, elapsed, remaining).
    First tick fires immediately; subsequent ticks fire every tick_interval.
    Final yield: (False, seconds, 0.0) — sleep complete.
    Cancel yield: (True, elapsed, remaining) — caller must return immediately.
    """
    elapsed = 0.0
    last_tick = -tick_interval  # fire first tick on entry
    while elapsed < seconds:
        if cancel_check and cancel_check():
            yield True, elapsed, seconds - elapsed
            return
        chunk = min(0.5, seconds - elapsed)
        time.sleep(chunk)
        elapsed += chunk
        if elapsed - last_tick >= tick_interval:
            yield False, elapsed, max(0.0, seconds - elapsed)
            last_tick = elapsed
    yield False, seconds, 0.0


def build_keepa_client(cfg: AppConfig) -> tuple[KeepaClient, Cache, TokenBucket]:
    cache = Cache(cache_dir() / "keepa.sqlite")
    bucket = TokenBucket(refill_rate_per_min=1.0)
    return KeepaClient(cfg, cache, bucket), cache, bucket


def iter_process(
    cfg: AppConfig,
    rs,
    inputs_by_row_id: Dict[int, InputRow],
    *,
    include_descriptions: bool = True,
    variations_fetch_max: int = 0,
    cancel_check: Optional[Callable[[], bool]] = None,
    is_resume: bool = False,
    state_mod=None,
    save_output_row_fn: Optional[Callable[[str, int, dict], None]] = None,
) -> Iterator[ProgressEvent]:
    """Drive the full run, yielding a ProgressEvent after every meaningful event.

    Emits events during waits so the UI log shows live activity — not just after
    each completed row. The run never pauses for token or network reasons unless
    the user explicitly stops it.
    """
    sm = state_mod if state_mod is not None else _disk_state_mod
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

    writer_ctx = _NullWriter() if save_output_row_fn else ReportWriter(
        rs.output_csv, include_descriptions=include_descriptions, allow_resume=is_resume
    )
    _last_heartbeat_t = 0.0

    _last_message = ""

    try:
        with writer_ctx as writer:
            sm.set_status(rs, "running")
            _last_message = f"▶ Run {rs.run_id} started — {rs.rows_total - rs.rows_done} rows to process"
            yield _ev("start", _last_message)
            remaining = list(rs.remaining_row_ids)
            already_done = set(rs.completed_row_ids)

            for row_id in remaining:
                if cancel_check and cancel_check():
                    sm.set_status(rs, "paused")
                    yield _ev("paused", "⏸ Stopped by user.")
                    return

                if row_id in already_done:
                    log.info("skipping row#%s — already done", row_id)
                    if row_id in rs.remaining_row_ids:
                        rs.remaining_row_ids.remove(row_id)
                    sm.save(rs)
                    continue

                in_row = inputs_by_row_id.get(row_id)
                if not in_row:
                    sm.mark_error(rs, row_id, "?", "input", "missing input row")
                    yield _ev("row_error", f"⚠ row#{row_id} skipped — missing input")
                    continue

                key = in_row.lookup_key
                fetch_kind = "asin" if in_row.lookup_is_asin else "upc"
                row_t0 = time.time()

                yield _ev("start",
                          f"→ row#{row_id} ({fetch_kind}={key}, cost=${in_row.cost:.2f}) "
                          f"— fetching from Keepa …")

                # ── fetch with full automatic retry ────────────────────────────
                product = None
                _fetched = False
                _drift_attempts = 0
                _net_attempts = 0

                while True:
                    try:
                        product = (
                            client.fetch_by_asin(key, cancel_check=cancel_check)
                            if in_row.lookup_is_asin
                            else client.fetch_by_upc(key, cancel_check=cancel_check)
                        )
                        _fetched = True
                        break

                    except CancelledByUser:
                        sm.set_status(rs, "paused")
                        yield _ev("paused", "⏸ Stopped by user mid-wait.")
                        return

                    except TokensExhausted as e:
                        if e.retryable:
                            # ── NOT_ENOUGH_TOKEN drift ──
                            _drift_attempts += 1
                            if _drift_attempts > _MAX_DRIFT_RETRIES:
                                log.warning("Drift retries exhausted row#%s", row_id)
                                sm.set_status(rs, "paused")
                                yield _ev("paused",
                                          f"⚠ row#{row_id}: token drift retries exhausted "
                                          f"after {_MAX_DRIFT_RETRIES} attempts — "
                                          f"resume will retry this row.")
                                return
                            backoff = min(
                                _DRIFT_BASE_SLEEP_S * (2 ** (_drift_attempts - 1)),
                                _DRIFT_MAX_SLEEP_S,
                            )
                            yield _ev("start",
                                      f"⚡ row#{row_id}: token count drift detected "
                                      f"(attempt {_drift_attempts}/{_MAX_DRIFT_RETRIES}) — "
                                      f"backing off {_fmt_s(backoff)}, bucket reset to 0")
                            for cancelled, _, remaining in _interruptible_wait(
                                backoff, cancel_check, _RETRY_TICK_INTERVAL_S
                            ):
                                if cancelled:
                                    sm.set_status(rs, "paused")
                                    yield _ev("paused", "⏸ Stopped during drift backoff.")
                                    return
                                if remaining > 0:
                                    yield _ev("start",
                                              f"⡿ row#{row_id}: drift backoff — "
                                              f"{_fmt_s(remaining)} remaining "
                                              f"(attempt {_drift_attempts}/{_MAX_DRIFT_RETRIES})")

                        else:
                            # ── Token wait exceeds configured limit ──
                            # Sleep the exact required duration and retry — never pauses.
                            wait_s = e.wait_seconds if e.wait_seconds > 0 else 3600.0
                            yield _ev("start",
                                      f"⏳ row#{row_id}: tokens depleted — sleeping "
                                      f"{_fmt_s(wait_s)} for refill, auto-retrying "
                                      f"(~{bucket.refill_rate_per_min:.0f} token/min, "
                                      f"have {client.tokens_left()})")
                            for cancelled, _, remaining in _interruptible_wait(
                                wait_s, cancel_check, _TOKEN_TICK_INTERVAL_S
                            ):
                                if cancelled:
                                    sm.set_status(rs, "paused")
                                    yield _ev("paused", "⏸ Stopped during token sleep.")
                                    return
                                if remaining > 0:
                                    yield _ev("start",
                                              f"⏳ row#{row_id}: token sleep — "
                                              f"{_fmt_s(remaining)} remaining "
                                              f"(now have ~{client.tokens_left()} tokens)")
                            _drift_attempts = 0  # tokens refilled; reset drift counter

                    except Exception as e:
                        _net_attempts += 1
                        if _net_attempts > _MAX_NET_RETRIES:
                            log.exception(
                                "fetch failed %s=%s after %d retries", fetch_kind, key, _MAX_NET_RETRIES
                            )
                            sm.mark_error(rs, row_id, key, "fetch", repr(e))
                            yield _ev("row_error",
                                      f"⚠ row#{row_id} {fetch_kind}={key} failed after "
                                      f"{_MAX_NET_RETRIES} retries — skipping row: {e}")
                            break
                        backoff = min(
                            _NET_BASE_SLEEP_S * (2 ** (_net_attempts - 1)),
                            _NET_MAX_SLEEP_S,
                        )
                        yield _ev("start",
                                  f"🌐 row#{row_id}: network error (attempt "
                                  f"{_net_attempts}/{_MAX_NET_RETRIES}) — "
                                  f"retry in {_fmt_s(backoff)}: {e}")
                        for cancelled, _, remaining in _interruptible_wait(
                            backoff, cancel_check, _RETRY_TICK_INTERVAL_S
                        ):
                            if cancelled:
                                sm.set_status(rs, "paused")
                                yield _ev("paused", "⏸ Stopped during network retry.")
                                return
                            if remaining > 0:
                                yield _ev("start",
                                          f"🌐 row#{row_id}: network retry "
                                          f"{_net_attempts}/{_MAX_NET_RETRIES} — "
                                          f"{_fmt_s(remaining)} remaining")

                if not _fetched:
                    continue

                # ── build + save report row ────────────────────────────────────
                row = build_row(
                    in_row, product, cfg,
                    fetch_asin=fetch_asin,
                    variations_fetch_max=variations_fetch_max,
                )

                if save_output_row_fn:
                    save_output_row_fn(rs.run_id, row_id, row)
                else:
                    writer.write(row)

                sm.mark_done(rs, row_id, client.tokens_left())

                row_seconds = time.time() - row_t0
                cache_hit = client.last_was_cache_hit
                tokens_used = client.last_tokens_consumed
                waited = client.last_wait_seconds
                src = "💾 cache" if cache_hit else f"🌐 Keepa ({tokens_used}t)"
                wait_str = f" ⏳{_fmt_s(waited)} wait" if waited > 1 else ""
                verdict = row.get("viability_label", "—")
                _last_message = (
                    f"✅ row#{row_id} {fetch_kind}={key} → {verdict} "
                    f"[{src}{wait_str} ⏱{row_seconds:.1f}s] "
                    f"profit=${row.get('estimated_profit', '—')} "
                    f"roi={row.get('roi_pct', '—')}%"
                )

                # ── heartbeat ─────────────────────────────────────────────────
                now = time.time()
                if now - _last_heartbeat_t >= _HEARTBEAT_INTERVAL_S and hasattr(sm, "write_heartbeat"):
                    sm.write_heartbeat(rs.run_id, rs.rows_done, client.tokens_left(),
                                       last_message=_last_message)
                    _last_heartbeat_t = now

                yield _ev("row_done", _last_message, last_row=row,
                          cache_hit=cache_hit, tokens_consumed=tokens_used,
                          wait_seconds=waited, row_seconds=row_seconds)
                time.sleep(0.05)
    finally:
        cache.close()

    sm.set_status(rs, "finished")
    yield _ev("finished",
              f"🏁 Run complete — {rs.rows_done}/{rs.rows_total} processed")
