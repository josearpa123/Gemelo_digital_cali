"""Whitelisted actions the assistant may request. The LLM's JSON is validated here with
Pydantic before anything touches the simulation; anything else is rejected."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

Strategy = Literal["fixed", "maxpressure", "rl"]


class _Action(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProvocarAccidente(_Action):
    accion: Literal["provocar_accidente"]
    calle: str | None = Field(default=None, max_length=80)
    duracion_s: int = Field(default=600, ge=60, le=3600)


class CambiarEstrategia(_Action):
    accion: Literal["cambiar_estrategia"]
    estrategia: Strategy


class CambiarDemanda(_Action):
    accion: Literal["cambiar_demanda"]
    nivel: Literal["valley", "peak", "peak_plus"]


class Pausar(_Action):
    accion: Literal["pausar"]


class Reanudar(_Action):
    accion: Literal["reanudar"]


class Comparar(_Action):
    accion: Literal["comparar"]
    a: Strategy = "rl"
    b: Strategy = "fixed"


Action = Annotated[
    ProvocarAccidente | CambiarEstrategia | CambiarDemanda | Pausar | Reanudar | Comparar,
    Field(discriminator="accion"),
]
ACTIONS = (
    "provocar_accidente",
    "cambiar_estrategia",
    "cambiar_demanda",
    "pausar",
    "reanudar",
    "comparar",
)
_adapter = TypeAdapter(Action)


class InvalidAction(ValueError):
    def __init__(self, reason: str, kind: str):
        super().__init__(reason)
        self.kind = kind  # respuesta_invalida (not a JSON object) · fuera_de_lista · parametros


def parse_action(text: str):
    """JSON text from the LLM → validated action, or InvalidAction."""
    try:
        raw = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidAction(f"JSON inválido: {exc}", "respuesta_invalida") from exc
    if not isinstance(raw, dict):
        raise InvalidAction("se esperaba un objeto JSON", "respuesta_invalida")
    if raw.get("accion") not in ACTIONS:
        raise InvalidAction(
            f"acción fuera de la lista blanca: {raw.get('accion')!r}", "fuera_de_lista"
        )
    try:
        return _adapter.validate_python(raw)
    except ValidationError as exc:
        errors = "; ".join(f"{'.'.join(map(str, e['loc'][1:]))}: {e['msg']}" for e in exc.errors())
        raise InvalidAction(f"parámetros inválidos: {errors}", "parametros") from exc


SCHEMA_HINT = """Responde SOLO con un objeto JSON, sin texto adicional, con una de estas acciones:
{"accion": "provocar_accidente", "calle": "<calle del corredor>", "duracion_s": 60-3600}
{"accion": "cambiar_estrategia", "estrategia": "fixed" | "maxpressure" | "rl"}
{"accion": "cambiar_demanda", "nivel": "valley" | "peak" | "peak_plus"}
{"accion": "pausar"}
{"accion": "reanudar"}
{"accion": "comparar", "a": "rl" | "fixed" | "maxpressure", "b": "rl" | "fixed" | "maxpressure"}
"pasa a hora pico" es cambiar_demanda con nivel "peak"; "hora valle" es "valley".
Si la orden no corresponde a ninguna, responde {"accion": "desconocida"}."""
