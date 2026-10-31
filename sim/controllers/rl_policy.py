"""Trained PPO policy driving every tls live, with the same TrafficSignal logic as training."""

import json
import time
from pathlib import Path

import numpy as np

from sim.controllers.base import Controller, restore_programs
from sim.tracing import NullTracer, new_trace_id

MODELS_DIR = Path("models")
MAX_NEIGHBORS = 4  # rl.observation.MAX_NEIGHBORS (rl/ is imported lazily, it needs sumo-rl)
INFERENCE_BUDGET_MS = 200  # slower agents hand their tls back to fixed time
FALLBACK_SECONDS = 120  # simulated seconds in fixed time before the agent takes over again


def find_model(models_dir: Path = MODELS_DIR) -> Path | None:
    """models/current/model.zip if present, otherwise the most recent trained model."""
    current = models_dir / "current" / "model.zip"
    if current.exists():
        return current
    candidates = sorted(models_dir.glob("*/model.zip"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


class _EnvShim:
    """The subset of sumo-rl's SumoEnvironment that TrafficSignal and our observation use."""

    fixed_ts = False

    def __init__(self, sumo, net_file: str, observation_class):
        self.sumo = sumo
        self._net = net_file
        self.observation_class = observation_class
        self.traffic_signals = {}
        self.vehicles = {}  # per-vehicle waiting-time cache used by sumo-rl's reward

    @property
    def sim_step(self) -> float:
        return self.sumo.simulation.getTime()


def cached_wait_per_lane(ts, cache: dict) -> list[float]:
    """sumo-rl's TrafficSignal.get_accumulated_waiting_time_per_lane, reading each vehicle's
    accumulated waiting time from the runner's per-step cache instead of one libsumo call
    per vehicle (same values: the cache is filled right after the last simulation step)."""
    vehicles = ts.env.vehicles
    out = []
    for lane in ts.lanes:
        total = 0.0
        if lane.startswith(":"):  # pedestrian crossing / walking area: never holds vehicles
            out.append(total)
            continue
        for veh in ts.sumo.lane.getLastStepVehicleIDs(lane):
            acc = cache.get(veh)
            if acc is None:
                acc = ts.sumo.vehicle.getAccumulatedWaitingTime(veh)
            record = vehicles.get(veh)
            if record is None:
                record = vehicles[veh] = {lane: acc}
            else:
                record[lane] = acc - sum(v for k, v in record.items() if k != lane)
            total += record[lane]
        out.append(total)
    return out


def vehicle_lanes(lanes) -> list[str]:
    return [lane for lane in lanes if not lane.startswith(":")]


def fast_pressure(ts, in_lanes: list[str], out_lanes: list[str]) -> int:
    """sumo-rl's TrafficSignal.get_pressure without pedestrian lanes (always 0 vehicles)."""
    count = ts.sumo.lane.getLastStepVehicleNumber
    return sum(map(count, out_lanes)) - sum(map(count, in_lanes))


class AgentTimeout(RuntimeError):
    """The policy did not answer within INFERENCE_BUDGET_MS."""


def model_version(model_path: Path) -> str:
    """Run id of the model (resolving models/current) plus its file date."""
    resolved = model_path.resolve()
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(resolved.stat().st_mtime))
    return f"{resolved.parent.name} ({stamp})"


class RLController(Controller):
    name = "rl"
    label = "Agentes RL (PPO)"

    def __init__(
        self,
        net_file: str,
        model_path: Path,
        tracer=None,
        faults=None,
        names: dict[str, str] | None = None,
        edge_names: dict[str, str] | None = None,
        wait_cache=None,
    ):
        from stable_baselines3 import PPO

        from rl.reward import NeighborReward

        started = time.perf_counter()
        self.net_file = net_file
        self.model_path = model_path
        self.model = PPO.load(str(model_path), device="cpu")
        self.obs_size = self.model.observation_space.shape[0]
        config = model_path.parent / "config.json"
        self.config = json.loads(config.read_text()) if config.exists() else {}
        self.signals = {}
        self.tracer = tracer or NullTracer()
        self.faults = faults
        self.names = names or {}
        self.edge_names = edge_names or {}
        self.wait_cache = wait_cache  # () -> {vehicle: accumulated waiting time}
        self.roads: dict[str, list[tuple[str, str]]] = {}
        self.alpha = float(self.config.get("alpha", 0.0))
        self.reward = NeighborReward(alpha=self.alpha)
        self.version = model_version(model_path)
        self.fallback: dict[str, float] = {}  # tls -> simulated time when the agent takes over
        self.last_obs: dict[str, np.ndarray] = {}
        self.tracer.emit(
            "rl",
            "carga_modelo",
            data={
                "modelo": self.version,
                "alpha": self.alpha,
                "timesteps": self.config.get("timesteps"),
                "carga_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )

    def activate(self, sumo, programs: dict) -> None:
        from rl.observation import NeighborObservation

        self.sumo = sumo
        self.programs = programs
        self.env = _EnvShim(sumo, self.net_file, NeighborObservation)
        now = int(sumo.simulation.getTime())
        for tls_id in programs:
            self._new_signal(tls_id, now)
        self.signals = self.env.traffic_signals
        # re-activation after a reconnection: tls still in fallback stay in fixed time
        for tls_id in self.fallback:
            restore_programs(sumo, {tls_id: programs[tls_id]})

    def _new_signal(self, tls_id: str, now: int) -> None:
        from sumo_rl.environment.traffic_signal import TrafficSignal

        from rl.env import DELTA_TIME, MAX_GREEN, MIN_GREEN, YELLOW_TIME

        ts = TrafficSignal(
            self.env,
            tls_id,
            DELTA_TIME,
            YELLOW_TIME,
            MIN_GREEN,
            MAX_GREEN,
            now,
            "diff-waiting-time",
            self.sumo,
        )
        # faster equivalents of the reward's two terms (tests/unit/test_rl_tracing.py checks
        # they return the same values as sumo-rl's originals)
        in_lanes, out_lanes = vehicle_lanes(ts.lanes), vehicle_lanes(ts.out_lanes)
        ts.get_pressure = lambda: fast_pressure(ts, in_lanes, out_lanes)
        if self.wait_cache is not None:
            ts.get_accumulated_waiting_time_per_lane = lambda: cached_wait_per_lane(
                ts, self.wait_cache()
            )
        self.env.traffic_signals[tls_id] = ts
        # incoming edges with their road name (pedestrian crossings and walking areas skipped);
        # edge-level queries are ~4x fewer libsumo calls than lane-level ones
        edges = dict.fromkeys(ln.rsplit("_", 1)[0] for ln in ts.lanes if not ln.startswith(":"))
        self.roads[tls_id] = [(edge, self.edge_names.get(edge) or edge) for edge in edges]
        if len(self.env.vehicles) > 5000:  # forget vehicles that already left
            alive = set(self.sumo.vehicle.getIDList())
            self.env.vehicles = {v: r for v, r in self.env.vehicles.items() if v in alive}

    @property
    def fallback_tls(self) -> list[str]:
        return sorted(self.fallback)

    def step(self, sumo) -> None:
        now = sumo.simulation.getTime()
        for tls_id, ts in list(self.signals.items()):
            if tls_id in self.fallback:
                if now >= self.fallback[tls_id]:
                    self._recover(tls_id, now)
            elif ts.time_to_act:
                self._decide(sumo, tls_id, ts, now)

    def _observe(self, tls_id: str, ts, now: float, trace_id: str) -> np.ndarray:
        obs = ts.compute_observation()
        simulated = bool(self.faults and self.faults.take("detector_loss", tls_id))
        if simulated:
            # the lane detectors (density and queue of every incoming lane) return nothing
            start = ts.num_green_phases + 2
            obs = obs.astype(np.float32, copy=True)
            obs[start : start + 2 * len(ts.lanes)] = np.nan
        missing = np.isnan(obs)
        if missing.any():
            last = self.last_obs.get(tls_id)
            obs = np.where(missing, last if last is not None else 0.0, obs).astype(np.float32)
            self.tracer.emit(
                "rl",
                "observacion_incompleta",
                "warn",
                data={
                    "interseccion": self.names.get(tls_id, tls_id),
                    "valores_perdidos": int(missing.sum()),
                    "de": int(missing.size),
                    "respaldo": "último valor válido"
                    if last is not None
                    else "cero (sin historia)",
                    "simulado": simulated,
                },
                sim_t=now,
                tls_id=tls_id,
                trace_id=trace_id,
            )
        self.last_obs[tls_id] = obs
        return obs

    def _approaches(self, sumo, tls_id: str) -> list[dict]:
        """Queue and waiting time per incoming road."""
        by_road: dict[str, dict] = {}
        for edge, road in self.roads[tls_id]:
            item = by_road.get(road)
            if item is None:
                item = by_road[road] = {"via": road, "cola": 0, "espera_s": 0.0}
            item["cola"] += sumo.edge.getLastStepHaltingNumber(edge)
            item["espera_s"] += sumo.edge.getWaitingTime(edge)
        out = sorted(by_road.values(), key=lambda a: (a["cola"], a["espera_s"]), reverse=True)
        for a in out:
            a["espera_s"] = round(a["espera_s"], 1)
        return out

    def _decide(self, sumo, tls_id: str, ts, now: float) -> None:
        trace_id = new_trace_id()
        name = self.names.get(tls_id, tls_id)
        previous = int(ts.green_phase)
        obs = self._observe(tls_id, ts, now, trace_id)
        padded = np.zeros(self.obs_size, dtype=np.float32)
        padded[: len(obs)] = obs[: self.obs_size]
        started = time.perf_counter()
        try:
            if self.faults and self.faults.take("rl_no_response", tls_id):
                raise AgentTimeout("agente sin respuesta (fallo simulado)")
            action, _ = self.model.predict(padded, deterministic=True)
            inference_ms = (time.perf_counter() - started) * 1000
            if inference_ms > INFERENCE_BUDGET_MS:
                raise AgentTimeout(
                    f"inferencia de {inference_ms:.0f} ms > {INFERENCE_BUDGET_MS} ms"
                )
        except Exception as exc:  # any agent failure: this tls goes back to fixed time
            self._to_fixed(tls_id, now, str(exc) or type(exc).__name__, trace_id)
            return
        action = int(action)
        # SuperSuit maps padded actions beyond this tls' phases to phase 0
        chosen = action if action < ts.num_green_phases else 0
        if not self.tracer.enabled:  # reward and approaches are computed only for the traces
            ts.set_next_phase(chosen)
            return
        reward = float(self.reward(ts))
        approaches = self._approaches(sumo, tls_id)
        ts.set_next_phase(chosen)
        top = approaches[0] if approaches else None
        reason = (
            f"mayor cola en {top['via']}: {top['cola']} veh, {top['espera_s']} s de espera"
            if top and top["cola"]
            else "sin colas en las aproximaciones"
        )
        neighbors = [round(float(q), 3) for q in obs[-MAX_NEIGHBORS:]] if self.alpha else []
        self.tracer.emit(
            "rl",
            "decision",
            data={
                "interseccion": name,
                "fase_anterior": previous,
                "fase_elegida": chosen,
                "cambia": chosen != previous,
                "estado_verde": ts.green_phases[chosen].state,
                "motivo": reason,
                "aproximaciones": approaches,
                "recompensa": round(reward, 4),
                "alpha": self.alpha,
                "usa_vecinas": self.alpha > 0,
                "cola_vecinas": neighbors,
                "inference_ms": round(inference_ms, 3),
                "modelo": self.version,
            },
            sim_t=now,
            tls_id=tls_id,
            trace_id=trace_id,
        )

    def _to_fixed(self, tls_id: str, now: float, reason: str, trace_id: str) -> None:
        restore_programs(self.sumo, {tls_id: self.programs[tls_id]})
        self.fallback[tls_id] = now + FALLBACK_SECONDS
        self.tracer.emit(
            "rl",
            "fallback_control",
            "fallback",
            data={
                "interseccion": self.names.get(tls_id, tls_id),
                "motivo": reason,
                "umbral_ms": INFERENCE_BUDGET_MS,
                "control": "tiempo fijo",
                "vuelve_en_s": FALLBACK_SECONDS,
            },
            sim_t=now,
            tls_id=tls_id,
            trace_id=trace_id,
        )

    def _recover(self, tls_id: str, now: float) -> None:
        self._new_signal(tls_id, int(now))
        self.signals = self.env.traffic_signals
        del self.fallback[tls_id]
        self.tracer.emit(
            "rl",
            "control_recuperado",
            data={"interseccion": self.names.get(tls_id, tls_id), "control": "agente RL"},
            sim_t=now,
            tls_id=tls_id,
        )

    def after_step(self) -> None:
        for tls_id, ts in self.signals.items():
            if tls_id not in self.fallback:
                ts.update()

    def deactivate(self, sumo, programs: dict) -> None:
        self.signals = {}
        self.fallback = {}
        super().deactivate(sumo, programs)
