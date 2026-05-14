"""LLC Compliance Tracker — Central Line Group LLC."""
from __future__ import annotations

import io
from datetime import date
from typing import Optional

import pandas as pd
import streamlit as st

# ── static data ───────────────────────────────────────────────────────────────

_COMPANY = {
    "name": "Central Line Group LLC",
}

_FREQUENCY_OPTIONS = ["Quarterly", "Annual", "One-time", "Monthly", "Other"]

_STATUS_OPTIONS = ["Pending", "Done", "Overdue"]
_STATUS_ICON    = {"Pending": "⏳", "Done": "✅", "Overdue": "⚠️"}


def _assigned_str(value) -> str:
    """Render assigned_to (list[str] | legacy str | None) as a comma-joined string."""
    if not value:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return str(value)


def _assigned_list(value) -> list[str]:
    """Normalize assigned_to to a clean list[str]."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    s = str(value).strip()
    return [s] if s else []

_TEMPLATES: dict[str, str] = {
    "quarterly": (
        "filing_type,jurisdiction,year,quarter,due_date,assigned_to,notes\n"
        "NJ Sales Tax Return,New Jersey,2026,Q2 (May-Jun),2026-07-31,LLC,First return\n"
        "Federal Est. Tax 1040-ES,Federal,2026,Q2 (Apr-Jun),2026-06-16,LLC,Pay at irs.gov/payments\n"
    ),
    "annual": (
        "filing_type,jurisdiction,year,due_date,assigned_to,notes\n"
        "Federal Form 1065,Federal,2026,2027-03-15,LLC,Partnership return + K-1s\n"
        "Personal Form 1040,Federal,2026,2027-04-15,LLC,Attach K-1 from Form 1065\n"
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
    from sa_rebuild.auth import login_wall
    return login_wall("compliance_user", "LLC Compliance")


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
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
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
                "#":            r.get("order", i),
                "Year":         r.get("year", ""),
                "Filing Type":  r.get("filing_type", ""),
                "Jurisdiction": r.get("jurisdiction", ""),
                "Quarter":      r.get("quarter", "") or r.get("period", ""),
                "Due Date":     r.get("due_date"),
                "Assigned To":  _assigned_str(r.get("assigned_to")),
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
                "#":            r.get("order", i),
                "Year":         r.get("year", ""),
                "Filing":       r.get("filing_type", ""),
                "Jurisdiction": r.get("jurisdiction", ""),
                "Due Date":     r.get("due_date"),
                "Assigned To":  _assigned_str(r.get("assigned_to")),
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
                "#":              r.get("order", i),
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

@st.dialog("✏️ Edit Filing")
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
    from sa_rebuild.compliance.db import get_members
    assigned_opts = get_members()
    cur_who_list = _assigned_list(row.get("assigned_to"))
    default_who = [n for n in cur_who_list if n in assigned_opts] or ["LLC"]
    new_who = c6.multiselect(
        "Assigned To", assigned_opts,
        default=default_who,
        help="Select one or more members. Use for joint filings.",
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
        from sa_rebuild.compliance.db import update_filing
        update_filing(row["id"], updates, user_email)
        st.rerun()
    if cancel.button("Cancel", use_container_width=True, key="edit_cancel"):
        st.rerun()


@st.dialog("➕ Add Filing")
def _add_modal(category: str, user_email: str, has_confirmation: bool) -> None:
    filing_label = "Item" if category == "one_time" else "Filing Type"
    due_label    = "Due / Target" if category == "one_time" else "Due Date"

    with st.form("add_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_type = c1.text_input(f"{filing_label} *")
        new_jur  = c2.selectbox("Jurisdiction", ["Federal", "New Jersey", "N/A"])

        c3, c4 = st.columns(2)
        new_due = c3.date_input(due_label, value=None)
        from sa_rebuild.compliance.db import get_members
        new_who = c4.multiselect(
            "Assigned To", get_members(), default=["LLC"],
            help="Select one or more members. Use for joint filings.",
        )

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
            year_val    = int(new_year) if new_year else None
            quarter_val = new_quarter.strip() if new_quarter else None
            period_val  = (f"{quarter_val} {year_val}".strip()
                           if quarter_val else str(year_val or ""))
            from sa_rebuild.compliance.db import add_filing
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
            f"{_assigned_str(r.get('assigned_to'))} — due {r.get('due_date') or '—'}"
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
        f"{_assigned_str(row.get('assigned_to'))}"
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


# ── Quick Reference dialogs ──────────────────────────────────────────────────

@st.dialog("➕ Add Quick Reference Row")
def _add_qref_modal(user_email: str) -> None:
    with st.form("add_qref_form", clear_on_submit=True):
        new_filing = st.text_input("Filing *")
        c1, c2 = st.columns(2)
        new_freq  = c1.selectbox("Frequency", _FREQUENCY_OPTIONS)
        new_who   = c2.text_input("Who Files", placeholder="LLC / Members (joint) / ...")
        new_due   = st.text_input("Due Date Pattern", placeholder="e.g. Jul 20 / Oct 20 / Jan 20 / Apr 20")
        new_where = st.text_input("Where to File", placeholder="e.g. taxportal.nj.gov")
        submitted = st.form_submit_button("Add", type="primary")
    if submitted:
        if not new_filing.strip():
            st.error("Filing is required.")
        else:
            from sa_rebuild.compliance.db import add_quick_reference
            add_quick_reference({
                "filing":           new_filing.strip(),
                "frequency":        new_freq,
                "due_date_pattern": new_due.strip(),
                "who_files":        new_who.strip(),
                "where_to_file":    new_where.strip(),
            }, user_email)
            st.rerun()


@st.dialog("✏️ Edit Quick Reference Row")
def _edit_qref_modal(row: dict, user_email: str) -> None:
    st.markdown(f"**{row.get('filing', '')}**")
    st.divider()
    new_filing = st.text_input("Filing", value=row.get("filing", ""))
    c1, c2 = st.columns(2)
    cur_freq = row.get("frequency", "Quarterly")
    new_freq = c1.selectbox(
        "Frequency", _FREQUENCY_OPTIONS,
        index=_FREQUENCY_OPTIONS.index(cur_freq) if cur_freq in _FREQUENCY_OPTIONS else 0,
    )
    new_who   = c2.text_input("Who Files", value=row.get("who_files", ""))
    new_due   = st.text_input("Due Date Pattern", value=row.get("due_date_pattern", ""))
    new_where = st.text_input("Where to File", value=row.get("where_to_file", ""))
    st.divider()
    save, cancel = st.columns(2)
    if save.button("💾 Save", type="primary", use_container_width=True, key="qref_save"):
        if not new_filing.strip():
            st.error("Filing is required.")
        else:
            from sa_rebuild.compliance.db import update_quick_reference
            update_quick_reference(row["id"], {
                "filing":           new_filing.strip(),
                "frequency":        new_freq,
                "due_date_pattern": new_due.strip(),
                "who_files":        new_who.strip(),
                "where_to_file":    new_where.strip(),
            }, user_email)
            st.rerun()
    if cancel.button("Cancel", use_container_width=True, key="qref_cancel"):
        st.rerun()


@st.dialog("🗑️ Confirm Delete Quick Reference")
def _delete_qref_modal(rows: list[dict]) -> None:
    st.warning(f"Permanently delete **{len(rows)} row(s)**?")
    for r in rows:
        st.markdown(f"- **{r.get('filing','')}** — {r.get('frequency','')} — {r.get('due_date_pattern','')}")
    st.divider()
    confirm, cancel = st.columns(2)
    if confirm.button("Yes, delete", type="primary", use_container_width=True, key="qref_del_confirm"):
        from sa_rebuild.compliance.db import delete_quick_reference
        for r in rows:
            delete_quick_reference(r["id"])
        st.rerun()
    if cancel.button("Cancel", use_container_width=True, key="qref_del_cancel"):
        st.rerun()


# ── Key Websites dialogs ─────────────────────────────────────────────────────

@st.dialog("➕ Add Key Website")
def _add_site_modal(user_email: str) -> None:
    with st.form("add_site_form", clear_on_submit=True):
        new_name = st.text_input("Name *")
        new_url  = st.text_input("URL *", placeholder="e.g. irs.gov/payments")
        new_note = st.text_input("Note",  placeholder="What it's used for")
        submitted = st.form_submit_button("Add", type="primary")
    if submitted:
        if not new_name.strip() or not new_url.strip():
            st.error("Name and URL are required.")
        else:
            from sa_rebuild.compliance.db import add_key_website
            add_key_website({
                "name": new_name.strip(),
                "url":  new_url.strip(),
                "note": new_note.strip(),
            }, user_email)
            st.rerun()


@st.dialog("✏️ Edit Key Website")
def _edit_site_modal(row: dict, user_email: str) -> None:
    st.markdown(f"**{row.get('name', '')}**")
    st.divider()
    new_name = st.text_input("Name", value=row.get("name", ""))
    new_url  = st.text_input("URL",  value=row.get("url", ""))
    new_note = st.text_input("Note", value=row.get("note", ""))
    st.divider()
    save, cancel = st.columns(2)
    if save.button("💾 Save", type="primary", use_container_width=True, key="site_save"):
        if not new_name.strip() or not new_url.strip():
            st.error("Name and URL are required.")
        else:
            from sa_rebuild.compliance.db import update_key_website
            update_key_website(row["id"], {
                "name": new_name.strip(),
                "url":  new_url.strip(),
                "note": new_note.strip(),
            }, user_email)
            st.rerun()
    if cancel.button("Cancel", use_container_width=True, key="site_cancel"):
        st.rerun()


@st.dialog("🗑️ Confirm Delete Website")
def _delete_site_modal(rows: list[dict]) -> None:
    st.warning(f"Permanently delete **{len(rows)} website(s)**?")
    for r in rows:
        st.markdown(f"- **{r.get('name','')}** — `{r.get('url','')}`")
    st.divider()
    confirm, cancel = st.columns(2)
    if confirm.button("Yes, delete", type="primary", use_container_width=True, key="site_del_confirm"):
        from sa_rebuild.compliance.db import delete_key_website
        for r in rows:
            delete_key_website(r["id"])
        st.rerun()
    if cancel.button("Cancel", use_container_width=True, key="site_del_cancel"):
        st.rerun()


# ── editable section renderers (Dashboard) ───────────────────────────────────

def _render_quick_reference_section(user_email: str) -> None:
    from sa_rebuild.compliance.db import (
        get_quick_reference, ensure_order_quick_reference, move_quick_reference_rows,
    )
    rows = get_quick_reference()
    ensure_order_quick_reference(rows)

    tbl_state = st.session_state.get("tbl_qref", {})
    prev_sel = tbl_state.get("selection", {}).get("rows", []) if isinstance(tbl_state, dict) else []
    sel_idx  = sorted(i for i in prev_sel if i < len(rows))
    sel_rows = [rows[i] for i in sel_idx]
    n_sel    = len(sel_rows)
    can_up   = bool(sel_idx and sel_idx[0] > 0)
    can_dn   = bool(sel_idx and sel_idx[-1] < len(rows) - 1)

    b1, b2, b3, b4, b5 = st.columns(5)
    if b1.button("Edit", key="btn_edit_qref", disabled=n_sel != 1, use_container_width=True):
        _edit_qref_modal(sel_rows[0], user_email)
    if b2.button(f"Delete{f' ({n_sel})' if n_sel else ''}",
                 key="btn_del_qref", disabled=n_sel == 0, use_container_width=True):
        _delete_qref_modal(sel_rows)
    if b3.button("+ Add", key="btn_add_qref", use_container_width=True):
        _add_qref_modal(user_email)
    if b4.button("↑ Up", key="btn_up_qref", disabled=not can_up, use_container_width=True):
        group = [rows[i] for i in sel_idx]
        upper = rows[sel_idx[0] - 1]
        move_quick_reference_rows([upper] + group, group + [upper])
        st.session_state["tbl_qref"] = {"selection": {"rows": [i - 1 for i in sel_idx], "columns": []}}
        st.rerun()
    if b5.button("↓ Down", key="btn_dn_qref", disabled=not can_dn, use_container_width=True):
        group = [rows[i] for i in sel_idx]
        lower = rows[sel_idx[-1] + 1]
        move_quick_reference_rows(group + [lower], [lower] + group)
        st.session_state["tbl_qref"] = {"selection": {"rows": [i + 1 for i in sel_idx], "columns": []}}
        st.rerun()

    df = pd.DataFrame([
        {
            "#":                  r.get("order", i),
            "Filing":             r.get("filing", ""),
            "Frequency":          r.get("frequency", ""),
            "Due Date Pattern":   r.get("due_date_pattern", ""),
            "Who Files":          r.get("who_files", ""),
            "Where":              r.get("where_to_file", ""),
        }
        for i, r in enumerate(rows, 1)
    ])
    st.dataframe(
        df, use_container_width=True, hide_index=True,
        selection_mode="multi-row", on_select="rerun", key="tbl_qref",
    )


def _render_key_websites_section(user_email: str) -> None:
    from sa_rebuild.compliance.db import (
        get_key_websites, ensure_order_key_websites, move_key_website_rows,
    )
    rows = get_key_websites()
    ensure_order_key_websites(rows)

    tbl_state = st.session_state.get("tbl_sites", {})
    prev_sel = tbl_state.get("selection", {}).get("rows", []) if isinstance(tbl_state, dict) else []
    sel_idx  = sorted(i for i in prev_sel if i < len(rows))
    sel_rows = [rows[i] for i in sel_idx]
    n_sel    = len(sel_rows)
    can_up   = bool(sel_idx and sel_idx[0] > 0)
    can_dn   = bool(sel_idx and sel_idx[-1] < len(rows) - 1)

    b1, b2, b3, b4, b5 = st.columns(5)
    if b1.button("Edit", key="btn_edit_site", disabled=n_sel != 1, use_container_width=True):
        _edit_site_modal(sel_rows[0], user_email)
    if b2.button(f"Delete{f' ({n_sel})' if n_sel else ''}",
                 key="btn_del_site", disabled=n_sel == 0, use_container_width=True):
        _delete_site_modal(sel_rows)
    if b3.button("+ Add", key="btn_add_site", use_container_width=True):
        _add_site_modal(user_email)
    if b4.button("↑ Up", key="btn_up_site", disabled=not can_up, use_container_width=True):
        group = [rows[i] for i in sel_idx]
        upper = rows[sel_idx[0] - 1]
        move_key_website_rows([upper] + group, group + [upper])
        st.session_state["tbl_sites"] = {"selection": {"rows": [i - 1 for i in sel_idx], "columns": []}}
        st.rerun()
    if b5.button("↓ Down", key="btn_dn_site", disabled=not can_dn, use_container_width=True):
        group = [rows[i] for i in sel_idx]
        lower = rows[sel_idx[-1] + 1]
        move_key_website_rows(group + [lower], [lower] + group)
        st.session_state["tbl_sites"] = {"selection": {"rows": [i + 1 for i in sel_idx], "columns": []}}
        st.rerun()

    df = pd.DataFrame([
        {
            "#":    r.get("order", i),
            "Name": r.get("name", ""),
            "URL":  r.get("url", ""),
            "Note": r.get("note", ""),
        }
        for i, r in enumerate(rows, 1)
    ])
    st.dataframe(
        df, use_container_width=True, hide_index=True,
        selection_mode="multi-row", on_select="rerun", key="tbl_sites",
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
                "assigned_to":         [n.strip() for n in str(row.get("assigned_to", "LLC")).split(",") if n.strip()] or ["LLC"],
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


def _matches(value, selected: list) -> bool:
    """Empty list = no filter (show all). Non-empty = value must be in list."""
    return not selected or value in selected


def _render_filters(category: str, rows: list[dict]) -> list[dict]:
    years     = sorted({str(r["year"]) for r in rows if r.get("year")}, reverse=True)
    assignees: set[str] = set()
    for r in rows:
        assignees.update(_assigned_list(r.get("assigned_to")))
    assignees = sorted(assignees)
    has_quarter = (category == "quarterly")

    # Header row: label on left, clear button on right
    lbl, _, clr = st.columns([3, 4, 2])
    lbl.markdown("**Filters**")
    if clr.button("✖ Clear filters", key=f"btn_clear_{category}", use_container_width=True,
                  help="Reset all filters to defaults"):
        for field in ("status", "year", "who", "quarter"):
            k = _fk(category, field)
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

    # Multiselect row — full width now that Clear is on its own row
    n_cols = 4 if has_quarter else 3
    cols = st.columns(n_cols)

    # Status defaults to Pending + Overdue so Done rows are hidden unless requested
    sel_status = cols[0].multiselect(
        "Status", _STATUS_OPTIONS,
        default=["Pending", "Overdue"],
        key=_fk(category, "status"),
    )
    sel_years = cols[1].multiselect(
        "Year", years, default=[],
        placeholder="All years",
        key=_fk(category, "year"),
    )
    sel_who = cols[2].multiselect(
        "Assigned To", assignees, default=[],
        placeholder="Everyone",
        key=_fk(category, "who"),
    )
    sel_quarter: list = []
    if has_quarter:
        quarters = sorted({r.get("quarter", "") for r in rows if r.get("quarter")})
        sel_quarter = cols[3].multiselect(
            "Quarter", quarters, default=[],
            placeholder="All quarters",
            key=_fk(category, "quarter"),
        )

    def _who_match(row_value, selected: list) -> bool:
        if not selected:
            return True
        return any(n in selected for n in _assigned_list(row_value))

    return [
        r for r in rows
        if _matches(r.get("status"), sel_status)
        and _matches(str(r.get("year", "")), sel_years)
        and _who_match(r.get("assigned_to"), sel_who)
        and _matches(r.get("quarter"), sel_quarter)
    ]


# ── tab renderer ──────────────────────────────────────────────────────────────

def _render_filing_tab(
    category: str,
    user_email: str,
    has_confirmation: bool = False,
) -> None:

    from sa_rebuild.compliance.db import ensure_order, move_rows
    rows = _load(category)
    ensure_order(rows)

    # ── Import / export (top) ─────────────────────────────────────────────────
    show_key = f"show_import_{category}"
    st.session_state.setdefault(show_key, False)

    imp1, imp2 = st.columns(2)
    imp1.download_button(
        "📥 Download CSV template",
        key=f"btn_tmpl_{category}",
        data=_TEMPLATES[category],
        file_name=f"{category}_template.csv",
        mime="text/csv",
        use_container_width=True,
    )
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
                        st.session_state[show_key] = False
                        _do_import(raw, category, user_email)

    st.divider()

    # ── Filters ───────────────────────────────────────────────────────────────
    filtered = _render_filters(category, rows)

    # ── Selection from previous render (session state) ────────────────────────
    tbl_state = st.session_state.get(f"tbl_{category}", {})
    prev_sel = (
        tbl_state.get("selection", {}).get("rows", [])
        if isinstance(tbl_state, dict) else []
    )
    selected_indices = sorted(i for i in prev_sel if i < len(filtered))
    selected_rows    = [filtered[i] for i in selected_indices]
    n_sel            = len(selected_rows)
    can_up = bool(selected_indices and selected_indices[0] > 0)
    can_dn = bool(selected_indices and selected_indices[-1] < len(filtered) - 1)

    # ── Action bar (above table) ──────────────────────────────────────────────
    b1, b2, b3, b4, b5, b6 = st.columns(6)

    if b1.button("Edit", key=f"btn_edit_{category}",
                 disabled=n_sel != 1, use_container_width=True,
                 help="Select exactly one row to edit"):
        _edit_modal(selected_rows[0], user_email, has_confirmation, category)

    if b2.button(f"Delete{f' ({n_sel})' if n_sel else ''}",
                 key=f"btn_del_{category}",
                 disabled=n_sel == 0, use_container_width=True,
                 help="Select one or more rows to delete"):
        _delete_modal(selected_rows, user_email)

    if b3.button("+ Add", key=f"btn_add_{category}", use_container_width=True):
        _add_modal(category, user_email, has_confirmation)

    if b4.button("History", key=f"btn_hist_{category}",
                 disabled=n_sel != 1, use_container_width=True,
                 help="Select one row to view change history"):
        _history_modal(selected_rows[0])

    if b5.button("↑ Up", key=f"btn_up_{category}",
                 disabled=not can_up, use_container_width=True,
                 help="Move selected row(s) up — saves to database"):
        group = [filtered[i] for i in selected_indices]
        upper = filtered[selected_indices[0] - 1]
        move_rows([upper] + group, group + [upper])
        # Shift selection indices up by 1 so the check follows the moved row
        st.session_state[f"tbl_{category}"] = {
            "selection": {"rows": [i - 1 for i in selected_indices], "columns": []}
        }
        st.rerun()

    if b6.button("↓ Down", key=f"btn_dn_{category}",
                 disabled=not can_dn, use_container_width=True,
                 help="Move selected row(s) down — saves to database"):
        group = [filtered[i] for i in selected_indices]
        lower = filtered[selected_indices[-1] + 1]
        move_rows(group + [lower], [lower] + group)
        # Shift selection indices down by 1 so the check follows the moved row
        st.session_state[f"tbl_{category}"] = {
            "selection": {"rows": [i + 1 for i in selected_indices], "columns": []}
        }
        st.rerun()

    # ── Table ─────────────────────────────────────────────────────────────────
    if filtered:
        st.caption(
            f"{len(filtered)} of {len(rows)} rows  "
            "— click a column header to sort, select rows to edit"
        )
    else:
        st.info("No filings match the current filters. Click **✖ Clear** to reset.")

    display_df = _display_df(filtered, category)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
        key=f"tbl_{category}",
    )


# ── dashboard ─────────────────────────────────────────────────────────────────

def _render_dashboard(user_email: str = "") -> None:
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
                who = _assigned_str(r.get("assigned_to")) or "LLC"
                st.markdown(
                    f"**{r['filing_type']}** — {who}  \n"
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
                who = _assigned_str(r.get("assigned_to")) or "LLC"
                st.markdown(
                    f"**{r['filing_type']}** — {who}  \n"
                    f"Due: `{r.get('due_date')}` ({label})  |  {period}",
                )

    st.divider()
    st.subheader("Filing Quick Reference")
    st.caption("Editable — add / edit / delete / reorder rows. Persists to Firestore.")
    _render_quick_reference_section(user_email)

    st.divider()
    st.subheader("Key Websites")
    st.caption("Editable — add / edit / delete / reorder rows. Persists to Firestore.")
    _render_key_websites_section(user_email)


# ── settings ─────────────────────────────────────────────────────────────────

@st.dialog("Remove Member")
def _remove_member_modal(member: dict) -> None:
    from sa_rebuild.compliance.db import (
        count_filings_by_assignee, reassign_filings,
        add_member, delete_member, get_members_with_ids,
    )
    name = member["name"]
    filing_count = count_filings_by_assignee(name)

    if filing_count:
        st.warning(
            f"**{name}** is assigned to **{filing_count} filing(s)**. "
            "Choose who to reassign them to before removing."
        )
        other_names = [m["name"] for m in get_members_with_ids() if m["id"] != member["id"]]
        existing_options = ["LLC"] + other_names
        mode = st.radio("Reassign to", ["Existing member", "New name"], horizontal=True)
        if mode == "Existing member":
            reassign_to = st.selectbox("Member", existing_options)
            new_member_name = None
        else:
            reassign_to = None
            new_member_name = st.text_input("New member name", placeholder="Full name or display name")
    else:
        st.info(f"No filings are currently assigned to **{name}**.")
        reassign_to = None
        new_member_name = None

    st.divider()
    c_confirm, c_cancel = st.columns(2)
    if c_confirm.button("Remove", type="primary", use_container_width=True):
        if filing_count:
            target = (new_member_name or "").strip() if new_member_name is not None else reassign_to
            if not target:
                st.error("Enter a name to reassign to.")
                return
            if new_member_name is not None and new_member_name.strip():
                add_member(new_member_name.strip())
            reassign_filings(name, target)
        delete_member(member["id"])
        st.rerun()
    if c_cancel.button("Cancel", use_container_width=True):
        st.rerun()


def _render_settings_tab() -> None:
    from sa_rebuild.compliance.db import (
        get_company_info, save_company_info,
        get_members_with_ids, add_member,
        sync_members_from_filings,
    )

    st.subheader("Company Info")
    co = get_company_info()
    with st.form("form_company_info"):
        new_name = st.text_input(
            "Company name",
            value=co.get("name") or _COMPANY["name"],
        )
        new_formed = st.text_input(
            "Formation date",
            value=co.get("formed", ""),
            placeholder="e.g. April 27, 2026",
        )
        if st.form_submit_button("Save", type="primary"):
            save_company_info({"name": new_name.strip(), "formed": new_formed.strip()})
            st.success("Saved.")
            st.rerun()

    st.divider()
    st.subheader("Members")
    st.caption("These names appear in the 'Assigned To' dropdown throughout the app.")

    members = get_members_with_ids()
    if members:
        for m in members:
            col_name, col_del = st.columns([6, 1])
            col_name.write(m["name"])
            if col_del.button("Remove", key=f"del_member_{m['id']}", help=f"Remove {m['name']}"):
                _remove_member_modal(m)
    else:
        st.info("No members yet — add one below or click 'Sync from filings'.")

    c_add, c_sync = st.columns(2)

    with c_add:
        with st.form("form_add_member", clear_on_submit=True):
            new_member = st.text_input("Add member", placeholder="Full name or display name")
            if st.form_submit_button("Add", type="primary"):
                if new_member.strip():
                    add_member(new_member.strip())
                    st.rerun()
                else:
                    st.error("Name cannot be empty.")

    with c_sync:
        st.markdown("**Sync from existing filings**")
        st.caption("Reads every 'Assigned To' in the database and adds any missing names.")
        if st.button("Sync now", key="btn_sync_members"):
            added = sync_members_from_filings()
            if added:
                st.success(f"Added {added} new member(s).")
                st.rerun()
            else:
                st.info("All assignees are already in the members list.")


# ── main ──────────────────────────────────────────────────────────────────────

_CSS = """
<style>
/* ── full-width layout ── */
.main .block-container,
div[data-testid="stMainBlockContainer"] {
    max-width: 100% !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}

