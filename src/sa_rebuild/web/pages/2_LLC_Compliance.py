"""LLC Compliance Tracker — Central Line Group LLC."""
from __future__ import annotations

import io
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ── static data ───────────────────────────────────────────────────────────────

_COMPANY = {
    "name":   "Central Line Group LLC",
    "ein":    "42-2162254",
    "nj_id":  "0451453963",
    "formed": "April 27, 2026",
}

_QUICK_REF = [
    ("NJ Sales Tax Return",      "Quarterly", "Jan 31 / Apr 30 / Jul 31 / Oct 31", "LLC",         "nj.gov/taxation"),
    ("Federal Est. Tax 1040-ES", "Quarterly", "Apr 15 / Jun 15 / Sep 15 / Jan 15", "Each member", "irs.gov/payments"),
    ("NJ Est. Tax NJ-1040-ES",   "Quarterly", "Apr 15 / Jun 15 / Sep 15 / Jan 15", "Each member", "nj.gov/taxation"),
    ("Federal Form 1065",        "Annual",    "March 15",                           "LLC",         "irs.gov"),
    ("NJ Form NJ-1065",          "Annual",    "March 15",                           "LLC",         "nj.gov/taxation"),
    ("Personal Form 1040",       "Annual",    "April 15",                           "Each member", "irs.gov"),
    ("Personal NJ-1040",         "Annual",    "April 15",                           "Each member", "nj.gov/taxation"),
    ("NJ Annual Report ($75)",   "Annual",    "April 30",                           "LLC",         "njportal.com/DOR/annualreports"),
    ("FinCEN BOI Report",        "One-time", "Filed Apr 27, 2026",                  "LLC",         "boiefiling.fincen.gov"),
    ("NJ LLC Formation",         "One-time", "Filed Apr 27, 2026",                  "LLC",         "njportal.com"),
]

_KEY_SITES = [
    ("IRS Direct Pay",     "irs.gov/payments",               "Federal est. tax & 1065"),
    ("NJ Taxation Portal", "nj.gov/taxation",                "NJ est. tax, sales tax, NJ-1065"),
    ("NJ Annual Report",   "njportal.com/DOR/annualreports", "LLC renewal -- $75/yr"),
    ("FinCEN BOI Filing",  "boiefiling.fincen.gov",          "Beneficial ownership report"),
]

_STATUS_OPTIONS   = ["Pending", "Done", "Overdue"]
_STATUS_ICON      = {"Pending": "⏳", "Done": "✅", "Overdue": "⚠️"}
_ASSIGNED_OPTIONS = ["LLC", "Kadiatu", "Emmanuel"]

_TEMPLATES: dict[str, str] = {
    "quarterly": (
        "filing_type,jurisdiction,year,quarter,due_date,assigned_to,notes\n"
        "NJ Sales Tax Return,New Jersey,2026,Q2 (May-Jun),2026-07-31,LLC,First return\n"
        "Federal Est. Tax 1040-ES,Federal,2026,Q2 (Apr-Jun),2026-06-16,Kadiatu,Pay at irs.gov/payments\n"
    ),
    "annual": (
        "filing_type,jurisdiction,year,due_date,assigned_to,notes\n"
        "Federal Form 1065,Federal,2026,2027-03-15,LLC,Partnership return + K-1s\n"
        "Personal Form 1040,Federal,2026,2027-04-15,Kadiatu,Attach K-1 from Form 1065\n"
    ),
    "one_time": (
        "filing_type,jurisdiction,due_date,assigned_to,notes,confirmation_number\n"
        "Open Business Bank Account,N/A,2026-05-01,LLC,Use EIN + Certificate of Formation,\n"
        "Amazon Seller Account Setup,N/A,2026-06-01,LLC,Configure NJ 6.625% tax settings,\n"
    ),
}

# ── helpers ───────────────────────────────────────────────────────────────────

def _firebase_ready() -> bool:
    try:
        from sa_rebuild.compliance.firebase_client import firebase_configured
        return firebase_configured()
    except Exception:
        return False


