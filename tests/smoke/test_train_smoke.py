"""PPO trains 1000 timesteps on roosevelt4 with a short episode, saves and loads."""

import json
import multiprocessing
from pathlib import Path

import pytest

NET = Path("scenarios/roosevelt4/roosevelt4.net.xml")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not NET.exists(), reason="run python -m sim.network.build_osm first"),
]


def test_train_1000_timesteps_saves_loadable_model(tmp_path):
    pytest.importorskip("stable_baselines3")
    from stable_baselines3 import PPO

    from rl.train import train
    from sim.demand import train_routes

    if not all(r.exists() for r in train_routes(NET)):
        pytest.skip("run make dataset first")
    multiprocessing.set_start_method("spawn", force=True)
    out = train(
        NET,
        timesteps=1000,
        alpha=0.3,
        seed=0,
        n_envs=1,
        num_seconds=300,
        out_root=tmp_path / "models",
        tb_root=tmp_path / "tb",
        checkpoint_every=500,
        traces_root=tmp_path / "traces",
    )
    assert (out / "model.zip").exists()
    assert (out / "config.json").exists()
    assert list((out / "checkpoints").glob("ppo_*_steps.zip"))
    model = PPO.load(str(out / "model.zip"), device="cpu")
    assert model.observation_space.shape[0] > 0
    config = json.loads((out / "config.json").read_text())
    assert config["status"] == "completed"
    assert config["provenance"]["network_sha256"]
    checkpoint = max((out / "checkpoints").glob("ppo_*_steps.zip"), key=lambda p: p.stat().st_mtime)
    saved = PPO.load(str(checkpoint), device="cpu")
    resumed = train(
        NET,
        timesteps=512,
        alpha=0.3,
        seed=0,
        n_envs=1,
        num_seconds=300,
        out_root=tmp_path / "models",
        tb_root=tmp_path / "tb",
        checkpoint_every=500,
        traces_root=tmp_path / "traces",
        resume=checkpoint,
    )
    restored = PPO.load(str(resumed / "model.zip"), device="cpu")
    assert restored.num_timesteps > model.num_timesteps
    config = json.loads((resumed / "config.json").read_text())
    assert config["initial_timesteps"] == saved.num_timesteps
