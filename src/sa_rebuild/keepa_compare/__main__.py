"""keepa_compare — match a cost CSV against a Keepa export and compute FBA metrics.

No Keepa API key required. Works entirely from a Keepa Product Viewer export file.

Usage (CLI):
    python -m sa_rebuild.keepa_compare <cost.csv> <keepa_export.xlsx|.csv> [-o output.csv]

Public API:
    from sa_rebuild.keepa_compare import run_compare
    df = run_compare(Path("cost.csv"), Path("export.xlsx"))
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

import pandas as pd


# ── Fee constants — mirror SellerAmp profile (see config.yaml) ───────────────

INBOUND_PER_LB = 0.80       # inbound shipping cost per lb
SALES_TAX_PCT  = 0.0663     # sales tax applied to sell price (misc in SellerAmp)
REFERRAL_DEFAULT = 0.15     # fallback referral fee when Keepa doesn't provide one
MIN_PROFIT_USD = 1.00       # minimum profit for "Recommend"
MIN_ROI        = 0.30       # minimum ROI (30%) for "Recommend"

# FBA fulfillment fee fallback tier table (max_weight_lbs → fee USD)
# Used only when Keepa's "FBA Pick&Pack Fee" column is empty.
_FBA_TIERS = [
    (0.25, 3.06), (0.5, 3.34), (0.75, 3.60),
    (1.0,  3.71), (1.5, 4.31), (2.0, 4.83), (3.0, 5.45),
]


# ── Price columns in relevance order (buybox → amazon → FBA new → all others) ─

PRICE_COLS: list[str] = [
    "Buy Box: Current",
    "Buy Box: 90 days avg.",
    "Amazon: Current",
    "Amazon: 90 days avg.",
    "New, 3rd Party FBA: Current",
    "New, 3rd Party FBA: 90 days avg.",
    "New: Current",
    "New: 90 days avg.",
    "New, 3rd Party FBM: Current",
    "New, 3rd Party FBM: 90 days avg.",
    "New, Prime exclusive: Current",
    "New, Prime exclusive: 90 days avg.",
    "Lightning Deals: Current",
    "Buy Box: Strikethrough Price",
    "List Price: Current",
    "List Price: 90 days avg.",
    "eBay New: Current",
    "eBay New: 90 days avg.",
    "eBay Used: Current",
    "eBay Used: 90 days avg.",
    "Buy Box Used: Current",
    "Buy Box Used: 90 days avg.",
    "Used: Current",
    "Used: 90 days avg.",
    "Used, like new: Current",
    "Used, like new: 90 days avg.",
    "Used, very good: Current",
    "Used, very good: 90 days avg.",
    "Used, good: Current",
    "Used, good: 90 days avg.",
    "Used, acceptable: Current",
    "Used, acceptable: 90 days avg.",
    "Warehouse Deals: Current",
    "Warehouse Deals: 90 days avg.",
]

# Keepa source columns consumed explicitly — excluded from the trailing block
# so they don't appear twice in the output.
_CONSUMED_KEEPA: frozenset[str] = frozenset(PRICE_COLS) | {
    "Title",
    "ASIN",
    "Imported by Code",
    "Package: Weight (g)",
    "Item: Weight (g)",
    "URL: URL slug",
    "Product Codes: UPC",
    "FBA Pick&Pack Fee",
    "Referral Fee %",
    "Referral Fee based on current Buy Box price",
}


# ── Numeric / code helpers ────────────────────────────────────────────────────

def _num(v) -> Optional[float]:
    """Parse any value to float, returning None for empty/NaN."""
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    try:
        return float(str(v).strip().rstrip("%"))
    except (ValueError, TypeError):
        return None


# Patterns used exclusively for repairing input CSV codes at read time.
# NOT applied to Keepa export data (which is already well-formatted).
_SCI_NOTATION = re.compile(r"^[+\-]?[\d.]+[eE][+\-]?\d+$")
_PURE_FLOAT   = re.compile(r"^[+\-]?\d+\.\d*$")


def _repair_input_code(v) -> str:
    """Repair Excel/CSV mangling of a UPC or ASIN from the user's input file.

    Only called on the cost CSV — never on Keepa export data, which is
    already clean and would risk false transformations if run through this.

    Cases handled:
    - Scientific notation  "8.83503E+11"    → "883503000000"
    - Float suffix         "701619100159.0" → "701619100159"

    ASINs (e.g. "B08N5WRWNW") contain letters so neither numeric pattern
    matches — they pass through unchanged.
    Precision loss is safe: UPC-A (12 digits) / EAN-13 / EAN-14 (13–14 digits)
    are all within float64's 15–16 significant digit range.
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", ""):
        return ""
    if _SCI_NOTATION.match(s):
        try:
            return str(int(float(s)))
        except (ValueError, OverflowError):
            pass
    if _PURE_FLOAT.match(s):
        try:
            return str(int(float(s)))
        except (ValueError, OverflowError):
            pass
    return s


