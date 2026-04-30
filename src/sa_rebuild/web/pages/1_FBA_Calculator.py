"""FBA Sourcing Calculator — drag-drop CSV, watch progress, download report."""
from __future__ import annotations

import dataclasses
import io
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sa_rebuild import __version__
from sa_rebuild.fba import cloud_state
from sa_rebuild.fba.csv_io import COLUMN_DESCRIPTIONS, InputRow, REPORT_COLUMNS, read_input
from sa_rebuild.config import AppConfig
from sa_rebuild.paths import get_keepa_api_key, set_keepa_api_key
from sa_rebuild.fba.runner import iter_process, ProgressEvent


# ──────────────────────────────────────────── helpers

def _fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


TEMPLATE_CSV = (
    "upc,asin,cost,weight_lbs,prep_cost\n"
    "028800127321,,8.91,0.73,0.00\n"
    ",B005ET6J2K,8.91,0.73,0.00\n"
    "883503388642,,31.43,0.40,0.00\n"
)


# Firestore read throttle — all read paths are rate-limited to stay inside
# the free-tier 50K reads/day quota.
_HIST_TTL_S = 60.0      # run history list refresh interval
_PRIOR_TTL_S = 60.0     # load_last refresh interval
_FS_POLL_S   = 30.0     # Firestore-progress rerun interval
_CANCEL_POLL_S = 60.0   # cancel-monitor poll interval
_HIST_LIMIT  = 10       # max runs fetched per history query (10 reads × 1440/day = 14 400/day)


def _ensure_session():
    ss = st.session_state
    ss.setdefault("worker_thread", None)
    ss.setdefault("cancel_monitor_thread", None)
    ss.setdefault("events", [])
    ss.setdefault("cancel_flag", threading.Event())
    ss.setdefault("run_id", None)
    ss.setdefault("started_at", None)
    ss.setdefault("auto_resumed", False)
    ss.setdefault("tracked_run_id", None)
    # Firestore read caches — avoids re-reading on every 0.5 s rerun
    ss.setdefault("_runs_cache", None)
    ss.setdefault("_runs_cache_ts", 0.0)
    ss.setdefault("_prior_cache", None)
    ss.setdefault("_prior_cache_ts", 0.0)


def _cached_list_runs() -> list:
    """Return run history, fetching from Firestore at most once per _HIST_TTL_S."""
    ss = st.session_state
    now = time.time()
    if ss._runs_cache is not None and now - ss._runs_cache_ts < _HIST_TTL_S:
        return ss._runs_cache
    try:
        runs = cloud_state.list_all_runs(limit=_HIST_LIMIT)
        ss._runs_cache = runs
        ss._runs_cache_ts = now
    except Exception:
        if ss._runs_cache is not None:
            return ss._runs_cache
        raise
    return ss._runs_cache


def _cached_load_last() -> Optional[cloud_state.RunState]:
    """Return the most recent run, fetching from Firestore at most once per _PRIOR_TTL_S."""
    ss = st.session_state
    now = time.time()
    if ss._prior_cache_ts and now - ss._prior_cache_ts < _PRIOR_TTL_S:
        return ss._prior_cache
    try:
        run = cloud_state.load_last()
        ss._prior_cache = run
        ss._prior_cache_ts = now
    except Exception:
        return ss._prior_cache
    return run


def _rows_from_cloud_state(rs: cloud_state.RunState) -> dict[int, InputRow]:
    return {r["row_id"]: InputRow(**r) for r in rs.input_rows}


def _start_cancel_monitor(run_id: str, cancel_event: threading.Event) -> threading.Thread:
    def _monitor():
        while not cancel_event.is_set():
            time.sleep(_CANCEL_POLL_S)
            try:
                if cloud_state.is_cancelled(run_id):
                    cancel_event.set()
            except Exception:
                pass
    t = threading.Thread(target=_monitor, daemon=True)
    t.start()
    return t


