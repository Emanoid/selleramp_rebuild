"""Buy-box dominance + competition analysis."""
from __future__ import annotations

from collections import Counter
from typing import Dict, Optional, Tuple

from rapidfuzz import fuzz

from ...config import AppConfig
from ..keepa_data import buybox_seller_history, filter_window, live_offers


def _share_in_window(product: dict, days: int) -> Counter:
    """Count of buy-box winner samples by seller_id within last `days` days."""
    series = buybox_seller_history(product)
    series = filter_window(series, days=days)
    return Counter(sid for _, sid in series)


def _total(c: Counter) -> int:
    return sum(c.values())


def amazon_buybox_share(product: dict, cfg: AppConfig) -> float:
    """Fraction of last-N-days buy box samples won by Amazon. 0..1."""
    counts = _share_in_window(product, cfg.competition.amazon_dominance_window_days)
    total = _total(counts)
    if total == 0:
        return 0.0
    return counts.get(cfg.marketplace.amazon_seller_id, 0) / total


def top_non_amazon_seller(product: dict, cfg: AppConfig) -> Tuple[Optional[str], float]:
    """Most-frequent non-Amazon buy-box winner over last-N-days. Returns (seller_id, share)."""
    counts = _share_in_window(product, cfg.competition.amazon_dominance_window_days)
    counts.pop(cfg.marketplace.amazon_seller_id, None)
    total = _total(counts) + 0  # only non-Amazon samples
    if total == 0:
        return None, 0.0
    sid, n = counts.most_common(1)[0]
    return sid, n / total


def top_buybox_seller_recent(product: dict, cfg: AppConfig) -> Tuple[Optional[str], float]:
    """Most-frequent buy-box winner (any seller) in last `top_buybox_window_days`."""
    counts = _share_in_window(product, cfg.competition.top_buybox_window_days)
    total = _total(counts)
    if total == 0:
        return None, 0.0
    sid, n = counts.most_common(1)[0]
    return sid, n / total


def seller_id_to_name(product: dict, seller_id: Optional[str]) -> Optional[str]:
    """Resolve seller_id to display name from offers payload (no extra token cost)."""
    if not seller_id:
        return None
    if seller_id == "ATVPDKIKX0DER":
        return "Amazon.com"
    for o in product.get("offers") or []:
        if o.get("sellerId") == seller_id:
            return o.get("sellerName") or o.get("seller") or None
    return None


def _is_new(offer: dict) -> bool:
    return offer.get("condition") in (1, "1", None)


def fba_seller_count(product: dict) -> int:
    """Distinct FBA-New sellers currently live."""
    seen: set[str] = set()
    for o in live_offers(product):
        if o.get("isFBA") and _is_new(o):
            sid = o.get("sellerId")
            if sid:
                seen.add(sid)
    return len(seen)


def fbm_seller_count(product: dict) -> int:
    """Distinct FBM-New sellers currently live."""
    seen: set[str] = set()
    for o in live_offers(product):
        if not o.get("isFBA") and _is_new(o):
            sid = o.get("sellerId")
            if sid:
                seen.add(sid)
    return len(seen)


def dominance(product: dict, cfg: AppConfig) -> Dict[str, object]:
    """Return amazon/brand dominance flags + label + the diagnostic numbers."""
    amz_share = amazon_buybox_share(product, cfg)
    amz_dominant = amz_share >= cfg.competition.amazon_dominance_pct

    brand_dominant = False
    brand_match_seller_id: Optional[str] = None
    brand_match_share = 0.0
    if not amz_dominant:
        sid, share = top_non_amazon_seller(product, cfg)
        brand = (product.get("brand") or "").strip()
        seller_name = seller_id_to_name(product, sid)
        if (
            sid
            and brand
            and seller_name
            and share >= cfg.competition.brand_dominance_pct
            and fuzz.partial_ratio(brand.lower(), seller_name.lower())
            >= cfg.competition.brand_name_fuzz_threshold
        ):
            brand_dominant = True
            brand_match_seller_id = sid
            brand_match_share = share

    if amz_dominant:
        label = "Amazon dominant"
    elif brand_dominant:
        label = "Brand dominant (heuristic)"
    else:
        label = "Open"

    top_id, top_share = top_buybox_seller_recent(product, cfg)
    top_name = seller_id_to_name(product, top_id) or top_id or "—"

    return {
        "amazon_buybox_share_pct": round(amz_share * 100, 1),
        "amazon_dominant": amz_dominant,
        "brand_dominant": brand_dominant,
        "brand_match_seller_id": brand_match_seller_id,
        "brand_match_share_pct": round(brand_match_share * 100, 1) if brand_match_share else 0.0,
        "top_buybox_seller_id": top_id,
        "top_buybox_seller_name": top_name,
        "top_buybox_seller_share_pct": round(top_share * 100, 1),
        "fba_seller_count": fba_seller_count(product),
        "fbm_seller_count": fbm_seller_count(product),
        "dominance_label": label,
    }
