"""Sales velocity + BSR percentile."""
from __future__ import annotations

from typing import Optional

from ...config import AppConfig
from ..keepa_data import (
    latest_monthly_sold_history,
    leaf_category_name,
    root_category_name,
)


def monthly_sold(product: dict) -> Optional[int]:
    """Resolve a monthly-units-sold estimate for THIS ASIN (the variation child if applicable).

    Priority:
      1. stats.monthlySold (Amazon's "X+ bought" badge)
      2. monthlySoldHistory latest non-empty value
      3. salesRankDrops30 (lower bound on units sold)
    """
    stats = product.get("stats") or {}
    val = stats.get("monthlySold")
    if val is not None and val >= 0:
        return int(val)
    hist_val = latest_monthly_sold_history(product)
    if hist_val is not None and hist_val >= 0:
        return hist_val
    drops = stats.get("salesRankDrops30")
    if drops is not None and drops >= 0:
        return int(drops)
    return None


def current_bsr(product: dict) -> Optional[int]:
    stats = product.get("stats") or {}
    current = stats.get("current") or []
    if len(current) > 3:
        v = current[3]
        if v not in (None, -1):
            return int(v)
    sr = product.get("salesRanks") or {}
    for _cat, series in sr.items():
        if series and len(series) >= 2:
            last = series[-1]
            if last not in (None, -1):
                return int(last)
    return None


def bsr_pct(product: dict, cfg: AppConfig) -> Optional[float]:
    """BSR / category-size, where category is the LEAF (matches SellerAmp).
    Falls back to root if leaf size unknown. Returns None if no size info available.
    """
    bsr = current_bsr(product)
    if bsr is None or bsr <= 0:
        return None
    leaf = leaf_category_name(product)
    if leaf:
        size = cfg.category_sizes.get(leaf)
        if size:
            return round(bsr / size, 6)
    root = root_category_name(product)
    if root:
        size = cfg.category_sizes.get(root)
        if size:
            return round(bsr / size, 6)
    return None