def _login_wall() -> Optional[dict]:
    ss = st.session_state
    if ss.get("compliance_user"):
        return ss["compliance_user"]

    st.markdown(
        "<h2 style='margin-bottom:0'>🔐 LLC Compliance Login</h2>"
        f"<p style='color:grey'>{_COMPANY['name']}</p>",
        unsafe_allow_html=True,
    )
    with st.form("compliance_login", clear_on_submit=False):
        email     = st.text_input("Email")
        password  = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")

    if submitted:
        if not email or not password:
            st.error("Enter your email and password.")
        else:
            try:
                from sa_rebuild.compliance.auth import sign_in
                user = sign_in(email.strip(), password)
                ss["compliance_user"] = user
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except RuntimeError as exc:
                st.error(f"Configuration error: {exc}")
    st.stop()
    return None


def _load(category: str) -> list[dict]:
    from sa_rebuild.compliance.db import get_filings
    return get_filings(category)


def _parse_date_str(val) -> Optional[date]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, date):
        return val
    from datetime import datetime
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _sicon(status: str) -> str:
    return f"{_STATUS_ICON.get(status, '•')} {status}"


def _new_ids(category: str) -> set:
    return st.session_state.get(f"new_ids_{category}", set())


def _display_df(rows: list[dict], category: str) -> pd.DataFrame:
    """Read-only DataFrame matching spreadsheet column layout."""
    new = _new_ids(category)

    def badge(doc_id: str) -> str:
        return "New" if doc_id in new else ""

    if category == "quarterly":
        cols = ["", "#", "Year", "Filing Type", "Jurisdiction", "Quarter",
                "Due Date", "Assigned To", "Status", "Date Filed", "Notes"]
        if not rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame([
            {
                "":             badge(r["id"]),
                "#":            i,
                "Year":         r.get("year", ""),
                "Filing Type":  r.get("filing_type", ""),
                "Jurisdiction": r.get("jurisdiction", ""),
                "Quarter":      r.get("quarter", "") or r.get("period", ""),
                "Due Date":     r.get("due_date"),
                "Assigned To":  r.get("assigned_to", ""),
                "Status":       _sicon(r.get("status", "Pending")),
                "Date Filed":   r.get("date_filed"),
                "Notes":        r.get("notes", ""),
            }
            for i, r in enumerate(rows, 1)
        ])

    elif category == "annual":
        cols = ["", "#", "Year", "Filing", "Jurisdiction",
                "Due Date", "Assigned To", "Status", "Date Filed", "Notes"]
        if not rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame([
            {
                "":             badge(r["id"]),
                "#":            i,
                "Year":         r.get("year", ""),
                "Filing":       r.get("filing_type", ""),
                "Jurisdiction": r.get("jurisdiction", ""),
                "Due Date":     r.get("due_date"),
                "Assigned To":  r.get("assigned_to", ""),
                "Status":       _sicon(r.get("status", "Pending")),
                "Date Filed":   r.get("date_filed"),
                "Notes":        r.get("notes", ""),
            }
            for i, r in enumerate(rows, 1)
        ])

    else:  # one_time
        cols = ["", "#", "Item", "Jurisdiction", "Due / Target",
                "Status", "Date Completed", "Confirmation #", "Notes"]
        if not rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame([
            {
                "":               badge(r["id"]),
                "#":              i,
                "Item":           r.get("filing_type", ""),
                "Jurisdiction":   r.get("jurisdiction", ""),
                "Due / Target":   r.get("due_date"),
                "Status":         _sicon(r.get("status", "Pending")),
                "Date Completed": r.get("date_filed"),
                "Confirmation #": r.get("confirmation_number", "") or "",
                "Notes":          r.get("notes", ""),
            }
            for i, r in enumerate(rows, 1)
        ])


# ── dialogs ───────────────────────────────────────────────────────────────────