/* ── buttons: use bare `button` so !important beats all emotion class selectors ── */
button {
    font-size: 0.68rem !important;
    height: 2rem !important;
    min-height: 2rem !important;
    max-height: 2rem !important;
    padding: 0 0.5rem !important;
    line-height: 1 !important;
    box-sizing: border-box !important;
}
/* Also target every child node (p/span/div) that emotion may wrap text in */
button * {
    font-size: 0.68rem !important;
    line-height: 1 !important;
    margin: 0 !important;
}

/* ── multiselect labels, tags, dropdown ── */
[data-testid="stMultiSelect"] label,
[data-testid="stMultiSelect"] label p {
    font-size: 0.70rem !important;
    margin-bottom: 0.05rem !important;
}
[data-testid="stMultiSelect"] [data-baseweb="tag"] span {
    font-size: 0.62rem !important;
}
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
    min-height: 28px !important;
    font-size: 0.70rem !important;
}
[data-testid="stMultiSelect"] [data-baseweb="menu"] li {
    font-size: 0.70rem !important;
    padding: 3px 8px !important;
}

/* ── dialog / modal ── */
[role="dialog"] p,
[role="dialog"] label,
[role="dialog"] label p {
    font-size: 0.82rem !important;
}
[role="dialog"] input,
[role="dialog"] textarea {
    font-size: 0.82rem !important;
}
[data-testid="stDialog"] > div {
    max-width: 560px !important;
    width: 560px !important;
}
</style>
"""


def main() -> None:
    st.html(_CSS)
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
                "4. Create user accounts for each member\n"
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
    from sa_rebuild.compliance.db import get_company_info
    _co = get_company_info()
    _caption = _co.get("name") or _COMPANY["name"]
    if _co.get("formed"):
        _caption += f"  |  Formed: {_co['formed']}"
    st.caption(_caption)

    tab_dash, tab_q, tab_a, tab_ot, tab_cfg = st.tabs(
        ["📊 Dashboard", "🗓️ Quarterly", "📆 Annual", "✅ One-Time", "⚙️ Settings"]
    )

    with tab_dash:
        _render_dashboard(user["email"])

    with tab_q:
        st.subheader("Quarterly Filings")
        _render_filing_tab("quarterly", user["email"])

    with tab_a:
        st.subheader("Annual Filings")
        _render_filing_tab("annual", user["email"])

    with tab_ot:
        st.subheader("One-Time & Setup Items")
        _render_filing_tab("one_time", user["email"], has_confirmation=True)

    with tab_cfg:
        _render_settings_tab()


main()
