"""One real call to Groq with the key of the env file (or the panel). Manual: make test-live.
Confirms model, tokens, cost and the rate-limit headers of this account."""

import asyncio
import json

import pytest

from api.llm.client import DEFAULTS, LLMSettings, OpenAICompatClient
from api.llm.pricing import costs, load_pricing, prices_for

pytestmark = pytest.mark.live


def test_one_real_groq_call(groq_key):
    model, base_url, _ = DEFAULTS["groq"]  # conftest sets LLM_PROVIDER=fake for other tests
    settings = LLMSettings("groq", model, base_url, groq_key, "free", "low")
    result = asyncio.run(
        OpenAICompatClient(settings).complete([{"role": "user", "content": "Responde solo: OK"}])
    )
    prices = prices_for(load_pricing(), "groq", settings.model)
    cost = costs(prices, settings.plan, result.tokens_in, result.tokens_out, result.tokens_cached)
    print(
        json.dumps(
            {
                "model": result.model,
                "text": result.text,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "latency_s": round(result.latency_s, 3),
                "limits": result.limits,
                **cost,
            },
            indent=2,
        )
    )
    assert result.model == "openai/gpt-oss-120b"
    assert result.tokens_in > 0 and result.tokens_out > 0
    assert cost["price_known"] and cost["cost_paid_usd"] > 0
