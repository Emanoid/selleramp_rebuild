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
_SRC = _HERE.parents[3]  # pages/ → web/ → sa_rebuild/ → src/
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ── static reference data ─────────────────────────────────────────────────────

_COMPANY = {
    "name": "Central Line Group LLC",
    "ein": "42-2162254",
    "nj_id": "0451453963",
    "formed": "April 27, 2026",
}

_QUICK_REF = [
    ("NJ Sales Tax Return",       "Quarterly",  "Jan 31 / Apr 30 / Jul 31 / Oct 31", "LLC",         "nj.gov/taxation"),
    ("Federal Est. Tax 1040-ES",  "Quarterly",  "Apr 15 / Jun 15 / Sep 15 / Jan 15", "Each member", "irs.gov/payments"),
    ("NJ Est. Tax NJ-1040-ES",    "Quarterly",  "Apr 15 / Jun 15 / Sep 15 / Jan 15", "Each member", "nj.gov/taxation"),
    ("Federal Form 1065",         "Annual",     "March 15",                           "LLC",         "irs.gov"),
    ("NJ Form NJ-1065",           "Annual",     "March 15",                           "LLC",         "nj.gov/taxation"),
    ("Personal Form 1040",        "Annual",     "April 15",                           "Each member", "irs.gov"),
    ("Personal NJ-1040",          "Annual",     "April 15",                           "Each member", "nj.gov/taxation"),
    ("NJ Annual Report ($75)",    "Annual",     "April 30",                           "LLC",         "njportal.com/DOR/annualreports"),
    ("FinCEN BOI Report",         "One-time ✅","Filed Apr 27, 2026",                 "LLC",         "boiefiling.fincen.gov"),
    ("NJ LLC Formation",          "One-time ✅","Filed Apr 27, 2026",                 "LLC",         "njportal.com"),
]

_KEY_SITES = [
    ("IRS Direct Pay",      "irs.gov/payments",               "Federal est. tax & 1065"),
    ("NJ Taxation Portal",  "nj.gov/taxation",                "NJ est. tax, sales tax, NJ-1065"),
    ("NJ Annual Report",    "njportal.com/DOR/annualreports", "LLC renewal — $75/yr"),
    ("FinCEN BOI Filing",   "boiefiling.fincen.gov",          "Beneficial ownership report"),
]

_STATUS_OPTIONS   = ["Pending", "Done", "Overdue"]
_STATUS_ICON      = {"Pending": "⏳", "Done": "✅", "Overdue": "⚠️"}
_ASSIGNED_OPTIONS = ["LLC", "Kadiatu", "Emmanuel"]

# ── template CSVs ─────────────────────────────────────────────────────────────

