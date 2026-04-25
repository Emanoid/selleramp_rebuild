from datetime import datetime, timedelta, timezone

from sa_rebuild.analytics import competition
from sa_rebuild.config import AppConfig
from sa_rebuild.keepa_data import KEEPA_EPOCH_MINUTES


AMZ = "ATVPDKIKX0DER"


def _ktm(dt: datetime) -> int:
    return int(dt.timestamp() // 60) - KEEPA_EPOCH_MINUTES


def _hist(samples):
    out = []
    for dt, sid in samples:
        out.append(_ktm(dt))
        out.append(sid)
    return out


def _live_offer(sid: str, *, fba: bool, condition: int = 1):
    now = datetime.now(tz=timezone.utc)
    return {
        "sellerId": sid,
        "sellerName": sid,
        "isFBA": fba,
        "condition": condition,
        "lastSeen": _ktm(now),
    }


def test_amazon_dominance_flagged_when_share_above_threshold():
    now = datetime.now(tz=timezone.utc)
    samples = [(now - timedelta(days=d), AMZ) for d in range(80, 0, -1)]
    samples += [(now - timedelta(days=d), "A_OTHER") for d in range(10, 0, -1)]
    product = {"buyBoxSellerIdHistory": _hist(samples), "offers": [], "brand": ""}
    out = competition.dominance(product, AppConfig())
    assert out["amazon_dominant"] is True
    assert out["dominance_label"] == "Amazon dominant"


def test_brand_dominance_heuristic_matches_when_seller_name_resembles_brand():
    now = datetime.now(tz=timezone.utc)
    samples = [(now - timedelta(days=d), "SELLER_NINTENDO") for d in range(90, 5, -1)]
    samples += [(now - timedelta(days=d), AMZ) for d in range(5, 0, -1)]
    product = {
        "buyBoxSellerIdHistory": _hist(samples),
        "offers": [
            {
                "sellerId": "SELLER_NINTENDO",
                "sellerName": "Nintendo of America Inc.",
                "isFBA": True,
                "condition": 1,
                "lastSeen": _ktm(now),
            }
        ],
        "liveOffersOrder": [0],
        "brand": "Nintendo",
    }
    out = competition.dominance(product, AppConfig())
    assert out["brand_dominant"] is True


def test_fba_seller_count_uses_live_offers_only():
    now = datetime.now(tz=timezone.utc)
    # 100 FBA offers in payload, but only 2 marked live.
    offers = [_live_offer(f"S{i}", fba=True) for i in range(100)]
    product = {
        "buyBoxSellerIdHistory": [],
        "offers": offers,
        "liveOffersOrder": [3, 17],
        "brand": "Acme",
    }
    out = competition.dominance(product, AppConfig())
    assert out["fba_seller_count"] == 2
    assert out["fbm_seller_count"] == 0


def test_fbm_seller_count_separated_from_fba():
    now = datetime.now(tz=timezone.utc)
    offers = [_live_offer("S1", fba=False), _live_offer("S2", fba=True)]
    product = {
        "buyBoxSellerIdHistory": [],
        "offers": offers,
        "liveOffersOrder": [0, 1],
        "brand": "Acme",
    }
    out = competition.dominance(product, AppConfig())
    assert out["fba_seller_count"] == 1
    assert out["fbm_seller_count"] == 1
