"""Training traces: one JSON line per episode written by the trainer's callback."""

import json

import pytest

pytest.importorskip("stable_baselines3")

from rl.trace_callback import EpisodeTraceCallback  # noqa: E402


class FakeModel:
    num_timesteps = 0


def test_one_line_per_finished_episode(tmp_path):
    cb = EpisodeTraceCallback("ppo_test", tmp_path, delta_time=5)
    cb.model = FakeModel()
    cb.num_timesteps = 0
    cb._on_training_start()
    for step in range(3):
        cb.locals = {"infos": [{"system_mean_waiting_time": 10.0 * (step + 1)}] * 2}
        cb.num_timesteps += 2
        cb._on_step()
    cb.locals = {
        "infos": [
            {"system_mean_waiting_time": 40.0, "episode": {"r": -4.0, "l": 4}},
            {"system_mean_waiting_time": 40.0, "episode": {"r": -2.0, "l": 4}},
        ]
    }
    cb.num_timesteps += 2
    cb._on_step()
    cb._on_training_end()
    lines = [json.loads(x) for x in (tmp_path / "ppo_test.jsonl").read_text().splitlines()]
    assert [x["type"] for x in lines] == ["entrenamiento_inicio", "episodio", "entrenamiento_fin"]
    ep = lines[1]
    assert ep["run_id"] == "ppo_test" and ep["episodio"] == 1 and ep["agentes"] == 2
    assert ep["recompensa_media"] == -3.0
    assert ep["espera_media_s"] == 25.0  # mean of 10, 20, 30, 40
    assert ep["duracion_sim_s"] == 20 and ep["timesteps"] == 8
