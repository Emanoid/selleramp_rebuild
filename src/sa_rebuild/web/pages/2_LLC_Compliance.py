"""LLC Compliance Tracker — Central Line Group LLC."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[3]  # pages/ → web/ → sa_rebuild/ → src/
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ── static reference data ────────────────────────────────────────────────────

_COMPANY = {
    "name": "Central Line Group LLC",
    "ein": "42-2162254",
    "nj_id": "0451453963",
    "formed": "April 27, 2026",
}

_QUICK_REF = [
    ("NJ Sales Tax Return",        "Quarterly",  "Jan 31 / Apr 30 / Jul 31 / Oct 31", "LLC",         "nj.gov/taxation"),
    ("Federal Est. Tax 1040-ES",   "Quarterly",  "Apr 15 / Jun 15 / Sep 15 / Jan 15", "Each member", "irs.gov/payments"),
    ("NJ Est. Tax NJ-1040-ES",     "Quarterly",  "Apr 15 / Jun 15 / Sep 15 / Jan 15", "Each member", "nj.gov/taxation"),
    ("Federal Form 1065",          "Annual",     "March 15",                           "LLC",         "irs.gov"),
    ("NJ Form NJ-1065",            "Annual",     "March 15",                           "LLC",         "nj.gov/taxation"),
    ("Personal Form 1040",         "Annual",     "April 15",                           "Each member", "irs.gov"),
    ("Personal NJ-1040",           "Annual",     "April 15",                           "Each member", "nj.gov/taxation"),
    ("NJ Annual Report ($75)",     "Annual",     "April 30",                           "LLC",         "njportal.com/DOR/annualreports"),
    ("FinCEN BOI Report",          "One-time ✅", "Filed Apr 27, 2026",                "LLC",         "boiefiling.fincen.gov"),
    ("NJ LLC Formation",           "One-time ✅", "Filed Apr 27, 2026",                "LLC",         "njportal.com"),
]

_KEY_SITES = [
    ("IRS Direct Pay",       "irs.gov/payments",                  "Federal est. tax & 1065"),
    ("NJ Taxation Portal",   "nj.gov/taxation",                   "NJ est. tax, sales tax, NJ-1065"),
    ("NJ Annual Report",     "njportal.com/DOR/annualreports",    "LLC renewal — $75/yr"),
    ("FinCEN BOI Filing",    "boiefiling.fincen.gov",             "Beneficial ownership report"),
]

_STATUS_OPTIONS  = ["Pending", "Done", "Overdue"]
_STATUS_ICON     = {"Pending": "⏳", "Done": "✅", "Overdue": "⚠️"}
_ASSIGNED_OPTIONS = ["LLC", "Kadiatu", "Emmanuel"]

# ── firebase availability check ──────────────────────────────────────────────

def _firebase_ready() -> bool:
    try:
        from sa_rebuild.compliance.firebase_client import firebase_configured
        return firebase_configured()
    except Exception:
        return False


# ── auth helpers ─────────────────────────────────────────────────────────────

def _login_wall() -> Optional[dict]:
    """Show login form if not authenticated. Returns user dict or None (stops page)."""
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


# ── data helpers ─────────────────────────────────────────────────────────────

def _load(category: str) -> list[dict]:
    from sa_rebuild.compliance.db import get_filings
    return get_filings(category)


def _df(rows: list[dict], extra_hidden: list[str] | None = None) -> pd.DataFrame:
    cols = [
        "id", "filing_type", "jurisdiction", "year", "period", "quarter",
        "due_date", "status", "date_filed", "confirmation_number",
        "assigned_to", "notes", "category", "updated_by", "updated_at", "created_at",
    ]
    df = pd.DataFrame(rows, columns=[c for c in cols if any(c in r for r in rows)])
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]


def _column_config(hide_extra: list[str] | None = None) -> dict:
    hidden = {"id", "category", "year", "quarter", "updated_by", "updated_at", "created_at"}
    if hide_extra:
        hidden.update(hide_extra)
    cfg: dict = {h: None for h in hidden}
    cfg.update({
        "filing_type":        st.column_config.TextColumn("Filing", disabled=True),
        "jurisdiction":       st.column_config.TextColumn("Jurisdiction", disabled=True),
        "period":             st.column_config.TextColumn("Period", disabled=True),
        "due_date":           st.column_config.DateColumn("Due Date", disabled=True),
        "assigned_to":        st.column_config.TextColumn("Assigned To", disabled=True),
        "status":             st.column_config.SelectboxColumn("Status", options=_STATUS_OPTIONS, required=True),
        "date_filed":         st.column_config.DateColumn("Date Filed"),
        "confirmation_number":st.column_config.TextColumn("Conf. #", max_chars=80),
        "notes":              st.column_config.TextColumn("Notes", max_chars=300, width="large"),
    })
    return cfg


def _save_edits(original: list[dict], edited_df: pd.DataFrame, user_email: str) -> int:
    """Detect changed rows and write them to Firestore. Returns number of rows saved."""
    from sa_rebuild.compliance.db import update_filing

    orig_by_id = {r["id"]: r for r in original}
    editable_fields = ["status", "date_filed", "confirmation_number", "notes"]
    saved = 0
    for _, row in edited_df.iterrows():
        doc_id = row.get("id")
        if not doc_id:
            continue
        orig = orig_by_id.get(doc_id, {})
        updates = {}
        for f in editable_fields:
            new_val = row.get(f)
            old_val = orig.get(f)
            # Normalise NaN/None
            if new_val is None or (isinstance(new_val, float) and pd.isna(new_val)):
                new_val = None
            if new_val != old_val:
                updates[f] = new_val
        if updates:
            update_filing(doc_id, updates, user_email)
            saved += 1
    return saved


# ── tab renderers ─────────────────────────────────────────────────────────────

def _render_dashboard(user_email: str) -> None:
    from sa_rebuild.compliance.db import get_filings

    q_rows  = _load("quarterly")
    a_rows  = _load("annual")
    ot_rows = _load("one_time")
    all_rows = q_rows + a_rows + ot_rows

    def _counts(rows):
        done  = sum(1 for r in rows if r.get("status") == "Done")
        return done, len(rows)

    q_done, q_tot   = _counts(q_rows)
    a_done, a_tot   = _counts(a_rows)
    ot_done, ot_tot = _counts(ot_rows)

    c1, c2, c3 = st.columns(3)
    c1.metric("Quarterly",  f"{q_done} / {q_tot} done",  delta=f"{q_tot - q_done} pending")
    c2.metric("Annual",     f"{a_done} / {a_tot} done",  delta=f"{a_tot - a_done} pending")
    c3.metric("One-Time",   f"{ot_done} / {ot_tot} done", delta=f"{ot_tot - ot_done} pending")

    st.divider()

    today = date.today()
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
                icon = _STATUS_ICON.get(r.get("status", "Pending"), "•")
                st.markdown(
                    f"**{r['filing_type']}** — {r.get('assigned_to','LLC')}  \n"
                    f"Due: `{r.get('due_date')}` &nbsp;|&nbsp; {r.get('period','')}",
                )

    with right:
        st.subheader(f"📅 Coming up next")
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


def _render_filing_tab(
    category: str,
    user_email: str,
    has_confirmation: bool = False,
    has_quarter_filter: bool = False,
) -> None:
    rows = _load(category)
    if not rows:
        st.info("No filings found. Run the seed script or add rows below.")

    # ── filters ──
    years = sorted({r["year"] for r in rows if r.get("year")}, reverse=True)
    assignees = sorted({r["assigned_to"] for r in rows if r.get("assigned_to")})
    f1, f2 = st.columns(2)
    sel_year = f1.selectbox("Year", ["All"] + [str(y) for y in years], key=f"yr_{category}")
    sel_who  = f2.selectbox("Assigned to", ["All"] + assignees, key=f"who_{category}")

    filtered = [
        r for r in rows
        if (sel_year == "All" or str(r.get("year")) == sel_year)
        and (sel_who == "All" or r.get("assigned_to") == sel_who)
    ]

    if not filtered:
        st.warning("No rows match the current filters.")
        return

    original_df = _df(filtered)
    hide = [] if has_confirmation else ["confirmation_number"]

    st.caption(f"{len(filtered)} rows — edit Status, Date Filed, Conf. #, or Notes inline then click Save.")
    edited = st.data_editor(
        original_df,
        column_config=_column_config(hide_extra=hide),
        hide_index=True,
        use_container_width=True,
        key=f"editor_{category}_{sel_year}_{sel_who}",
        num_rows="fixed",
    )

    if st.button("💾 Save changes", type="primary", key=f"save_{category}"):
        saved = _save_edits(filtered, edited, user_email)
        if saved:
            st.success(f"Saved {saved} row(s).")
            st.rerun()
        else:
            st.info("No changes detected.")

    # ── add new row ──────────────────────────────────────────────────────────
    with st.expander("➕ Add a filing row"):
        with st.form(f"add_{category}", clear_on_submit=True):
            ac1, ac2 = st.columns(2)
            new_type  = ac1.text_input("Filing type")
            new_jur   = ac2.selectbox("Jurisdiction", ["Federal", "New Jersey", "N/A"])
            ac3, ac4  = st.columns(2)
            new_year  = ac3.number_input("Year", min_value=2024, max_value=2035,
                                         value=date.today().year, step=1)
            new_due   = ac4.date_input("Due date", value=None)
            ac5, ac6  = st.columns(2)
            new_who   = ac5.selectbox("Assigned to", _ASSIGNED_OPTIONS)
            new_per   = ac6.text_input("Period label", placeholder="e.g. Q2 2026 or 2026")
            new_notes = st.text_input("Notes")
            if has_confirmation:
                new_conf = st.text_input("Confirmation #")
            add_ok = st.form_submit_button("Add row")

        if add_ok:
            if not new_type:
                st.error("Filing type is required.")
            else:
                from sa_rebuild.compliance.db import add_filing
                add_filing({
                    "category":            category,
                    "filing_type":         new_type,
                    "jurisdiction":        new_jur,
                    "year":                int(new_year),
                    "period":              new_per or str(new_year),
                    "quarter":             None,
                    "due_date":            new_due,
                    "status":              "Pending",
                    "date_filed":          None,
                    "confirmation_number": new_conf if has_confirmation else None,
                    "assigned_to":         new_who,
                    "notes":               new_notes,
                }, user_email)
                st.success(f"Added: {new_type}")
                st.rerun()

    # ── delete a row ─────────────────────────────────────────────────────────
    with st.expander("🗑️ Delete a filing row"):
        labels = {
            r["id"]: f"{r.get('period','')} — {r['filing_type']} — {r.get('assigned_to','')}"
            for r in filtered
        }
        if not labels:
            st.info("No rows to delete.")
        else:
            del_id = st.selectbox(
                "Select filing to delete",
                options=list(labels.keys()),
                format_func=lambda k: labels[k],
                key=f"del_{category}",
            )
            if st.button("Delete (cannot be undone)", type="secondary", key=f"del_btn_{category}"):
                from sa_rebuild.compliance.db import delete_filing
                delete_filing(del_id)
                st.success("Deleted.")
                st.rerun()

    # ── history ───────────────────────────────────────────────────────────────
    with st.expander("🕐 View change history for a row"):
        hist_labels = {
            r["id"]: f"{r.get('period','')} — {r['filing_type']} — {r.get('assigned_to','')}"
            for r in filtered
        }
        hist_id = st.selectbox(
            "Select filing",
            options=list(hist_labels.keys()),
            format_func=lambda k: hist_labels[k],
            key=f"hist_{category}",
        )
        if hist_id:
            from sa_rebuild.compliance.db import get_filing_history
            history = get_filing_history(hist_id)
            if not history:
                st.info("No history yet — changes are logged after the first edit.")
            else:
                for h in reversed(history):
                    ts = h.get("changed_at")
                    ts_str = ts.strftime("%Y-%m-%d %H:%M") if hasattr(ts, "strftime") else str(ts)
                    st.markdown(
                        f"**{ts_str}** — {h.get('changed_by','?')}  \n"
                        f"`{h.get('old_status')}` → `{h.get('new_status')}`"
                        + (f"  \n_{h.get('note')}_" if h.get("note") else "")
                    )


# ── main page ─────────────────────────────────────────────────────────────────

def main() -> None:
    # Check Firebase config first
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

    # ── sidebar user info ────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"**Logged in as**  \n{user['email']}")
        if st.button("Sign out", key="compliance_signout"):
            del st.session_state["compliance_user"]
            st.rerun()
        st.divider()

    # ── page header ──────────────────────────────────────────────────────────
    st.title("📋 LLC Compliance Tracker")
    st.caption(
        f"{_COMPANY['name']}  |  EIN: {_COMPANY['ein']}  |  "
        f"NJ ID: {_COMPANY['nj_id']}  |  Formed: {_COMPANY['formed']}"
    )

    # ── tabs ─────────────────────────────────────────────────────────────────
    tab_dash, tab_q, tab_a, tab_ot = st.tabs(
        ["📊 Dashboard", "🗓️ Quarterly", "📆 Annual", "✅ One-Time"]
    )

    with tab_dash:
        _render_dashboard(user["email"])

    with tab_q:
        st.subheader("Quarterly Filings")
        _render_filing_tab("quarterly", user["email"], has_confirmation=False, has_quarter_filter=True)

    with tab_a:
        st.subheader("Annual Filings")
        _render_filing_tab("annual", user["email"], has_confirmation=False)

    with tab_ot:
        st.subheader("One-Time & Setup Items")
        _render_filing_tab("one_time", user["email"], has_confirmation=True)


main()
