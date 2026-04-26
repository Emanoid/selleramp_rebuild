"""CSV input parsing + append-on-row output writing."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class InputRow:
    row_id: int
    upc: Optional[str] = None
    asin: Optional[str] = None
    cost: float = 0.0
    weight_lbs: Optional[float] = None
    prep_cost: Optional[float] = None

    @property
    def lookup_key(self) -> str:
        """The identifier we send to Keepa — ASIN preferred when both are present."""
        return self.asin or self.upc or ""

    @property
    def lookup_is_asin(self) -> bool:
        return bool(self.asin)


REPORT_COLUMNS: List[str] = [
    "upc",
    "asin",
    "title",
    "brand",
    "category_root",
    "category_leaf",
    "is_variation",
    "variation_count",
    "viable_variations",
    "cost",
    "weight_lbs",
    "inbound_cost",
    "prep_cost",
    "current_lowest_fba_new",
    "current_lowest_live_new",
    "current_buy_box",
    "buy_box_30d_avg",
    "buy_box_volatility_cv",
    "buybox_oos_pct_30d",
    "recommended_sell_price",
    "referral_fee",
    "fba_fulfillment_fee",
    "misc_fee",
    "total_fees",
    "estimated_profit",
    "roi_pct",
    "monthly_sales",
    "parent_monthly_sales",
    "bsr",
    "bsr_pct",
    "live_fba_seller_count",
    "live_fbm_seller_count",
    "top_buybox_seller_name",
    "top_buybox_seller_share_pct",
    "amazon_buybox_share_pct",
    "amazon_dominant",
    "brand_dominant",
    "dominance_label",
    "storefront_url",
    "viability_label",
    "notes",
]


# Plain-language column meanings written as the FIRST data row of the report.
# Keep one tight sentence per column; consumers can skip this row by filtering
# upc == "[COLUMN HELP — skip this row]" or via `pd.read_csv(..., skiprows=[1])`.
COLUMN_DESCRIPTIONS: dict[str, str] = {
    "upc": "[COLUMN HELP — skip this row] The UPC/EAN you supplied.",
    "asin": "Amazon's product ID Keepa matched to this UPC (or that you supplied directly).",
    "title": "Product title from Amazon.",
    "brand": "Brand name from Amazon.",
    "category_root": "Top-level Amazon category (e.g., 'Clothing, Shoes & Jewelry').",
    "category_leaf": "Most specific Amazon category (e.g., 'Mules & Clogs') — used for BSR%.",
    "is_variation": "True if this ASIN is a child of a variation parent (size/color sibling exists).",
    "variation_count": "Number of sibling variations under the parent listing.",
    "viable_variations": "Sibling ASINs whose current buy box >= recommended sell price AND total live sellers < max_seller_count. Format: 'asin (attrs)'. Empty when --variations N is not set.",
    "cost": "Your wholesale cost per unit (from input CSV).",
    "weight_lbs": "Per-unit weight used for inbound shipping math. From input column if given, else Keepa's package weight.",
    "inbound_cost": "weight_lbs × inbound_per_lb_usd ($0.80/lb in your profile).",
    "prep_cost": "Per-unit prep cost from input CSV.",
    "current_lowest_fba_new": "Cheapest currently-live FBA New offer in $USD. Blank if no live FBA offers.",
    "current_lowest_live_new": "Cheapest currently-live New offer of ANY fulfillment (FBA or FBM).",
    "current_buy_box": "Buy-box price right now (with shipping). Blank when buy box is empty.",
    "buy_box_30d_avg": "Time-weighted mean buy-box price over the last 30 days.",
    "buy_box_volatility_cv": "Coefficient of variation (stddev/mean) of buy-box price over last 90d. <0.05 = stable.",
    "buybox_oos_pct_30d": "% of last 30 days the buy box was empty (no one was eligible to win it).",
    "recommended_sell_price": "Anchor on 30d avg buy box. If avg30 < current_buy_box, use mean(avg30, current_buy_box). Fallback: lowest current listing.",
    "referral_fee": "Amazon's referral fee = sell_price × referral_pct (config override > Keepa value > 15% default).",
    "fba_fulfillment_fee": "Amazon's FBA pick-and-pack fee. Keepa's value when present, else local weight-tier fallback.",
    "misc_fee": "Configurable misc fee on sell price (6.63% in your profile, mirrors SellerAmp Misc Fee %).",
    "total_fees": "referral_fee + fba_fulfillment_fee + misc_fee (Amazon-side fees only).",
    "estimated_profit": "sell_price − cost − total_fees − inbound_cost − prep_cost.",
    "roi_pct": "estimated_profit ÷ (cost + inbound_cost + prep_cost), as a percent.",
    "monthly_sales": "Estimated units sold per month for THIS ASIN (the variation child). Source priority: Keepa monthlySold → monthlySoldHistory latest → salesRankDrops30 lower bound.",
    "parent_monthly_sales": "Same metric but for the variation parent (sums siblings). Only populated when --variations N>0 since it costs an extra fetch.",
    "bsr": "Current Best Sellers Rank in the leaf category.",
    "bsr_pct": "bsr ÷ leaf-category size × 100, as a percent. <2% means top 2% — fast mover.",
    "live_fba_seller_count": "Distinct FBA-New sellers currently live.",
    "live_fbm_seller_count": "Distinct FBM-New sellers currently live.",
    "top_buybox_seller_name": "Seller (or seller ID) that won the buy box most often in the last 30 days.",
    "top_buybox_seller_share_pct": "% of last-30d buy-box samples won by the top seller above.",
    "amazon_buybox_share_pct": "% of last-90d buy-box samples won by Amazon itself.",
    "amazon_dominant": "True if Amazon held the buy box ≥ 70% of last 90 days. You can't compete here.",
    "brand_dominant": "Heuristic — True if a single 3P seller whose name resembles the brand held buy box ≥ 60% of last 90 days. Verify manually.",
    "dominance_label": "'Amazon dominant' / 'Brand dominant (heuristic)' / 'Open'.",
    "storefront_url": "Click-through to the Amazon listing.",
    "viability_label": "Buy / Caution — thin margin / Caution — crowded / Skip — Below cost / Skip — Amazon dominant / Skip — Brand dominant / Skip — Slow seller / Pass.",
    "notes": "Free-text caveats: variation child, buy-box gone for X% of 30d, FBA fallback fee used, etc.",
}


def _parse_float(s: str) -> Optional[float]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def read_input(path: Path | str) -> List[InputRow]:
    """Accept CSVs with `upc` and/or `asin`. At least one must be present per row."""
    rows: List[InputRow] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = set(reader.fieldnames or [])
        if "cost" not in fields:
            raise ValueError(f"Input CSV must have a 'cost' column. Got: {reader.fieldnames}")
        if "upc" not in fields and "asin" not in fields:
            raise ValueError(
                f"Input CSV must have at least one of 'upc' or 'asin'. Got: {reader.fieldnames}"
            )
        for idx, raw in enumerate(reader):
            upc = (raw.get("upc") or "").strip() or None
            asin = (raw.get("asin") or "").strip() or None
            if not upc and not asin:
                continue
            cost = _parse_float(raw.get("cost", ""))
            if cost is None:
                continue
            rows.append(
                InputRow(
                    row_id=idx,
                    upc=upc,
                    asin=asin,
                    cost=cost,
                    weight_lbs=_parse_float(raw.get("weight_lbs", "")),
                    prep_cost=_parse_float(raw.get("prep_cost", "")),
                )
            )
    return rows


class ReportWriter:
    """Append-on-row writer — file is usable mid-run.

    With include_descriptions=True (default), a column-help row is inserted
    immediately after the header on first write.

    `allow_resume`: when True, opening an existing file appends to it (resume
    semantics). When False (default), opening an existing file raises — this
    catches the bug where two parallel runs land on the same timestamped
    output path and silently double-write.
    """

    def __init__(self, path: Path | str, include_descriptions: bool = True,
                 allow_resume: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fresh = not self.path.exists()
        if not self._fresh and not allow_resume:
            raise FileExistsError(
                f"Refusing to append to existing report {self.path}. "
                "Pass allow_resume=True to deliberately continue an interrupted run, "
                "or use a unique output path."
            )
        self._fh = self.path.open("a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
        if self._fresh:
            self._writer.writeheader()
            if include_descriptions:
                self._writer.writerow({c: COLUMN_DESCRIPTIONS.get(c, "") for c in REPORT_COLUMNS})
            self._fh.flush()

    def write(self, row: dict) -> None:
        self._writer.writerow(row)
        self._fh.flush()

    def write_many(self, rows: Iterable[dict]) -> None:
        for r in rows:
            self.write(r)

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> "ReportWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
