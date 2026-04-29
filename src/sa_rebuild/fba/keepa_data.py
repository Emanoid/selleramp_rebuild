"""Helpers for navigating Keepa product payloads.

Keepa CSV indices we use:
    NEW = 1, SALES = 3, NEW_FBA = 11, BUY_BOX_SHIPPING = 18

Prices are in cents in raw `csv` arrays. Timestamps are "Keepa minutes" (KTM):
    unix_seconds = (ktm + 21564000) * 60
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Iterable, List, Optional, Sequence, Tuple

KEEPA_EPOCH_MINUTES = 21564000

CSV_AMAZON = 0
CSV_NEW = 1
CSV_USED = 2
CSV_SALES = 3
CSV_NEW_FBA = 11
CSV_BUY_BOX_SHIPPING = 18


def ktm_to_dt(ktm: int) -> datetime:
    return datetime.fromtimestamp((ktm + KEEPA_EPOCH_MINUTES) * 60, tz=timezone.utc)


def cents_to_usd(cents: float | int | None) -> Optional[float]:
    if cents is None:
        return None
    try:
        c = float(cents)
    except (TypeError, ValueError):
        return None
    if c <= 0:
        return None
    return round(c / 100.0, 2)


def get_stat_avg(product: dict, period: str, csv_index: int) -> Optional[float]:
    """Read stats.avg30/avg90/avg180 array safely. Returns USD."""
    stats = product.get("stats") or {}
    arr = stats.get(period)
    if not arr or len(arr) <= csv_index:
        return None
    val = arr[csv_index]
    return cents_to_usd(val)


def current_buy_box_price(product: dict) -> Optional[float]:
    """Latest buy-box-with-shipping price (USD). None if buy box currently absent."""
    stats = product.get("stats") or {}
    current = stats.get("current") or []
    if len(current) > CSV_BUY_BOX_SHIPPING:
        usd = cents_to_usd(current[CSV_BUY_BOX_SHIPPING])
        if usd is not None:
            return usd
    bb = stats.get("buyBoxPrice")
    return cents_to_usd(bb)


def iter_variation_asins(product: dict) -> List[Tuple[str, str]]:
    """For variation parents/children, return [(sibling_asin, attributes_label), ...]."""
    out: List[Tuple[str, str]] = []
    variations = product.get("variations") or []
    for v in variations:
        asin = v.get("asin")
        if not asin:
            continue
        attrs = v.get("attributes") or []
        label_parts = [f"{a.get('dimension','?')}:{a.get('value','?')}" for a in attrs]
        out.append((asin, ", ".join(label_parts) or "—"))
    return out


def decode_csv_pairs(csv_array: Sequence[int] | None) -> List[Tuple[datetime, float]]:
    """Decode raw Keepa csv pairs (alternating ktm, value) into (datetime, usd)."""
    out: List[Tuple[datetime, float]] = []
    if not csv_array:
        return out
    it = iter(csv_array)
    for ktm in it:
        try:
            val = next(it)
        except StopIteration:
            break
        if val is None or val == -1:
            continue
        try:
            ts = ktm_to_dt(int(ktm))
        except (TypeError, ValueError, OSError):
            continue
        usd = cents_to_usd(val)
        if usd is None:
            continue
        out.append((ts, usd))
    return out


def buy_box_history(product: dict) -> List[Tuple[datetime, float]]:
    """Return list of (ts, usd) for buy-box-with-shipping price history."""
    csv = product.get("csv")
    if csv and len(csv) > CSV_BUY_BOX_SHIPPING:
        return decode_csv_pairs(csv[CSV_BUY_BOX_SHIPPING])
    return []


def new_fba_history(product: dict) -> List[Tuple[datetime, float]]:
    csv = product.get("csv")
    if csv and len(csv) > CSV_NEW_FBA:
        return decode_csv_pairs(csv[CSV_NEW_FBA])
    return []


def buybox_seller_history(product: dict) -> List[Tuple[datetime, str]]:
    """Decode buyBoxSellerIdHistory: alternating ktm, seller_id (string)."""
    raw = product.get("buyBoxSellerIdHistory") or []
    out: List[Tuple[datetime, str]] = []
    it = iter(raw)
    for ktm in it:
        try:
            sid = next(it)
        except StopIteration:
            break
        if sid in (None, "", "-1"):
            continue
        try:
            ts = ktm_to_dt(int(ktm))
        except (TypeError, ValueError, OSError):
            continue
        out.append((ts, str(sid)))
    return out


def filter_window(
    series: Iterable[Tuple[datetime, float]],
    days: int,
    now: Optional[datetime] = None,
) -> List[Tuple[datetime, float]]:
    now = now or datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=days)
    return [(t, v) for t, v in series if t >= cutoff]


def time_weighted_mean(series: Sequence[Tuple[datetime, float]]) -> Optional[float]:
    """Time-weighted mean of a piecewise-constant series of (ts, value) samples."""
    if not series:
        return None
    if len(series) == 1:
        return series[0][1]
    pts = sorted(series, key=lambda x: x[0])
    total_w = 0.0
    total_v = 0.0
    for (t1, v1), (t2, _v2) in zip(pts, pts[1:]):
        w = max(0.0, (t2 - t1).total_seconds())
        total_w += w
        total_v += v1 * w
    if total_w == 0:
        return mean(v for _, v in pts)
    return total_v / total_w


def coefficient_of_variation(values: Sequence[float]) -> Optional[float]:
    """CV = stddev / mean. Returns None if not computable."""
    vals = [v for v in values if v is not None]
    if len(vals) < 3:
        return None
    m = mean(vals)
    if m <= 0:
        return None
    return pstdev(vals) / m


def percentile(values: Sequence[float], pct: float) -> Optional[float]:
    """Linear-interp percentile (pct in 0..1)."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    k = pct * (len(vals) - 1)
    lo = int(k)
    hi = min(lo + 1, len(vals) - 1)
    frac = k - lo
    return vals[lo] + (vals[hi] - vals[lo]) * frac


