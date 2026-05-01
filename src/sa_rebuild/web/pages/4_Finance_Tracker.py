"""Finance Tracker — Central Line Group LLC."""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import date
from typing import Optional

import pandas as pd
import streamlit as st

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[3]  # …/src
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ── constants ─────────────────────────────────────────────────────────────────

_EXPENSE_TYPES = ["Static", "Recurring"]
_FREQUENCIES   = ["Once", "Day", "Week", "Month", "Year"]

# ── helpers ───────────────────────────────────────────────────────────────────

def _firebase_ready() -> bool:
    try:
        from sa_rebuild.compliance.firebase_client import firebase_configured
        return firebase_configured()
    except Exception:
        return False


def _parse_date(val) -> Optional[date]:
    if val is None:
        return None
    from datetime import datetime as _dt
    if isinstance(val, _dt):   # must check datetime before date (datetime subclasses date)
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None
    return None


# ── calculator logic ──────────────────────────────────────────────────────────

def _months_inclusive(start: date, end: date) -> int:
    """Inclusive month count matching Excel DATEDIF(...,"m")+1."""
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def _years_inclusive(start: date, end: date) -> int:
    """Inclusive year count matching Excel DATEDIF(...,"y")+1."""
    return (end.year - start.year) + 1


def _recurring_amount(unit_price: float, frequency: str, start: date, end: date) -> float:
    """Compute recurring cost between start and end (inclusive logic matching Excel)."""
    if frequency == "Day":
        return unit_price * (end - start).days
    if frequency == "Week":
        return unit_price * (end - start).days / 7
    if frequency == "Month":
        return unit_price * _months_inclusive(start, end)
    if frequency == "Year":
        return unit_price * _years_inclusive(start, end)
    return 0.0


def _compute_total_spent(expense: dict) -> float:
    """Full spend from start_date to min(end_date, today) — used for display column."""
    today = date.today()
    exp_type   = expense.get("type", "Static")
    unit_price = float(expense.get("unit_price") or 0)
    start_date = _parse_date(expense.get("start_date"))
    end_date   = _parse_date(expense.get("end_date"))
    frequency  = expense.get("frequency", "Once")

    if not start_date or unit_price == 0:
        return 0.0
    if exp_type == "Static" or frequency == "Once":
        return unit_price

    eff_end = min(end_date, today) if end_date else today
    if start_date > eff_end:
        return 0.0
    return _recurring_amount(unit_price, frequency, start_date, eff_end)


def _compute_expense_for_range(expense: dict, calc_start: date, calc_end: date) -> float:
    """Expense amount clipped to [calc_start, calc_end] — used by expense calculator and dashboard."""
    exp_type   = expense.get("type", "Static")
    unit_price = float(expense.get("unit_price") or 0)
    start_date = _parse_date(expense.get("start_date"))
    end_date   = _parse_date(expense.get("end_date"))
    frequency  = expense.get("frequency", "Once")

    if not start_date or unit_price == 0:
        return 0.0

    if exp_type == "Static" or frequency == "Once":
        return unit_price if calc_start <= start_date <= calc_end else 0.0

    # Bug fix: use calc_end (not today) as the cap for open-ended recurring expenses
    eff_end = min(end_date, calc_end) if end_date else calc_end
    range_s = max(start_date, calc_start)
    range_e = min(eff_end, calc_end)
    if range_s > range_e:
        return 0.0
    return _recurring_amount(unit_price, frequency, range_s, range_e)


def _compute_profit_expenses(expenses: list[dict], profit_start: date, profit_end: date) -> float:
    """Match Excel SUMPRODUCT: sum total_spent where start>=profit_start and eff_end<=profit_end."""
    total = 0.0
    for exp in expenses:
        start_date = _parse_date(exp.get("start_date"))
        if start_date is None:
            continue
        end_date = _parse_date(exp.get("end_date"))
        # Bug fix: use profit_end (not today) for open-ended expenses
        eff_end  = end_date if end_date else profit_end
        if start_date >= profit_start and eff_end <= profit_end:
            total += _compute_total_spent(exp)
    return total


# ── data loaders ──────────────────────────────────────────────────────────────

def _load_expenses() -> list[dict]:
    from sa_rebuild.finance_tracker.db import get_expenses
    return get_expenses()


def _load_income() -> list[dict]:
    from sa_rebuild.finance_tracker.db import get_income
    return get_income()


def _load_settings() -> dict:
    from sa_rebuild.finance_tracker.db import get_settings
    return get_settings()


# ── display dataframes ────────────────────────────────────────────────────────

