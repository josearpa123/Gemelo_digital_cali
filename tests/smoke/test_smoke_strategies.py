"""Every available strategy runs 300 steps on roosevelt4 (peak, seed 0) without errors."""

from pathlib import Path

import pytest

NET = Path("scenarios/roosevelt4/roosevelt4.net.xml")
ROUTES = Path("scenarios/roosevelt4/demand/peak_s0.rou.xml")

pytestmark = pytest.mark.skipif(
    not (NET.exists() and ROUTES.exists()), reason="run make dataset first"
)


@pytest.fixture(scope="module")
def runner():
    from sim.runner import SimRunner

    r = SimRunner(NET, ROUTES)
    yield r
    r.close()


@pytest.mark.parametrize("strategy", ["fixed", "maxpressure", "rl"])
def test_strategy_runs_300_steps(runner, strategy):
    if strategy not in runner.strategies:
        pytest.skip(f"{strategy} not available (no trained model)")
    runner.start(strategy)
    for _ in range(300):
        runner.step()
    snap = runner.snapshot()
    assert snap["t"] == 300
    assert snap["strategy"] == strategy
    assert snap["metrics"]["arrived"] > 0
    assert len(snap["tls"]) == 4


def test_accident_lane_does_not_break_routes(runner):
    """Closing the accident lane for 15 min must not strand vehicles with an invalid route."""
    from sim.events import load_event

    event = load_event(NET)
    runner.start("fixed")
    runner.set_accident(True, event["lane"] if event else None)
    for _ in range(900):
        runner.step()
    assert runner.accident_lane
    runner.set_accident(False)
    assert runner.accident_lane is None