def _norm_code(v) -> str:
    """Normalize a UPC/ASIN/EAN to uppercase alphanumeric for comparison.

    Strips leading zeros so that Excel-truncated codes (e.g. 29992001000)
    match the full form with a leading zero (029992001000). Both sides of the
    lookup use this function so the stripping is symmetric.
    Returns empty string for None/NaN/blank.
    """
    raw = re.sub(r"[^0-9A-Za-z]", "", str(v or "")).upper()
    if not raw or raw in ("NAN", "NONE", "NA", "NULL"):
        return ""
    # lstrip("0") is safe: ASINs start with letters so are unaffected;
    # all-zero edge case returns "0".
    stripped = raw.lstrip("0")
    return stripped if stripped else "0"


def _g_to_lbs(grams) -> Optional[float]:
    v = _num(grams)
    return round(v / 453.592, 4) if v and v > 0 else None


def _fba_fee_fallback(weight_lbs: Optional[float]) -> float:
    """Conservative FBA fee estimate when Keepa doesn't publish a Pick&Pack fee."""
    if not weight_lbs or weight_lbs <= 0:
        return 4.00
    for cap, fee in _FBA_TIERS:
        if weight_lbs <= cap:
            return fee
    over = max(0.0, weight_lbs - 3.0)
    return round(5.45 + 0.16 * (over * 4), 2)


# ── Recommended sell price (mirrors fba/analytics/pricing.py) ────────────────

def _rec_price(krow: pd.Series) -> Optional[float]:
    """
    Pricing rule (same as Keepa Search Tool):
      1. Anchor on Buy Box 90-day average.
      2. If avg30 < current BB (market spiked up) → use mean(avg30, current) to avoid
         chasing the spike.
      3. If avg30 >= current BB (stable or dipping) → use avg30 directly.
      4. No buy-box data → fall back to FBA New current, then any New current.
    """
    avg30  = _num(krow.get("Buy Box: 90 days avg."))
    cur_bb = _num(krow.get("Buy Box: Current"))
    fba    = _num(krow.get("New, 3rd Party FBA: Current"))
    new    = _num(krow.get("New: Current"))

    if avg30 is not None and cur_bb is not None:
        return round((avg30 + cur_bb) / 2.0, 2) if avg30 < cur_bb else round(avg30, 2)
    if avg30   is not None: return round(avg30,  2)
    if cur_bb  is not None: return round(cur_bb, 2)
    if fba     is not None: return round(fba,    2)
    if new     is not None: return round(new,    2)
    return None


# ── Fee computation (mirrors fba/analytics/fees.py) ──────────────────────────

def _compute_fees(sell: float, cost: float, weight_lbs: Optional[float],
                  krow: pd.Series) -> dict:
    """
    Returns fee breakdown dict plus _profit and _roi private keys.
    Uses Keepa's 'Referral Fee %' and 'FBA Pick&Pack Fee' when available;
    falls back to config defaults otherwise.
    """
    ref_raw = _num(krow.get("Referral Fee %"))
    if ref_raw is None:
        ref_pct = REFERRAL_DEFAULT
    elif ref_raw > 1:
        ref_pct = ref_raw / 100.0   # Keepa sometimes stores as e.g. 12.0
    else:
        ref_pct = ref_raw            # stored as 0.12

    fba_raw = _num(krow.get("FBA Pick&Pack Fee"))
    fba_ff  = fba_raw if fba_raw is not None else _fba_fee_fallback(weight_lbs)

    referral   = round(sell * ref_pct, 2)
    sales_tax  = round(sell * SALES_TAX_PCT, 2)
    inbound    = round((weight_lbs or 0.0) * INBOUND_PER_LB, 2)
    total_amz  = round(referral + fba_ff + sales_tax, 2)
    total_out  = round(cost + inbound, 2)
    profit     = round(sell - cost - total_amz - inbound, 2)
    roi        = round(profit / total_out, 4) if total_out > 0 else None

    return {
        "Fee: Referral Fee":       referral,
        "Fee: FBA Pick&Pack":      round(fba_ff, 2),
        "Fee: Sales Tax":          sales_tax,
        "Fee: Inbound Cost":       inbound,
        "Fee: Total Amazon Fees":  total_amz,
        "_profit": profit,
        "_roi":    roi,
    }