@st.dialog("✏️ Edit Filing", width="large")
def _edit_modal(row: dict, user_email: str, has_confirmation: bool, category: str) -> None:
    filing_label     = "Item"           if category == "one_time" else "Filing Type"
    date_filed_label = "Date Completed" if category == "one_time" else "Date Filed"
    due_label        = "Due / Target"   if category == "one_time" else "Due Date"

    st.markdown(f"**{row['filing_type']}** — {row.get('jurisdiction', '')}")
    st.divider()

    c1, c2 = st.columns(2)
    cur_status = row.get("status", "Pending")
    new_status = c1.selectbox(
        "Status *", _STATUS_OPTIONS,
        index=_STATUS_OPTIONS.index(cur_status) if cur_status in _STATUS_OPTIONS else 0,
    )
    cur_filed = row.get("date_filed")
    new_date_filed = c2.date_input(
        date_filed_label,
        value=cur_filed if isinstance(cur_filed, date) else None,
    )

    if has_confirmation:
        new_conf = st.text_input("Confirmation #", value=row.get("confirmation_number") or "")

    new_notes = st.text_area("Notes", value=row.get("notes") or "", height=80)

    st.divider()
    st.caption("Structural details — update only if the filing itself changes")

    c3, c4 = st.columns(2)
    new_type = c3.text_input(filing_label, value=row.get("filing_type", ""))
    _JURISDICTIONS = ["Federal", "New Jersey", "N/A"]
    cur_jur = row.get("jurisdiction", "N/A")
    new_jur = c4.selectbox(
        "Jurisdiction", _JURISDICTIONS,
        index=_JURISDICTIONS.index(cur_jur) if cur_jur in _JURISDICTIONS else 2,
    )

    c5, c6 = st.columns(2)
    cur_due = row.get("due_date")
    new_due = c5.date_input(
        due_label,
        value=cur_due if isinstance(cur_due, date) else None,
    )
    cur_who = row.get("assigned_to", "LLC")
    new_who = c6.selectbox(
        "Assigned To", _ASSIGNED_OPTIONS,
        index=_ASSIGNED_OPTIONS.index(cur_who) if cur_who in _ASSIGNED_OPTIONS else 0,
    )

    new_year = None
    new_quarter = None
    if category != "one_time":
        c7, c8 = st.columns(2)
        new_year = c7.number_input(
            "Year", min_value=2024, max_value=2035,
            value=int(row.get("year") or date.today().year), step=1,
        )
        if category == "quarterly":
            new_quarter = c8.text_input(
                "Quarter", value=row.get("quarter", ""),
                placeholder="e.g. Q2 (Apr-Jun)",
            )

    st.divider()
    save, cancel = st.columns(2)
    if save.button("💾 Save", type="primary", use_container_width=True, key="edit_save"):
        from sa_rebuild.compliance.db import update_filing
        updates: dict = {
            "status":       new_status,
            "date_filed":   new_date_filed,
            "notes":        new_notes,
            "filing_type":  new_type.strip(),
            "jurisdiction": new_jur,
            "due_date":     new_due,
            "assigned_to":  new_who,
        }
        if new_year is not None:
            updates["year"] = int(new_year)
        if category == "quarterly" and new_quarter is not None:
            updates["quarter"] = new_quarter.strip() or None
            updates["period"]  = f"{new_quarter.strip()} {int(new_year)}".strip()
        if has_confirmation:
            updates["confirmation_number"] = new_conf.strip() or None
        update_filing(row["id"], updates, user_email)
        st.rerun()
    if cancel.button("Cancel", use_container_width=True, key="edit_cancel"):
        st.rerun()


