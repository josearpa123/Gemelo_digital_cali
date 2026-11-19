import json
from pathlib import Path

from rl.env import MultiRouteEnvironment
from sim.demand import generate
from sim.events import event_path

NET = Path("scenarios/roosevelt4/roosevelt4.net.xml")


def test_event_training_closes_and_restores_the_lane(tmp_path):
    net = tmp_path / NET.name
    net.write_bytes(NET.read_bytes())
    event = json.loads(event_path(NET).read_text())
    event.update(begin=10, duration=15)
    event_path(net).write_text(json.dumps(event))
    route = generate(net, "event", 100, end=60)
    env = MultiRouteEnvironment(
        route_files=[str(route)],
        net_file=str(net),
        num_seconds=60,
        sumo_seed=0,
        sumo_warnings=False,
    )
    try:
        env.reset()
        lane = event["lane"]
        allowed = list(env.sumo.lane.getAllowed(lane))
        speed = env.sumo.lane.getMaxSpeed(lane)
        for _ in range(15):
            env._sumo_step()
        assert list(env.sumo.lane.getAllowed(lane)) == ["authority"]
        assert env.sumo.lane.getMaxSpeed(lane) == 1.0
        for _ in range(15):
            env._sumo_step()
        assert list(env.sumo.lane.getAllowed(lane)) == allowed
        assert env.sumo.lane.getMaxSpeed(lane) == speed
    finally:
        env.close()
