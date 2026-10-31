"""Regressions found in the H-TRAZAS review: LLM faults with the default provider and no key,
and the live test pointing at Groq whatever the test environment says."""

import asyncio

import pytest

from api.llm.assistant import Assistant
from api.llm.client import DEFAULTS, LLMSettings, OpenAICompatClient
from sim.faults import FaultInjector
from sim.tracing import Tracer


class _Sim:
    corridor = "Av. Roosevelt (Calle 6)"

    async def context(self, mode, text):
        return {}

    async def execute(self, action):
        return "ok"


@pytest.mark.parametrize(
    "fault, expected",
    [("llm_timeout", "error_timeout"), ("llm_rate_limit", "error_limite")],
)
def test_llm_faults_show_retries_with_the_default_provider_and_no_key(fault, expected):
    tracer = Tracer(None)
    settings = LLMSettings("groq", "openai/gpt-oss-120b", "https://x.invalid/v1", "", "free", None)
    faults = FaultInjector(tracer)
    assistant = Assistant(OpenAICompatClient(settings), tracer, faults, {}, _Sim(), backoff_s=0)
    faults.arm(fault)
    res = asyncio.run(assistant.ask("comando", "pasa a hora valle"))
    types = [e["type"] for e in tracer.all_events() if e["trace_id"] == res["trace_id"]]
    tracer.close()
    assert expected in types and types.count("reintento") == 2


def test_live_test_settings_point_at_groq():
    model, base_url, _ = DEFAULTS["groq"]  # what tests/live/test_groq_live.py uses
    settings = LLMSettings("groq", model, base_url, "k", "free", "low")
    assert settings.base_url == "https://api.groq.com/openai/v1"
    assert settings.model == "openai/gpt-oss-120b"


def test_live_test_does_not_build_settings_from_the_test_environment():
    text = open("tests/live/test_groq_live.py", encoding="utf-8").read()
    assert "from_env" not in text and 'DEFAULTS["groq"]' in text
