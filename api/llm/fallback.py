"""Rule-based answers used when the LLM is not available, built only from real data."""

NOTE = "(Respuesta por reglas: el asistente de IA no respondió.)"


def explain(ctx: dict) -> str:
    decisions = ctx.get("decisiones") or []
    name = ctx.get("interseccion") or "la intersección"
    if not ctx.get("tls_id"):
        known = ", ".join(ctx.get("intersecciones", {}).values())
        return (
            "No identifiqué esa intersección en la red. "
            f"Las intersecciones del gemelo son: {known}. {NOTE}"
        )
    if not decisions:
        now = ctx.get("estado_actual") or {}
        return (
            f"No hay decisiones RL registradas para {name}: la estrategia activa es "
            f"{ctx.get('estrategia')}. Cola actual: {now.get('queue', 'n/d')} vehículos. {NOTE}"
        )
    d = decisions[0]
    data = d["data"]
    change = (
        f"pasó de la fase {data['fase_anterior']} a la {data['fase_elegida']}"
        if data["cambia"]
        else f"mantuvo la fase {data['fase_elegida']}"
    )
    return (
        f"En t = {d['sim_t']:.0f} s el agente de {name} {change}: {data['motivo']}. "
        f"Recompensa {data['recompensa']}, inferencia {data['inference_ms']} ms, "
        f"modelo {data['modelo']}. {NOTE}"
    )


def summary(ctx: dict) -> str:
    m = ctx.get("metricas") or {}
    sc = ctx.get("escenario") or {}
    return (
        f"Escenario {sc.get('escenario', 'n/d')} en {sc.get('corredor', 'n/d')}, estrategia "
        f"{ctx.get('estrategia')}, t = {ctx.get('t', 0):.0f} s: "
        f"{m.get('vehicles', 0)} vehículos en red, "
        f"{m.get('queue', 0)} detenidos en semáforos, espera media por viaje "
        f"{m.get('mean_trip_wait', 0)} s, {m.get('arrived', 0)} viajes completados, "
        f"{m.get('teleports', 0)} teletransportes. {NOTE}"
    )


def command() -> str:
    return f"No se ejecutó ninguna acción. Usa los controles del panel. {NOTE}"
