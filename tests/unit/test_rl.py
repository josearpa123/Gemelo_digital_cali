"""Observation size on a real sumo-rl env and reward bookkeeping with fake signals."""

from types import SimpleNamespace

import pytest

pytest.importorskip("sumo_rl")

from rl import reward as reward_mod  # noqa: E402
from rl.observation import MAX_NEIGHBORS  # noqa: E402
from rl.reward import NeighborReward  # noqa: E402


def test_observation_size_matches_space(grid_cfg):
    from rl.env import MultiRouteEnvironment
    from rl.observation import NeighborObservation

    net = grid_cfg.parent / "grid2x2.net.xml"
    routes = grid_cfg.parent / "grid2x2.rou.xml"
    env = MultiRouteEnvironment(
        route_files=[str(routes)],
        net_file=str(net),
        num_seconds=60,
        observation_class=NeighborObservation,
        sumo_warnings=False,
        sumo_seed=0,
    )
    try:
        obs = env.reset()
        obs = obs[0] if isinstance(obs, tuple) else obs
        assert set(obs) == set(env.traffic_signals)
        for tls_id, ts in env.traffic_signals.items():
            expected = ts.num_green_phases + 2 + 2 * len(ts.lanes) + MAX_NEIGHBORS
            assert obs[tls_id].shape == (expected,)
            assert env.observation_spaces(tls_id).shape == (expected,)
    finally:
        env.close()


class FakeSignal:
    def __init__(self, tls_id, env, value):
        self.id, self.env, self.value, self.calls = tls_id, env, value, 0

    def _diff_waiting_time_reward(self):
        self.calls += 1
        return self.value

    def get_pressure(self):
        return 0.0


@pytest.fixture
def fake_env(monkeypatch):
    env = SimpleNamespace(sim_step=0, _net="fake.net.xml", traffic_signals={})
    for tls_id, value in {"A": -1.0, "B": -3.0, "C": -5.0}.items():
        env.traffic_signals[tls_id] = FakeSignal(tls_id, env, value)
    neighbors = {"A": ("B", "C"), "B": ("A",), "C": ("A",)}
    monkeypatch.setattr(reward_mod, "neighbor_map", lambda net: neighbors)
    return env


def test_base_reward_computed_once_per_step(fake_env):
    fn = NeighborReward(alpha=0.3)
    for ts in fake_env.traffic_signals.values():
        fn(ts)
    assert all(ts.calls == 1 for ts in fake_env.traffic_signals.values())
    fake_env.sim_step = 5
    fn(fake_env.traffic_signals["A"])
    assert all(ts.calls == 2 for ts in fake_env.traffic_signals.values())


def test_alpha_zero_ignores_neighbors(fake_env):
    assert NeighborReward(alpha=0.0)(fake_env.traffic_signals["A"]) == pytest.approx(-1.0)


def test_alpha_adds_mean_of_neighbors(fake_env):
    r = NeighborReward(alpha=0.3)(fake_env.traffic_signals["A"])
    assert r == pytest.approx(-1.0 + 0.3 * (-3.0 - 5.0) / 2)


def test_pressure_weight_is_added():
    ts = SimpleNamespace(_diff_waiting_time_reward=lambda: -2.0, get_pressure=lambda: -10.0)
    assert reward_mod.base_reward(ts, 0.05) == pytest.approx(-2.5)
