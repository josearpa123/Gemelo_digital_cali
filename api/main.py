"""sim-api: runs one live SUMO simulation, streams its state and traces to the web panel,
hosts the LLM assistant and serves the panel itself (http://localhost:8000)."""

import asyncio
import csv
import io
import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import fastapi
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.llm.assistant import Assistant
from api.llm.client import make_client
from api.llm.pricing import load_pricing
from sim.faults import FAULTS, FaultInjector
from sim.intersections import find_tls, mentions_corridor
from sim.runner import DEMAND_LEVELS, SimRunner
from sim.trace_summary import summarize
from sim.tracing import COMPONENTS, Tracer

NET = Path(os.environ.get("SIM_NET", "scenarios/roosevelt4/roosevelt4.net.xml"))
ROUTES = Path(os.environ.get("SIM_ROUTES", "scenarios/roosevelt4/demand/peak_s0.rou.xml"))
AUTOSTART = os.environ.get("SIM_AUTOSTART", "1") == "1"
WEB = Path(os.environ.get("WEB_DIR", "web"))
EVAL_SUMMARY = Path("outputs/eval/summary.md")
TICK = 0.1  # seconds of wall time between simulation batches
SPEEDS = (1, 2, 5, 10, 20, 50)
INGEST_EVERY = 5.0  # seconds between reads of the trainer's episode files


def sumo_version() -> str:
    binary = shutil.which("sumo")
    if binary is None:
        return "missing"
    out = subprocess.run([binary, "--version"], capture_output=True, text=True, check=False)
    return out.stdout.splitlines()[0] if out.stdout else "unknown"


SUMO_VERSION = sumo_version()


def build_dataset() -> None:
    """Generate the seeded demand dataset (same as `make dataset`, about 6 s)."""
    print("routes missing: generating the demand dataset (python -m sim.demand --dataset)")
    subprocess.run(
        ["python", "-m", "sim.demand", "--dataset", "--net", str(NET)], check=False, timeout=600
    )


class SimState:
    def __init__(self):
        # libsumo must always be driven from the same thread
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sumo")
        self.runner: SimRunner | None = None
        self.snapshot: dict | None = None
        self.version = 0
        self.paused = False
        self.speed = 5
        self.error: str | None = None
        self.task: asyncio.Task | None = None
        self.ingest_task: asyncio.Task | None = None
        self.tracer: Tracer | None = None
        self.faults: FaultInjector | None = None
        self.assistant: Assistant | None = None

    async def call(self, fn, *args):
        return await asyncio.get_running_loop().run_in_executor(self.executor, fn, *args)

    def _advance(self, steps: int) -> dict:
        for _ in range(steps):
            self.runner.step()
        return self.runner.snapshot()

    async def loop(self):
        carry = 0.0
        while True:
            await asyncio.sleep(TICK)
            if self.paused or self.runner is None:
                continue
            carry += self.speed * TICK
            steps, carry = int(carry), carry - int(carry)
            if steps == 0:
                continue
            try:
                self.snapshot = await self.call(self._advance, steps)
                self.version += 1
            except Exception as exc:  # keep the API alive and report the failure
                self.error = repr(exc)
                self.paused = True

    async def ingest_training(self, folder: Path):
        while True:
            await asyncio.to_thread(self.tracer.ingest_jsonl, folder)
            await asyncio.sleep(INGEST_EVERY)


state = SimState()


