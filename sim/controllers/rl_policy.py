"""Trained PPO policy driving every tls live, with the same TrafficSignal logic as training."""

import json
from pathlib import Path

import numpy as np

from sim.controllers.base import Controller

MODELS_DIR = Path("models")


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

    @property
    def sim_step(self) -> float:
        return self.sumo.simulation.getTime()


class RLController(Controller):
    name = "rl"
    label = "Agentes RL (PPO)"

    def __init__(self, net_file: str, model_path: Path):
        from stable_baselines3 import PPO

        self.net_file = net_file
        self.model_path = model_path
        self.model = PPO.load(str(model_path), device="cpu")
        self.obs_size = self.model.observation_space.shape[0]
        config = model_path.parent / "config.json"
        self.config = json.loads(config.read_text()) if config.exists() else {}
        self.signals = {}

    def activate(self, sumo, programs: dict) -> None:
        from sumo_rl.environment.traffic_signal import TrafficSignal

        from rl.env import DELTA_TIME, MAX_GREEN, MIN_GREEN, YELLOW_TIME
        from rl.observation import NeighborObservation

        env = _EnvShim(sumo, self.net_file, NeighborObservation)
        now = int(sumo.simulation.getTime())
        for tls_id in programs:
            env.traffic_signals[tls_id] = TrafficSignal(
                env,
                tls_id,
                DELTA_TIME,
                YELLOW_TIME,
                MIN_GREEN,
                MAX_GREEN,
                now,
                "diff-waiting-time",
                sumo,
            )
        self.signals = env.traffic_signals

    def step(self, sumo) -> None:
        for ts in self.signals.values():
            if ts.time_to_act:
                obs = ts.compute_observation()
                padded = np.zeros(self.obs_size, dtype=np.float32)
                padded[: len(obs)] = obs[: self.obs_size]
                action, _ = self.model.predict(padded, deterministic=True)
                action = int(action)
                # SuperSuit maps padded actions beyond this tls' phases to phase 0
                ts.set_next_phase(action if action < ts.num_green_phases else 0)

    def after_step(self) -> None:
        for ts in self.signals.values():
            ts.update()

    def deactivate(self, sumo, programs: dict) -> None:
        self.signals = {}
        super().deactivate(sumo, programs)
