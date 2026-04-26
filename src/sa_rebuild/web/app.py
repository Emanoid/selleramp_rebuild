"""Streamlit UI — drag-drop CSV in browser, watch progress, download report.

Designed for non-technical users. Run via:
    streamlit run -m sa_rebuild.web.app
or, when bundled, via the desktop launcher in `desktop_launcher.py`.
"""
from __future__ import annotations

import io
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

# Streamlit runs this file as a standalone script, not as a package module,
# so relative imports fail. Make sure the package's parent dir is on sys.path
# (works both from-source and inside the PyInstaller bundle's _MEIPASS).
_HERE = Path(__file__).resolve()
for candidate in (_HERE.parents[2], getattr(sys, "_MEIPASS", None)):
    if candidate and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from sa_rebuild import state as state_mod
from sa_rebuild.config import AppConfig
from sa_rebuild.csv_io import COLUMN_DESCRIPTIONS, REPORT_COLUMNS, read_input
from sa_rebuild.paths import (
    app_home,
    get_keepa_api_key,
    input_dir,
    output_dir,
    set_keepa_api_key,
)
from sa_rebuild.runner import iter_process, ProgressEvent

st.set_page_config(page_title="sa-rebuild — FBA Sourcing Calculator", layout="wide")


# ---------------------------------------------------------------------------- helpers

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


def _ensure_session():
    ss = st.session_state
    ss.setdefault("worker_thread", None)
    ss.setdefault("events", [])
    ss.setdefault("cancel_flag", threading.Event())
    ss.setdefault("run_id", None)
    ss.setdefault("output_path", None)
    ss.setdefault("started_at", None)


def _start_run(
    cfg: AppConfig,
    input_path: Path,
    output_path: Path,
    variations: int,
    include_descriptions: bool,
):
    ss = st.session_state
    rows = read_input(input_path)
    if not rows:
        st.error("No usable rows in the uploaded CSV.")
        return
    rs = state_mod.RunState.new(
        input_csv=str(input_path),
        output_csv=str(output_path),
        row_ids=[r.row_id for r in rows],
    )
    state_mod.save(rs)
    inputs_by_row_id = {r.row_id: r for r in rows}
    ss.run_id = rs.run_id
    ss.output_path = str(output_path)
    ss.started_at = time.time()
    ss.events = []
    ss.cancel_flag = threading.Event()

    cancel = ss.cancel_flag
    events_buf = ss.events

    def worker():
        for ev in iter_process(
            cfg, rs, inputs_by_row_id,
            include_descriptions=include_descriptions,
            variations_fetch_max=variations,
            cancel_check=cancel.is_set,
        ):
            events_buf.append(ev)

    ss.worker_thread = threading.Thread(target=worker, daemon=True)
    ss.worker_thread.start()


def _resume_existing(cfg: AppConfig, variations: int, include_descriptions: bool) -> bool:
    rs = state_mod.load_last()
    if rs is None or not rs.remaining_row_ids:
        return False
    rows = read_input(rs.input_csv)
    inputs_by_row_id = {r.row_id: r for r in rows}
    ss = st.session_state
    ss.run_id = rs.run_id
    ss.output_path = rs.output_csv
    ss.started_at = time.time()
    ss.events = []
    ss.cancel_flag = threading.Event()
    cancel = ss.cancel_flag
    events_buf = ss.events

    def worker():
        for ev in iter_process(
            cfg, rs, inputs_by_row_id,
            include_descriptions=include_descriptions,
            variations_fetch_max=variations,
            cancel_check=cancel.is_set,
        ):
            events_buf.append(ev)

    ss.worker_thread = threading.Thread(target=worker, daemon=True)
    ss.worker_thread.start()
    return True


def _live_tokens(events: list[ProgressEvent]) -> tuple[int, float]:
    """Extrapolate current token count from the latest event + elapsed time + refill rate.

    Returns (predicted_tokens, refill_rate_per_min).
    """
    if not events:
        return 0, 1.0
    latest = events[-1]
    elapsed_min = max(0.0, (time.time() - latest.timestamp) / 60.0)
    refill = latest.refill_rate_per_min or 1.0
    # Bucket size cap (Keepa Pro = 60). Anything larger gets clamped here only for
    # display; the runner uses Keepa's actual response numbers.
    return min(60, int(latest.tokens_left + elapsed_min * refill)), refill


def _avg_tokens_per_row(events: list[ProgressEvent]) -> Optional[float]:
    rows = [e for e in events if e.kind == "row_done" and not e.cache_hit]
    if not rows:
        return None
    return sum(e.tokens_consumed for e in rows) / len(rows)