class Bridge:
    """What the assistant may read from and do to the simulation."""

    @property
    def corridor(self) -> str:
        return _runner().zone["corridor"]

    async def context(self, mode: str, text: str) -> dict:
        runner = _runner()
        snap = state.snapshot or {}
        ctx = {
            "estrategia": runner.strategy,
            "demanda": runner.demand,
            "pausado": state.paused,
            "t": snap.get("t", 0.0),
            "escenario": runner.scenario_info(),
        }
        if mode == "explicar":
            tls = find_tls(runner.zone, text)
            ctx |= {"tls_id": tls, "intersecciones": runner.names, "fuentes": ["rl.decision"]}
            if tls:
                ctx["interseccion"] = runner.names.get(tls, tls)
                ctx["estado_actual"] = next(
                    (t for t in snap.get("tls", []) if t["id"] == tls), None
                )
                ctx["decisiones"] = [
                    {"sim_t": e["sim_t"], "data": e["data"]}
                    for e in state.tracer.query(
                        component="rl", type="decision", tls_id=tls, limit=3
                    )
                ]
                ctx["fallbacks"] = [
                    {"sim_t": e["sim_t"], "data": e["data"]}
                    for e in state.tracer.query(
                        component="rl", type="fallback_control", tls_id=tls, limit=2
                    )
                ]
        elif mode == "resumen":
            ctx |= {
                "metricas": snap.get("metrics", {}),
                "impactos": [
                    e["data"]
                    for e in state.tracer.query(component="event", type="impacto", limit=5)
                ],
                "fuentes": ["estado en vivo", "event.impacto"],
            }
        else:
            ctx |= {"corredor": runner.zone["corridor"], "fuentes": ["estado en vivo"]}
        return ctx

    async def execute(self, action) -> str:
        runner = _runner()
        if action.accion == "provocar_accidente":
            if action.calle and not mentions_corridor(runner.zone, action.calle):
                raise ValueError(
                    f"la calle «{action.calle}» no está en la red del gemelo "
                    f"(corredor: {runner.zone['corridor']})"
                )
            if runner.accident_lane:
                raise ValueError("ya hay un accidente activo")
            await state.call(runner.set_accident, True, None, action.duracion_s)
            await _refresh()
            return (
                f"Accidente provocado en {runner.zone['corridor']} (carril "
                f"{runner.accident_lane}) durante {action.duracion_s} s simulados."
            )
        if action.accion == "cambiar_estrategia":
            await apply_control("strategy", action.estrategia)
            return f"Estrategia cambiada a {action.estrategia}."
        if action.accion == "cambiar_demanda":
            await apply_control("demand", action.nivel)
            return f"Demanda cambiada a {action.nivel}."
        if action.accion in ("pausar", "reanudar"):
            await apply_control("pause", action.accion == "pausar")
            return "Simulación pausada." if action.accion == "pausar" else "Simulación reanudada."
        if action.accion == "comparar":
            if not EVAL_SUMMARY.exists():
                return (
                    f"No hay resultados de evaluación en este equipo ({EVAL_SUMMARY}). "
                    "Córrelos con `make evaluate`; no invento la comparación."
                )
            lines = EVAL_SUMMARY.read_text(encoding="utf-8").splitlines()
            return f"Comparación {action.a} vs {action.b} según {EVAL_SUMMARY}:\n" + "\n".join(
                lines[:30]
            )
        raise ValueError(f"acción no soportada: {action.accion}")


@asynccontextmanager
async def lifespan(_app):
    outputs = Path(os.environ.get("OUTPUTS_DIR", "outputs"))
    db = os.environ.get("TRACES_DB", str(outputs / "traces.db"))
    state.tracer = Tracer(Path(db), log_path=outputs / "traces" / "events.jsonl")
    state.faults = FaultInjector(state.tracer)
    state.assistant = Assistant(make_client(), state.tracer, state.faults, load_pricing(), Bridge())
    if state.assistant.client.settings.api_key:  # key saved from the panel earlier
        state.tracer.add_secret(state.assistant.client.settings.api_key)
    if AUTOSTART and NET.exists() and not ROUTES.exists():
        await asyncio.to_thread(build_dataset)  # fresh clone: route files are not versioned
    if AUTOSTART and NET.exists() and ROUTES.exists():
        state.runner = SimRunner(
            NET, ROUTES, tracer=state.tracer, faults=state.faults, state_dir=outputs / "state"
        )
        await state.call(state.runner.start, "fixed")
        state.snapshot = await state.call(state.runner.snapshot)
        state.task = asyncio.create_task(state.loop())
    state.ingest_task = asyncio.create_task(state.ingest_training(outputs / "traces" / "training"))
    yield
    for task in (state.task, state.ingest_task):
        if task:
            task.cancel()
    if state.runner:
        await state.call(state.runner.close)
    state.tracer.close()


