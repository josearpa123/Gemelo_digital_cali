"""sim-api: runs one live SUMO simulation and streams its state to the web panel."""

import asyncio
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import fastapi
from pydantic import BaseModel

from sim.runner import DEMAND_LEVELS, SimRunner

NET = Path(os.environ.get("SIM_NET", "scenarios/roosevelt4/roosevelt4.net.xml"))
ROUTES = Path(os.environ.get("SIM_ROUTES", "scenarios/roosevelt4/demand/peak_s0.rou.xml"))
AUTOSTART = os.environ.get("SIM_AUTOSTART", "1") == "1"
TICK = 0.1  # seconds of wall time between simulation batches
SPEEDS = (1, 2, 5, 10, 20, 50)


def sumo_version() -> str:
    binary = shutil.which("sumo")
    if binary is None:
        return "missing"
    out = subprocess.run([binary, "--version"], capture_output=True, text=True, check=False)
    return out.stdout.splitlines()[0] if out.stdout else "unknown"


SUMO_VERSION = sumo_version()


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


state = SimState()


@asynccontextmanager
async def lifespan(_app):
    if AUTOSTART and NET.exists() and ROUTES.exists():
        state.runner = SimRunner(NET, ROUTES)
        await state.call(state.runner.start, "fixed")
        state.snapshot = await state.call(state.runner.snapshot)
        state.task = asyncio.create_task(state.loop())
    yield
    if state.task:
        state.task.cancel()
    if state.runner:
        await state.call(state.runner.close)


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
    return {"paused": state.paused, "speed": state.speed, "error": state.error}


class Control(BaseModel):
    action: str
    value: str | int | bool | None = None


@app.post("/api/control")
async def control(cmd: Control) -> dict:
    runner = _runner()
    try:
        if cmd.action == "strategy":
            await state.call(runner.set_strategy, str(cmd.value))
        elif cmd.action == "restart":
            await state.call(runner.start, str(cmd.value or runner.strategy))
            state.error = None
        elif cmd.action == "accident":
            await state.call(runner.set_accident, bool(cmd.value))
        elif cmd.action == "demand":
            await state.call(runner.set_demand, str(cmd.value))
        elif cmd.action == "pause":
            state.paused = bool(cmd.value)
        elif cmd.action == "speed":
            if int(cmd.value) not in SPEEDS:
                raise ValueError(f"speed must be one of {SPEEDS}")
            state.speed = int(cmd.value)
        else:
            raise ValueError(f"unknown action: {cmd.action}")
    except (ValueError, KeyError) as exc:
        raise fastapi.HTTPException(400, str(exc)) from exc
    state.snapshot = await state.call(runner.snapshot)
    state.version += 1
    return _status() | {
        "strategy": runner.strategy,
        "accident_lane": runner.accident_lane,
        "demand": runner.demand,
    }


@app.websocket("/ws/state")
async def ws_state(ws: fastapi.WebSocket):
    await ws.accept()
    sent = -1
    try:
        while True:
            if state.version != sent and state.snapshot is not None:
                sent = state.version
                await ws.send_json(_status() | state.snapshot)
            await asyncio.sleep(0.1)
    except (fastapi.WebSocketDisconnect, RuntimeError):
        return
