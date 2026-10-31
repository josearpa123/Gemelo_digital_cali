"""Real (free plan) and equivalent paid cost from config/llm_pricing.yaml."""

from pathlib import Path

import pytest

from api.llm.pricing import cost, costs, limits_for, load_pricing, prices_for

PRICES = {"input_per_mtok": 0.15, "cached_input_per_mtok": 0.075, "output_per_mtok": 0.60}


def test_yaml_has_the_groq_list_prices_and_limits():
    pricing = load_pricing(Path("config/llm_pricing.yaml"))
    assert prices_for(pricing, "groq", "openai/gpt-oss-120b") == PRICES
    assert limits_for(pricing, "groq")["requests_per_minute"] == 30
    assert prices_for(pricing, "groq", "unknown-model") is None


def test_equivalent_paid_cost():
    # 1 M input + 1 M output = 0.15 + 0.60
    assert cost(PRICES, 1_000_000, 1_000_000) == pytest.approx(0.75)
    # 1000 in + 500 out = 0.00015 + 0.0003
    assert cost(PRICES, 1000, 500) == pytest.approx(0.00045)
    # cached input tokens are billed at the cached price
    assert cost(PRICES, 1000, 0, cached=1000) == pytest.approx(0.000075)


def test_free_plan_real_cost_is_zero_and_paid_plan_pays():
    free = costs(PRICES, "free", 1000, 500)
    assert free == {
        "cost_real_usd": 0.0,
        "cost_paid_usd": pytest.approx(0.00045),
        "price_known": True,
    }
    paid = costs(PRICES, "paid", 1000, 500)
    assert paid["cost_real_usd"] == paid["cost_paid_usd"]
    # the panel shows 4 decimals: 2000 in + 1000 out = 0.0003 + 0.0006
    assert f"{costs(PRICES, 'free', 2000, 1000)['cost_paid_usd']:.4f}" == "0.0009"


def test_unknown_price_is_not_invented():
    assert costs(None, "paid", 1000, 500) == {
        "cost_real_usd": 0.0,
        "cost_paid_usd": 0.0,
        "price_known": False,
    }
