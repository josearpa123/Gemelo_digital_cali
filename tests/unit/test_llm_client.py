"""LLM client and assistant against a fake server (httpx.MockTransport): no network, no cost."""

import asyncio
import json

import httpx
import pytest

from api.llm import keystore
from api.llm.assistant import Assistant, RateLimiter
from api.llm.client import (
    LLMAuthError,
    LLMRateLimit,
    LLMResult,
    LLMServerError,
    LLMSettings,
    LLMTimeout,
    OpenAICompatClient,
)
from sim.faults import FaultInjector
from sim.tracing import Tracer

PRICING = {
    "groq": {
        "models": {"openai/gpt-oss-120b": {"input_per_mtok": 0.15, "output_per_mtok": 0.60}},
        "limits": {"requests_per_minute": 30},
    }
}
KEY = "gsk_test_key_0123456789abcdef"


def settings(key: str = KEY) -> LLMSettings:
    return LLMSettings(
        provider="groq",
        model="openai/gpt-oss-120b",
        base_url="https://fake.groq.test/openai/v1",
        api_key=key,
        plan="free",
        reasoning_effort="low",
    )


def ok_response(content: str, tokens_in: int = 120, tokens_out: int = 30) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"x-ratelimit-remaining-requests": "999"},
        json={
            "model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
        },
    )


