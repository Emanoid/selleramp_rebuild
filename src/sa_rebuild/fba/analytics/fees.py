"""Fee math — referral, FBA fulfillment, inbound shipping, misc% — mirrors SellerAmp profile."""
from __future__ import annotations

from typing import Optional

from ...config import AppConfig
from ..keepa_data import package_weight_lbs, root_category_name


def _referral_pct(product: dict, cfg: AppConfig) -> float:
    """Resolve referral-fee % with this priority:
      1. config override by root category (lets the user calibrate vs SellerAmp,
         e.g. apparel = 17% even when Keepa generically reports 15%)
      2. Keepa's `referralFeePercent`
      3. config default (15%)
    """
    root = root_category_name(product)
    if root and root in cfg.fees.referral_overrides_by_root_category:
        return cfg.fees.referral_overrides_by_root_category[root]
    rp = product.get("referralFeePercent")
    if rp is not None and rp > 0:
        return float(rp) / 100.0
    return cfg.fees.referral_default_pct


def referral_fee(product: dict, sell_price: float, cfg: AppConfig) -> float:
    return round(sell_price * _referral_pct(product, cfg), 2)


def fba_fulfillment_fee(product: dict) -> Optional[float]:
    """Prefer Keepa's published pickAndPackFee (USD). None if missing -> caller falls back."""
    fees = product.get("fbaFees") or {}
    cents = fees.get("pickAndPackFee")
    if cents is None or cents <= 0:
        return None
    return round(cents / 100.0, 2)


def fba_fulfillment_fee_fallback(weight_lbs: Optional[float]) -> float:
    """Coarse US FBA fallback when Keepa doesn't return a fee.
    Tier table is intentionally conservative — actual fees should come from Keepa.
    """
    if not weight_lbs or weight_lbs <= 0:
        return 4.00
    if weight_lbs <= 0.25:
        return 3.06
    if weight_lbs <= 0.5:
        return 3.34
    if weight_lbs <= 0.75:
        return 3.60
    if weight_lbs <= 1.0:
        return 3.71
    if weight_lbs <= 1.5:
        return 4.31
    if weight_lbs <= 2.0:
        return 4.83
    if weight_lbs <= 3.0:
        return 5.45
    # > 3 lb large standard: 5.45 + 0.16 per 4oz over 3lb
    over = max(0.0, weight_lbs - 3.0)
    return round(5.45 + 0.16 * (over * 4), 2)


def inbound_cost(product: dict, weight_lbs_override: Optional[float], cfg: AppConfig) -> float:
    w = weight_lbs_override if weight_lbs_override else package_weight_lbs(product)
    if not w:
        return 0.0
    return round(w * cfg.fees.inbound_per_lb_usd, 2)


def misc_fee(sell_price: float, cfg: AppConfig) -> float:
    return round(sell_price * cfg.fees.misc_pct + cfg.fees.misc_flat_usd, 2)


def compute_fees(
    product: dict,
    sell_price: float,
    weight_lbs_override: Optional[float],
    cfg: AppConfig,
) -> dict:
    referral = referral_fee(product, sell_price, cfg)
    fba_ff = fba_fulfillment_fee(product)
    if fba_ff is None:
        w = weight_lbs_override if weight_lbs_override else package_weight_lbs(product)
        fba_ff = fba_fulfillment_fee_fallback(w)
    misc = misc_fee(sell_price, cfg)
    inbound = inbound_cost(product, weight_lbs_override, cfg)
    total_amazon = round(referral + fba_ff + misc, 2)
    return {
        "referral_fee": referral,
        "fba_fulfillment_fee": fba_ff,
        "misc_fee": misc,
        "inbound_cost": inbound,
        "total_amazon_fees": total_amazon,
    }


def profit_and_roi(
    sell_price: float,
    cost: float,
    fees: dict,
    prep_cost: float,
    cfg: AppConfig,
) -> dict:
    prep = (prep_cost or 0.0) + cfg.fees.prep_flat_usd
    total_out_of_pocket = round(cost + fees["inbound_cost"] + prep, 2)
    profit = round(sell_price - cost - fees["total_amazon_fees"] - fees["inbound_cost"] - prep, 2)
    roi = round(profit / total_out_of_pocket, 4) if total_out_of_pocket > 0 else None
    return {
        "prep_cost": round(prep, 2),
        "total_out_of_pocket": total_out_of_pocket,
        "estimated_profit": profit,
        "roi_pct": roi,
    }
