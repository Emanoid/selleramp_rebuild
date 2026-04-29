from sa_rebuild.fba.analytics import viability
from sa_rebuild.config import AppConfig


def test_buy_label_when_thresholds_pass():
    cfg = AppConfig()
    assert viability.label(
        profit=2.00, roi=0.45, bsr_pct=0.005,
        fba_seller_count=5, amazon_dominant=False, brand_dominant=False, cfg=cfg,
        recommended_price=20.00, cost=10.00,
    ) == "Buy"


def test_below_cost_short_circuits_to_skip():
    cfg = AppConfig()
    out = viability.label(
        profit=-5.0, roi=-0.5, bsr_pct=0.005,
        fba_seller_count=2, amazon_dominant=False, brand_dominant=False, cfg=cfg,
        recommended_price=19.97, cost=31.43,
    )
    assert out == "Skip — Sell price below cost"


def test_amazon_dominant_short_circuits():
    cfg = AppConfig()
    assert viability.label(
        profit=99.0, roi=10.0, bsr_pct=0.001,
        fba_seller_count=1, amazon_dominant=True, brand_dominant=False, cfg=cfg,
        recommended_price=50, cost=10,
    ).startswith("Skip")


def test_slow_seller_filter():
    cfg = AppConfig()
    assert viability.label(
        profit=5.0, roi=0.5, bsr_pct=0.05,
        fba_seller_count=2, amazon_dominant=False, brand_dominant=False, cfg=cfg,
        recommended_price=50, cost=10,
    ) == "Skip — Slow seller"


def test_thin_margin_caution():
    cfg = AppConfig()
    out = viability.label(
        profit=0.50, roi=0.05, bsr_pct=0.005,
        fba_seller_count=2, amazon_dominant=False, brand_dominant=False, cfg=cfg,
        recommended_price=15, cost=10,
    )
    assert out.startswith("Caution")


def test_pass_when_no_profit():
    cfg = AppConfig()
    assert viability.label(
        profit=-1.0, roi=-0.1, bsr_pct=0.005,
        fba_seller_count=2, amazon_dominant=False, brand_dominant=False, cfg=cfg,
        recommended_price=15, cost=10,
    ) == "Pass"
