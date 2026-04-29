"""Buy-box pricing analysis and recommended sell price."""
from __future__ import annotations

from typing import Optional

from ...config import AppConfig
from ..keepa_data import (
    CSV_BUY_BOX_SHIPPING,
    buy_box_history,
    coefficient_of_variation,
    current_buy_box_price,
    filter_window,
    get_stat_avg,
    live_offers,
    new_fba_history,
    offer_current_price_usd,
    percentile,
    time_weighted_mean,
)


def _is_new(offer: dict) -> bool:
    cond = offer.get("condition")
    return cond in (1, "1", None)


def current_lowest_fba_new(product: dict) -> Optional[float]:
    """Cheapest live FBA-New offer in $USD."""
    candidates: list[float] = []
    for o in live_offers(product):
        if not o.get("isFBA") or not _is_new(o):
            continue
        usd = offer_current_price_usd(o)
        if usd is not None:
            candidates.append(usd)
    if candidates:
        return min(candidates)
    return None


def current_lowest_live_new(product: dict) -> Optional[float]:
    """Cheapest live New offer of ANY fulfillment (FBA or FBM)."""
    candidates: list[float] = []
    for o in live_offers(product):
        if not _is_new(o):
            continue
        usd = offer_current_price_usd(o)
        if usd is not None:
            candidates.append(usd)
    if candidates:
        return min(candidates)
    return None


def buybox_30d_avg(product: dict) -> Optional[float]:
    avg = get_stat_avg(product, "avg30", CSV_BUY_BOX_SHIPPING)
    if avg is not None:
        return avg
    series = filter_window(buy_box_history(product), days=30)
    return time_weighted_mean(series)


def buybox_volatility_cv(product: dict, window_days: int = 90) -> Optional[float]:
    series = filter_window(buy_box_history(product), days=window_days)
    return coefficient_of_variation([v for _, v in series])


def recommended_sell_price(product: dict, cfg: AppConfig) -> Optional[float]:
    """Recommended sell price.

    Rule:
      1. Anchor on the 30-day buy-box average.
      2. If that average is BELOW the current buy-box price, market has moved up
         recently — hedge to the mean of (avg30, current_bb) so we don't get too
         greedy chasing the spike.
      3. Otherwise (avg30 >= current_bb, market dipped or unchanged) — use the
         30-day average; don't chase a temporary dip.
      4. If no buy-box data at all, fall back to the lowest current live listing
         (FBA preferred, FBM otherwise).
    """
    avg30 = buybox_30d_avg(product)
    current_bb = current_buy_box_price(product)

    if avg30 is not None and current_bb is not None:
        if avg30 < current_bb:
            return round((avg30 + current_bb) / 2.0, 2)
        return round(avg30, 2)

    if avg30 is not None:
        return round(avg30, 2)
    if current_bb is not None:
        return round(current_bb, 2)

    fba_floor = current_lowest_fba_new(product)
    if fba_floor is not None:
        return round(fba_floor, 2)
    any_floor = current_lowest_live_new(product)
    if any_floor is not None:
        return round(any_floor, 2)
    return None
