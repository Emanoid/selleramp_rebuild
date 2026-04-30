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

## Next steps
- None outstanding for this feature
- Deploy: push to main, Streamlit Cloud picks up the new page automatically
