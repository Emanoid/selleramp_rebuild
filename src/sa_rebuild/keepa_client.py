"""Token-aware Keepa wrapper with caching and graceful token-exhaustion."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import keepa  # PyPI: keepa

from .cache import Cache
from .config import AppConfig
from .token_bucket import TokenBucket


log = logging.getLogger("sa_rebuild")


class TokensExhausted(Exception):
    """Raised when predicted wait exceeds runtime.max_wait_minutes — caller checkpoints and exits."""


class KeepaClient:
    def __init__(self, cfg: AppConfig, cache: Cache, bucket: TokenBucket):
        if not cfg.keepa_api_key:
            raise RuntimeError("KEEPA_API_KEY not set in environment / .env")
        self.cfg = cfg
        self.cache = cache
        self.bucket = bucket
        # `wait=False` makes the lib raise instead of blocking — we handle waits ourselves.
        self._api = keepa.Keepa(cfg.keepa_api_key, timeout=60)
        # Seed bucket from initial library state if available.
        initial_left = getattr(self._api, "tokens_left", None)
        if initial_left is not None:
            self.bucket.update(int(initial_left))

    # ------------------------------------------------------------------ helpers

    def _cache_key(self, kind: str, ident: str) -> str:
        domain = self.cfg.marketplace.domain
        stats = self.cfg.keepa.stats_days
        offers = self.cfg.keepa.offers
        return f"{domain}:{kind}:{ident}:s{stats}:o{offers}"

    def _ttl_seconds(self) -> int:
        return self.cfg.keepa.cache_ttl_hours * 3600

    def _ensure_tokens(self, expected: int) -> None:
        max_wait_s = self.cfg.runtime.max_wait_minutes * 60
        slept = self.bucket.wait_for(expected, max_wait_seconds=max_wait_s)
        if slept < 0:
            raise TokensExhausted(
                f"Need {expected} tokens; predicted wait > {self.cfg.runtime.max_wait_minutes}m. "
                f"Currently ~{self.bucket.predicted_now()} tokens, refill {self.bucket.refill_rate_per_min}/min."
            )

    def _query(self, *, items: list[str], product_code_is_asin: bool) -> list[dict]:
        kp_cfg = self.cfg.keepa
        results = self._api.query(
            items=items,
            domain=self.cfg.marketplace.domain,
            stats=kp_cfg.stats_days,
            history=kp_cfg.history,
            offers=kp_cfg.offers,
            rating=kp_cfg.rating,
            product_code_is_asin=product_code_is_asin,
            wait=False,
        )
        # Update bucket from the library's post-call state.
        tokens_left = getattr(self._api, "tokens_left", None)
        refill = getattr(self._api, "tokens_per_minute", None)
        if tokens_left is not None:
            self.bucket.update(int(tokens_left), refill)
        return results or []

    # ------------------------------------------------------------------ public

    def fetch_by_upc(self, upc: str) -> Optional[Dict[str, Any]]:
        """Resolve a UPC straight to a fully-hydrated product blob (single call)."""
        cached = self.cache.get(self._cache_key("upc", upc))
        if cached is not None:
            log.debug("cache hit upc=%s", upc)
            return cached or None

        self._ensure_tokens(self.cfg.keepa.expected_token_cost)
        log.info("keepa upc=%s tokens_before=%s", upc, self.bucket.tokens_left)
        try:
            results = self._query(items=[upc], product_code_is_asin=False)
        except Exception as e:
            log.error("keepa query failed upc=%s err=%s", upc, e)
            raise
        product = results[0] if results else None
        # Cache positive AND negative resolutions to avoid re-spending tokens on bad UPCs.
        self.cache.set(
            self._cache_key("upc", upc),
            product or {},
            ttl_seconds=self._ttl_seconds(),
        )
        return product

    def fetch_by_asin(self, asin: str) -> Optional[Dict[str, Any]]:
        cached = self.cache.get(self._cache_key("asin", asin))
        if cached is not None:
            return cached or None
        self._ensure_tokens(self.cfg.keepa.expected_token_cost)
        results = self._query(items=[asin], product_code_is_asin=True)
        product = results[0] if results else None
        self.cache.set(
            self._cache_key("asin", asin),
            product or {},
            ttl_seconds=self._ttl_seconds(),
        )
        return product

    def tokens_left(self) -> int:
        return self.bucket.predicted_now()
