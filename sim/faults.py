"""One-shot fault injection for the "Armar fallo" control of the panel.

A fault is armed from the API and consumed by the first component that reaches the point
where it applies (next RL decision, next simulation step, next LLM request); then it is
disarmed. Thread-safe: the API arms, the simulation thread and the assistant consume."""

import threading

FAULTS = {
    "rl_no_response": "Agente RL sin respuesta → ese semáforo pasa a tiempo fijo",
    "detector_loss": "Detector con datos perdidos → el agente usa el último valor válido",
    "traci_disconnect": "Desconexión de TraCI → reconexión y reanudación del escenario",
    "llm_timeout": "Timeout del LLM → reintentos y fallback del asistente",
    "llm_rate_limit": "Límite de peticiones (429) → reintentos y fallback del asistente",
    "llm_invalid": "Respuesta inválida del LLM → acción rechazada, nada se ejecuta",
}


class FaultInjector:
    def __init__(self, tracer=None):
        self._armed: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.tracer = tracer

    def arm(self, kind: str, tls_id: str | None = None) -> dict:
        if kind not in FAULTS:
            raise ValueError(f"unknown fault: {kind}")
        armed = {"kind": kind, "tls_id": tls_id, "label": FAULTS[kind]}
        with self._lock:
            self._armed[kind] = armed
        if self.tracer:
            component = (
                "llm" if kind.startswith("llm") else ("sim" if kind.startswith("traci") else "rl")
            )
            self.tracer.emit(component, "fallo_armado", "warn", data=armed, tls_id=tls_id)
        return armed

    def take(self, kind: str, tls_id: str | None = None) -> dict | None:
        """Consume the fault if it is armed (and targets `tls_id`, when it has a target)."""
        with self._lock:
            armed = self._armed.get(kind)
            if armed is None:
                return None
            if armed["tls_id"] and tls_id and armed["tls_id"] != tls_id:
                return None
            return self._armed.pop(kind)

    def is_armed(self, kind: str) -> bool:
        return kind in self._armed

    def armed(self) -> list[dict]:
        with self._lock:
            return list(self._armed.values())

    def disarm_all(self) -> None:
        with self._lock:
            self._armed.clear()