def _eta_seconds(events: list[ProgressEvent], remaining: int) -> Optional[float]:
    """ETA based on token budget: remaining_rows * avg_tokens_per_row vs current tokens."""
    if remaining <= 0:
        return 0.0
    avg = _avg_tokens_per_row(events)
    if avg is None or avg <= 0:
        # Pre-first-row fallback: rate-based
        done = [e for e in events if e.kind == "row_done"]
        if len(done) < 1:
            return None
        started = st.session_state.get("started_at") or time.time()
        elapsed = time.time() - started
        rate = len(done) / max(elapsed, 1.0)
        return remaining / rate if rate > 0 else None
    tokens_now, refill = _live_tokens(events)
    tokens_needed = remaining * avg
    deficit = max(0, tokens_needed - tokens_now)
    return deficit * 60.0 / refill


# ---------------------------------------------------------------------------- UI

_ensure_session()
ss = st.session_state

st.title("sa-rebuild")
st.caption("Drag-drop a CSV of UPC/ASIN + cost. Get a per-row Buy/Caution/Skip report from Keepa.")

# ---- Sidebar: API key + settings -------------------------------------------
with st.sidebar:
    st.header("Setup")
    current_key = get_keepa_api_key() or ""
    masked = (current_key[:4] + "…" + current_key[-4:]) if len(current_key) >= 8 else ""
    new_key = st.text_input(
        "Keepa API key",
        value=current_key,
        type="password",
        help=f"Saved locally in {app_home()/'settings.json'}. Never leaves your machine. Currently: {masked or 'not set'}",
    )
    if new_key and new_key != current_key:
        set_keepa_api_key(new_key)
        st.success("Key saved.")

    st.divider()
    st.subheader("Run options")
    variations = st.slider(
        "Sibling variations to score per parent",
        min_value=0, max_value=50, value=0, step=1,
        help="0 = disabled (default). Each sibling fetched costs ~7 Keepa tokens. Enable when you want viable_variations + parent_monthly_sales filled in.",
    )
    include_descriptions = st.checkbox(
        "Include column-help row in report CSV",
        value=True,
        help="Adds a plain-language description as the second row of the report. Disable for cleaner pandas/Excel imports.",
    )

    st.divider()
    st.subheader("Throttling")
    max_wait_minutes = st.slider(
        "Max wait per row (minutes)",
        min_value=5, max_value=720, value=240, step=5,
        help=(
            "If a row needs longer than this for Keepa tokens to refill, the run "
            "auto-pauses (you click Resume later). Default 240 (4 h) means most "
            "rows sleep through. Lower it if you'd rather have manual pauses; "
            "raise it if you want fully unattended runs."
        ),
    )

    st.divider()
    st.caption(f"Data folder: `{app_home()}`")

# ---- Top section: template + upload ----------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("1. Get the input template")
    st.download_button(
        "Download CSV template",
        data=TEMPLATE_CSV,
        file_name="sa-rebuild-template.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.caption(
        "Required columns: `cost`, plus at least one of `upc` or `asin`. "
        "Optional: `weight_lbs`, `prep_cost`. ASIN wins when both present."
    )

with right:
    st.subheader("2. Upload your CSV")
    uploaded = st.file_uploader(
        "Drop a CSV here", type=["csv"], accept_multiple_files=False,
        label_visibility="collapsed",
    )

# ---- Resume detection ------------------------------------------------------
prior = state_mod.load_last()
worker_running = ss.worker_thread is not None and ss.worker_thread.is_alive()

if prior and prior.remaining_row_ids and not worker_running and ss.run_id != prior.run_id:
    st.warning(
        f"Previous run {prior.run_id} was paused with {len(prior.remaining_row_ids)} "
        f"of {prior.rows_total} rows remaining."
    )
    if st.button("▶ Resume previous run", type="primary"):
        if not get_keepa_api_key():
            st.error("Enter your Keepa API key in the sidebar first.")
        else:
            cfg = AppConfig.load()
            cfg.runtime.max_wait_minutes = max_wait_minutes
            if _resume_existing(cfg, variations, include_descriptions):
                st.rerun()

# ---- Run button ------------------------------------------------------------
st.subheader("3. Run analysis")

run_disabled = uploaded is None or worker_running
if st.button("▶ Start run", type="primary", disabled=run_disabled):
    if not get_keepa_api_key():
        st.error("Enter your Keepa API key in the sidebar first.")
    else:
        ts = time.strftime("%Y%m%dT%H%M%S")
        in_path = input_dir() / f"upload_{ts}.csv"
        in_path.write_bytes(uploaded.getvalue())
        out_path = output_dir() / f"report_{ts}.csv"
        cfg = AppConfig.load()
        cfg.runtime.max_wait_minutes = max_wait_minutes
        _start_run(cfg, in_path, out_path, variations, include_descriptions)
        st.rerun()

