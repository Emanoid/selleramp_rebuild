"""Assemble the per-UPC output row from product + analytics."""
from __future__ import annotations

from typing import Callable, Optional

from .analytics import competition, fees, pricing, sales, variations, viability
from .config import AppConfig
from .csv_io import InputRow
from .keepa_data import (
    current_buy_box_price,
    is_variation_listing,
    leaf_category_name,
    out_of_stock_pct_30d_buybox,
    package_weight_lbs,
    root_category_name,
    variation_count,
)


def storefront_url(asin: str) -> str:
    return f"https://www.amazon.com/dp/{asin}"


def build_row(
    input_row: InputRow,
    product: Optional[dict],
    cfg: AppConfig,
    fetch_asin: Optional[Callable[[str], Optional[dict]]] = None,
    variations_fetch_max: int = 0,
) -> dict:
    base = {
        "upc": input_row.upc or "",
        "cost": round(input_row.cost, 2),
        "weight_lbs": input_row.weight_lbs,
        "prep_cost": input_row.prep_cost,
    }

    if not product:
        base.update({
            "asin": input_row.asin or "",
            "viability_label": "Pass — not found on Keepa",
            "notes": "No product matched this UPC/ASIN.",
        })
        return base

    asin = product.get("asin") or input_row.asin or ""
    title = product.get("title") or ""
    brand = product.get("brand") or ""
    cat_root = root_category_name(product) or ""
    cat_leaf = leaf_category_name(product) or ""
    is_var = is_variation_listing(product)
    var_count = variation_count(product)

    weight_lbs = input_row.weight_lbs or package_weight_lbs(product)

    rec_price = pricing.recommended_sell_price(product, cfg)
    fba_floor = pricing.current_lowest_fba_new(product)
    any_floor = pricing.current_lowest_live_new(product)
    bb_now = current_buy_box_price(product)
    bb30 = pricing.buybox_30d_avg(product)
    cv = pricing.buybox_volatility_cv(product)
    oos = out_of_stock_pct_30d_buybox(product)

    if rec_price is None:
        notes = []
        if not (product.get("offers") or []):
            notes.append("Keepa returned no offers payload.")
        if oos is not None and oos >= 50:
            notes.append(f"Buy box OOS {oos:.0f}% of last 30d.")
        if is_var:
            notes.append(
                f"Variation child (parent={product.get('parentAsin')}, "
                f"{var_count or '?'} siblings)."
            )
        return {
            **base,
            "asin": asin,
            "title": title,
            "brand": brand,
            "category_root": cat_root,
            "category_leaf": cat_leaf,
            "is_variation": is_var,
            "variation_count": var_count,
            "current_lowest_fba_new": fba_floor,
            "current_lowest_live_new": any_floor,
            "current_buy_box": bb_now,
            "buy_box_30d_avg": bb30,
            "buy_box_volatility_cv": round(cv, 4) if cv is not None else None,
            "buybox_oos_pct_30d": oos,
            "storefront_url": storefront_url(asin),
            "viability_label": "Pass — no recommended price (no live offers)",
            "notes": " ".join(notes) or "Insufficient pricing data.",
        }

    fee_breakdown = fees.compute_fees(product, rec_price, weight_lbs, cfg)
    pr = fees.profit_and_roi(rec_price, input_row.cost, fee_breakdown, input_row.prep_cost or 0.0, cfg)

    dom = competition.dominance(product, cfg)
    bsr = sales.current_bsr(product)
    bsr_p = sales.bsr_pct(product, cfg)
    monthly = sales.monthly_sold(product)

    parent_monthly = None
    viable_var_str = ""
    if is_var and fetch_asin is not None and variations_fetch_max > 0:
        parent_monthly = variations.parent_monthly_sales(product, fetch_asin)
        sib_results = variations.viable_variations(
            product, rec_price, variations_fetch_max, cfg, fetch_asin
        )
        viable_var_str = variations.format_viable(sib_results)

    label = viability.label(
        profit=pr["estimated_profit"],
        roi=pr["roi_pct"],
        bsr_pct=bsr_p,
        fba_seller_count=int(dom["fba_seller_count"]),
        amazon_dominant=bool(dom["amazon_dominant"]),
        brand_dominant=bool(dom["brand_dominant"]),
        cfg=cfg,
        recommended_price=rec_price,
        cost=input_row.cost,
    )

    notes_parts: list[str] = []
    if is_var:
        suffix = ""
        if variations_fetch_max == 0:
            suffix = " Pass --variations N to fetch siblings for parent_monthly_sales / viable_variations."
        notes_parts.append(
            f"Variation child (parent {product.get('parentAsin')}, "
            f"{var_count or '?'} siblings) — metrics are for THIS child only.{suffix}"
        )
    if oos is not None and oos >= 50:
        notes_parts.append(f"Buy box OOS {oos:.0f}% of last 30d.")
    if fba_floor is None and any_floor is not None:
        notes_parts.append(
            f"No live FBA offer; lowest live New is FBM at ${any_floor:.2f} — "
            "you'd typically win buy box as FBA."
        )
    if dom["brand_dominant"]:
        notes_parts.append(
            f"Brand-dominance heuristic matched {dom['top_buybox_seller_name']} "
            f"({dom['brand_match_share_pct']}%) — verify manually."
        )
    if bsr_p is None and bsr is not None:
        notes_parts.append("BSR% unknown (no category size in config) — raw BSR shown.")
    if fees.fba_fulfillment_fee(product) is None:
        notes_parts.append("FBA fee from local fallback table.")

    return {
        **base,
        "asin": asin,
        "title": title,
        "brand": brand,
        "category_root": cat_root,
        "category_leaf": cat_leaf,
        "is_variation": is_var,
        "variation_count": var_count,
        "viable_variations": viable_var_str,
        "weight_lbs": round(weight_lbs, 3) if weight_lbs else None,
        "inbound_cost": fee_breakdown["inbound_cost"],
        "prep_cost": pr["prep_cost"],
        "current_lowest_fba_new": fba_floor,
        "current_lowest_live_new": any_floor,
        "current_buy_box": bb_now,
        "buy_box_30d_avg": bb30,
        "buy_box_volatility_cv": round(cv, 4) if cv is not None else None,
        "buybox_oos_pct_30d": oos,
        "recommended_sell_price": rec_price,
        "referral_fee": fee_breakdown["referral_fee"],
        "fba_fulfillment_fee": fee_breakdown["fba_fulfillment_fee"],
        "misc_fee": fee_breakdown["misc_fee"],
        "total_fees": fee_breakdown["total_amazon_fees"],
        "estimated_profit": pr["estimated_profit"],
        "roi_pct": round(pr["roi_pct"] * 100, 2) if pr["roi_pct"] is not None else None,
        "monthly_sales": monthly,
        "parent_monthly_sales": parent_monthly,
        "bsr": bsr,
        "bsr_pct": round(bsr_p * 100, 3) if bsr_p is not None else None,
        "live_fba_seller_count": dom["fba_seller_count"],
        "live_fbm_seller_count": dom["fbm_seller_count"],
        "top_buybox_seller_name": dom["top_buybox_seller_name"],
        "top_buybox_seller_share_pct": dom["top_buybox_seller_share_pct"],
        "amazon_buybox_share_pct": dom["amazon_buybox_share_pct"],
        "amazon_dominant": dom["amazon_dominant"],
        "brand_dominant": dom["brand_dominant"],
        "dominance_label": dom["dominance_label"],
        "storefront_url": storefront_url(asin),
        "viability_label": label,
        "notes": " ".join(notes_parts),
    }