def _launch_worker(rs: cloud_state.RunState, inputs_by_row_id: dict,
                   cfg: AppConfig, variations: int,
                   include_descriptions: bool, is_resume: bool):
    ss = st.session_state
    if ss.worker_thread is not None and ss.worker_thread.is_alive():
        st.warning("A run is already in progress.")
        return
    ss.run_id = rs.run_id
    ss.tracked_run_id = rs.run_id  # auto-track whatever we launch
    ss.started_at = time.time()
    ss.events = []
    ss.cancel_flag = threading.Event()
    ss.cancel_monitor_thread = _start_cancel_monitor(rs.run_id, ss.cancel_flag)
    events_buf = ss.events
    cancel = ss.cancel_flag

    def worker():
        for ev in iter_process(
            cfg, rs, inputs_by_row_id,
            include_descriptions=include_descriptions,
            variations_fetch_max=variations,
            cancel_check=cancel.is_set,
            is_resume=is_resume,
            state_mod=cloud_state,
            save_output_row_fn=cloud_state.save_output_row,
        ):
            events_buf.append(ev)

    ss.worker_thread = threading.Thread(target=worker, daemon=True)
    ss.worker_thread.start()


def _start_new_run(cfg: AppConfig, uploaded_bytes: bytes,
                   variations: int, include_descriptions: bool):
    ts = time.strftime("%Y%m%dT%H%M%S")
    tmp = Path(f"/tmp/sa_rebuild_upload_{ts}.csv")
    tmp.write_bytes(uploaded_bytes)
    rows = read_input(tmp)
    if not rows:
        st.error("No usable rows in the uploaded CSV.")
        return
    input_rows_dicts = [dataclasses.asdict(r) for r in rows]
    rs = cloud_state.RunState.new(
        input_csv=str(tmp), output_csv="",
        row_ids=[r.row_id for r in rows],
        input_rows=input_rows_dicts,
    )
    cloud_state.save(rs)
    _launch_worker(rs, {r.row_id: r for r in rows}, cfg, variations, include_descriptions,
                   is_resume=False)


def _resume_run(rs: cloud_state.RunState, cfg: AppConfig,
                variations: int, include_descriptions: bool):
    _launch_worker(rs, _rows_from_cloud_state(rs), cfg, variations, include_descriptions,
                   is_resume=True)


def _avg_tokens_per_row(events: list[ProgressEvent]) -> Optional[float]:
    rows = [e for e in events if e.kind == "row_done" and not e.cache_hit]
    return sum(e.tokens_consumed for e in rows) / len(rows) if rows else None


def _live_tokens(events: list[ProgressEvent]) -> tuple[int, float]:
    if not events:
        return 0, 1.0
    latest = events[-1]
    elapsed_min = max(0.0, (time.time() - latest.timestamp) / 60.0)
    refill = latest.refill_rate_per_min or 1.0
    return min(60, int(latest.tokens_left + elapsed_min * refill)), refill


def _eta_seconds(events: list[ProgressEvent], remaining: int) -> Optional[float]:
    if remaining <= 0:
        return 0.0
    avg = _avg_tokens_per_row(events)
    if avg is None or avg <= 0:
        done = [e for e in events if e.kind == "row_done"]
        if not done:
            return None
        rate = len(done) / max(time.time() - (st.session_state.get("started_at") or time.time()), 1.0)
        return remaining / rate if rate > 0 else None
    tokens_now, refill = _live_tokens(events)
    return max(0, remaining * avg - tokens_now) * 60.0 / refill


def _download_button(run_id: str, include_descriptions: bool, key_suffix: str = ""):
    try:
        csv_bytes = cloud_state.build_output_csv(
            run_id, include_descriptions=include_descriptions
        ).encode("utf-8")
        ts_label = run_id.split("-")[0]
        st.download_button(
            f"📥 Download report_{ts_label}.csv",
            data=csv_bytes,
            file_name=f"report_{ts_label}.csv",
            mime="text/csv",
            width="stretch",
            type="primary",
            key=f"dl_{run_id}{key_suffix}",
        )
    except Exception as e:
        st.warning(f"Could not build download: {e}")