@st.dialog("➕ Add Filing", width="large")
def _add_modal(category: str, user_email: str, has_confirmation: bool) -> None:
    filing_label = "Item" if category == "one_time" else "Filing Type"
    due_label    = "Due / Target" if category == "one_time" else "Due Date"

    with st.form("add_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_type = c1.text_input(f"{filing_label} *")
        new_jur  = c2.selectbox("Jurisdiction", ["Federal", "New Jersey", "N/A"])

        c3, c4 = st.columns(2)
        new_due = c3.date_input(due_label, value=None)
        new_who = c4.selectbox("Assigned To", _ASSIGNED_OPTIONS)

        new_year = None
        new_quarter = None
        if category != "one_time":
            c5, c6 = st.columns(2)
            new_year = c5.number_input("Year", min_value=2024, max_value=2035,
                                       value=date.today().year, step=1)
            if category == "quarterly":
                new_quarter = c6.text_input("Quarter", placeholder="e.g. Q2 (Apr-Jun)")

        new_notes = st.text_area("Notes", height=80)
        new_conf  = st.text_input("Confirmation #") if has_confirmation else None
        submitted = st.form_submit_button("Add", type="primary")

    if submitted:
        if not new_type.strip():
            st.error(f"{filing_label} is required.")
        else:
            from sa_rebuild.compliance.db import add_filing
            year_val    = int(new_year) if new_year else None
            quarter_val = new_quarter.strip() if new_quarter else None
            period_val  = (f"{quarter_val} {year_val}".strip()
                           if quarter_val else str(year_val or ""))
            new_id = add_filing({
                "category":            category,
                "filing_type":         new_type.strip(),
                "jurisdiction":        new_jur,
                "year":                year_val,
                "period":              period_val,
                "quarter":             quarter_val,
                "due_date":            new_due,
                "status":              "Pending",
                "date_filed":          None,
                "confirmation_number": (new_conf.strip() or None) if new_conf else None,
                "assigned_to":         new_who,
                "notes":               new_notes.strip(),
            }, user_email)
            ids = st.session_state.get(f"new_ids_{category}", set())
            ids.add(new_id)
            st.session_state[f"new_ids_{category}"] = ids
            st.rerun()


@st.dialog("🗑️ Confirm Delete")
def _delete_modal(rows: list[dict], user_email: str) -> None:
    st.warning(f"You are about to permanently delete **{len(rows)} filing(s)**.")
    st.markdown("**Rows to be deleted:**")
    for r in rows:
        st.markdown(
            f"- **{r.get('filing_type', '')}** — "
            f"{r.get('quarter', r.get('period', ''))} — "
            f"{r.get('assigned_to', '')} — due {r.get('due_date') or '—'}"
        )
    st.divider()
    confirm, cancel = st.columns(2)
    if confirm.button("Yes, delete", key="del_confirm", type="primary", use_container_width=True):
        from sa_rebuild.compliance.db import delete_filing
        failed = []
        deleted_ids = {r["id"] for r in rows}
        for r in rows:
            try:
                delete_filing(r["id"])
            except Exception as exc:
                failed.append(f"{r.get('filing_type', r['id'])}: {exc}")
        if failed:
            for msg in failed:
                st.error(f"Delete failed — {msg}")
        else:
            for cat in ("quarterly", "annual", "one_time"):
                key = f"new_ids_{cat}"
                if key in st.session_state:
                    st.session_state[key] -= deleted_ids
            st.rerun()
    if cancel.button("Cancel", key="del_cancel", use_container_width=True):
        st.rerun()


@st.dialog("🕐 Change History")
def _history_modal(row: dict) -> None:
    st.markdown(
        f"**{row['filing_type']}** — "
        f"{row.get('quarter', row.get('period', ''))} — "
        f"{row.get('assigned_to', '')}"
    )
    st.divider()
    from sa_rebuild.compliance.db import get_filing_history
    history = get_filing_history(row["id"])
    if not history:
        st.info("No history yet — status changes are logged automatically.")
    else:
        for h in reversed(history):
            ts = h.get("changed_at")
            ts_str = ts.strftime("%Y-%m-%d %H:%M") if hasattr(ts, "strftime") else str(ts)
            st.markdown(
                f"**{ts_str}** — {h.get('changed_by', '?')}  \n"
                f"`{h.get('old_status')}` → `{h.get('new_status')}`"
                + (f"  \n_{h.get('note')}_" if h.get("note") else "")
            )


# ── import ────────────────────────────────────────────────────────────────────

def _do_import(raw: bytes, category: str, user_email: str) -> None:
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        st.error(f"Could not parse CSV: {exc}")
        return

    if "filing_type" not in df.columns:
        st.error("CSV must have a `filing_type` column. Download the template for the correct format.")
        return

    from sa_rebuild.compliance.db import add_filing
    added, errors = 0, []
    new_ids: set = st.session_state.get(f"new_ids_{category}", set())

    for i, row in df.iterrows():
        try:
            year_val    = row.get("year")
            quarter_val = str(row.get("quarter", "")).strip() or None
            year_int    = int(year_val) if pd.notna(year_val) and year_val else None
            period_val  = (f"{quarter_val} {year_int}".strip()
                           if quarter_val else str(year_int or ""))
            new_id = add_filing({
                "category":            category,
                "filing_type":         str(row.get("filing_type", "")).strip(),
                "jurisdiction":        str(row.get("jurisdiction", "N/A")).strip(),
                "year":                year_int,
                "period":              period_val,
                "quarter":             quarter_val,
                "due_date":            _parse_date_str(row.get("due_date")),
                "status":              "Pending",
                "date_filed":          None,
                "confirmation_number": str(row.get("confirmation_number", "")).strip() or None,
                "assigned_to":         str(row.get("assigned_to", "LLC")).strip(),
                "notes":               str(row.get("notes", "")).strip(),
            }, user_email)
            new_ids.add(new_id)
            added += 1
        except Exception as exc:
            errors.append(f"Row {i + 1}: {exc}")

    st.session_state[f"new_ids_{category}"] = new_ids
    if added:
        st.success(f"Imported {added} filing(s). New rows are marked 'New' in the first column.")
    for e in errors:
        st.error(e)
    if added:
        st.rerun()


# ── filters ───────────────────────────────────────────────────────────────────

def _fk(category: str, field: str) -> str:
    return f"flt_{category}_{field}"


def _render_filters(category: str, rows: list[dict]) -> list[dict]:
    years     = sorted({r["year"] for r in rows if r.get("year")}, reverse=True)
    assignees = sorted({r["assigned_to"] for r in rows if r.get("assigned_to")})

    has_quarter = (category == "quarterly")
    n_cols = 4 if has_quarter else 3
    cols = st.columns(n_cols + 1)  # +1 for Clear button

    sel_year = cols[0].selectbox(
        "Year", ["All"] + [str(y) for y in years], key=_fk(category, "year"),
    )
    sel_who = cols[1].selectbox(
        "Assigned To", ["All"] + assignees, key=_fk(category, "who"),
    )
    sel_status = cols[2].selectbox(
        "Status", ["All"] + _STATUS_OPTIONS, key=_fk(category, "status"),
    )

    sel_quarter = None
    if has_quarter:
        quarters = sorted({r.get("quarter", "") for r in rows if r.get("quarter")})
        sel_quarter = cols[3].selectbox(
            "Quarter", ["All"] + quarters, key=_fk(category, "quarter"),
        )

    if cols[-1].button("✖ Clear", key=f"btn_clear_{category}", use_container_width=True):
        for field in ("year", "who", "status", "quarter"):
            k = _fk(category, field)
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

    return [
        r for r in rows
        if (sel_year == "All"    or str(r.get("year")) == sel_year)
        and (sel_who == "All"    or r.get("assigned_to") == sel_who)
        and (sel_status == "All" or r.get("status") == sel_status)
        and (sel_quarter is None or sel_quarter == "All"
             or r.get("quarter") == sel_quarter)
    ]


# ── tab renderer ──────────────────────────────────────────────────────────────

def _render_filing_tab(
    category: str,
    user_email: str,
    has_confirmation: bool = False,
) -> None:
    from sa_rebuild.compliance.db import ensure_order, swap_order

    rows = _load(category)
    ensure_order(rows)          # one-time lazy migration, no-op once done
    filtered = _render_filters(category, rows)

    if filtered:
        st.caption(
            f"{len(filtered)} of {len(rows)} rows  "
            "— click a column header to sort, select rows to edit or delete"
        )
    else:
        st.info("No filings match the current filters. Click **✖ Clear** to reset.")

    display_df = _display_df(filtered, category)

    event = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
        key=f"tbl_{category}",
    )

    selected_indices = event.selection.rows if hasattr(event, "selection") else []
    selected_rows    = [filtered[i] for i in selected_indices if i < len(filtered)]
    n_sel            = len(selected_rows)

    # Action bar
    st.divider()
    b1, b2, b3, b4, b5, b6 = st.columns(6)

    if b1.button("✏️ Edit", key=f"btn_edit_{category}",
                 disabled=n_sel != 1, use_container_width=True,
                 help="Select exactly one row to edit"):
        _edit_modal(selected_rows[0], user_email, has_confirmation, category)

    if b2.button(f"🗑️ Delete{f' ({n_sel})' if n_sel else ''}",
                 key=f"btn_del_{category}",
                 disabled=n_sel == 0, use_container_width=True,
                 help="Select one or more rows to delete"):
        _delete_modal(selected_rows, user_email)

    if b3.button("➕ Add", key=f"btn_add_{category}", use_container_width=True):
        _add_modal(category, user_email, has_confirmation)

    if b4.button("🕐 History", key=f"btn_hist_{category}",
                 disabled=n_sel != 1, use_container_width=True,
                 help="Select one row to view change history"):
        if n_sel == 1:
            _history_modal(selected_rows[0])

    sel_idx = selected_indices[0] if n_sel == 1 else None
    can_up  = (sel_idx is not None and sel_idx > 0)
    can_dn  = (sel_idx is not None and sel_idx < len(filtered) - 1)

    if b5.button("↑ Move up", key=f"btn_up_{category}",
                 disabled=not can_up, use_container_width=True,
                 help="Move selected row up (saves order to database)"):
        swap_order(filtered[sel_idx], filtered[sel_idx - 1])
        st.rerun()

    if b6.button("↓ Move down", key=f"btn_dn_{category}",
                 disabled=not can_dn, use_container_width=True,
                 help="Move selected row down (saves order to database)"):
        swap_order(filtered[sel_idx], filtered[sel_idx + 1])
        st.rerun()

    # Import / export
    st.divider()
    imp1, imp2 = st.columns(2)

    imp1.download_button(
        "📥 Download CSV template",
        key=f"btn_tmpl_{category}",
        data=_TEMPLATES[category],
        file_name=f"{category}_template.csv",
        mime="text/csv",
        use_container_width=True,
    )

    show_key = f"show_import_{category}"
    st.session_state.setdefault(show_key, False)
    if imp2.button("📤 Import from CSV", key=f"btn_imp_{category}", use_container_width=True):
        st.session_state[show_key] = not st.session_state[show_key]

    if st.session_state[show_key]:
        st.markdown("Upload a filled CSV (download the template above for correct columns):")
        uploaded = st.file_uploader(
            "CSV file", type=["csv"], key=f"upload_{category}",
            label_visibility="collapsed",
        )
        if uploaded:
            raw = uploaded.getvalue()
            try:
                preview_df = pd.read_csv(io.BytesIO(raw))
            except Exception as exc:
                st.error(f"Could not parse CSV: {exc}")
                preview_df = None

            if preview_df is not None:
                if "filing_type" not in preview_df.columns:
                    st.error("CSV must have a `filing_type` column.")
                else:
                    st.markdown(f"**Preview — {len(preview_df)} row(s):**")
                    st.dataframe(preview_df, hide_index=True, use_container_width=True)
                    if st.button(
                        f"✅ Import {len(preview_df)} row(s)",
                        key=f"btn_confirm_import_{category}",
                        type="primary",
                    ):
                        _do_import(raw, category, user_email)
                        st.session_state[show_key] = False


