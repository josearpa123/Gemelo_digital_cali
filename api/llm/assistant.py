"""Assistant orchestration: context → LLM call (timeout, retries, rate limit, injected
faults) → validated action or text → traces. Falls back to rules so the demo never
depends on the LLM."""

import asyncio
import json
import time
from collections import deque
from typing import Protocol

import httpx

from api.llm import fallback, keystore
from api.llm.actions import SCHEMA_HINT, InvalidAction, parse_action
from api.llm.client import LLMAuthError, LLMClient, LLMError, LLMRateLimit
from api.llm.pricing import costs, limits_for, prices_for
from sim.tracing import new_trace_id

MAX_RETRIES = 2
MAX_WAIT_S = 4.0
MODES = ("explicar", "comando", "resumen")
LLM_FAULTS = ("llm_timeout", "llm_rate_limit", "llm_invalid")

SYSTEM = (
    "Eres el asistente del gemelo digital de movilidad de Cali (corredor {corredor}). "
    "Los semáforos los controlan agentes de aprendizaje por refuerzo; tú no los controlas. "
    "Responde en español, en máximo 120 palabras, usando SOLO los datos del contexto. "
    "Si el contexto no tiene el dato o la calle no está en la red, dilo sin inventar."
)


class SimBridge(Protocol):
    corridor: str

    async def context(self, mode: str, text: str) -> dict: ...

    async def execute(self, action) -> str: ...