def root_category_name(product: dict) -> Optional[str]:
    tree = product.get("categoryTree") or []
    if tree:
        return tree[0].get("name")
    return product.get("rootCategory") or product.get("productGroup")


def leaf_category_name(product: dict) -> Optional[str]:
    tree = product.get("categoryTree") or []
    if tree:
        return tree[-1].get("name")
    return None


def live_offers(product: dict) -> List[dict]:
    """Return only currently-live offers from a Keepa product payload.

    Prefers `liveOffersOrder` (Keepa's own list of live-offer indices). When
    Keepa returns the key with an empty list, that's an authoritative "no live
    offers" — we trust it. Falls back to filtering by `lastSeen` within 48h
    only when the key is absent entirely.
    """
    offers = product.get("offers") or []
    if "liveOffersOrder" in product:
        order = product.get("liveOffersOrder") or []
        return [offers[i] for i in order if isinstance(i, int) and 0 <= i < len(offers)]
    cutoff_dt = datetime.now(tz=timezone.utc) - timedelta(hours=48)
    cutoff_ktm = int(cutoff_dt.timestamp() // 60) - KEEPA_EPOCH_MINUTES
    return [o for o in offers if (o.get("lastSeen") or 0) >= cutoff_ktm]


def offer_current_price_usd(offer: dict) -> Optional[float]:
    """Latest price+shipping (USD) from an offer's offerCSV (alternating ts,price,ship)."""
    csv = offer.get("offerCSV") or []
    if len(csv) < 3:
        return None
    price_cents = csv[-2]
    ship_cents = csv[-1]
    if price_cents in (None, -1):
        return None
    if ship_cents in (None, -1):
        ship_cents = 0
    total = price_cents + ship_cents
    if total <= 0:
        return None
    return round(total / 100.0, 2)


def is_variation_listing(product: dict) -> bool:
    """True if this ASIN is a child of a variation parent."""
    parent = product.get("parentAsin")
    asin = product.get("asin")
    if parent and asin and parent != asin:
        return True
    variations = product.get("variations")
    return bool(variations)


def variation_count(product: dict) -> Optional[int]:
    variations = product.get("variations")
    if isinstance(variations, list):
        return len(variations)
    return None


def out_of_stock_pct_30d_buybox(product: dict) -> Optional[float]:
    """Buy-box out-of-stock percentage over last 30d (0..100), if Keepa returned it."""
    stats = product.get("stats") or {}
    arr = stats.get("outOfStockPercentage30") or []
    if len(arr) > CSV_BUY_BOX_SHIPPING:
        v = arr[CSV_BUY_BOX_SHIPPING]
        if v not in (None, -1):
            return float(v)
    return None


def latest_monthly_sold_history(product: dict) -> Optional[int]:
    """Decode `monthlySoldHistory` (alternating ktm,count) and return the latest count."""
    raw = product.get("monthlySoldHistory")
    if not raw:
        return None
    last_val: Optional[int] = None
    it = iter(raw)
    for _ts in it:
        try:
            v = next(it)
        except StopIteration:
            break
        if v not in (None, -1):
            last_val = int(v)
    return last_val


def package_weight_lbs(product: dict) -> Optional[float]:
    g = product.get("packageWeight")
    if g is None or g <= 0:
        # Item weight fallback
        g = product.get("itemWeight")
    if g is None or g <= 0:
        return None
    # Keepa weight is in grams.
    return round(g / 453.59237, 3)