app = fastapi.FastAPI(title="Gemelo digital Cali · sim-api", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    scenario = None
    if state.runner:
        scenario = {"net": NET.name, "routes": ROUTES.name, "strategy": state.runner.strategy}
    return {"status": "ok", "sumo": SUMO_VERSION, "scenario": scenario, "error": state.error}


def _runner() -> SimRunner:
    if state.runner is None:
        raise fastapi.HTTPException(503, "simulation not started (missing net or routes?)")
    return state.runner


@app.get("/api/network")
async def network() -> dict:
    runner = _runner()
    return await state.call(runner.network_geojson)


@app.get("/api/strategies")
def strategies() -> dict:
    return {
        "strategies": _runner().strategy_list(),
        "speeds": SPEEDS,
        "demand_levels": list(DEMAND_LEVELS),
    }


@app.get("/api/state")
def current_state() -> dict:
    return _status() | {"snapshot": state.snapshot}


def _status() -> dict:
    return {
        "paused": state.paused,
        "speed": state.speed,
        "error": state.error,
        "faults_armed": [f["kind"] for f in state.faults.armed()] if state.faults else [],
    }


class Control(BaseModel):
    action: str
    value: str | int | bool | None = None


async def _refresh() -> None:
    state.snapshot = await state.call(_runner().snapshot)
    state.version += 1


async def apply_control(action: str, value) -> dict:
    runner = _runner()
    if action == "strategy":
        await state.call(runner.set_strategy, str(value))
    elif action == "restart":
        await state.call(runner.start, str(value or runner.strategy))
        state.error = None
    elif action == "accident":
        await state.call(runner.set_accident, bool(value))
    elif action == "demand":
        await state.call(runner.set_demand, str(value))
    elif action == "pause":
        if bool(value) != state.paused:
            await state.call(runner.mark, "pausa" if value else "reanudacion")
        state.paused = bool(value)
    elif action == "speed":
        if int(value) not in SPEEDS:
            raise ValueError(f"speed must be one of {SPEEDS}")
        state.speed = int(value)
    else:
        raise ValueError(f"unknown action: {action}")
    await _refresh()
    return _status() | {
        "strategy": runner.strategy,
        "accident_lane": runner.accident_lane,
        "demand": runner.demand,
    }


@app.post("/api/control")
async def control(cmd: Control) -> dict:
    try:
        return await apply_control(cmd.action, cmd.value)
    except (ValueError, KeyError) as exc:
        raise fastapi.HTTPException(400, str(exc)) from exc


# ---- traces ---------------------------------------------------------------------------
def _query_args(component, tls_id, type, desde, hasta) -> dict:
    if component is not None and component not in COMPONENTS:
        raise fastapi.HTTPException(400, f"component must be one of {COMPONENTS}")
    return {"component": component, "tls_id": tls_id, "type": type, "since": desde, "until": hasta}


@app.get("/api/traces")
def traces(
    component: str | None = None,
    tls_id: str | None = None,
    type: str | None = None,
    desde: float | None = None,
    hasta: float | None = None,
    after_seq: int | None = None,
    limit: int = fastapi.Query(200, ge=1, le=5000),
) -> dict:
    args = _query_args(component, tls_id, type, desde, hasta)
    events = state.tracer.query(**args, after_seq=after_seq, limit=limit)
    return {"events": events, "count": len(events)}


def trace_summary() -> dict:
    tracer = state.tracer
    return summarize(
        sim_seconds=tracer.query(component="sim", type="sim_segundo", limit=60),
        decisions=tracer.query(component="rl", type="decision", limit=2000),
        llm_events=tracer.query(component="llm", limit=100_000),
        counts=tracer.counts(),
        now=time.time(),
        fallback_tls=state.runner.fallback_tls if state.runner else [],
    )


@app.get("/api/traces/summary")
def traces_summary() -> dict:
    return trace_summary()


@app.get("/api/traces/export.csv")
def traces_export(
    component: str | None = None,
    tls_id: str | None = None,
    type: str | None = None,
    desde: float | None = None,
    hasta: float | None = None,
) -> StreamingResponse:
    args = _query_args(component, tls_id, type, desde, hasta)
    events = list(reversed(state.tracer.query(**args, limit=10**7)))
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "seq",
            "trace_id",
            "hora_real",
            "tiempo_simulado",
            "componente",
            "tipo",
            "estado",
            "tls_id",
            "datos",
        ]
    )
    for e in events:
        writer.writerow(
            [
                e["seq"],
                e["trace_id"],
                datetime.fromtimestamp(e["ts"]).isoformat(timespec="milliseconds"),
                e["sim_t"],
                e["component"],
                e["type"],
                e["status"],
                e["tls_id"] or "",
                json.dumps(e["data"], ensure_ascii=False),
            ]
        )
    name = f"trazas_{datetime.now():%Y%m%d-%H%M%S}.csv"
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.get("/api/traces/{trace_id}")
def trace_detail(trace_id: str) -> dict:
    events = list(reversed(state.tracer.query(trace_id=trace_id, limit=1000)))
    if not events:
        raise fastapi.HTTPException(404, f"trace not found: {trace_id}")
    return {"trace_id": trace_id, "events": events}