class RateLimiter:
    """Sliding one-minute window, so the free plan limit is never exceeded by us."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.calls: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self.calls and now - self.calls[0] > 60:
            self.calls.popleft()
        if len(self.calls) >= self.per_minute:
            return False
        self.calls.append(now)
        return True


class FaultTransport(httpx.AsyncBaseTransport):
    """Simulated provider failures for the "Armar fallo" control (no real call is made)."""

    def __init__(self, kind: str):
        self.kind = kind

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self.kind == "llm_timeout":
            raise httpx.ReadTimeout("simulated timeout", request=request)
        if self.kind == "llm_rate_limit":
            return httpx.Response(429, headers={"retry-after": "1"}, json={"error": "rate_limit"})
        json_mode = b"response_format" in request.content
        content = '{"accion": "provocar_accidente", "calle": ' if json_mode else ""
        return httpx.Response(
            200,
            json={
                "model": "fallo-simulado",
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            },
        )


class Assistant:
    def __init__(
        self,
        client: LLMClient,
        tracer,
        faults,
        pricing: dict,
        sim: SimBridge,
        backoff_s: float = 0.5,
    ):
        self.client = client
        self.tracer = tracer
        self.faults = faults
        self.sim = sim
        self.backoff_s = backoff_s
        s = client.settings
        self.prices = prices_for(pricing, s.provider, s.model)
        self.limits = limits_for(pricing, s.provider)
        self.limiter = RateLimiter(int(self.limits.get("requests_per_minute", 30)))

    def set_key(self, key: str | None, persist: bool = True) -> dict:
        """Key from the panel: saved under secrets/ (or only in memory) and never echoed."""
        s = self.client.settings
        if key:
            if persist:
                keystore.save(key)
            elif not keystore.KEY_FORMAT.match(key):
                raise ValueError("la clave tiene un formato inválido")
            self.tracer.add_secret(key)
            s.use_key(key)
        else:
            keystore.clear()
            s.use_key("")
        self._emit(
            new_trace_id(),
            "clave_configurada" if key else "clave_borrada",
            origen=s.key_source,
            guardada=bool(key and persist),
        )
        return self.info()

    async def test_key(self) -> dict:
        """One tiny real call to check the key (traced like any other call)."""
        trace_id = new_trace_id()
        self._emit(trace_id, "consulta_creada", modo="prueba", texto="prueba de conexión")
        result, reason = await self._call(trace_id, "prueba", "", {})
        if result is None:
            self._emit(trace_id, "fallback_usado", "fallback", motivo=reason)
            return {"ok": False, "trace_id": trace_id, "error": reason}
        return {"ok": True, "trace_id": trace_id, "model": result.model, "answer": result.text}

    def info(self) -> dict:
        return self.client.settings.public() | {"limits": self.limits, "prices": self.prices}

    def _emit(self, trace_id: str, type_: str, status: str = "ok", **data) -> None:
        s = self.client.settings
        self.tracer.emit(
            "llm",
            type_,
            status,
            data={"proveedor": s.provider, "modelo": s.model} | data,
            trace_id=trace_id,
        )

    async def ask(self, mode: str, text: str) -> dict:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        trace_id = new_trace_id()
        self._emit(trace_id, "consulta_creada", modo=mode, texto=text[:300])
        ctx = await self.sim.context(mode, text)
        self._emit(
            trace_id,
            "contexto_armado",
            fuentes=ctx.get("fuentes", []),
            tls_id=ctx.get("tls_id"),
            caracteres=len(json.dumps(ctx, default=str)),
        )
        result, reason = await self._call(trace_id, mode, text, ctx)
        if result is None:
            return self._fallback(trace_id, mode, ctx, reason)
        if mode != "comando":
            if not result.text.strip():
                self._emit(trace_id, "respuesta_invalida", "error", error="respuesta vacía")
                return self._fallback(trace_id, mode, ctx, "respuesta vacía")
            return {"trace_id": trace_id, "mode": mode, "source": "llm", "answer": result.text}
        return await self._command(trace_id, result.text)

    async def _call(self, trace_id: str, mode: str, text: str, ctx: dict):
        if not self.limiter.allow():
            self._emit(
                trace_id,
                "limite_alcanzado",
                "warn",
                limite=f"{self.limiter.per_minute} peticiones/min (local)",
            )
            return None, "límite local de peticiones por minuto"
        fault = next((f for f in LLM_FAULTS if self.faults and self.faults.take(f)), None)
        transport = FaultTransport(fault) if fault else None
        messages = self._messages(mode, text, ctx)
        reason = "error"
        for attempt in range(1, MAX_RETRIES + 2):
            self._emit(trace_id, "llamada_enviada", intento=attempt, fallo_simulado=fault)
            try:
                result = await self.client.complete(
                    messages, json_mode=mode == "comando", transport=transport
                )
            except LLMAuthError as exc:
                self._emit(trace_id, exc.status, "error", error=str(exc), intento=attempt)
                return None, str(exc)
            except LLMError as exc:
                reason = str(exc)
                data = {"error": reason, "intento": attempt}
                if isinstance(exc, LLMRateLimit):
                    data["retry_after_s"] = exc.retry_after
                self._emit(trace_id, exc.status, "error", **data)
                if attempt > MAX_RETRIES:
                    break
                wait = self.backoff_s * 2 ** (attempt - 1)
                if isinstance(exc, LLMRateLimit) and exc.retry_after and self.backoff_s:
                    wait = max(wait, exc.retry_after)
                wait = min(wait, MAX_WAIT_S)
                self._emit(trace_id, "reintento", "warn", intento=attempt + 1, espera_s=wait)
                await asyncio.sleep(wait)
                continue
            self._emit(
                trace_id,
                "respuesta_ok",
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                tokens_cached=result.tokens_cached,
                latency_s=round(result.latency_s, 3),
                modelo_respuesta=result.model,
                limites=result.limits,
                intento=attempt,
                **costs(
                    self.prices,
                    self.client.settings.plan,
                    result.tokens_in,
                    result.tokens_out,
                    result.tokens_cached,
                ),
            )
            return result, None
        return None, reason

    def _messages(self, mode: str, text: str, ctx: dict) -> list[dict]:
        system = SYSTEM.format(corredor=self.sim.corridor)
        context = json.dumps(ctx, ensure_ascii=False, default=str)
        if mode == "prueba":
            return [{"role": "user", "content": "Responde solo: OK"}]
        if mode == "comando":
            system += "\n" + SCHEMA_HINT
            user = f"Contexto: {context}\nOrden del usuario: {text}"
        elif mode == "explicar":
            user = (
                f"Contexto (trazas reales de las decisiones de los agentes): {context}\n"
                f"Pregunta: {text}"
            )
        else:
            user = f"Métricas reales de la corrida: {context}\nRedacta un resumen corto. {text}"
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    async def _command(self, trace_id: str, text: str) -> dict:
        try:
            action = parse_action(text)
        except InvalidAction as exc:
            if exc.kind == "respuesta_invalida":
                self._emit(trace_id, "respuesta_invalida", "error", error=str(exc))
            self._emit(trace_id, "accion_rechazada", "warn", motivo=str(exc))
            return {
                "trace_id": trace_id,
                "mode": "comando",
                "source": "llm",
                "answer": f"No ejecuté nada: {exc}",
                "executed": False,
            }
        self._emit(trace_id, "accion_validada", accion=action.model_dump())
        try:
            outcome = await self.sim.execute(action)
        except (ValueError, KeyError) as exc:
            self._emit(
                trace_id, "accion_rechazada", "warn", accion=action.model_dump(), motivo=str(exc)
            )
            return {
                "trace_id": trace_id,
                "mode": "comando",
                "source": "llm",
                "answer": f"No ejecuté nada: {exc}",
                "executed": False,
            }
        self._emit(trace_id, "accion_ejecutada", accion=action.model_dump(), resultado=outcome)
        return {
            "trace_id": trace_id,
            "mode": "comando",
            "source": "llm",
            "answer": outcome,
            "action": action.model_dump(),
            "executed": True,
        }

    def _fallback(self, trace_id: str, mode: str, ctx: dict, reason: str | None) -> dict:
        self._emit(trace_id, "fallback_usado", "fallback", motivo=reason)
        answer = {"explicar": fallback.explain, "resumen": fallback.summary}.get(mode)
        return {
            "trace_id": trace_id,
            "mode": mode,
            "source": "fallback",
            "answer": answer(ctx) if answer else fallback.command(),
            "executed": False if mode == "comando" else None,
        }
