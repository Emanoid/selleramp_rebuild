# Plan

## Current branch: `llc_compliance_tool`

---

## keepa_compare — completed 2026-04-30

### What was built
New standalone app `src/keepa_compare/` — offline FBA comparison tool that matches a wholesale cost CSV against a Keepa Product Viewer export (no API key needed).

### Files created
- `src/keepa_compare/__init__.py` — package marker
- `src/keepa_compare/__main__.py` — all matching logic, fee math, CLI entry point, and `run_compare()` public API
- `src/sa_rebuild/web/pages/3_Keepa_Compare.py` — Streamlit page (page 3 in sidebar)
- `README.md` — updated with full Keepa SellerAmp Compare section (user + developer docs, pricing algorithm explanation, column reference)

### Key decisions
- Multiple ASINs per UPC → one output row per ASIN, sorted by weight distance ascending (not filtered)
- Misc % renamed to Sales Tax throughout (SALES_TAX_PCT = 6.63%)
- `_norm_code()` guards against pandas `dtype=str` turning empty cells into `"NAN"` — fixes UPC matching when ASIN column is blank
- Weight matching uses `Package: Weight (g)` first, `Item: Weight (g)` as fallback, 9999 when unavailable
- Fee constants at top of `__main__.py` mirror config.yaml defaults exactly

### Output column order
Investment Decision → Recommended Selling Price → ROI → Estimated Profit → cost →
Price cols (BB, Amazon, FBA, New, FBM, ...) →
Diff cols (price − cost) →
Fee breakdown (Referral, FBA, Sales Tax, Inbound, Total) →
Keepa weights → Input weight → Weight distance →
Title → Amazon URL → Matched ASIN →
Input UPC → Input ASIN →
All remaining Keepa columns

### Verified output
- 3,677 rows from 1,560 input rows × multiple ASIN matches
- 931 Recommend, 2,746 Not Recommend, 118 no match
- Fee math spot-checked: correct referral, FBA, sales tax, inbound values

---

---

## finance_tracker — completed 2026-04-30

### What was built
New Streamlit webapp reproducing `CentralLineGroup_Finance_Tracker.xlsx` as a 4th app in the toolbox.

### Files created
- `src/sa_rebuild/auth.py` — shared Firebase login wall (`sign_in`, `login_wall(session_key, app_name)`); both LLC Compliance and Finance Tracker now use this
- `src/sa_rebuild/finance_tracker/__init__.py` — package marker
- `src/sa_rebuild/finance_tracker/db.py` — Firestore CRUD for expenses, income, and settings
- `src/sa_rebuild/web/pages/4_Finance_Tracker.py` — full UI: Dashboard, Expenses, Amazon Income, Amazon Profit, Settings tabs

### Files modified
- `src/sa_rebuild/web/pages/2_LLC_Compliance.py` — `_login_wall()` now delegates to `sa_rebuild.auth.login_wall`
- `src/sa_rebuild/web/app.py` — Finance Tracker registered as page 4
- `src/sa_rebuild/web/home.py` — Finance Tracker card added; all 4 tool cards converted from `st.info` text to `st.page_link` clickable buttons
- `README.md` — Finance Tracker section added (user docs, developer docs, Firestore schema, code layout)

### Key decisions
- Shared auth module: both apps call `login_wall(session_key, app_name)` — sessions are independent via different `session_key` values
- Expense calculator clips each recurring expense to `[calc_start, calc_end]` — matches Excel SUMPRODUCT logic
- Profit tab uses a stricter filter (entire expense period must fall within profit range) — matches Excel's B10 formula
- Amazon Profit tab uses session state for tax rate / reinvest % / member %s; "Save as Defaults" is the explicit persist action

### Firestore collections added
- `finance_expenses`, `finance_income`, `finance_settings`

### Bug fixes & UX improvements — 2026-04-30

All 9 issues from user testing addressed in `4_Finance_Tracker.py`:

1. **Bug #1 fixed** — `_compute_expense_for_range`: was capping open-ended expenses to `today` instead of `calc_end`; now uses `calc_end` so future-range recurring expenses calculate correctly
2. **Bug #2 fixed** — `_render_expense_filters` / `_render_income_filters`: `st.session_state.pop()` removed key but Streamlit multiselect retained visual state; now sets `= []` to properly reset widgets
3. **Bug #3 fixed** — `_compute_profit_expenses`: was capping open-ended expenses to `today` instead of `profit_end`; now includes all recurring expenses whose period falls within the profit range
4. **% symbols** — Profit tab member section now has column headers ("Member | % ownership | Share ($)")
5. **Formula captions** — Pre-Tax Profit, Tax Reserve, Reinvest Amount, Distributable, and each member share now show the formula with actual values as a small caption below the metric
6. **Compact layout** — Removed all `st.subheader()` calls replaced with `st.markdown("**...**")` or eliminated; Profit tab restructured to 4-column row for Tax/Reinvest (no scrolling); enhanced CSS shrinks metrics, labels, inputs, dividers; removed duplicate `st.subheader()` calls in `main()`
7. **Receipt reminder** — Add/Edit expense modals now show a persistent `st.info()` banner (not just a tooltip) with the OneDrive path
8. **Settings alignment** — Settings tab wrapped in `st.columns([1,6,1])` to narrow it; member rows now have "Name / % ownership" caption headers; labels hidden on inputs use caption headers for context
9. **Consistent spacing** — CSS improvements applied globally: compact metrics, captions, form labels, dividers, number inputs, column gaps

## Next steps
- Test end-to-end with live Firebase (login, add expense, calculator, profit tab)
- Deploy: push to main, Streamlit Cloud picks up the new page automatically
