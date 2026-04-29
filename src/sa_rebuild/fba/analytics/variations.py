"""Per-variation viability — fetches sibling ASINs and scores them.

Opt-in: each sibling fetch costs ~7 Keepa tokens. Driven by --variations N.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from ...config import AppConfig
from ..keepa_data import current_buy_box_price, iter_variation_asins
from .competition import fba_seller_count, fbm_seller_count
from .pricing import buybox_30d_avg

log = logging.getLogger("sa_rebuild")


def viable_variations(
    parent_or_child: dict,
    main_recommended_price: float,
    fetch_max: int,
    cfg: AppConfig,
    fetch_asin,
) -> List[dict]:
    """Return list of {asin, attributes, buy_box, sellers, viable_bool} for siblings.

    fetch_asin: callable(asin: str) -> dict | None. Caller provides the closure
    so we don't import the client here.
    """
    if fetch_max <= 0 or main_recommended_price is None:
        return []
    siblings = iter_variation_asins(parent_or_child)
    own_asin = parent_or_child.get("asin")
    siblings = [(a, attrs) for a, attrs in siblings if a != own_asin]
    if not siblings:
        return []

    results: List[dict] = []
    for asin, attrs in siblings[:fetch_max]:
        try:
            sib = fetch_asin(asin)
        except Exception as e:
            log.warning("variation fetch failed asin=%s err=%s", asin, e)
            continue
        if not sib:
            continue
        bb = current_buy_box_price(sib) or buybox_30d_avg(sib)
        fba = fba_seller_count(sib)
        fbm = fbm_seller_count(sib)
        total = fba + fbm
        viable = (
            bb is not None
            and bb >= main_recommended_price * cfg.variations.buy_box_min_ratio
            and total < cfg.variations.max_seller_count
        )
        results.append({
            "asin": asin,
            "attributes": attrs,
            "buy_box": bb,
            "sellers": total,
            "viable": viable,
        })
    return results


def format_viable(results: List[dict]) -> str:
    """Pipe-separated list of viable siblings: 'asin (attrs) bb=$X sellers=N'."""
    parts = []
    for r in results:
        if not r["viable"]:
            continue
        bb = f"${r['buy_box']:.2f}" if r["buy_box"] is not None else "—"
        parts.append(f"{r['asin']} ({r['attributes']}) bb={bb} sellers={r['sellers']}")
    return " | ".join(parts)


def parent_monthly_sales(
    parent_or_child: dict,
    fetch_asin,
) -> Optional[int]:
    """Fetch the parent ASIN and return its monthlySold estimate.

    Returns None if not a variation child or fetch fails.
    """
    parent_asin = parent_or_child.get("parentAsin")
    own = parent_or_child.get("asin")
    if not parent_asin or parent_asin == own:
        return None
    try:
        parent = fetch_asin(parent_asin)
    except Exception as e:
        log.warning("parent fetch failed asin=%s err=%s", parent_asin, e)
        return None
    if not parent:
        return None
    from .sales import monthly_sold
    return monthly_sold(parent)
