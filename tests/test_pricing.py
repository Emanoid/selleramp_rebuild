from datetime import datetime, timedelta, timezone

from sa_rebuild.analytics import pricing
from sa_rebuild.config import AppConfig
from sa_rebuild.keepa_data import CSV_BUY_BOX_SHIPPING, KEEPA_EPOCH_MINUTES


def _ktm(dt: datetime) -> int:
    return int(dt.timestamp() // 60) - KEEPA_EPOCH_MINUTES


def _build_csv_pairs(samples):
    flat = []
    for dt, usd in samples:
        flat.append(_ktm(dt))
        flat.append(int(round(usd * 100)))
    return flat


def _stats_with_avg30(usd: float | None, current_bb_usd: float | None = None):
    """Build a stats dict with avg30[18] populated."""
    avg30 = [-1] * 19
    avg30[CSV_BUY_BOX_SHIPPING] = int(round(usd * 100)) if usd is not None else -1
    current = [-1] * 19
    current[CSV_BUY_BOX_SHIPPING] = int(round(current_bb_usd * 100)) if current_bb_usd is not None else -1
    return {"avg30": avg30, "current": current}


def _product(*, avg30=None, current_bb=None, offers=None, live=None):
    p = {"csv": [None] * 19, "stats": _stats_with_avg30(avg30, current_bb), "offers": offers or []}
    if live is not None:
        p["liveOffersOrder"] = live
    return p


def test_recommended_uses_30d_avg_when_avg30_above_or_equal_current():
    # avg30=$50, current=$45 -> avg30 >= current_bb, use avg30 ($50)
    p = _product(avg30=50.0, current_bb=45.0)
    assert pricing.recommended_sell_price(p, AppConfig()) == 50.00


def test_recommended_hedges_to_mean_when_avg30_below_current():
    # avg30=$40, current=$60 -> avg30 < current_bb, use mean ($50)
    p = _product(avg30=40.0, current_bb=60.0)
    assert pricing.recommended_sell_price(p, AppConfig()) == 50.00


def test_recommended_falls_back_to_current_when_no_avg30():
    p = _product(avg30=None, current_bb=64.0)
    assert pricing.recommended_sell_price(p, AppConfig()) == 64.00


def test_recommended_falls_back_to_avg30_when_no_current_bb():
    p = _product(avg30=49.96, current_bb=None)
    assert pricing.recommended_sell_price(p, AppConfig()) == 49.96


def _offer(*, fba: bool, price_usd: float, ship_usd: float = 0.0, condition: int = 1, sid: str = "S"):
    now = datetime.now(tz=timezone.utc)
    return {
        "isFBA": fba,
        "condition": condition,
        "sellerId": sid,
        "lastSeen": _ktm(now),
        "offerCSV": [_ktm(now), int(price_usd * 100), int(ship_usd * 100)],
    }


def test_recommended_ultimate_fallback_is_lowest_current_listing():
    """No buy box history at all -> use lowest live listing."""
    p = _product(avg30=None, current_bb=None,
                 offers=[_offer(fba=False, price_usd=64.0)], live=[0])
    assert pricing.recommended_sell_price(p, AppConfig()) == 64.00


def test_recommended_returns_none_when_no_data_at_all():
    p = _product(avg30=None, current_bb=None, offers=[], live=[])
    assert pricing.recommended_sell_price(p, AppConfig()) is None
