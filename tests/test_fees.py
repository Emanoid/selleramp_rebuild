"""Parity tests for fee math against the user's SellerAmp 'FBA' profile."""
from sa_rebuild.fba.analytics import fees
from sa_rebuild.config import AppConfig


def _cfg():
    cfg = AppConfig()
    # Match user's profile values explicitly so the test is self-documenting.
    cfg.fees.inbound_per_lb_usd = 0.80
    cfg.fees.misc_pct = 0.0663
    cfg.fees.referral_default_pct = 0.15
    return cfg


def test_misc_fee_matches_6_63_percent():
    cfg = _cfg()
    assert fees.misc_fee(25.00, cfg) == round(25.00 * 0.0663, 2)
    assert fees.misc_fee(100.00, cfg) == round(100.00 * 0.0663, 2)


def test_inbound_uses_eighty_cents_per_pound():
    cfg = _cfg()
    # 1.0 lb -> $0.80
    assert fees.inbound_cost({"packageWeight": 453.59237}, None, cfg) == 0.80
    # CSV override beats Keepa's value
    assert fees.inbound_cost({}, 2.5, cfg) == 2.0


def test_referral_default_falls_back_to_15_percent_when_keepa_missing():
    cfg = _cfg()
    # No referralFeePercent on product, no override category -> default 15%.
    assert fees.referral_fee({}, 25.00, cfg) == 3.75


def test_referral_uses_keepa_value_when_present():
    cfg = _cfg()
    assert fees.referral_fee({"referralFeePercent": 8}, 25.00, cfg) == 2.00


def test_config_override_beats_keepa_referral():
    cfg = _cfg()
    cfg.fees.referral_overrides_by_root_category = {"Clothing, Shoes & Jewelry": 0.17}
    p = {
        "referralFeePercent": 15,  # Keepa says 15
        "categoryTree": [{"name": "Clothing, Shoes & Jewelry"}],
    }
    # Override wins -> 17% × 64 = $10.88
    assert fees.referral_fee(p, 64.00, cfg) == 10.88


def test_compute_fees_total_matches_selleramp_components():
    cfg = _cfg()
    product = {
        "fbaFees": {"pickAndPackFee": 371},  # cents -> $3.71 (1lb std)
        "referralFeePercent": 15,
    }
    breakdown = fees.compute_fees(product, sell_price=25.00, weight_lbs_override=1.0, cfg=cfg)
    assert breakdown["referral_fee"] == 3.75
    assert breakdown["fba_fulfillment_fee"] == 3.71
    assert breakdown["misc_fee"] == round(25.00 * 0.0663, 2)
    assert breakdown["inbound_cost"] == 0.80
    assert breakdown["total_amazon_fees"] == round(3.75 + 3.71 + breakdown["misc_fee"], 2)


def test_profit_and_roi_endtoend_sample():
    cfg = _cfg()
    product = {"fbaFees": {"pickAndPackFee": 371}, "referralFeePercent": 15}
    breakdown = fees.compute_fees(product, sell_price=25.00, weight_lbs_override=1.0, cfg=cfg)
    pr = fees.profit_and_roi(sell_price=25.00, cost=10.00, fees=breakdown, prep_cost=0.0, cfg=cfg)
    # profit = 25 - 10 - (3.75+3.71+1.66) - 0.80 - 0 = 5.08
    assert pr["estimated_profit"] == 5.08
    assert pr["roi_pct"] == round(5.08 / (10.00 + 0.80), 4)


def test_fba_fallback_table_monotonic():
    """Fallback fees should never decrease as weight grows."""
    last = -1.0
    for w in [0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0]:
        v = fees.fba_fulfillment_fee_fallback(w)
        assert v >= last
        last = v
