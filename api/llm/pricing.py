"""Token prices and plan limits from config/llm_pricing.yaml (never hard-coded)."""

from pathlib import Path

import yaml

PRICING = Path("config/llm_pricing.yaml")


def load_pricing(path: Path = PRICING) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def prices_for(pricing: dict, provider: str, model: str) -> dict | None:
    return ((pricing.get(provider) or {}).get("models") or {}).get(model)


def limits_for(pricing: dict, provider: str) -> dict:
    return (pricing.get(provider) or {}).get("limits") or {}


def cost(prices: dict | None, tokens_in: int, tokens_out: int, cached: int = 0) -> float | None:
    """List-price cost in US$ (None when the model has no known price)."""
    if prices is None:
        return None
    cached = min(cached, tokens_in)
    usd = (
        (tokens_in - cached) * prices["input_per_mtok"]
        + cached * prices.get("cached_input_per_mtok", prices["input_per_mtok"])
        + tokens_out * prices["output_per_mtok"]
    ) / 1_000_000
    return round(usd, 8)


def costs(prices: dict | None, plan: str, tokens_in: int, tokens_out: int, cached: int = 0) -> dict:
    """Real cost (US$ 0 on the free plan) and equivalent paid cost at list price."""
    paid = cost(prices, tokens_in, tokens_out, cached)
    if paid is None:
        return {"cost_real_usd": 0.0, "cost_paid_usd": 0.0, "price_known": False}
    return {
        "cost_real_usd": 0.0 if plan == "free" else paid,
        "cost_paid_usd": paid,
        "price_known": True,
    }