class FaultRequest(BaseModel):
    fault: str
    tls_id: str | None = None


@app.get("/api/faults")
def faults() -> dict:
    return {
        "available": [{"id": k, "label": v} for k, v in FAULTS.items()],
        "armed": state.faults.armed(),
    }


@app.post("/api/faults/arm")
def arm_fault(req: FaultRequest) -> dict:
    try:
        armed = state.faults.arm(req.fault, req.tls_id)
    except ValueError as exc:
        raise fastapi.HTTPException(400, str(exc)) from exc
    note = None
    if req.fault in ("rl_no_response", "detector_loss") and (
        state.runner is None or state.runner.strategy != "rl"
    ):
        note = "se aplicará en la próxima decisión de un agente RL (activa la estrategia RL)"
    return {"armed": armed, "note": note}


# ---- assistant ------------------------------------------------------------------------
class AssistantRequest(BaseModel):
    modo: str
    texto: str = ""


@app.get("/api/llm/info")
def llm_info() -> dict:
    return state.assistant.info()


class KeyRequest(BaseModel):
    api_key: str
    persist: bool = True


@app.post("/api/llm/key")
def set_llm_key(req: KeyRequest) -> dict:
    """Store the provider key typed in the panel. The response never contains it."""
    try:
        return state.assistant.set_key(req.api_key.strip(), req.persist)
    except (ValueError, OSError) as exc:
        raise fastapi.HTTPException(400, str(exc)) from exc


@app.delete("/api/llm/key")
def clear_llm_key() -> dict:
    return state.assistant.set_key(None)


@app.post("/api/llm/test")
async def test_llm_key() -> dict:
    """One real, minimal call to the provider to check the key (traced)."""
    return await state.assistant.test_key()


@app.post("/api/assistant")
async def assistant(req: AssistantRequest) -> dict:
    _runner()
    try:
        return await state.assistant.ask(req.modo, req.texto[:500])
    except ValueError as exc:
        raise fastapi.HTTPException(400, str(exc)) from exc


# ---- live stream ----------------------------------------------------------------------
@app.websocket("/ws/state")
async def ws_state(ws: fastapi.WebSocket):
    await ws.accept()
    sent = -1
    seq = state.tracer.last_seq
    try:
        while True:
            new = state.tracer.since(seq)
            if (state.version != sent or new) and state.snapshot is not None:
                sent = state.version
                if new:
                    seq = new[-1]["seq"]
                await ws.send_json(_status() | state.snapshot | {"traces": new})
            await asyncio.sleep(0.1)
    except (fastapi.WebSocketDisconnect, RuntimeError):
        return


# the panel (web/) on the same origin and port as the API; must be mounted last
app.mount("/", StaticFiles(directory=WEB, html=True, check_dir=False), name="web")