# ── dashboard ─────────────────────────────────────────────────────────────────

def _render_dashboard() -> None:
    q_rows  = _load("quarterly")
    a_rows  = _load("annual")
    ot_rows = _load("one_time")
    all_rows = q_rows + a_rows + ot_rows

    def _counts(rows):
        done = sum(1 for r in rows if r.get("status") == "Done")
        return done, len(rows)

    q_done,  q_tot  = _counts(q_rows)
    a_done,  a_tot  = _counts(a_rows)
    ot_done, ot_tot = _counts(ot_rows)

    c1, c2, c3 = st.columns(3)
    c1.metric("Quarterly",  f"{q_done} / {q_tot} done",   delta=f"{q_tot  - q_done} pending")
    c2.metric("Annual",     f"{a_done} / {a_tot} done",   delta=f"{a_tot  - a_done} pending")
    c3.metric("One-Time",   f"{ot_done} / {ot_tot} done", delta=f"{ot_tot - ot_done} pending")

    st.divider()
    today    = date.today()
    overdue  = [r for r in all_rows
                if r.get("status") != "Done" and r.get("due_date") and r["due_date"] < today]
    upcoming = sorted(
        [r for r in all_rows
         if r.get("status") != "Done" and r.get("due_date") and r["due_date"] >= today],
        key=lambda r: r["due_date"],
    )[:5]

    left, right = st.columns(2)
    with left:
        st.subheader(f"Overdue ({len(overdue)})")
        if not overdue:
            st.success("Nothing overdue.")
        else:
            for r in sorted(overdue, key=lambda x: x.get("due_date") or date.max):
                period = r.get("quarter") or r.get("period", "")
                st.markdown(
                    f"**{r['filing_type']}** — {r.get('assigned_to','LLC')}  \n"
                    f"Due: `{r.get('due_date')}`  |  {period}",
                )

    with right:
        st.subheader("Coming up next")
        if not upcoming:
            st.info("No upcoming filings found.")
        else:
            for r in upcoming:
                days_left = (r["due_date"] - today).days
                label  = f"{days_left}d" if days_left > 0 else "today"
                period = r.get("quarter") or r.get("period", "")
                st.markdown(
                    f"**{r['filing_type']}** — {r.get('assigned_to','LLC')}  \n"
                    f"Due: `{r.get('due_date')}` ({label})  |  {period}",
                )

    st.divider()
    st.subheader("Filing Quick Reference")
    ref_df = pd.DataFrame(
        _QUICK_REF,
        columns=["Filing", "Frequency", "Due Date Pattern", "Who Files", "Where"],
    )
    st.dataframe(ref_df, hide_index=True, use_container_width=True)

    st.subheader("Key Websites")
    for name, url, note in _KEY_SITES:
        st.markdown(f"- **{name}** — `{url}` — {note}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not _firebase_ready():
        st.warning(
            "**Firebase not configured.**  \n"
            "Follow the setup steps in `compliance_tool_plan.md` to connect the database.  \n"
            "You need `FIREBASE_WEB_API_KEY`, `FIREBASE_PROJECT_ID`, and a "
            "`service_account.json` file (or `FIREBASE_SERVICE_ACCOUNT_JSON` secret)."
        )
        with st.expander("Setup checklist"):
            st.markdown(
                "1. Create a Firebase project at console.firebase.google.com\n"
                "2. Enable Firestore Database (us-east1)\n"
                "3. Enable Authentication → Email/Password\n"
                "4. Create user accounts (Kadiatu & Emmanuel)\n"
                "5. Generate service account key → save as `service_account.json`\n"
                "6. Get Web API Key → add to `.env` as `FIREBASE_WEB_API_KEY`\n"
                "7. Run `python scripts/seed_compliance.py path/to/tracker.xlsx`\n\n"
                "Full instructions: `compliance_tool_plan.md`"
            )
        st.stop()
        return

    user = _login_wall()
    if not user:
        return

    with st.sidebar:
        st.markdown(f"**Logged in as**  \n{user['email']}")
        if st.button("Sign out", key="compliance_signout"):
            del st.session_state["compliance_user"]
            st.rerun()
        st.divider()

    st.title("📋 LLC Compliance Tracker")
    st.caption(
        f"{_COMPANY['name']}  |  EIN: {_COMPANY['ein']}  |  "
        f"NJ ID: {_COMPANY['nj_id']}  |  Formed: {_COMPANY['formed']}"
    )

    tab_dash, tab_q, tab_a, tab_ot = st.tabs(
        ["📊 Dashboard", "🗓️ Quarterly", "📆 Annual", "✅ One-Time"]
    )

    with tab_dash:
        _render_dashboard()

    with tab_q:
        st.subheader("Quarterly Filings")
        _render_filing_tab("quarterly", user["email"])

    with tab_a:
        st.subheader("Annual Filings")
        _render_filing_tab("annual", user["email"])

    with tab_ot:
        st.subheader("One-Time & Setup Items")
        _render_filing_tab("one_time", user["email"], has_confirmation=True)


main()