_TEMPLATES: dict[str, str] = {
    "quarterly": (
        "filing_type,jurisdiction,year,quarter,period,due_date,assigned_to,notes\n"
        "NJ Sales Tax Return,New Jersey,2026,Q2 (May-Jun),Q2 2026,2026-07-31,LLC,First return\n"
        "Federal Est. Tax 1040-ES,Federal,2026,Q2 (Apr-Jun),Q2 2026,2026-06-16,Kadiatu,Pay at irs.gov/payments\n"
    ),
    "annual": (
        "filing_type,jurisdiction,year,period,due_date,assigned_to,notes\n"
        "Federal Form 1065,Federal,2026,2026,2027-03-15,LLC,Partnership return + K-1s\n"
        "Personal Form 1040,Federal,2026,2026,2027-04-15,Kadiatu,Attach K-1 from Form 1065\n"
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
        f"<h2 style='margin-bottom:0'>🔐 LLC Compliance Login</h2>"
        f"<p style='color:grey'>{_COMPANY['name']}</p>",
        unsafe_allow_html=True,
    )
    with st.form("compliance_login", clear_on_submit=False):
        email    = st.text_input("Email")
        password = st.text_input("Password", type="password")
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


def _display_df(rows: list[dict], has_confirmation: bool) -> pd.DataFrame:
    """Build a human-readable, read-only DataFrame for display."""
    if not rows:
        cols = ["Filing", "Jurisdiction", "Period", "Due Date", "Status",
                "Assigned To", "Date Filed", "Notes"]
        if has_confirmation:
            cols.append("Conf. #")
        return pd.DataFrame(columns=cols)

    records = []
    for r in rows:
        status = r.get("status", "Pending")
        rec = {
            "Filing":      r.get("filing_type", ""),
            "Jurisdiction":r.get("jurisdiction", ""),
            "Period":      r.get("period", ""),
            "Due Date":    r.get("due_date"),
            "Status":      f"{_STATUS_ICON.get(status, '•')} {status}",
            "Assigned To": r.get("assigned_to", ""),
            "Date Filed":  r.get("date_filed"),
            "Notes":       r.get("notes", ""),
        }
        if has_confirmation:
            rec["Conf. #"] = r.get("confirmation_number", "") or ""
        records.append(rec)
    return pd.DataFrame(records)


# ── dialogs ───────────────────────────────────────────────────────────────────

@st.dialog("✏️ Edit Filing", width="large")
def _edit_modal(row: dict, user_email: str, has_confirmation: bool) -> None:
    st.markdown(
        f"**{row['filing_type']}**  \n"
        f"{row.get('period', '')}  ·  {row.get('jurisdiction', '')}  ·  {row.get('assigned_to', '')}"
    )
    st.divider()

    c1, c2 = st.columns(2)
    cur_status = row.get("status", "Pending")
    new_status = c1.selectbox(
        "Status", _STATUS_OPTIONS,
        index=_STATUS_OPTIONS.index(cur_status) if cur_status in _STATUS_OPTIONS else 0,
    )
    new_date_filed = c2.date_input("Date Filed", value=row.get("date_filed") or None)

    if has_confirmation:
        new_conf = st.text_input("Confirmation #", value=row.get("confirmation_number") or "")

    new_notes = st.text_area("Notes", value=row.get("notes") or "", height=100)

    save, cancel = st.columns(2)
    if save.button("💾 Save", type="primary", use_container_width=True):
        from sa_rebuild.compliance.db import update_filing
        updates: dict = {"status": new_status, "date_filed": new_date_filed, "notes": new_notes}
        if has_confirmation:
            updates["confirmation_number"] = new_conf
        update_filing(row["id"], updates, user_email)
        st.rerun()
    if cancel.button("Cancel", use_container_width=True):
        st.rerun()


@st.dialog("➕ Add Filing", width="large")
def _add_modal(category: str, user_email: str, has_confirmation: bool) -> None:
    with st.form("add_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_type = c1.text_input("Filing type *")
        new_jur  = c2.selectbox("Jurisdiction", ["Federal", "New Jersey", "N/A"])
        c3, c4   = st.columns(2)
        new_year = c3.number_input("Year", min_value=2024, max_value=2035,
                                   value=date.today().year, step=1)
        new_due  = c4.date_input("Due date", value=None)
        c5, c6   = st.columns(2)
        new_who  = c5.selectbox("Assigned to", _ASSIGNED_OPTIONS)
        new_per  = c6.text_input("Period label", placeholder="e.g. Q2 2026 or 2026")
        new_notes = st.text_area("Notes", height=80)
        new_conf  = st.text_input("Confirmation #") if has_confirmation else None
        submitted = st.form_submit_button("Add filing", type="primary")

    if submitted:
        if not new_type.strip():
            st.error("Filing type is required.")
        else:
            from sa_rebuild.compliance.db import add_filing
            add_filing({
                "category":            category,
                "filing_type":         new_type.strip(),
                "jurisdiction":        new_jur,
                "year":                int(new_year),
                "period":              new_per.strip() or str(int(new_year)),
                "quarter":             None,
                "due_date":            new_due,
                "status":              "Pending",
                "date_filed":          None,
                "confirmation_number": (new_conf.strip() or None) if new_conf else None,
                "assigned_to":         new_who,
                "notes":               new_notes.strip(),
            }, user_email)
            st.rerun()


@st.dialog("🗑️ Confirm Delete")
def _delete_modal(rows: list[dict], user_email: str) -> None:
    st.warning(f"You are about to permanently delete **{len(rows)} filing(s)**.")
    st.markdown("**Rows to be deleted:**")
    for r in rows:
        due = r.get("due_date") or "—"
        st.markdown(
            f"- **{r.get('filing_type','')}** — {r.get('period','')} — "
            f"{r.get('assigned_to','')} — due {due}"
        )
    st.divider()
    confirm, cancel = st.columns(2)
    if confirm.button("Yes, delete", type="primary", use_container_width=True):
        from sa_rebuild.compliance.db import delete_filing
        for r in rows:
            delete_filing(r["id"])
        st.rerun()
    if cancel.button("Cancel", use_container_width=True):
        st.rerun()


@st.dialog("🕐 Change History")
def _history_modal(row: dict) -> None:
    st.markdown(
        f"**{row['filing_type']}** — {row.get('period', '')} — {row.get('assigned_to', '')}"
    )
    st.divider()
    from sa_rebuild.compliance.db import get_filing_history
    history = get_filing_history(row["id"])
    if not history:
        st.info("No history yet — changes are logged after the first status edit.")
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

def _process_import(
    uploaded_file,
    category: str,
    user_email: str,
    has_confirmation: bool,
) -> None:
    try:
        df = pd.read_csv(io.BytesIO(uploaded_file.read()))
    except Exception as exc:
        st.error(f"Could not parse CSV: {exc}")
        return

    if "filing_type" not in df.columns:
        st.error("CSV must have a `filing_type` column. Download the template for the correct format.")
        return

    from sa_rebuild.compliance.db import add_filing
    added, errors = 0, []
    for i, row in df.iterrows():
        try:
            year_val = row.get("year")
            add_filing({
                "category":            category,
                "filing_type":         str(row.get("filing_type", "")).strip(),
                "jurisdiction":        str(row.get("jurisdiction", "N/A")).strip(),
                "year":                int(year_val) if pd.notna(year_val) else None,
                "period":              str(row.get("period", "")).strip(),
                "quarter":             str(row.get("quarter", "")).strip() or None,
                "due_date":            _parse_date_str(row.get("due_date")),
                "status":              "Pending",
                "date_filed":          None,
                "confirmation_number": str(row.get("confirmation_number", "")).strip() or None,
                "assigned_to":         str(row.get("assigned_to", "LLC")).strip(),
                "notes":               str(row.get("notes", "")).strip(),
            }, user_email)
            added += 1
        except Exception as exc:
            errors.append(f"Row {i + 1}: {exc}")

    if added:
        st.success(f"Imported {added} filing(s) successfully.")
    for e in errors:
        st.error(e)
    if added:
        st.rerun()


# ── tab renderer ──────────────────────────────────────────────────────────────

def _render_filing_tab(
    category: str,
    user_email: str,
    has_confirmation: bool = False,
) -> None:
    rows = _load(category)

    # ── filters ──────────────────────────────────────────────────────────────
    years     = sorted({r["year"] for r in rows if r.get("year")}, reverse=True)
    assignees = sorted({r["assigned_to"] for r in rows if r.get("assigned_to")})
    f1, f2 = st.columns(2)
    sel_year = f1.selectbox("Year", ["All"] + [str(y) for y in years], key=f"yr_{category}")
    sel_who  = f2.selectbox("Assigned to", ["All"] + assignees, key=f"who_{category}")

    filtered = [
        r for r in rows
        if (sel_year == "All" or str(r.get("year")) == sel_year)
        and (sel_who == "All" or r.get("assigned_to") == sel_who)
    ]

    # ── table (read-only, row-selectable) ────────────────────────────────────
    display_df = _display_df(filtered, has_confirmation)

    if filtered:
        st.caption(
            f"{len(filtered)} rows — click a row to select it, then use the action buttons below."
        )
    else:
        st.info("No filings yet — click **➕ Add Filing** to add one, or import from CSV.")

    event = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
        key=f"tbl_{category}_{sel_year}_{sel_who}",
    )

    selected_indices = event.selection.rows if hasattr(event, "selection") else []
    selected_rows    = [filtered[i] for i in selected_indices if i < len(filtered)]
    n_sel            = len(selected_rows)

    # ── action bar ───────────────────────────────────────────────────────────
    st.divider()
    b1, b2, b3, b4, b5 = st.columns(5)

    if b1.button(
        "✏️ Edit",
        disabled=n_sel != 1,
        use_container_width=True,
        help="Select exactly one row to edit",
    ):
        _edit_modal(selected_rows[0], user_email, has_confirmation)

    if b2.button(
        f"🗑️ Delete{f' ({n_sel})' if n_sel else ''}",
        disabled=n_sel == 0,
        use_container_width=True,
        help="Select one or more rows to delete",
    ):
        _delete_modal(selected_rows, user_email)

    if b3.button("➕ Add Filing", use_container_width=True):
        _add_modal(category, user_email, has_confirmation)

    if n_sel == 1 and b4.button("🕐 History", use_container_width=True):
        _history_modal(selected_rows[0])
    elif n_sel != 1:
        b4.button("🕐 History", use_container_width=True, disabled=True,
                  help="Select one row to view its history")

    # ── import / export ──────────────────────────────────────────────────────
    st.divider()
    imp1, imp2 = st.columns(2)

    imp1.download_button(
        "📥 Download CSV template",
        data=_TEMPLATES[category],
        file_name=f"{category}_template.csv",
        mime="text/csv",
        use_container_width=True,
        help="Download a blank template to fill in and re-upload",
    )

    show_import_key = f"show_import_{category}"
    st.session_state.setdefault(show_import_key, False)
    if imp2.button("📤 Import from CSV", use_container_width=True):
        st.session_state[show_import_key] = not st.session_state[show_import_key]

    if st.session_state[show_import_key]:
        st.markdown("**Upload a filled CSV** (use the template above for the correct column format):")
        uploaded = st.file_uploader(
            "Choose CSV file", type=["csv"], key=f"upload_{category}",
            label_visibility="collapsed",
        )
        if uploaded:
            _process_import(uploaded, category, user_email, has_confirmation)


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
    c1.metric("Quarterly",  f"{q_done} / {q_tot} done",  delta=f"{q_tot  - q_done} pending")
    c2.metric("Annual",     f"{a_done} / {a_tot} done",  delta=f"{a_tot  - a_done} pending")
    c3.metric("One-Time",   f"{ot_done} / {ot_tot} done",delta=f"{ot_tot - ot_done} pending")

    st.divider()
    today   = date.today()
    overdue = [r for r in all_rows
               if r.get("status") != "Done" and r.get("due_date") and r["due_date"] < today]
    upcoming = sorted(
        [r for r in all_rows
         if r.get("status") != "Done" and r.get("due_date") and r["due_date"] >= today],
        key=lambda r: r["due_date"],
    )[:5]

    left, right = st.columns(2)
    with left:
        st.subheader(f"⚠️ Overdue ({len(overdue)})")
        if not overdue:
            st.success("Nothing overdue.")
        else:
            for r in sorted(overdue, key=lambda x: x.get("due_date") or date.max):
                st.markdown(
                    f"**{r['filing_type']}** — {r.get('assigned_to','LLC')}  \n"
                    f"Due: `{r.get('due_date')}` &nbsp;|&nbsp; {r.get('period','')}",
                )

    with right:
        st.subheader("📅 Coming up next")
        if not upcoming:
            st.info("No upcoming filings found.")
        else:
            for r in upcoming:
                days_left = (r["due_date"] - today).days
                label = f"{days_left}d" if days_left > 0 else "today"
                st.markdown(
                    f"**{r['filing_type']}** — {r.get('assigned_to','LLC')}  \n"
                    f"Due: `{r.get('due_date')}` ({label})  |  {r.get('period','')}",
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