def _expenses_df(rows: list[dict]) -> pd.DataFrame:
    cols = ["#", "Type", "Item Description", "Unit Price ($)", "Frequency",
            "Start Date", "End Date", "Total Spent ($)", "Receipt Filename", "Notes"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame([
        {
            "#":                r.get("order", i),
            "Type":             r.get("type", ""),
            "Item Description": r.get("item_description", ""),
            "Unit Price ($)":   round(float(r.get("unit_price") or 0), 2),
            "Frequency":        r.get("frequency", ""),
            "Start Date":       r.get("start_date"),
            "End Date":         r.get("end_date"),
            "Total Spent ($)":  round(_compute_total_spent(r), 2),
            "Receipt Filename": r.get("receipt_filename", ""),
            "Notes":            r.get("notes", ""),
        }
        for i, r in enumerate(rows, 1)
    ])


def _income_df(rows: list[dict]) -> pd.DataFrame:
    cols = ["#", "Date", "Type", "Amount ($)", "Notes"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame([
        {
            "#":          r.get("order", i),
            "Date":       r.get("date"),
            "Type":       r.get("type", ""),
            "Amount ($)": round(float(r.get("amount") or 0), 2),
            "Notes":      r.get("notes", ""),
        }
        for i, r in enumerate(rows, 1)
    ])


# ── filter helpers ────────────────────────────────────────────────────────────

def _fk(tab: str, field: str) -> str:
    return f"flt_ft_{tab}_{field}"


def _matches(value, selected: list) -> bool:
    return not selected or value in selected


def _render_expense_filters(rows: list[dict]) -> list[dict]:
    lbl, _, clr = st.columns([3, 4, 2])
    lbl.markdown("**Filters**")
    if clr.button("✖ Clear", key="btn_clear_exp", use_container_width=True):
        for f in ("type", "frequency"):
            st.session_state[_fk("exp", f)] = []
        st.rerun()
    c1, c2 = st.columns(2)
    sel_type = c1.multiselect("Type", _EXPENSE_TYPES, default=[], key=_fk("exp", "type"))
    sel_freq = c2.multiselect("Frequency", _FREQUENCIES, default=[], key=_fk("exp", "frequency"))
    return [
        r for r in rows
        if _matches(r.get("type"), sel_type) and _matches(r.get("frequency"), sel_freq)
    ]


def _render_income_filters(rows: list[dict], income_types: list[str]) -> list[dict]:
    lbl, _, clr = st.columns([3, 4, 2])
    lbl.markdown("**Filters**")
    if clr.button("✖ Clear", key="btn_clear_inc", use_container_width=True):
        st.session_state[_fk("inc", "type")] = []
        st.rerun()
    sel_type = st.multiselect("Type", income_types, default=[], key=_fk("inc", "type"))
    return [r for r in rows if _matches(r.get("type"), sel_type)]


# ── expense dialogs ───────────────────────────────────────────────────────────

@st.dialog("➕ Add Expense")
def _add_expense_modal(user_email: str, onedrive_path: str) -> None:
    if onedrive_path:
        st.info(f"📁 Upload receipt to: `{onedrive_path}`")
    else:
        st.caption("Set your receipt upload path in ⚙️ Settings.")
    with st.form("add_expense_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_type = c1.selectbox("Type *", _EXPENSE_TYPES)
        new_freq = c2.selectbox("Frequency", _FREQUENCIES)
        new_desc  = st.text_input("Item Description *")
        new_price = st.number_input("Unit Price ($)", min_value=0.0, step=0.01, format="%.2f")
        c5, c6 = st.columns(2)
        new_start = c5.date_input("Start Date", value=date.today())
        ongoing = c6.checkbox("Ongoing (no end date)", value=True, key="add_exp_ongoing")
        new_end = None
        if not ongoing:
            new_end = st.date_input("End Date", value=date.today(), key="add_exp_end_date")
        new_receipt = st.text_input(
            "Receipt Filename",
            placeholder="e.g. receipt_jan2026.pdf",
        )
        new_notes = st.text_area("Notes", height=60)
        submitted = st.form_submit_button("Add", type="primary")

    if submitted:
        if not new_desc.strip():
            st.error("Item Description is required.")
        elif new_price <= 0:
            st.error("Unit Price must be > 0.")
        else:
            from sa_rebuild.finance_tracker.db import add_expense
            freq_val = "Once" if new_type == "Static" else new_freq
            add_expense({
                "type":             new_type,
                "item_description": new_desc.strip(),
                "unit_price":       new_price,
                "frequency":        freq_val,
                "start_date":       new_start,
                "end_date":         new_end,
                "receipt_filename": new_receipt.strip(),
                "notes":            new_notes.strip(),
            }, user_email)
            st.rerun()


@st.dialog("✏️ Edit Expense")
def _edit_expense_modal(row: dict, user_email: str, onedrive_path: str) -> None:
    st.markdown(f"**{row.get('item_description', '')}**")
    if onedrive_path:
        st.info(f"📁 Upload receipt to: `{onedrive_path}`")
    else:
        st.caption("Set your receipt upload path in ⚙️ Settings.")
    st.divider()
    c1, c2 = st.columns(2)
    cur_type = row.get("type", "Static")
    new_type = c1.selectbox("Type", _EXPENSE_TYPES,
                            index=_EXPENSE_TYPES.index(cur_type) if cur_type in _EXPENSE_TYPES else 0)
    cur_freq = row.get("frequency", "Once")
    new_freq = c2.selectbox("Frequency", _FREQUENCIES,
                            index=_FREQUENCIES.index(cur_freq) if cur_freq in _FREQUENCIES else 0)
    new_desc  = st.text_input("Item Description", value=row.get("item_description", ""))
    new_price = st.number_input("Unit Price ($)", value=float(row.get("unit_price") or 0),
                                min_value=0.0, step=0.01, format="%.2f")
    c5, c6 = st.columns(2)
    cur_start = _parse_date(row.get("start_date"))
    new_start = c5.date_input("Start Date", value=cur_start or date.today())
    cur_end   = _parse_date(row.get("end_date"))
    ongoing   = c6.checkbox("Ongoing (no end date)", value=(cur_end is None), key="edit_exp_ongoing")
    new_end   = None
    if not ongoing:
        new_end = st.date_input("End Date", value=cur_end or date.today(), key="edit_exp_end_date")
    new_receipt = st.text_input("Receipt Filename", value=row.get("receipt_filename", ""))
    new_notes = st.text_area("Notes", value=row.get("notes", ""), height=60)
    st.divider()
    save, cancel = st.columns(2)
    if save.button("💾 Save", type="primary", use_container_width=True, key="edit_exp_save"):
        if not new_desc.strip():
            st.error("Item Description is required.")
        else:
            from sa_rebuild.finance_tracker.db import update_expense
            freq_val = "Once" if new_type == "Static" else new_freq
            update_expense(row["id"], {
                "type":             new_type,
                "item_description": new_desc.strip(),
                "unit_price":       new_price,
                "frequency":        freq_val,
                "start_date":       new_start,
                "end_date":         new_end,
                "receipt_filename": new_receipt.strip(),
                "notes":            new_notes.strip(),
            }, user_email)
            st.rerun()
    if cancel.button("Cancel", use_container_width=True, key="edit_exp_cancel"):
        st.rerun()


@st.dialog("🗑️ Confirm Delete")
def _delete_expense_modal(rows: list[dict]) -> None:
    st.warning(f"Permanently delete **{len(rows)} expense(s)**?")
    for r in rows:
        st.markdown(
            f"- **{r.get('item_description', '')}** — "
            f"{r.get('type', '')} — ${float(r.get('unit_price') or 0):.2f}/{r.get('frequency', '')}"
        )
    st.divider()
    confirm, cancel = st.columns(2)
    if confirm.button("Yes, delete", type="primary", use_container_width=True, key="del_exp_confirm"):
        from sa_rebuild.finance_tracker.db import delete_expense
        for r in rows:
            delete_expense(r["id"])
        st.rerun()
    if cancel.button("Cancel", use_container_width=True, key="del_exp_cancel"):
        st.rerun()


# ── income dialogs ────────────────────────────────────────────────────────────

@st.dialog("➕ Add Income")
def _add_income_modal(user_email: str, income_types: list[str]) -> None:
    with st.form("add_income_form", clear_on_submit=True):
        c1, c2    = st.columns(2)
        new_date  = c1.date_input("Date *", value=date.today())
        new_type  = c2.selectbox("Type *", income_types)
        new_amount = st.number_input("Amount ($) *", min_value=0.0, step=0.01, format="%.2f")
        new_notes  = st.text_area("Notes", height=60)
        submitted  = st.form_submit_button("Add", type="primary")

    if submitted:
        if new_amount <= 0:
            st.error("Amount must be > 0.")
        else:
            from sa_rebuild.finance_tracker.db import add_income
            add_income({
                "date":   new_date,
                "type":   new_type,
                "amount": new_amount,
                "notes":  new_notes.strip(),
            }, user_email)
            st.rerun()


@st.dialog("✏️ Edit Income")
def _edit_income_modal(row: dict, user_email: str, income_types: list[str]) -> None:
    st.markdown(f"**${float(row.get('amount') or 0):.2f}** — {row.get('type', '')}")
    st.divider()
    c1, c2    = st.columns(2)
    cur_date  = _parse_date(row.get("date"))
    new_date  = c1.date_input("Date", value=cur_date or date.today())
    cur_type  = row.get("type", income_types[0] if income_types else "")
    idx       = income_types.index(cur_type) if cur_type in income_types else 0
    new_type  = c2.selectbox("Type", income_types, index=idx)
    new_amount = st.number_input("Amount ($)", value=float(row.get("amount") or 0),
                                 min_value=0.0, step=0.01, format="%.2f")
    new_notes  = st.text_area("Notes", value=row.get("notes", ""), height=60)
    st.divider()
    save, cancel = st.columns(2)
    if save.button("💾 Save", type="primary", use_container_width=True, key="edit_inc_save"):
        if new_amount <= 0:
            st.error("Amount must be > 0.")
        else:
            from sa_rebuild.finance_tracker.db import update_income
            update_income(row["id"], {
                "date":   new_date,
                "type":   new_type,
                "amount": new_amount,
                "notes":  new_notes.strip(),
            }, user_email)
            st.rerun()
    if cancel.button("Cancel", use_container_width=True, key="edit_inc_cancel"):
        st.rerun()


@st.dialog("🗑️ Confirm Delete")
def _delete_income_modal(rows: list[dict]) -> None:
    st.warning(f"Permanently delete **{len(rows)} income record(s)**?")
    for r in rows:
        st.markdown(
            f"- **${float(r.get('amount') or 0):.2f}** — "
            f"{r.get('date')} — {r.get('type', '')}"
        )
    st.divider()
    confirm, cancel = st.columns(2)
    if confirm.button("Yes, delete", type="primary", use_container_width=True, key="del_inc_confirm"):
        from sa_rebuild.finance_tracker.db import delete_income
        for r in rows:
            delete_income(r["id"])
        st.rerun()
    if cancel.button("Cancel", use_container_width=True, key="del_inc_cancel"):
        st.rerun()


# ── tab renderers ─────────────────────────────────────────────────────────────

def _render_dashboard(expenses: list[dict], income: list[dict], settings: dict) -> None:
    today = date.today()
    try:
        default_start = date(today.year - 1, today.month, today.day)
    except ValueError:
        default_start = date(today.year - 1, today.month, 1)

    st.session_state.setdefault("dash_start", default_start)
    st.session_state.setdefault("dash_end", today)

    dc1, dc2 = st.columns(2)
    dash_start = dc1.date_input("Start Date", value=st.session_state["dash_start"], key="dash_start_w")
    dash_end   = dc2.date_input("End Date",   value=st.session_state["dash_end"],   key="dash_end_w")
    st.session_state["dash_start"] = dash_start
    st.session_state["dash_end"]   = dash_end

    st.divider()

    revenue      = sum(
        float(r.get("amount") or 0) for r in income
        if _parse_date(r.get("date")) and dash_start <= _parse_date(r.get("date")) <= dash_end
    )
    recurring_exp = sum(
        _compute_expense_for_range(e, dash_start, dash_end)
        for e in expenses if e.get("type") == "Recurring"
    )
    static_exp = sum(
        _compute_expense_for_range(e, dash_start, dash_end)
        for e in expenses if e.get("type") == "Static"
    )
    total_exp     = recurring_exp + static_exp
    profit        = revenue - total_exp
    tax_rate      = float(settings.get("tax_rate", 0.35))
    reinvest_pct  = float(settings.get("reinvest_pct", 0.50))
    tax_reserve   = max(0.0, profit * tax_rate)
    reinvest_amt  = max(0.0, (profit - tax_reserve) * reinvest_pct)
    distributable = profit - tax_reserve - reinvest_amt

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Gross Revenue",  f"${revenue:,.2f}")
    mc2.metric("Total Expenses", f"${total_exp:,.2f}")
    mc3.metric("Pre-Tax Profit", f"${profit:,.2f}",
               delta=f"{profit/revenue*100:.1f}% margin" if revenue else "—")

    st.divider()

    def pct(amt: float) -> str:
        return f"{amt/revenue*100:.1f}%" if revenue else "—"

    members = settings.get("members", [])
    table_rows = [
        ("Gross Revenue",                            revenue,       pct(revenue)),
        ("Recurring Expenses",                       recurring_exp, pct(recurring_exp)),
        ("Static / One-time",                        static_exp,    pct(static_exp)),
        ("Total Expenses",                           total_exp,     pct(total_exp)),
        ("Pre-Tax Profit",                           profit,        pct(profit)),
        (f"Tax Reserve ({tax_rate*100:.0f}%)",       tax_reserve,   pct(tax_reserve)),
        (f"Reinvestment ({reinvest_pct*100:.0f}%)",  reinvest_amt,  pct(reinvest_amt)),
        ("Distributable Profit",                     distributable, pct(distributable)),
    ]
    for m in members:
        share = distributable * float(m.get("pct", 0))
        table_rows.append((f"{m['name']} ({float(m.get('pct',0))*100:.0f}%)", share, pct(share)))

    df = pd.DataFrame(table_rows, columns=["Category", "Amount ($)", "% of Revenue"])
    df["Amount ($)"] = df["Amount ($)"].apply(lambda x: f"${x:,.2f}")
    st.dataframe(df, hide_index=True, use_container_width=True)


def _render_expenses_tab(user_email: str, settings: dict) -> None:
    from sa_rebuild.finance_tracker.db import ensure_order_expenses, move_expense_rows

    expenses    = _load_expenses()
    ensure_order_expenses(expenses)
    onedrive    = settings.get("onedrive_receipts_path", "")

    # Calculator
    st.markdown("**Expense Calculator**")
    today = date.today()
    cc1, cc2   = st.columns(2)
    calc_start = cc1.date_input("Start Date", value=date(today.year, today.month, 1), key="exp_calc_s")
    calc_end   = cc2.date_input("End Date",   value=today,                            key="exp_calc_e")

    if calc_start and calc_end and calc_start <= calc_end:
        static_exps    = [e for e in expenses if e.get("type") == "Static"]
        recurring_exps = [e for e in expenses if e.get("type") == "Recurring"]
        static_total   = sum(_compute_expense_for_range(e, calc_start, calc_end) for e in static_exps)
        recurring_total = sum(_compute_expense_for_range(e, calc_start, calc_end) for e in recurring_exps)
        n_static    = sum(1 for e in static_exps    if _compute_expense_for_range(e, calc_start, calc_end) > 0)
        n_recurring = sum(1 for e in recurring_exps if _compute_expense_for_range(e, calc_start, calc_end) > 0)
        ca, cb, cc_col = st.columns(3)
        ca.metric("Static Total",    f"${static_total:,.2f}")
        ca.caption(f"{n_static} item(s) in range")
        cb.metric("Recurring Total", f"${recurring_total:,.2f}")
        cb.caption(f"{n_recurring} item(s) in range")
        cc_col.metric("All Total",   f"${static_total + recurring_total:,.2f}")
    else:
        st.warning("End date must be on or after start date.")

    st.divider()

    filtered = _render_expense_filters(expenses)

    tbl_state = st.session_state.get("tbl_ft_exp", {})
    prev_sel  = tbl_state.get("selection", {}).get("rows", []) if isinstance(tbl_state, dict) else []
    sel_idx   = sorted(i for i in prev_sel if i < len(filtered))
    sel_rows  = [filtered[i] for i in sel_idx]
    n_sel     = len(sel_rows)
    can_up    = bool(sel_idx and sel_idx[0] > 0)
    can_dn    = bool(sel_idx and sel_idx[-1] < len(filtered) - 1)

    b1, b2, b3, b4, b5 = st.columns(5)
    if b1.button("Edit",   key="btn_edit_exp", disabled=n_sel != 1, use_container_width=True):
        _edit_expense_modal(sel_rows[0], user_email, onedrive)
    if b2.button(f"Delete{f' ({n_sel})' if n_sel else ''}",
                 key="btn_del_exp", disabled=n_sel == 0, use_container_width=True):
        _delete_expense_modal(sel_rows)
    if b3.button("+ Add",  key="btn_add_exp", use_container_width=True):
        _add_expense_modal(user_email, onedrive)
    if b4.button("↑ Up",   key="btn_up_exp", disabled=not can_up, use_container_width=True):
        group = [filtered[i] for i in sel_idx]
        upper = filtered[sel_idx[0] - 1]
        move_expense_rows([upper] + group, group + [upper])
        st.session_state["tbl_ft_exp"] = {"selection": {"rows": [i - 1 for i in sel_idx], "columns": []}}
        st.rerun()
    if b5.button("↓ Down", key="btn_dn_exp", disabled=not can_dn, use_container_width=True):
        group = [filtered[i] for i in sel_idx]
        lower = filtered[sel_idx[-1] + 1]
        move_expense_rows(group + [lower], [lower] + group)
        st.session_state["tbl_ft_exp"] = {"selection": {"rows": [i + 1 for i in sel_idx], "columns": []}}
        st.rerun()

    if filtered:
        st.caption(f"{len(filtered)} of {len(expenses)} rows — select rows to edit")
        if onedrive:
            st.caption(f"Receipt upload location: `{onedrive}`")
    else:
        st.info("No expenses match the current filters.")

    st.dataframe(
        _expenses_df(filtered),
        use_container_width=True,
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
        key="tbl_ft_exp",
    )


def _render_income_tab(user_email: str, settings: dict) -> None:
    from sa_rebuild.finance_tracker.db import ensure_order_income, move_income_rows

    income       = _load_income()
    ensure_order_income(income)
    income_types = settings.get("income_types", ["Income after Fees", "Reimbursement", "Other"])

    # Calculator
    st.markdown("**Income Calculator**")
    today = date.today()
    cc1, cc2   = st.columns(2)
    calc_start = cc1.date_input("Start Date", value=date(today.year, today.month, 1), key="inc_calc_s")
    calc_end   = cc2.date_input("End Date",   value=today,                            key="inc_calc_e")

    if calc_start and calc_end and calc_start <= calc_end:
        in_range    = [
            r for r in income
            if _parse_date(r.get("date")) and calc_start <= _parse_date(r.get("date")) <= calc_end
        ]
        net_revenue = sum(float(r.get("amount") or 0) for r in in_range)
        ci1, ci2 = st.columns(2)
        ci1.metric("Net Revenue",   f"${net_revenue:,.2f}")
        ci2.metric("# of Deposits", len(in_range))
    else:
        st.warning("End date must be on or after start date.")

    st.divider()

    filtered = _render_income_filters(income, income_types)

    tbl_state = st.session_state.get("tbl_ft_inc", {})
    prev_sel  = tbl_state.get("selection", {}).get("rows", []) if isinstance(tbl_state, dict) else []
    sel_idx   = sorted(i for i in prev_sel if i < len(filtered))
    sel_rows  = [filtered[i] for i in sel_idx]
    n_sel     = len(sel_rows)
    can_up    = bool(sel_idx and sel_idx[0] > 0)
    can_dn    = bool(sel_idx and sel_idx[-1] < len(filtered) - 1)

    b1, b2, b3, b4, b5 = st.columns(5)
    if b1.button("Edit",   key="btn_edit_inc", disabled=n_sel != 1, use_container_width=True):
        _edit_income_modal(sel_rows[0], user_email, income_types)
    if b2.button(f"Delete{f' ({n_sel})' if n_sel else ''}",
                 key="btn_del_inc", disabled=n_sel == 0, use_container_width=True):
        _delete_income_modal(sel_rows)
    if b3.button("+ Add",  key="btn_add_inc", use_container_width=True):
        _add_income_modal(user_email, income_types)
    if b4.button("↑ Up",   key="btn_up_inc", disabled=not can_up, use_container_width=True):
        group = [filtered[i] for i in sel_idx]
        upper = filtered[sel_idx[0] - 1]
        move_income_rows([upper] + group, group + [upper])
        st.session_state["tbl_ft_inc"] = {"selection": {"rows": [i - 1 for i in sel_idx], "columns": []}}
        st.rerun()
    if b5.button("↓ Down", key="btn_dn_inc", disabled=not can_dn, use_container_width=True):
        group = [filtered[i] for i in sel_idx]
        lower = filtered[sel_idx[-1] + 1]
        move_income_rows(group + [lower], [lower] + group)
        st.session_state["tbl_ft_inc"] = {"selection": {"rows": [i + 1 for i in sel_idx], "columns": []}}
        st.rerun()

    if filtered:
        st.caption(f"{len(filtered)} of {len(income)} rows — select rows to edit")
    else:
        st.info("No income records match the current filters.")

    st.dataframe(
        _income_df(filtered),
        use_container_width=True,
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
        key="tbl_ft_inc",
    )


def _render_profit_tab(
    expenses: list[dict], income: list[dict], settings: dict, user_email: str
) -> None:
    today = date.today()

    # Date range
    pc1, pc2     = st.columns(2)
    profit_start = pc1.date_input("Start Date", value=date(today.year, 1, 1), key="profit_start")
    profit_end   = pc2.date_input("End Date",   value=today,                  key="profit_end")

    if profit_start > profit_end:
        st.warning("End date must be on or after start date.")
        return

    # Initialise session state from settings defaults (once per session)
    # ft_profit_ver is a counter that forces widget re-creation on reset
    st.session_state.setdefault("ft_profit_ver", 0)
    ver = st.session_state["ft_profit_ver"]

    st.session_state.setdefault("ft_tax_rate",    float(settings.get("tax_rate", 0.35)))
    st.session_state.setdefault("ft_reinvest_pct", float(settings.get("reinvest_pct", 0.50)))
    if "ft_members" not in st.session_state:
        st.session_state["ft_members"] = [
            {"name": m["name"], "pct": float(m["pct"])}
            for m in settings.get("members", [])
        ]

    # Revenue & expenses
    revenue  = sum(
        float(r.get("amount") or 0) for r in income
        if _parse_date(r.get("date")) and profit_start <= _parse_date(r.get("date")) <= profit_end
    )
    exp_total = _compute_profit_expenses(expenses, profit_start, profit_end)
    pre_tax   = revenue - exp_total

    st.divider()
    rc1, rc2, rc3 = st.columns(3)
    rc1.metric("Revenue",        f"${revenue:,.2f}")
    rc2.metric("Expenses",       f"${exp_total:,.2f}")
    rc3.metric("Pre-Tax Profit", f"${pre_tax:,.2f}")
    rc3.caption(f"= ${revenue:,.2f} − ${exp_total:,.2f}")

    # Tax & reinvestment — inputs and computed values in one row
    # Widget keys include ver so changing ver forces fresh widgets (fixes Reset)
    st.divider()
    t1, t2, t3, t4 = st.columns(4)
    tax_pct_input = t1.number_input(
        "Tax Rate %",
        value=st.session_state["ft_tax_rate"] * 100,
        min_value=0.0, max_value=100.0, step=0.5, format="%.1f",
        key=f"ft_w_tax_{ver}",
    )
    st.session_state["ft_tax_rate"] = tax_pct_input / 100
    tax_reserve = max(0.0, pre_tax * (tax_pct_input / 100))

    reinvest_input = t2.number_input(
        "Reinvest %",
        value=st.session_state["ft_reinvest_pct"] * 100,
        min_value=0.0, max_value=100.0, step=0.5, format="%.1f",
        key=f"ft_w_rein_{ver}",
    )
    st.session_state["ft_reinvest_pct"] = reinvest_input / 100
    reinvest_amt = max(0.0, (pre_tax - tax_reserve) * (reinvest_input / 100))
    distributable = pre_tax - tax_reserve - reinvest_amt

    t3.metric("Tax Reserve",     f"${tax_reserve:,.2f}")
    t3.caption(f"= ${pre_tax:,.2f} × {tax_pct_input:.1f}%")
    t4.metric("Reinvest Amount", f"${reinvest_amt:,.2f}")
    t4.caption(f"= (${pre_tax:,.2f}−${tax_reserve:,.2f}) × {reinvest_input:.1f}%")

    # Member distribution
    st.divider()
    st.metric("Distributable", f"${distributable:,.2f}")
    st.caption(f"= ${pre_tax:,.2f}−${tax_reserve:,.2f}−${reinvest_amt:,.2f}")

    members   = st.session_state["ft_members"]
    total_pct = sum(m["pct"] for m in members)
    if members and abs(total_pct - 1.0) > 0.001:
        st.warning(f"Member %s sum to {total_pct*100:.1f}% — must equal 100%.")

    # Column headers for member rows
    hc1, hc2, hc3 = st.columns([3, 2, 3])
    hc1.caption("Member")
    hc2.caption("% ownership")
    hc3.caption("Share ($)")

    for i, m in enumerate(members):
        mc1, mc2, mc3 = st.columns([3, 2, 3])
        mc1.markdown(f"**{m['name']}**")
        new_pct = mc2.number_input(
            f"% {m['name']}",
            value=m["pct"] * 100,
            min_value=0.0, max_value=100.0, step=0.5, format="%.1f",
            key=f"ft_w_mpct_{i}_{ver}",
            label_visibility="collapsed",
        )
        members[i]["pct"] = new_pct / 100
        share = distributable * members[i]["pct"]
        mc3.metric(f"{m['name']} Share", f"${share:,.2f}", label_visibility="collapsed")
        mc3.caption(f"= ${distributable:,.2f} × {new_pct:.1f}%")
    st.session_state["ft_members"] = members

    st.divider()
    col_save, col_reset = st.columns(2)
    if col_save.button("💾 Save as Defaults", key="btn_save_profit_def", use_container_width=True):
        from sa_rebuild.finance_tracker.db import save_settings
        s = _load_settings()
        s["tax_rate"]    = st.session_state["ft_tax_rate"]
        s["reinvest_pct"] = st.session_state["ft_reinvest_pct"]
        s["members"]     = st.session_state["ft_members"]
        save_settings(s)
        st.success("Saved as defaults.")
    if col_reset.button("↺ Reset to Defaults", key="btn_reset_profit", use_container_width=True):
        # Bump version to force fresh widget instances on next render
        st.session_state["ft_profit_ver"] = st.session_state.get("ft_profit_ver", 0) + 1
        # Clear mirrored state so setdefault re-reads from settings
        for k in ["ft_tax_rate", "ft_reinvest_pct", "ft_members"]:
            st.session_state.pop(k, None)
        # Clear any stale versioned widget keys
        for k in [k for k in st.session_state if k.startswith("ft_w_")]:
            del st.session_state[k]
        st.rerun()


def _render_settings_tab(user_email: str) -> None:
    from sa_rebuild.finance_tracker.db import get_settings, save_settings

    settings = get_settings()

    # Narrow the settings layout
    _, col, _ = st.columns([1, 6, 1])

    with col:
        # OneDrive path
        st.markdown("**Receipt Storage**")
        with st.form("ft_form_onedrive"):
            new_path = st.text_input(
                "OneDrive Receipts Path",
                value=settings.get("onedrive_receipts_path", ""),
                placeholder="https://onedrive.live.com/... or \\\\Server\\Share\\Receipts",
            )
            if st.form_submit_button("Save", type="primary"):
                settings["onedrive_receipts_path"] = new_path.strip()
                save_settings(settings)
                st.success("Saved.")
                st.rerun()

        st.divider()

        # Income types
        st.markdown("**Income Types**")
        st.caption("Appear in the 'Type' dropdown on the Amazon Income tab.")
        income_types = list(settings.get("income_types", ["Income after Fees", "Reimbursement", "Other"]))

        for i, t in enumerate(income_types):
            col_t, col_del = st.columns([6, 1])
            col_t.write(t)
            if col_del.button("✕", key=f"del_itype_{i}", help=f"Remove {t}"):
                income_types.pop(i)
                settings["income_types"] = income_types
                save_settings(settings)
                st.rerun()

        with st.form("ft_form_add_itype", clear_on_submit=True):
            new_itype = st.text_input("Add income type", placeholder="e.g. Grant")
            if st.form_submit_button("Add", type="primary"):
                stripped = new_itype.strip()
                if not stripped:
                    st.error("Name cannot be empty.")
                elif stripped in income_types:
                    st.error("Already exists.")
                else:
                    income_types.append(stripped)
                    settings["income_types"] = income_types
                    save_settings(settings)
                    st.rerun()

        st.divider()

        # Default profit settings
        st.markdown("**Default Profit Settings**")
        st.caption(
            "Pre-populate the Amazon Profit tab. "
            "Change them there for ad-hoc calculations without overwriting these defaults."
        )

        members = list(settings.get("members", []))

        with st.form("ft_form_profit_defaults"):
            d1, d2 = st.columns(2)
            new_tax = d1.number_input(
                "Default Tax Rate %",
                value=float(settings.get("tax_rate", 0.35)) * 100,
                min_value=0.0, max_value=100.0, step=0.5, format="%.1f",
            )
            new_reinv = d2.number_input(
                "Default Reinvest %",
                value=float(settings.get("reinvest_pct", 0.50)) * 100,
                min_value=0.0, max_value=100.0, step=0.5, format="%.1f",
            )

            if members:
                st.markdown("**Members & Ownership %**")
                # Column headers
                hm1, hm2 = st.columns([3, 2])
                hm1.caption("Name")
                hm2.caption("% ownership")

            new_members = []
            for i, m in enumerate(members):
                mc1, mc2 = st.columns([3, 2])
                name = mc1.text_input(f"Name {i+1}", value=m.get("name", ""), key=f"s_mn_{i}",
                                      label_visibility="collapsed")
                pct  = mc2.number_input(
                    f"% {i+1}", value=float(m.get("pct", 0)) * 100,
                    min_value=0.0, max_value=100.0, step=0.5, format="%.1f",
                    key=f"s_mp_{i}", label_visibility="collapsed",
                )
                new_members.append({"name": name.strip(), "pct": pct / 100})

            if new_members:
                total_pct = sum(m["pct"] for m in new_members)
                if abs(total_pct - 1.0) > 0.001:
                    st.warning(f"Percentages sum to {total_pct*100:.1f}% — should equal 100%.")

            if st.form_submit_button("Save Defaults", type="primary"):
                settings["tax_rate"]    = new_tax / 100
                settings["reinvest_pct"] = new_reinv / 100
                settings["members"]     = new_members
                save_settings(settings)
                keys_to_clear = ["ft_tax_rate", "ft_reinvest_pct", "ft_members",
                                 "ft_tax_rate_input", "ft_reinvest_input"]
                keys_to_clear += [k for k in st.session_state if k.startswith("ft_mpct_")]
                for k in keys_to_clear:
                    st.session_state.pop(k, None)
                st.success("Defaults saved.")
                st.rerun()

        st.markdown("**Add member**")
        with st.form("ft_form_add_member", clear_on_submit=True):
            new_mn = st.text_input("Name", placeholder="Full name or display name")
            if st.form_submit_button("Add Member", type="primary"):
                if new_mn.strip():
                    members.append({"name": new_mn.strip(), "pct": 0.0})
                    settings["members"] = members
                    save_settings(settings)
                    st.rerun()
                else:
                    st.error("Name cannot be empty.")

        if members:
            st.markdown("**Remove member**")
            for i, m in enumerate(members):
                col_n, col_r = st.columns([6, 1])
                col_n.write(m["name"])
                if col_r.button("✕", key=f"rm_member_{i}", help=f"Remove {m['name']}"):
                    members.pop(i)
                    settings["members"] = members
                    save_settings(settings)
                    st.session_state.pop("ft_members", None)
                    st.rerun()


# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
<style>
/* Page layout — preserve default top padding so title is not clipped */
.main .block-container,
div[data-testid="stMainBlockContainer"] {
    max-width: 100% !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}

/* Compact buttons — reduce height and padding around text */
button {
    font-size: 0.68rem !important;
    height: 2rem !important;
    min-height: 2rem !important;
    max-height: 2rem !important;
    padding: 0 0.3rem !important;
    line-height: 2rem !important;
    box-sizing: border-box !important;
}
button > div { padding: 0 !important; }
button > div > p { margin: 0 !important; line-height: 1 !important; font-size: 0.68rem !important; }
button p, button span { font-size: 0.68rem !important; margin: 0 !important; line-height: 1 !important; }

/* Compact metrics */
[data-testid="stMetric"] {
    padding: 0.2rem 0.4rem !important;
    border: 1px solid rgba(128,128,128,0.2);
    border-radius: 4px;
}
[data-testid="stMetricLabel"] p { font-size: 0.70rem !important; margin: 0 !important; }
[data-testid="stMetricValue"]   { font-size: 1.0rem !important; line-height: 1.2 !important; }
[data-testid="stMetricDelta"]   { font-size: 0.65rem !important; }

/* Reduce gap between all elements in the main block */
[data-testid="stVerticalBlock"] { gap: 0.3rem !important; }

/* Compact dividers */
hr { margin: 0.2rem 0 !important; }

/* Compact form field labels */
[data-testid="stNumberInput"] label p,
[data-testid="stDateInput"] label p,
[data-testid="stTextInput"] label p,
[data-testid="stTextArea"] label p,
[data-testid="stCheckbox"] label p,
[data-testid="stSelectbox"] label p { font-size: 0.75rem !important; margin-bottom: 0.05rem !important; }

/* Compact input fields */
[data-testid="stNumberInput"] input  { font-size: 0.82rem !important; padding: 0.25rem 0.4rem !important; }
[data-testid="stDateInput"]   input  { font-size: 0.82rem !important; padding: 0.25rem 0.4rem !important; }
[data-testid="stTextInput"]   input  { font-size: 0.82rem !important; }

/* Compact multiselect */
[data-testid="stMultiSelect"] label,
[data-testid="stMultiSelect"] label p { font-size: 0.70rem !important; margin-bottom: 0.05rem !important; }
[data-testid="stMultiSelect"] [data-baseweb="tag"] span { font-size: 0.62rem !important; }
[data-testid="stMultiSelect"] [data-baseweb="select"] > div { min-height: 28px !important; font-size: 0.70rem !important; }
[data-testid="stMultiSelect"] [data-baseweb="menu"] li { font-size: 0.70rem !important; padding: 3px 8px !important; }

/* Caption text — use opacity so it adapts to both light and dark themes */
[data-testid="stCaptionContainer"] p {
    font-size: 0.67rem !important;
    opacity: 0.55;
    margin-top: 0.05rem !important;
    margin-bottom: 0 !important;
}

/* Dialog */
[role="dialog"] p, [role="dialog"] label, [role="dialog"] label p { font-size: 0.82rem !important; }
[role="dialog"] input, [role="dialog"] textarea { font-size: 0.82rem !important; }
[data-testid="stDialog"] > div { max-width: 560px !important; width: 560px !important; }
</style>
"""


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.html(_CSS)

    if not _firebase_ready():
        st.warning(
            "**Firebase not configured.**  \n"
            "Finance Tracker uses the same Firebase project as LLC Compliance.  \n"
            "Follow the setup instructions in README → LLC Compliance → For developers."
        )
        st.stop()
        return

    from sa_rebuild.auth import login_wall
    user = login_wall("finance_user", "Finance Tracker")
    if not user:
        return

    with st.sidebar:
        st.markdown(f"**Logged in as**  \n{user['email']}")
        if st.button("Sign out", key="ft_signout"):
            del st.session_state["finance_user"]
            st.rerun()
        st.divider()

    st.title("💰 Finance Tracker")
    st.caption("Central Line Group LLC — Revenue, Expenses & Profit")

    settings = _load_settings()
    expenses = _load_expenses()
    income   = _load_income()

    tab_dash, tab_exp, tab_inc, tab_profit, tab_cfg = st.tabs(
        ["📊 Dashboard", "💸 Expenses", "💵 Amazon Income", "📈 Amazon Profit", "⚙️ Settings"]
    )

    with tab_dash:
        _render_dashboard(expenses, income, settings)

    with tab_exp:
        _render_expenses_tab(user["email"], settings)

    with tab_inc:
        _render_income_tab(user["email"], settings)

    with tab_profit:
        _render_profit_tab(expenses, income, settings, user["email"])

    with tab_cfg:
        _render_settings_tab(user["email"])


main()
