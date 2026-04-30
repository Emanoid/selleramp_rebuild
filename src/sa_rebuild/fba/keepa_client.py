"""Token-aware Keepa wrapper with caching and graceful token-exhaustion."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import keepa  # PyPI: keepa

from .cache import Cache
from ..config import AppConfig
from .token_bucket import TokenBucket


log = logging.getLogger("sa_rebuild")


class TokensExhausted(Exception):
    """Raised when the token wait strategy requires caller intervention.

    retryable=True  → NOT_ENOUGH_TOKEN drift; runner should back off and retry.
    retryable=False → predicted wait exceeds max_wait_minutes; runner should
                      sleep wait_seconds then retry (never pause the whole run).
    """
    def __init__(self, msg: str, retryable: bool = False, wait_seconds: float = 0.0):
        super().__init__(msg)
        self.retryable = retryable
        self.wait_seconds = wait_seconds  # populated for the limit-exceeded case


class CancelledByUser(Exception):
    """Raised when the user requested stop while we were sleeping for token refill."""


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
        # Per-call stats — reset on every fetch_*; readable by callers afterward.
        self.last_was_cache_hit: bool = False
        self.last_tokens_consumed: int = 0
        self.last_wait_seconds: float = 0.0
        self.last_fetch_seconds: float = 0.0

    # ------------------------------------------------------------------ helpers

    def _cache_key(self, kind: str, ident: str) -> str:
        domain = self.cfg.marketplace.domain
        stats = self.cfg.keepa.stats_days
        offers = self.cfg.keepa.offers
        return f"{domain}:{kind}:{ident}:s{stats}:o{offers}"

    def _ttl_seconds(self) -> int:
        return self.cfg.keepa.cache_ttl_hours * 3600

    def _ensure_tokens(self, expected: int, cancel_check=None) -> float:
        """Raise immediately if tokens insufficient — never sleeps.

        The runner owns all sleeping via _interruptible_wait so it can emit
        live log events every 30s during token waits. Returns 0.0 if enough
        tokens are already available.
        """
        predicted = self.bucket.predicted_now()
        if predicted >= expected:
            return 0.0
        wait_needed = self.bucket.seconds_until(expected)
        raise TokensExhausted(
            f"Need {expected} tokens, have ~{predicted} "
            f"(refill {self.bucket.refill_rate_per_min:.0f}/min). "
            f"Estimated wait: {wait_needed / 60:.1f}m. Runner sleeping and retrying.",
            retryable=False,
            wait_seconds=wait_needed,
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

    def _reset_stats(self) -> None:
        self.last_was_cache_hit = False
        self.last_tokens_consumed = 0
        self.last_wait_seconds = 0.0
        self.last_fetch_seconds = 0.0

    def fetch_by_upc(self, upc: str, cancel_check=None) -> Optional[Dict[str, Any]]:
        """Resolve a UPC straight to a fully-hydrated product blob (single call)."""
        self._reset_stats()
        cached = self.cache.get(self._cache_key("upc", upc))
        if cached is not None:
            self.last_was_cache_hit = True
            log.debug("cache hit upc=%s", upc)
            return cached or None

        tokens_before = self.bucket.predicted_now()
        self.last_wait_seconds = self._ensure_tokens(
            self.cfg.keepa.expected_token_cost, cancel_check=cancel_check
        )
        log.info("keepa upc=%s tokens_before=%s", upc, self.bucket.tokens_left)
        t0 = time.time()
        try:
            results = self._query(items=[upc], product_code_is_asin=False)
        except Exception as e:
            log.error("keepa query failed upc=%s err=%s", upc, e)
            # Keepa library raises bare RuntimeError("NOT_ENOUGH_TOKEN") when
            # its own internal counter disagrees with ours. Convert to our
            # token-exhaustion exception so the runner pauses (and resumes
            # retrying this row) instead of treating it as a row-level fatal.
            if "NOT_ENOUGH_TOKEN" in str(e):
                self.bucket.update(0)  # force-reset local mirror so next wait is accurate
                raise TokensExhausted(
                    f"Keepa reported NOT_ENOUGH_TOKEN — local mirror reset to 0, will retry.",
                    retryable=True,
                ) from e
            raise
        self.last_fetch_seconds = time.time() - t0
        self.last_tokens_consumed = max(0, tokens_before - self.bucket.tokens_left)
        product = results[0] if results else None
        # Cache positive AND negative resolutions to avoid re-spending tokens on bad UPCs.
        self.cache.set(
            self._cache_key("upc", upc),
            product or {},
            ttl_seconds=self._ttl_seconds(),
        )
        return product

    def fetch_by_asin(self, asin: str, cancel_check=None) -> Optional[Dict[str, Any]]:
        self._reset_stats()
        cached = self.cache.get(self._cache_key("asin", asin))
        if cached is not None:
            self.last_was_cache_hit = True
            return cached or None
        tokens_before = self.bucket.predicted_now()
        self.last_wait_seconds = self._ensure_tokens(
            self.cfg.keepa.expected_token_cost, cancel_check=cancel_check
        )
        t0 = time.time()
        try:
            results = self._query(items=[asin], product_code_is_asin=True)
        except Exception as e:
            if "NOT_ENOUGH_TOKEN" in str(e):
                self.bucket.update(0)
                raise TokensExhausted(
                    f"Keepa reported NOT_ENOUGH_TOKEN — local mirror reset to 0, will retry.",
                    retryable=True,
                ) from e
            raise
        self.last_fetch_seconds = time.time() - t0
        self.last_tokens_consumed = max(0, tokens_before - self.bucket.tokens_left)
        product = results[0] if results else None
        self.cache.set(
            self._cache_key("asin", asin),
            product or {},
            ttl_seconds=self._ttl_seconds(),
        )
        return product

    def tokens_left(self) -> int:
        return self.bucket.predicted_now()