_FEE_COLS = [
    "Fee: Referral Fee",
    "Fee: FBA Pick&Pack",
    "Fee: Sales Tax",
    "Fee: Inbound Cost",
    "Fee: Total Amazon Fees",
]


# ── Keepa index ───────────────────────────────────────────────────────────────

def build_index(df: pd.DataFrame) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """
    Build lookup indexes from the Keepa export DataFrame.

    asin_idx: normalized ASIN → list of row positions
    upc_idx:  normalized UPC/EAN → list of row positions
        - "Imported by Code" is the primary UPC field (the code the user searched in Keepa)
        - "Product Codes: UPC" is a comma-separated list of all known UPCs for the product;
          any one matching is sufficient.
    """
    asin_idx: dict[str, list[int]] = {}
    upc_idx:  dict[str, list[int]] = {}

    for pos in range(len(df)):
        row = df.iloc[pos]

        asin = _norm_code(row.get("ASIN"))
        if asin:
            asin_idx.setdefault(asin, []).append(pos)

        imp = _norm_code(row.get("Imported by Code"))
        if imp:
            upc_idx.setdefault(imp, []).append(pos)

        for part in str(row.get("Product Codes: UPC") or "").split(","):
            u = _norm_code(part)
            if u:
                upc_idx.setdefault(u, []).append(pos)

    return asin_idx, upc_idx


def _weight_dist(krow: pd.Series, input_lbs: Optional[float]) -> float:
    """Absolute difference (lbs) between Keepa's package weight and the input weight."""
    if input_lbs is None:
        return 9999.0
    pkg = _g_to_lbs(krow.get("Package: Weight (g)")) or _g_to_lbs(krow.get("Item: Weight (g)"))
    return abs(pkg - input_lbs) if pkg is not None else 9999.0


def find_matches(inp: dict, asin_idx: dict, upc_idx: dict,
                 df: pd.DataFrame) -> list[int]:
    """
    Return all matching Keepa row positions for an input row.

    Matching priority:
      1. ASIN match (exact, normalized) — if input.asin is provided.
      2. UPC match — checks "Imported by Code" and every value in
         "Product Codes: UPC" (comma-separated); any single match is enough.

    Results are sorted by weight distance (closest weight first) so that
    when multiple ASINs share a UPC, the most likely physical match appears first.
    Each matching ASIN produces its own output row.
    """
    asin_in  = _norm_code(inp.get("asin"))
    upc_in   = _norm_code(inp.get("upc"))
    inp_lbs  = _num(inp.get("weight_lbs"))

    if asin_in:
        raw = asin_idx.get(asin_in, [])
    elif upc_in:
        seen: set[int] = set()
        raw = []
        for pos in upc_idx.get(upc_in, []):
            if pos not in seen:
                seen.add(pos)
                raw.append(pos)
    else:
        return []

    return sorted(raw, key=lambda p: _weight_dist(df.iloc[p], inp_lbs))


# ── Output row builder ────────────────────────────────────────────────────────

def _build_row(inp: dict, krow: Optional[pd.Series], keepa_cols: list[str]) -> dict:
    cost       = _num(inp.get("cost"))
    weight_lbs = _num(inp.get("weight_lbs"))
    out: dict  = {}

    # Decision block
    rec_price = _rec_price(krow) if krow is not None else None
    fees: dict = {}
    profit = roi = None
    decision = "Not Recommend"

    if rec_price is not None and cost is not None:
        fees   = _compute_fees(rec_price, cost, weight_lbs, krow)
        profit = fees.pop("_profit")
        roi    = fees.pop("_roi")
        if profit >= MIN_PROFIT_USD and roi is not None and roi >= MIN_ROI:
            decision = "Recommend"

    out["Investment Decision"]      = decision
    out["Recommended Selling Price"] = rec_price
    out["ROI"]                      = f"{roi * 100:.1f}%" if roi is not None else None
    out["Estimated Profit"]         = profit
    out["Wholesale Cost"]            = inp.get("cost")

    # Price columns
    for col in PRICE_COLS:
        out[col] = _num(krow.get(col)) if krow is not None else None

    # Diff columns (price − your cost)
    for col in PRICE_COLS:
        v = out[col]
        out[f"Diff: {col}"] = (
            round(v - cost, 2) if v is not None and cost is not None else None
        )

    # Fee breakdown
    for k in _FEE_COLS:
        out[k] = fees.get(k)

    # Weight block
    pkg_g  = _num(krow.get("Package: Weight (g)")) if krow is not None else None
    item_g = _num(krow.get("Item: Weight (g)"))    if krow is not None else None
    out["Keepa Package Weight (g)"]   = pkg_g
    out["Keepa Package Weight (lbs)"] = round(pkg_g / 453.592, 3) if pkg_g else None
    out["Keepa Item Weight (g)"]      = item_g
    out["Input Weight (lbs)"]         = weight_lbs
    out["Weight Distance (lbs)"]      = (
        round(_weight_dist(krow, weight_lbs), 3) if krow is not None else None
    )

    # Item description + link
    matched_asin = str(krow.get("ASIN") or "").strip() if krow is not None else ""
    out["Title"]        = krow.get("Title") if krow is not None else "NO MATCH FOUND"
    out["Amazon URL"]   = f"https://www.amazon.com/dp/{matched_asin}" if matched_asin else None
    out["Matched ASIN"] = matched_asin or None

    # Input identifiers
    out["Input UPC"]  = inp.get("upc")
    out["Input ASIN"] = inp.get("asin")

    # Remaining Keepa columns not already consumed above
    if krow is not None:
        for col in keepa_cols:
            if col not in _CONSUMED_KEEPA and col not in out:
                out[col] = krow.get(col)

    return out