def _show_dataframe_preview(run_id: str):
    try:
        csv_str = cloud_state.build_output_csv(run_id, include_descriptions=True)
        df = pd.read_csv(io.StringIO(csv_str))
        if len(df) > 0 and str(df.iloc[0].get("upc", "")).startswith("[COLUMN HELP"):
            df = df.iloc[1:].reset_index(drop=True)
        st.caption(f"Preview ({len(df)} data rows)")
        priority = ["upc", "asin", "title", "cost", "recommended_sell_price",
                    "estimated_profit", "roi_pct", "monthly_sales", "bsr_pct",
                    "live_fba_seller_count", "viability_label", "notes"]
        cols_present = [c for c in priority if c in df.columns]
        st.dataframe(df[cols_present], width="stretch", height=320)
        with st.expander("Show all columns"):
            st.dataframe(df, width="stretch", height=400)
    except Exception as e:
        st.caption(f"(Preview failed: {e})")


# ──────────────────────────────────────────── progress renderers

def _render_local_progress(events: list[ProgressEvent], worker_running: bool,
                            include_descriptions: bool) -> Optional[float]:
    """Progress view driven by in-memory events. Returns rerun interval (s) or None."""
    latest = events[-1] if events else None
    rows_done = latest.rows_done if latest else 0
    rows_total = latest.rows_total if latest else 0
    pct = (rows_done / rows_total) if rows_total else 0.0

    tokens_now, refill = _live_tokens(events)
    avg_tok = _avg_tokens_per_row(events)
    eta = _eta_seconds(events, rows_total - rows_done) if worker_running else 0.0
    done_events = [e for e in events if e.kind == "row_done"]
    cache_hits = sum(1 for e in done_events if e.cache_hit)
    total_tokens_used = sum(e.tokens_consumed for e in done_events)
    total_wait_s = sum(e.wait_seconds for e in done_events)
    error_count = sum(1 for e in events if e.kind == "row_error")

    c = st.columns(4)
    c[0].metric("Rows done", f"{rows_done}/{rows_total}",
                delta=f"{error_count} errors" if error_count else None, delta_color="inverse")
    c[1].metric("Tokens (live)", f"{tokens_now}/60",
                delta=f"+{refill:.0f}/min refill", delta_color="normal")
    c[2].metric("ETA", _fmt_duration(eta) if eta is not None else "—")
    last_label = next(
        (ev.last_row["viability_label"] for ev in reversed(events)
         if ev.last_row and ev.last_row.get("viability_label")), "—"
    )
    c[3].metric("Last verdict", last_label)

    c2 = st.columns(4)
    c2[0].metric("Tokens spent", total_tokens_used)
    c2[1].metric("Avg tokens/row", f"{avg_tok:.1f}" if avg_tok else "—")
    c2[2].metric("Cache hits", f"{cache_hits}/{len(done_events)}" if done_events else "0/0")
    c2[3].metric("Total wait", _fmt_duration(total_wait_s))

    st.progress(pct, text=f"{int(pct*100)}% — {(latest.last_message if latest else '')[:140]}")

    if worker_running:
        if st.button("⏹ Stop run", help="Checkpoints cleanly at the next row boundary."):
            st.session_state.cancel_flag.set()
            st.toast("Stopping at next checkpoint…")

        if latest and latest.kind in ("row_done", "start"):
            elapsed = time.time() - (latest.timestamp or time.time())
            if elapsed > 60:
                tokens_now2, refill2 = _live_tokens(events)
                short = max(0, (int(avg_tok) if avg_tok else 7) - tokens_now2)
                if short > 0:
                    st.info(f"⏳ Waiting for tokens — need {short} more, "
                            f"~{_fmt_duration(short * 60.0 / refill2)} until next row "
                            f"(elapsed {_fmt_duration(elapsed)})")
                else:
                    st.info(f"🌐 Fetching from Keepa… (elapsed {_fmt_duration(elapsed)})")

    # Log — newest first so latest activity is always visible at the top
    _LOG_CAP = 500
    log_events = events[-_LOG_CAP:]
    log_lines = []
    for ev in reversed(log_events):
        ts = time.strftime("%H:%M:%S", time.localtime(ev.timestamp)) if ev.timestamp else "??:??:??"
        icon = {
            "start":     "·",
            "row_done":  "✓",
            "row_error": "✗",
            "paused":    "⏸",
            "finished":  "★",
        }.get(ev.kind, "·")
        log_lines.append(f"[{ts}] {icon} {ev.last_message}")

    label = (
        f"Live log — {len(events)} events"
        + (f" (showing newest {_LOG_CAP})" if len(events) > _LOG_CAP else "")
        + " ↑ newest first"
    )
    with st.expander(label, expanded=True):
        st.code(
            "\n".join(log_lines) if log_lines else "(no events yet)",
            language=None,
        )

    ss = st.session_state
    finished = next((e for e in reversed(events) if e.kind in ("finished", "paused")), None)
    if finished and ss.run_id:
        st.divider()
        _download_button(ss.run_id, include_descriptions, key_suffix="_local")
        _show_dataframe_preview(ss.run_id)

    return 0.5 if worker_running else None


