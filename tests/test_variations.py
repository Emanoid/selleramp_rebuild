"""Variation viability — opt-in sibling fetching + scoring."""
from datetime import datetime, timezone

from sa_rebuild.analytics import variations
from sa_rebuild.config import AppConfig
from sa_rebuild.keepa_data import CSV_BUY_BOX_SHIPPING, KEEPA_EPOCH_MINUTES


def _ktm(dt: datetime) -> int:
    return int(dt.timestamp() // 60) - KEEPA_EPOCH_MINUTES


def _stats_current_bb(usd: float):
    arr = [-1] * 19
    arr[CSV_BUY_BOX_SHIPPING] = int(round(usd * 100))
    return {"current": arr}


def _live_offer(sid: str, *, fba: bool):
    now = datetime.now(tz=timezone.utc)
    return {"sellerId": sid, "isFBA": fba, "condition": 1, "lastSeen": _ktm(now)}


def _sibling(asin: str, current_bb: float, n_sellers: int, fba: bool = True):
    return {
        "asin": asin,
        "stats": _stats_current_bb(current_bb),
        "offers": [_live_offer(f"S{i}", fba=fba) for i in range(n_sellers)],
        "liveOffersOrder": list(range(n_sellers)),
    }


def test_disabled_when_fetch_max_zero():
    parent = {"asin": "P", "variations": [{"asin": "C1", "attributes": []}]}
    assert variations.viable_variations(parent, 50.0, 0, AppConfig(), lambda a: None) == []


def test_only_returns_siblings_meeting_buybox_and_seller_thresholds():
    parent = {
        "asin": "OWN",
        "variations": [
            {"asin": "OWN", "attributes": []},        # filtered out (own asin)
            {"asin": "GOOD", "attributes": [{"dimension": "Size", "value": "8"}]},
            {"asin": "TOO_CHEAP", "attributes": []},
            {"asin": "TOO_CROWDED", "attributes": []},
        ],
    }
    fixtures = {
        "GOOD": _sibling("GOOD", current_bb=70.0, n_sellers=3),
        "TOO_CHEAP": _sibling("TOO_CHEAP", current_bb=40.0, n_sellers=2),
        "TOO_CROWDED": _sibling("TOO_CROWDED", current_bb=80.0, n_sellers=15),
    }

    def fake_fetch(asin):
        return fixtures.get(asin)

    cfg = AppConfig()
    cfg.variations.max_seller_count = 10
    cfg.variations.buy_box_min_ratio = 1.0

    results = variations.viable_variations(parent, 50.0, 10, cfg, fake_fetch)
    by_asin = {r["asin"]: r for r in results}
    assert by_asin["GOOD"]["viable"] is True
    assert by_asin["TOO_CHEAP"]["viable"] is False     # bb < rec
    assert by_asin["TOO_CROWDED"]["viable"] is False   # too many sellers

    formatted = variations.format_viable(results)
    assert "GOOD" in formatted
    assert "TOO_CHEAP" not in formatted
    assert "TOO_CROWDED" not in formatted


def test_fetch_max_caps_calls():
    parent = {
        "asin": "OWN",
        "variations": [{"asin": f"S{i}", "attributes": []} for i in range(50)],
    }
    calls = []

    def fake_fetch(asin):
        calls.append(asin)
        return _sibling(asin, current_bb=99.0, n_sellers=1)

    variations.viable_variations(parent, 50.0, fetch_max=5, cfg=AppConfig(), fetch_asin=fake_fetch)
    assert len(calls) == 5


def test_parent_monthly_sales_returns_none_for_non_variation():
    p = {"asin": "X", "parentAsin": "X"}
    assert variations.parent_monthly_sales(p, lambda a: None) is None
