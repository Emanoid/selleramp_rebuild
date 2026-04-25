"""Composite viability label per row."""
from __future__ import annotations

from typing import Optional

from ..config import AppConfig


def label(
    *,
    profit: Optional[float],
    roi: Optional[float],
    bsr_pct: Optional[float],
    fba_seller_count: int,
    amazon_dominant: bool,
    brand_dominant: bool,
    cfg: AppConfig,
    recommended_price: Optional[float] = None,
    cost: Optional[float] = None,
) -> str:
    if recommended_price is not None and cost is not None and recommended_price < cost:
        return "Skip — Sell price below cost"
    if amazon_dominant:
        return "Skip — Amazon dominant"
    if brand_dominant:
        return "Skip — Brand dominant (heuristic)"
    if bsr_pct is not None and bsr_pct > cfg.viability.max_bsr_pct:
        return "Skip — Slow seller"
    if profit is None or roi is None:
        return "Pass — insufficient data"

    competitive = fba_seller_count <= cfg.viability.max_fba_seller_count

    if (
        profit >= cfg.viability.min_profit_usd
        and roi >= cfg.viability.min_roi_pct
        and competitive
    ):
        return "Buy"
    if profit > 0 and competitive:
        return "Caution — thin margin"
    if profit > 0 and not competitive:
        return "Caution — crowded"
    return "Pass"