# ---- Live progress ---------------------------------------------------------
worker_running = ss.worker_thread is not None and ss.worker_thread.is_alive()
events: list[ProgressEvent] = ss.events

if worker_running or events:
    st.divider()
    st.subheader("Progress")

    latest = events[-1] if events else None
    rows_done = latest.rows_done if latest else 0
    rows_total = latest.rows_total if latest else 0
    pct = (rows_done / rows_total) if rows_total else 0.0

    tokens_now, refill = _live_tokens(events)
    avg_tok = _avg_tokens_per_row(events)
    eta = _eta_seconds(events, rows_total - rows_done) if worker_running else 0.0

    # Aggregate stats across all events
    done_events = [e for e in events if e.kind == "row_done"]
    cache_hits = sum(1 for e in done_events if e.cache_hit)
    total_tokens_used = sum(e.tokens_consumed for e in done_events)
    total_wait_s = sum(e.wait_seconds for e in done_events)
    total_row_s = sum(e.row_seconds for e in done_events)
    error_count = sum(1 for e in events if e.kind == "row_error")

    # Row 1: high-level
    cols = st.columns(4)
    cols[0].metric("Rows done", f"{rows_done}/{rows_total}",
                   delta=f"{error_count} errors" if error_count else None,
                   delta_color="inverse")
    cols[1].metric(
        "Tokens (live)",
        f"{tokens_now}/60",
        delta=f"+{refill:.0f}/min refill",
        delta_color="normal",
    )
    cols[2].metric("ETA", _fmt_duration(eta) if eta is not None else "—")
    last_label = "—"
    for ev in reversed(events):
        if ev.last_row and ev.last_row.get("viability_label"):
            last_label = ev.last_row["viability_label"]
            break
    cols[3].metric("Last verdict", last_label)

    # Row 2: token economy
    cols2 = st.columns(4)
    cols2[0].metric("Tokens spent", total_tokens_used)
    cols2[1].metric("Avg tokens/row",
                    f"{avg_tok:.1f}" if avg_tok else "—",
                    help="Excludes cache hits.")
    cols2[2].metric("Cache hits", f"{cache_hits}/{len(done_events)}" if done_events else "0/0",
                    help="Free fetches served from local 24h cache.")
    cols2[3].metric("Total wait", _fmt_duration(total_wait_s),
                    help="Cumulative time spent sleeping for token refill.")

    st.progress(pct, text=f"{int(pct*100)}% — {(latest.last_message if latest else '')[:140]}")

    if st.button("⏹ Stop run (checkpoint and exit)"):
        ss.cancel_flag.set()
        st.toast("Stopping at next row boundary…")

    # Live event log — expanded by default, last 50
    with st.expander(f"Run log ({len(events)} events)", expanded=True):
        for ev in events[-50:]:
            icon = {"start": "▶", "row_done": "✅", "row_error": "⚠️", "paused": "⏸",
                    "finished": "🏁"}.get(ev.kind, "•")
            st.text(f"{icon} {ev.last_message}")

    if worker_running:
        time.sleep(1)
        st.rerun()

# ---- Final result download -------------------------------------------------
finished_event = next((e for e in reversed(events) if e.kind in ("finished", "paused")), None)
if finished_event and ss.output_path and Path(ss.output_path).exists():
    st.divider()
    st.subheader("4. Download report")

    out = Path(ss.output_path)
    raw = out.read_bytes()
    st.download_button(
        f"📥 Download {out.name}",
        data=raw,
        file_name=out.name,
        mime="text/csv",
        use_container_width=True,
        type="primary",
    )

    # In-app preview (skip the description row if present)
    try:
        df = pd.read_csv(io.BytesIO(raw))
        if len(df) > 0 and str(df.iloc[0].get("upc", "")).startswith("[COLUMN HELP"):
            df = df.iloc[1:].reset_index(drop=True)
        st.caption(f"Preview ({len(df)} data rows)")
        # Pin a useful subset of columns to surface; keep the full df below.
        priority_cols = [
            "upc", "asin", "title", "cost", "recommended_sell_price",
            "estimated_profit", "roi_pct", "monthly_sales", "bsr_pct",
            "live_fba_seller_count", "viability_label", "notes",
        ]
        cols_present = [c for c in priority_cols if c in df.columns]
        st.dataframe(df[cols_present], use_container_width=True, height=320)
        with st.expander("Show all columns"):
            st.dataframe(df, use_container_width=True, height=400)
    except Exception as e:
        st.caption(f"(Preview failed: {e})")

# ---- Help footer -----------------------------------------------------------
with st.expander("ℹ️ Column meanings"):
    md = "\n".join(f"- **{c}** — {COLUMN_DESCRIPTIONS.get(c, '')}" for c in REPORT_COLUMNS)
    st.markdown(md)