# ── Final column ordering ─────────────────────────────────────────────────────

def _col_order(keepa_cols: list[str]) -> list[str]:
    diff_cols   = [f"Diff: {c}" for c in PRICE_COLS]
    weight_cols = [
        "Keepa Package Weight (g)", "Keepa Package Weight (lbs)",
        "Keepa Item Weight (g)", "Input Weight (lbs)", "Weight Distance (lbs)",
    ]
    desc_cols   = ["Title", "Amazon URL", "Matched ASIN"]
    id_cols     = ["Input UPC", "Input ASIN"]
    remaining   = [c for c in keepa_cols if c not in _CONSUMED_KEEPA]

    return (
        ["Investment Decision", "Recommended Selling Price", "ROI", "Estimated Profit", "Wholesale Cost"]
        + PRICE_COLS
        + _FEE_COLS
        + weight_cols
        + desc_cols
        + id_cols
        + remaining
        + diff_cols   # diffs last — reference columns
    )


# ── Public API ────────────────────────────────────────────────────────────────

def run_compare(cost_path: Path, keepa_path: Path) -> pd.DataFrame:
    """
    Load both files, match every input row against the Keepa export, and return
    a fully analysed DataFrame ready to write to CSV.

    Multiple ASINs sharing the same UPC produce multiple output rows (one per ASIN),
    sorted by weight distance from the input weight — closest physical match first.
    """
    cost_df = pd.read_csv(cost_path, dtype=str)
    cost_df.columns = [c.strip().lower().replace(" ", "_") for c in cost_df.columns]
    # Repair Excel-mangled UPC/ASIN values (scientific notation, float suffixes)
    # only on input data — Keepa export is already clean.
    for col in ("upc", "asin"):
        if col in cost_df.columns:
            cost_df[col] = cost_df[col].map(_repair_input_code)

    if keepa_path.suffix.lower() in (".xlsx", ".xls"):
        keepa_df = pd.read_excel(keepa_path, dtype=str)
    else:
        keepa_df = pd.read_csv(keepa_path, dtype=str)
    keepa_cols = list(keepa_df.columns)

    asin_idx, upc_idx = build_index(keepa_df)
    col_order = _col_order(keepa_cols)

    rows_out: list[dict] = []
    for _, irow in cost_df.iterrows():
        inp     = dict(irow)
        matches = find_matches(inp, asin_idx, upc_idx, keepa_df)
        if not matches:
            rows_out.append(_build_row(inp, None, keepa_cols))
        else:
            for pos in matches:
                rows_out.append(_build_row(inp, keepa_df.iloc[pos], keepa_cols))

    out_df = pd.DataFrame(rows_out)
    for col in col_order:
        if col not in out_df.columns:
            out_df[col] = None

    final = [c for c in col_order if c in out_df.columns]
    extra = [c for c in out_df.columns if c not in final]
    return out_df[final + extra]


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description="Match a cost CSV against a Keepa Product Viewer export.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m sa_rebuild.keepa_compare my_products.csv KeepaExport.xlsx
  python -m sa_rebuild.keepa_compare my_products.csv KeepaExport.csv -o analysis.csv
        """,
    )
    p.add_argument("cost_csv",   help="Input CSV: upc/asin, cost, weight_lbs columns")
    p.add_argument("keepa_file", help="Keepa Product Viewer export (.xlsx or .csv)")
    p.add_argument("-o", "--output", default="keepa_compare_output.csv",
                   help="Output CSV path (default: keepa_compare_output.csv)")
    args = p.parse_args()

    result = run_compare(Path(args.cost_csv), Path(args.keepa_file))
    result.to_csv(args.output, index=False)
    print(f"Written {len(result)} rows → {args.output}")


if __name__ == "__main__":
    main()
