"""Indicators of the "Trazas" panel, computed only from stored trace events."""

from collections import Counter

FAILURE_STATUSES = ("error", "fallback")


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 3) if xs else None


def _values(events: list[dict], field: str) -> list[int | float]:
    return [
        value
        for event in events
        if type(value := event["data"].get(field)) in (int, float) and 0 <= value < 10**12
    ]


def summarize(
    sim_seconds: list[dict],
    decisions: list[dict],
    llm_events: list[dict],
    counts: list[tuple[str, str, str, int]],
    now: float,
    fallback_tls: list[str] | None = None,
) -> dict:
    """`sim_seconds`: newest `sim_segundo` events · `decisions`: newest RL `decision` events ·
    `llm_events`: recent LLM events · `counts`: (component, type, status, n) over all events."""
    recent_decisions = [d for d in decisions if now - d["ts"] <= 60]
    llm_ok = [e for e in llm_events if e["type"] == "respuesta_ok"]
    tokens_in = sum(_values(llm_ok, "tokens_in"))
    tokens_out = sum(_values(llm_ok, "tokens_out"))
    by_component = Counter()
    by_type = Counter()
    failures = 0
    for component, type_, status, n in counts:
        by_component[component] += n
        by_type[f"{component}.{type_}"] += n
        if status in FAILURE_STATUSES:
            failures += n
    return {
        "sim": {
            "real_time_factor": _mean([rtf for rtf in _values(sim_seconds, "rtf") if rtf]),
            "step_ms": _mean(_values(sim_seconds, "step_ms")),
            "window": len(sim_seconds),
        },
        "rl": {
            "decisions_per_min": len(recent_decisions),
            "inference_ms": _mean(_values(decisions, "inference_ms")),
            "fallback_tls": sorted(fallback_tls or []),
        },
        "llm": {
            "calls": by_type.get("llm.llamada_enviada", 0),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "tokens": tokens_in + tokens_out,
            "cost_real_usd": round(sum(_values(llm_ok, "cost_real_usd")), 6),
            "cost_paid_usd": round(sum(_values(llm_ok, "cost_paid_usd")), 6),
            "latency_s": _mean(_values(llm_ok, "latency_s")),
        },
        "failures": failures,
        "total": sum(by_component.values()),
        "by_component": dict(by_component),
        "by_type": dict(by_type),
    }
