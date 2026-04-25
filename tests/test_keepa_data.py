from datetime import datetime, timedelta, timezone

from sa_rebuild.keepa_data import (
    KEEPA_EPOCH_MINUTES,
    is_variation_listing,
    leaf_category_name,
    live_offers,
    out_of_stock_pct_30d_buybox,
    variation_count,
)


def _ktm(dt: datetime) -> int:
    return int(dt.timestamp() // 60) - KEEPA_EPOCH_MINUTES


def test_live_offers_uses_live_offers_order_when_present():
    offers = [{"sellerId": "S1"}, {"sellerId": "S2"}, {"sellerId": "S3"}]
    p = {"offers": offers, "liveOffersOrder": [2, 0]}
    out = live_offers(p)
    assert [o["sellerId"] for o in out] == ["S3", "S1"]


def test_live_offers_falls_back_to_lastSeen_within_48h():
    now = datetime.now(tz=timezone.utc)
    fresh = {"sellerId": "FRESH", "lastSeen": _ktm(now)}
    stale = {"sellerId": "STALE", "lastSeen": _ktm(now - timedelta(days=10))}
    p = {"offers": [fresh, stale]}  # no liveOffersOrder
    out = live_offers(p)
    assert [o["sellerId"] for o in out] == ["FRESH"]


def test_variation_detection():
    parent_only = {"asin": "A", "parentAsin": "P", "variations": []}
    assert is_variation_listing(parent_only) is True
    assert variation_count(parent_only) == 0

    standalone = {"asin": "A", "parentAsin": "A"}
    assert is_variation_listing(standalone) is False


def test_leaf_category_picks_last_in_tree():
    p = {"categoryTree": [{"name": "Clothing"}, {"name": "Shoes"}, {"name": "Mules & Clogs"}]}
    assert leaf_category_name(p) == "Mules & Clogs"


def test_oos_30d_buybox_index_18():
    arr = [-1] * 19
    arr[18] = 56
    p = {"stats": {"outOfStockPercentage30": arr}}
    assert out_of_stock_pct_30d_buybox(p) == 56.0