def _render_firestore_progress(rs: cloud_state.RunState, include_descriptions: bool,
                                variations: int, cfg: AppConfig) -> Optional[float]:
    """Progress view for a run tracked from history. Returns rerun interval (s) or None."""
    staleness = time.time() - rs.last_heartbeat if rs.last_heartbeat else None
    status_icon = {"running": "🟢", "paused": "⏸", "finished": "✅",
                   "cancelled": "🚫", "pending": "🟡"}.get(rs.status, "❓")

    st.caption(
        f"{status_icon} Status: **{rs.status}**"
        + (f" — last heartbeat {_fmt_duration(staleness)} ago" if staleness else "")
    )

    pct = (rs.rows_done / rs.rows_total) if rs.rows_total else 0.0
    st.progress(pct, text=f"{int(pct * 100)}% — {rs.rows_done}/{rs.rows_total} rows done")

    c = st.columns(3)
    c[0].metric("Rows done", f"{rs.rows_done}/{rs.rows_total}")
    c[1].metric("Rows remaining", len(rs.remaining_row_ids))
    c[2].metric("Errors", len(rs.errors))

    if rs.errors:
        with st.expander(f"Errors ({len(rs.errors)})"):
            for e in rs.errors:
                st.caption(f"row#{e['row_id']} — {e['message']}")

    col_a, col_b, col_c = st.columns(3)

    # Resume from this browser
    if rs.is_resumable and rs.remaining_row_ids:
        if col_a.button("▶ Resume here", key=f"fs_resume_{rs.run_id}", type="primary"):
            if not get_keepa_api_key():
                st.error("Enter your Keepa API key in the sidebar first.")
            else:
                _resume_run(rs, cfg, variations, include_descriptions)
                st.rerun()

    # Terminate
    if rs.status in ("running", "pending"):
        if col_b.button("⏹ Terminate", key=f"fs_term_{rs.run_id}"):
            cloud_state.cancel_run(rs.run_id)
            st.toast("Cancellation signal sent.")
            st.rerun()

    # Download
    if rs.rows_done > 0:
        _download_button(rs.run_id, include_descriptions, key_suffix="_fs")

    if rs.rows_done > 0:
        _show_dataframe_preview(rs.run_id)

    return _FS_POLL_S if rs.status == "running" else None


# ──────────────────────────────────────────── page

_ensure_session()
ss = st.session_state

st.title(f"FBA Sourcing Calculator  v{__version__}")
st.caption("Drag-drop a CSV of UPC/ASIN + cost. Get a per-row Buy/Caution/Skip report from Keepa.")

# ──────────────────────────────────────────── sidebar

with st.sidebar:
    st.header("Setup")
    current_key = get_keepa_api_key() or ""
    masked = (current_key[:4] + "…" + current_key[-4:]) if len(current_key) >= 8 else ""
    new_key = st.text_input("Keepa API key", value=current_key, type="password",
                            help=f"Currently: {masked or 'not set'}")
    if new_key and new_key != current_key:
        set_keepa_api_key(new_key)
        st.success("Key saved.")

    st.divider()
    st.subheader("Run options")
    variations = st.slider("Sibling variations per parent", min_value=0, max_value=50, value=0,
                           help="0 = disabled. Each sibling costs ~7 Keepa tokens.")
    include_descriptions = st.checkbox("Include column-help row in report CSV", value=True)

    st.divider()

cfg = AppConfig.load()
cfg.runtime.max_wait_minutes = 10080  # 1 week — runner auto-retries; never pauses for tokens

# ──────────────────────────────────────────── auto-resume on server restart

