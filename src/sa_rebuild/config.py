"""Config loader — pydantic models hydrated from config.yaml + .env."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class MarketplaceCfg(BaseModel):
    domain: str = "US"
    amazon_seller_id: str = "ATVPDKIKX0DER"


class KeepaCfg(BaseModel):
    stats_days: int = 180
    offers: int = 20
    history: bool = True
    rating: bool = True
    cache_ttl_hours: int = 24
    expected_token_cost: int = 8


class RuntimeCfg(BaseModel):
    max_wait_minutes: int = 30


class FeesCfg(BaseModel):
    inbound_per_lb_usd: float = 0.80
    misc_pct: float = 0.0663
    prep_flat_usd: float = 0.0
    misc_flat_usd: float = 0.0
    referral_default_pct: float = 0.15
    referral_overrides_by_root_category: Dict[str, float] = Field(default_factory=dict)


class PricingCfg(BaseModel):
    cv_stable: float = 0.05
    cv_moderate: float = 0.15


class CompetitionCfg(BaseModel):
    amazon_dominance_pct: float = 0.70
    brand_dominance_pct: float = 0.60
    brand_name_fuzz_threshold: int = 85
    amazon_dominance_window_days: int = 90
    top_buybox_window_days: int = 30


class ViabilityCfg(BaseModel):
    min_profit_usd: float = 1.00
    min_roi_pct: float = 0.30
    max_bsr_pct: float = 0.02
    max_fba_seller_count: int = 15


class VariationsCfg(BaseModel):
    fetch_max: int = 0  # 0 = disabled; CLI --variations N overrides
    max_seller_count: int = 10  # variation viable if total live sellers < this
    buy_box_min_ratio: float = 1.0  # buy box must be >= this × main rec_price


class AppConfig(BaseModel):
    marketplace: MarketplaceCfg = Field(default_factory=MarketplaceCfg)
    keepa: KeepaCfg = Field(default_factory=KeepaCfg)
    runtime: RuntimeCfg = Field(default_factory=RuntimeCfg)
    fees: FeesCfg = Field(default_factory=FeesCfg)
    pricing: PricingCfg = Field(default_factory=PricingCfg)
    competition: CompetitionCfg = Field(default_factory=CompetitionCfg)
    viability: ViabilityCfg = Field(default_factory=ViabilityCfg)
    variations: VariationsCfg = Field(default_factory=VariationsCfg)
    category_sizes: Dict[str, int] = Field(default_factory=dict)

    keepa_api_key: str = ""

    @classmethod
    def load(cls, config_path: Path | str | None = None) -> "AppConfig":
        """Load config.yaml from either an explicit path, the bundled binary,
        ./config.yaml in the working dir, or fall through to defaults.

        Resolves Keepa key from ~/.sa-rebuild/settings.json first, then
        KEEPA_API_KEY env var, then .env in the working dir.
        """
        from .paths import bundled_config_yaml, get_keepa_api_key

        load_dotenv()
        path: Optional[Path] = Path(config_path) if config_path else None
        if path is None or not path.exists():
            path = bundled_config_yaml()
        data: dict = {}
        if path and path.exists():
            with path.open() as f:
                data = yaml.safe_load(f) or {}
        cfg = cls(**data)
        cfg.keepa_api_key = get_keepa_api_key() or ""
        return cfg
