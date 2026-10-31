"""Training traces: one JSON line per finished episode, read by sim-api's "Trazas" panel.

Written by the trainer container into outputs/traces/training/<run_id>.jsonl, so the panel
shows training progress even though training runs in a separate process."""

import json
import time
from pathlib import Path

from stable_baselines3.common.callbacks import BaseCallback

TRAINING_TRACES = Path("outputs/traces/training")


class EpisodeTraceCallback(BaseCallback):
    """SuperSuit's vec env has one slot per (env copy, agent); every agent of an env copy
    ends its episode on the same step, so slots finishing together form one episode."""

    def __init__(self, run_id: str, folder: Path = TRAINING_TRACES, delta_time: int = 5):
        super().__init__()
        self.run_id = run_id
        self.path = Path(folder) / f"{run_id}.jsonl"
        self.delta_time = delta_time
        self.episodes = 0
        self._wait_sum: dict[int, float] = {}
        self._wait_n: dict[int, int] = {}
        self._last_end = time.time()

    def _on_training_start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write({"type": "entrenamiento_inicio", "timesteps": self.num_timesteps})

    def _write(self, item: dict) -> None:
        item = {"run_id": self.run_id, "ts": time.time()} | item
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(item) + "\n")

    def _on_step(self) -> bool:
        finished = []
        for i, info in enumerate(self.locals.get("infos", [])):
            wait = info.get("system_mean_waiting_time")
            if wait is not None:
                self._wait_sum[i] = self._wait_sum.get(i, 0.0) + float(wait)
                self._wait_n[i] = self._wait_n.get(i, 0) + 1
            if "episode" in info:
                n = self._wait_n.pop(i, 0)
                total = self._wait_sum.pop(i, 0.0)
                finished.append((info["episode"], total / n if n else None))
        if finished:
            now = time.time()
            waits = [w for _, w in finished if w is not None]
            length = max(int(ep["l"]) for ep, _ in finished)
            self.episodes += 1
            self._write(
                {
                    "type": "episodio",
                    "episodio": self.episodes,
                    "agentes": len(finished),
                    "recompensa_media": round(
                        sum(float(ep["r"]) for ep, _ in finished) / len(finished), 3
                    ),
                    "espera_media_s": round(sum(waits) / len(waits), 2) if waits else None,
                    "duracion_sim_s": length * self.delta_time,
                    "duracion_real_s": round(now - self._last_end, 1),
                    "timesteps": int(self.num_timesteps),
                }
            )
            self._last_end = now
        return True

    def _on_training_end(self) -> None:
        self._write({"type": "entrenamiento_fin", "timesteps": int(self.num_timesteps)})