worker_running = ss.worker_thread is not None and ss.worker_thread.is_alive()

if not worker_running and not ss.auto_resumed:
    try:
        prior = _cached_load_last()
        if prior and prior.is_orphaned and prior.remaining_row_ids:
            ss.auto_resumed = True
            stale_min = int((time.time() - prior.last_heartbeat) / 60) if prior.last_heartbeat else "?"
            st.warning(
                f"🔄 **Server restart detected** — run **{prior.run_id}** was interrupted "
                f"({stale_min}m ago, {prior.rows_done}/{prior.rows_total} rows done, "
                f"{len(prior.remaining_row_ids)} remaining). "
                f"Auto-resuming now — no action needed."
            )
            if get_keepa_api_key():
                _resume_run(prior, cfg, variations, include_descriptions)
                st.rerun()
            else:
                st.error(
                    "⚠️ Keepa API key missing — enter it in the sidebar to auto-resume. "
                    "Your progress is safe in Firestore."
                )
    except Exception as _e:
        st.warning(f"Could not check Firestore for prior run: {_e}")

# ──────────────────────────────────────────── upload + start

left, right = st.columns(2)
with left:
    st.subheader("1. Get the input template")
    st.download_button("Download CSV template", data=TEMPLATE_CSV,
                       file_name="sa-rebuild-template.csv", mime="text/csv", width="stretch")
    st.caption("Required: `cost` + at least one of `upc` or `asin`. Optional: `weight_lbs`, `prep_cost`.")

with right:
    st.subheader("2. Upload your CSV")
    uploaded = st.file_uploader("Drop a CSV here", type=["csv"],
                                accept_multiple_files=False, label_visibility="collapsed")

# resume banner (manual pause, not orphaned)
try:
    prior = _cached_load_last()
except Exception:
    prior = None

worker_running = ss.worker_thread is not None and ss.worker_thread.is_alive()

if (prior and prior.is_resumable and not prior.is_orphaned
        and prior.remaining_row_ids and not worker_running
        and ss.run_id != prior.run_id):
    st.warning(
        f"Run **{prior.run_id}** paused — "
        f"{len(prior.remaining_row_ids)}/{prior.rows_total} rows remaining."
    )
    if st.button("▶ Resume previous run", type="primary"):
        if not get_keepa_api_key():
            st.error("Enter your Keepa API key in the sidebar first.")
        else:
            _resume_run(prior, cfg, variations, include_descriptions)
            st.rerun()

st.subheader("3. Run analysis")
run_disabled = uploaded is None or worker_running
if st.button("▶ Start run", type="primary", disabled=run_disabled):
    if not get_keepa_api_key():
        st.error("Enter your Keepa API key in the sidebar first.")
    else:
        _start_new_run(cfg, uploaded.getvalue(), variations, include_descriptions)
        st.rerun()

# ──────────────────────────────────────────── progress section

worker_running = ss.worker_thread is not None and ss.worker_thread.is_alive()
tracked = ss.tracked_run_id
is_local_run = tracked and tracked == ss.run_id
is_foreign_run = tracked and tracked != ss.run_id

_rerun_after_s: Optional[float] = None

if worker_running or ss.events or tracked:
    st.divider()
    if is_foreign_run:
        st.subheader(f"Tracking run {tracked}")
    else:
        st.subheader("Progress")

if worker_running or ss.events:
    _rerun_after_s = _render_local_progress(ss.events, worker_running, include_descriptions)

elif tracked:
    try:
        tracked_rs = cloud_state.load(tracked)
        # Invalidate the runs-list cache so the history row reflects new status.
        ss._runs_cache_ts = 0.0
        _rerun_after_s = _render_firestore_progress(
            tracked_rs, include_descriptions, variations, cfg
        )
    except Exception as e:
        st.warning(f"Could not load run {tracked}: {e}")

# ──────────────────────────────────────────── run history

st.divider()
st.subheader("Run History")

_STATUS_ICON = {
    "running": "🟢", "pending": "🟡", "paused": "⏸",
    "finished": "✅", "cancelled": "🚫", "error": "❌", "": "❓",
}
_STATUS_HELP = {
    "running":   "Worker is active and sending heartbeats.",
    "pending":   "Run created but worker not yet started.",
    "paused":    "Manually stopped — click Resume or Track → Resume here.",
    "finished":  "All rows processed successfully.",
    "cancelled": "Terminated by user.",
    "error":     "Run ended with an unrecoverable error.",
}