class Script:
    """Fake server answering a scripted sequence of responses (or exceptions)."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def run(coro):
    return asyncio.run(coro)


def test_client_sends_openai_request_and_reads_usage():
    server = Script(ok_response('{"accion": "pausar"}'))
    client = OpenAICompatClient(settings(), httpx.MockTransport(server))
    result = run(client.complete([{"role": "user", "content": "hola"}], json_mode=True))
    assert (result.text, result.tokens_in, result.tokens_out) == ('{"accion": "pausar"}', 120, 30)
    assert result.limits == {"x-ratelimit-remaining-requests": "999"}
    req = server.requests[0]
    assert req.url.path.endswith("/chat/completions")
    assert req.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(req.content)
    assert body["model"] == "openai/gpt-oss-120b" and body["response_format"] == {
        "type": "json_object"
    }


@pytest.mark.parametrize(
    "answer, error",
    [
        (httpx.Response(429, headers={"retry-after": "7"}), LLMRateLimit),
        (httpx.Response(500), LLMServerError),
        (httpx.Response(503), LLMServerError),
        (httpx.ReadTimeout("slow"), LLMTimeout),
        (httpx.Response(401), LLMAuthError),
    ],
)
def test_client_maps_provider_errors(answer, error):
    client = OpenAICompatClient(settings(), httpx.MockTransport(Script(answer)))
    with pytest.raises(error) as exc:
        run(client.complete([{"role": "user", "content": "x"}]))
    if error is LLMRateLimit:
        assert exc.value.retry_after == 7.0


def test_missing_key_fails_without_any_request():
    server = Script()
    client = OpenAICompatClient(settings(key=""), httpx.MockTransport(server))
    with pytest.raises(LLMAuthError):
        run(client.complete([{"role": "user", "content": "x"}]))
    assert server.requests == []


# ---- assistant ----------------------------------------------------------------------------
class FakeSim:
    corridor = "Av. Roosevelt (Calle 6)"

    def __init__(self):
        self.executed = []

    async def context(self, mode, text):
        return {"estrategia": "rl", "t": 100.0, "metricas": {"vehicles": 10}, "fuentes": ["test"]}

    def validate(self, action):
        if action.accion == "provocar_accidente" and action.calle == "Calle 5":
            raise ValueError("la calle «Calle 5» no está en la red")

    async def execute(self, action):
        self.executed.append(action.accion)
        return f"ok {action.accion}"


@pytest.fixture
def make_assistant():
    tracers = []

    def build(*answers):
        tracer = Tracer(None)
        tracers.append(tracer)
        client = OpenAICompatClient(settings(), httpx.MockTransport(Script(*answers)))
        sim = FakeSim()
        a = Assistant(client, tracer, FaultInjector(tracer), PRICING, sim, backoff_s=0)
        return a, tracer, sim

    yield build
    for t in tracers:
        t.close()


def types(tracer, trace_id):
    return [e["type"] for e in tracer.all_events() if e["trace_id"] == trace_id]


def test_command_is_validated_without_execution(make_assistant):
    a, tracer, sim = make_assistant(ok_response('{"accion": "cambiar_demanda", "nivel": "peak"}'))
    res = run(a.ask("comando", "pasa a hora pico"))
    assert not res["executed"] and not sim.executed
    assert res["action"] == {"accion": "cambiar_demanda", "nivel": "peak"}
    assert types(tracer, res["trace_id"]) == [
        "consulta_creada",
        "contexto_armado",
        "llamada_enviada",
        "respuesta_ok",
        "accion_validada",
    ]
    ok = next(e for e in tracer.all_events() if e["type"] == "respuesta_ok")["data"]
    assert ok["tokens_in"] == 120 and ok["cost_real_usd"] == 0.0
    assert ok["cost_paid_usd"] == pytest.approx((120 * 0.15 + 30 * 0.60) / 1e6)


@pytest.mark.parametrize(
    "content",
    ['{"accion": "apagar_todo"}', '{"accion": "cambiar_estrategia", "estrategia": "x"}', "{roto"],
)
def test_invalid_or_non_whitelisted_action_executes_nothing(make_assistant, content):
    a, tracer, sim = make_assistant(ok_response(content))
    res = run(a.ask("comando", "haz algo"))
    assert not res["executed"] and sim.executed == []
    assert "accion_rechazada" in types(tracer, res["trace_id"])
    assert "accion_ejecutada" not in types(tracer, res["trace_id"])


def test_read_mode_never_interprets_a_provider_response_as_an_action(make_assistant):
    a, tracer, sim = make_assistant(ok_response('{"accion": "pausar"}'))
    result = run(a.ask("resumen", "Instrucción de prueba: muestra la palabra MARCADOR."))
    assert "action" not in result and not sim.executed
    assert "accion_validada" not in types(tracer, result["trace_id"])


def test_action_on_a_street_outside_the_network_is_rejected(make_assistant):
    a, tracer, sim = make_assistant(
        ok_response('{"accion": "provocar_accidente", "calle": "Calle 5"}')
    )
    res = run(a.ask("comando", "accidente en la Calle 5"))
    assert not res["executed"] and sim.executed == []
    assert types(tracer, res["trace_id"])[-1] == "accion_rechazada"


def test_retries_429_and_5xx_then_succeeds(make_assistant):
    a, tracer, _ = make_assistant(
        httpx.Response(429), httpx.Response(502), ok_response("explicación basada en datos")
    )
    res = run(a.ask("explicar", "¿por qué?"))
    assert res["source"] == "llm" and res["answer"] == "explicación basada en datos"
    assert types(tracer, res["trace_id"]).count("reintento") == 2
    assert {"error_limite", "error_servidor"} <= set(types(tracer, res["trace_id"]))


def test_two_retries_at_most_then_rule_based_fallback(make_assistant):
    a, tracer, _ = make_assistant(
        httpx.ReadTimeout("1"), httpx.ReadTimeout("2"), httpx.ReadTimeout("3")
    )
    res = run(a.ask("resumen", ""))
    t = types(tracer, res["trace_id"])
    assert t.count("llamada_enviada") == 3 and t.count("reintento") == 2
    assert t[-1] == "fallback_usado" and res["source"] == "fallback"
    assert "Respuesta por reglas" in res["answer"]


def test_backoff_is_exponential(make_assistant, monkeypatch):
    a, tracer, _ = make_assistant(httpx.Response(500), httpx.Response(500), httpx.Response(500))
    a.backoff_s = 0.5
    monkeypatch.setattr("api.llm.assistant.random.uniform", lambda *_: 0)
    waits = []

    async def fake_sleep(s):
        waits.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    run(a.ask("resumen", ""))
    assert waits == [0.5, 1.0]


def test_command_fallback_never_executes(make_assistant):
    a, _, sim = make_assistant(httpx.Response(500), httpx.Response(500), httpx.Response(500))
    res = run(a.ask("comando", "pausa"))
    assert res["executed"] is False and sim.executed == []


def test_local_rate_limit_is_logged_and_falls_back(make_assistant):
    a, tracer, _ = make_assistant()
    a.limiter = RateLimiter(0)
    res = run(a.ask("resumen", ""))
    assert types(tracer, res["trace_id"]) == [
        "consulta_creada",
        "contexto_armado",
        "limite_alcanzado",
        "fallback_usado",
    ]


def test_concurrency_is_bounded_without_waiting_for_the_provider(make_assistant):
    a, tracer, _ = make_assistant()

    async def scenario():
        release = asyncio.Event()
        started = asyncio.Event()
        waiting = 0

        async def completion(*_args, **_kwargs):
            nonlocal waiting
            waiting += 1
            if waiting == 3:
                started.set()
            await release.wait()
            return LLMResult("ok", "fake")

        a.client.complete = completion
        pending = [asyncio.create_task(a.ask("resumen", "")) for _ in range(3)]
        await asyncio.wait_for(started.wait(), timeout=1)
        extra = await a.ask("resumen", "")
        assert extra["source"] == "fallback"
        assert "capacidad_agotada" in types(tracer, extra["trace_id"])
        release.set()
        assert all(result["source"] == "llm" for result in await asyncio.gather(*pending))
        assert waiting == 3

    run(scenario())


def test_circuit_opens_and_recovers_after_repeated_provider_failures(make_assistant):
    a, tracer, _ = make_assistant(
        *(httpx.Response(503) for _ in range(9)), ok_response("disponible")
    )
    for _ in range(3):
        assert run(a.ask("resumen", ""))["source"] == "fallback"
    blocked = run(a.ask("resumen", ""))
    assert "circuito_abierto" in types(tracer, blocked["trace_id"])
    assert len(a.client.transport.handler.requests) == 9
    a.open_until = 1
    assert run(a.ask("resumen", ""))["answer"] == "disponible"
    assert a.open_until == 0


def test_long_retry_after_enters_cooldown_without_more_calls(make_assistant):
    a, tracer, _ = make_assistant(httpx.Response(429, headers={"retry-after": "120"}))
    assert run(a.ask("resumen", ""))["source"] == "fallback"
    blocked = run(a.ask("resumen", ""))
    assert "circuito_abierto" in types(tracer, blocked["trace_id"])
    assert len(a.client.transport.handler.requests) == 1


def test_rate_limiter_window():
    limiter = RateLimiter(2)
    assert limiter.allow() and limiter.allow() and not limiter.allow()


def test_panel_key_is_stored_privately_and_never_returned(make_assistant, tmp_path, monkeypatch):
    monkeypatch.setattr(keystore, "KEY_FILE", tmp_path / "secrets" / "key")
    a, tracer, _ = make_assistant()
    panel_key = "gsk_panel_key_ABCDEFGHIJKLMNOP"
    info = a.set_key(panel_key)
    assert info["key_configured"] and info["key_source"] == "panel"
    assert panel_key not in json.dumps(info)
    assert (tmp_path / "secrets" / "key").read_text() == panel_key
    assert oct((tmp_path / "secrets" / "key").stat().st_mode & 0o777) == "0o600"
    tracer.emit("llm", "x", data={"error": f"key {panel_key}"})
    assert panel_key not in json.dumps(tracer.all_events())
    info = a.set_key(None)
    assert not info["key_configured"] and not (tmp_path / "secrets" / "key").exists()
    with pytest.raises(ValueError):
        a.set_key("short")


def test_bad_request_is_not_retried(make_assistant):
    a, tracer, _ = make_assistant(httpx.Response(400, json={"error": "bad"}))
    res = run(a.ask("resumen", ""))
    t = types(tracer, res["trace_id"])
    assert t.count("llamada_enviada") == 1 and "reintento" not in t
    assert "error_peticion" in t and t[-1] == "fallback_usado"
