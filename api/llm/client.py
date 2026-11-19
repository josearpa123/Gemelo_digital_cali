"""Provider-agnostic LLM client. Groq and Ollama both speak the OpenAI chat API, so one
adapter covers them; `fake` answers locally (tests and e2e, no network, no cost)."""

import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime

import httpx

from api.llm import keystore

TIMEOUT_S = 2.0
MAX_RESPONSE_BYTES = 65536
DEFAULTS = {
    "groq": ("openai/gpt-oss-120b", "https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openai_compat": ("llama3.1", "http://host.docker.internal:11434/v1", "LLM_API_KEY"),
    "fake": ("fake-local", "http://fake.local/v1", ""),
}


class LLMError(Exception):
    status = "error_servidor"


class LLMTimeout(LLMError):
    status = "error_timeout"


class LLMRateLimit(LLMError):
    status = "error_limite"

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMServerError(LLMError):
    status = "error_servidor"


class LLMAuthError(LLMError):
    status = "error_autenticacion"


class LLMBadRequest(LLMError):
    """4xx other than 401/403/429: retrying the same request cannot help."""

    status = "error_peticion"


@dataclass
class LLMResult:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cached: int = 0
    latency_s: float = 0.0
    limits: dict = field(default_factory=dict)


@dataclass
class LLMSettings:
    provider: str
    model: str
    base_url: str
    api_key: str
    plan: str
    reasoning_effort: str | None
    env_key: str = ""
    key_source: str | None = None  # "panel" (secrets/, set from the UI) · "env" · None

    @classmethod
    def from_env(cls, key_file=None) -> "LLMSettings":
        provider = os.environ.get("LLM_PROVIDER") or "groq"
        if provider not in DEFAULTS:
            raise ValueError("Proveedor LLM no configurado")
        model, base_url, key_env = DEFAULTS[provider]
        settings = cls(
            provider=provider,
            model=os.environ.get("LLM_MODEL") or model,
            base_url=(os.environ.get("LLM_BASE_URL") or base_url)
            if provider == "openai_compat"
            else base_url,
            api_key="",
            plan=os.environ.get("LLM_PLAN") or "free",
            reasoning_effort=os.environ.get("LLM_REASONING_EFFORT", "low") or None,
            env_key=os.environ.get(key_env, "") if key_env else "",
        )
        panel_key = (
            (keystore.load(key_file) if key_file else keystore.load()) if provider == "groq" else ""
        )
        settings.use_key(panel_key)
        return settings

    def use_key(self, panel_key: str) -> None:
        """A key entered in the panel wins over the one in the env file."""
        if panel_key:
            self.api_key, self.key_source = panel_key, "panel"
        elif self.env_key:
            self.api_key, self.key_source = self.env_key, "env"
        else:
            self.api_key, self.key_source = "", None

    def public(self) -> dict:
        """Safe to show in the panel: never includes the key itself."""
        return {
            "provider": self.provider,
            "model": self.model,
            "plan": self.plan,
            "key_required": self.provider == "groq",
            "key_configured": bool(self.api_key),
            "key_source": self.key_source,
        }


class LLMClient:
    """Interface: one chat completion. Errors are raised as LLMError subclasses."""

    settings: LLMSettings

    async def complete(
        self,
        messages: list[dict],
        json_mode: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> LLMResult:
        raise NotImplementedError


class OpenAICompatClient(LLMClient):
    def __init__(self, settings: LLMSettings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def complete(
        self,
        messages: list[dict],
        json_mode: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> LLMResult:
        s = self.settings
        # a simulated fault (transport given) must show even without a key
        if s.provider == "groq" and not s.api_key and transport is None:
            raise LLMAuthError("GROQ_API_KEY no está configurada")
        body = {"model": s.model, "messages": messages, "temperature": 0.2, "max_tokens": 900}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if s.reasoning_effort and "gpt-oss" in s.model:
            body["reasoning_effort"] = s.reasoning_effort
        headers = {"Accept-Encoding": "identity"}
        if s.api_key:
            headers["Authorization"] = f"Bearer {s.api_key}"
        started = time.perf_counter()
        try:
            async with (
                httpx.AsyncClient(
                    base_url=s.base_url,
                    timeout=TIMEOUT_S,
                    trust_env=False,
                    transport=transport or self.transport,
                ) as http,
                http.stream("POST", "/chat/completions", json=body, headers=headers) as res,
            ):
                self._check_status(res)
                if res.headers.get("content-encoding", "identity").lower() != "identity":
                    raise LLMServerError("codificación inesperada del proveedor")
                content = bytearray()
                async for chunk in res.aiter_bytes(chunk_size=4096):
                    if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise LLMServerError("respuesta demasiado grande")
                    content.extend(chunk)
                limits = {k: v for k, v in res.headers.items() if k.startswith("x-ratelimit")}
        except httpx.TimeoutException as exc:
            raise LLMTimeout("tiempo del proveedor agotado") from exc
        except httpx.RequestError as exc:
            raise LLMServerError("error de transporte del proveedor") from exc
        try:
            payload = json.loads(content)
            usage = payload.get("usage") or {}
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
            text = payload["choices"][0]["message"].get("content") or ""
            if not isinstance(text, str) or len(text) > 6000:
                raise ValueError("contenido inválido")
            return LLMResult(
                text=text,
                model=s.model,
                tokens_in=max(0, int(usage.get("prompt_tokens", 0))),
                tokens_out=max(0, int(usage.get("completion_tokens", 0))),
                tokens_cached=max(0, int(cached)),
                latency_s=time.perf_counter() - started,
                limits=limits,
            )
        except (ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError) as exc:
            raise LLMServerError("respuesta inválida del proveedor") from exc

    @staticmethod
    def _check_status(res: httpx.Response) -> None:
        if res.status_code == 429:
            value = res.headers.get("retry-after", "0")
            try:
                retry = float(value)
            except ValueError:
                try:
                    retry = parsedate_to_datetime(value).timestamp() - time.time()
                except (ValueError, OverflowError):
                    retry = 0
            retry = retry if math.isfinite(retry) and retry > 0 else None
            raise LLMRateLimit("429 límite de peticiones", retry)
        if res.status_code in (401, 403):
            raise LLMAuthError(f"{res.status_code} clave rechazada por el proveedor")
        if res.status_code >= 500:
            raise LLMServerError(f"{res.status_code} error del servidor")
        if not res.is_success:
            raise LLMBadRequest(f"{res.status_code} petición rechazada por el proveedor")


class FakeClient(OpenAICompatClient):
    """Deterministic local stand-in that goes through the same HTTP code path with an
    in-process transport: commands are mapped by keywords, explanations echo the context."""

    def __init__(self, settings: LLMSettings):
        super().__init__(settings, httpx.MockTransport(self._handle))

    @staticmethod
    def _command(text: str) -> dict:
        t = text.lower()
        if "accidente" in t:
            return {"accion": "provocar_accidente", "calle": "Av. Roosevelt", "duracion_s": 600}
        if "valle" in t:
            return {"accion": "cambiar_demanda", "nivel": "valley"}
        if "pico" in t:
            return {"accion": "cambiar_demanda", "nivel": "peak"}
        if "compar" in t:
            return {"accion": "comparar", "a": "rl", "b": "fixed"}
        if "reanud" in t:
            return {"accion": "reanudar"}
        if "paus" in t:
            return {"accion": "pausar"}
        for key, strategy in (("max", "maxpressure"), ("fij", "fixed"), ("rl", "rl")):
            if key in t:
                return {"accion": "cambiar_estrategia", "estrategia": strategy}
        return {"accion": "desconocida"}

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        user = body["messages"][-1]["content"]
        if body.get("response_format"):
            order = re.search(r"Orden del usuario:\s*(.*)", user, re.S)
            content = json.dumps(self._command(order.group(1) if order else user))
        else:
            content = "[modelo local de prueba] Con base en el contexto: " + user[-400:]
        tokens_in = sum(len(m["content"]) for m in body["messages"]) // 4
        return httpx.Response(
            200,
            json={
                "model": self.settings.model,
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": tokens_in, "completion_tokens": len(content) // 4},
            },
        )


def make_client(settings: LLMSettings | None = None) -> LLMClient:
    settings = settings or LLMSettings.from_env()
    if settings.provider == "fake":
        return FakeClient(settings)
    return OpenAICompatClient(settings)