try:
    all_runs = _cached_list_runs()
except Exception as _e:
    all_runs = []
    st.warning(f"Could not load run history: {_e}")

if not all_runs:
    st.caption("No runs yet.")
else:
    for run in all_runs:
        icon = _STATUS_ICON.get(run.status, "❓")
        orphan_tag = " 🔄 *(orphaned — recovering on next open)*" if run.is_orphaned else ""
        is_tracked = run.run_id == ss.tracked_run_id
        tracking_tag = " ← **tracking**" if is_tracked else ""
        header = (
            f"{icon} `{run.run_id}` — "
            f"{run.rows_done}/{run.rows_total} rows — "
            f"{run.started_at}{orphan_tag}{tracking_tag}"
        )
        with st.expander(header, expanded=is_tracked):
            action_cols = st.columns(4)

            # Track button — attach this browser to the run's progress
            if not is_tracked:
                if action_cols[0].button("🔍 Track", key=f"track_{run.run_id}",
                                         help="Watch this run's live progress from this browser."):
                    ss.tracked_run_id = run.run_id
                    ss._runs_cache_ts = 0.0
                    st.rerun()
            else:
                if action_cols[0].button("✕ Untrack", key=f"untrack_{run.run_id}"):
                    ss.tracked_run_id = None
                    ss._runs_cache_ts = 0.0
                    st.rerun()

            # Download
            if run.rows_done > 0:
                try:
                    csv_bytes = cloud_state.build_output_csv(
                        run.run_id, include_descriptions=include_descriptions
                    ).encode("utf-8")
                    ts_label = run.run_id.split("-")[0]
                    action_cols[1].download_button(
                        "📥 Download",
                        data=csv_bytes,
                        file_name=f"report_{ts_label}.csv",
                        mime="text/csv",
                        key=f"hist_dl_{run.run_id}",
                    )
                except Exception:
                    pass

            # Terminate
            if run.status in ("running", "pending"):
                if action_cols[2].button("⏹ Terminate", key=f"hist_term_{run.run_id}"):
                    cloud_state.cancel_run(run.run_id)
                    ss._runs_cache_ts = 0.0
                    st.toast(f"Cancellation sent to {run.run_id}.")
                    st.rerun()

            # Delete
            if action_cols[3].button("🗑 Delete", key=f"hist_del_{run.run_id}"):
                cloud_state.delete_run(run.run_id)
                if ss.run_id == run.run_id:
                    ss.run_id = None
                    ss.events = []
                if ss.tracked_run_id == run.run_id:
                    ss.tracked_run_id = None
                ss._runs_cache_ts = 0.0
                ss._prior_cache_ts = 0.0
                st.toast(f"Deleted {run.run_id}.")
                st.rerun()

            if run.errors:
                st.caption(
                    f"Errors: "
                    + ", ".join(f"row#{e['row_id']} {e['message']}" for e in run.errors[:5])
                )

# ──────────────────────────────────────────── danger zone

st.divider()
with st.expander("⚠️ Danger zone"):
    st.caption("Permanently deletes all FBA run history and output rows from Firestore.")
    if st.button("🗑 Clear all FBA history", type="secondary"):
        try:
            n = cloud_state.clear_all_fba_data()
            ss.run_id = None
            ss.tracked_run_id = None
            ss.events = []
            ss._runs_cache_ts = 0.0
            ss._prior_cache_ts = 0.0
            st.success(f"Deleted {n} documents.")
            st.rerun()
        except Exception as e:
            st.error(f"Clear failed: {e}")

# ──────────────────────────────────────────── column help

with st.expander("ℹ️ Column meanings"):
    md = "\n".join(f"- **{c}** — {COLUMN_DESCRIPTIONS.get(c, '')}" for c in REPORT_COLUMNS)
    st.markdown(md)

# Single rerun point — ensures the full page always renders before refreshing.
if _rerun_after_s is not None:
    time.sleep(_rerun_after_s)
    st.rerun()
