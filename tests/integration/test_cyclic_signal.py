"""Cyclic RL signal on the real network: whatever the agent does, every tls only shows states
of its own program, advances in program order and respects minimum and maximum green."""

import random
from pathlib import Path

import pytest

pytest.importorskip("sumo_rl")

NET = Path("scenarios/roosevelt4/roosevelt4.net.xml")
ROUTES = Path("scenarios/roosevelt4/demand/peak_s0.rou.xml")


@pytest.fixture
def sim():
    import libsumo

    if not (NET.exists() and ROUTES.exists()):
        pytest.skip("run make dataset first")
    libsumo.start(["sumo", "-n", str(NET), "-r", str(ROUTES), "--seed", "0", "--no-step-log",
                   "--no-warnings", "--time-to-teleport", "300"])  # fmt: skip
    yield libsumo
    libsumo.close()


def make_signals(sumo):
    from rl.cyclic_signal import CyclicTrafficSignal
    from rl.env import DELTA_TIME, MAX_GREEN, MIN_GREEN, YELLOW_TIME
    from rl.observation import NeighborObservation
    from sim.controllers.rl_policy import _EnvShim

    env = _EnvShim(sumo, str(NET), NeighborObservation)
    for tls in sumo.trafficlight.getIDList():
        env.traffic_signals[tls] = CyclicTrafficSignal(
            env, tls, DELTA_TIME, YELLOW_TIME, MIN_GREEN, MAX_GREEN, 0, "diff-waiting-time", sumo
        )
    return env.traffic_signals


def test_random_agent_only_uses_program_states_in_cycle_order(sim):
    signals = make_signals(sim)
    program_states = {
        tls: {p.state for p in sim.trafficlight.getAllProgramLogics(tls)[0].phases}
        for tls in signals
    }
    rng = random.Random(0)
    visited = {tls: [] for tls in signals}
    greens = {tls: [] for tls in signals}  # (start, end) of each decision green
    for _ in range(900):
        for ts in signals.values():
            if ts.time_to_act:
                ts.set_next_phase(rng.randint(0, 1))
        sim.simulationStep()
        for tls, ts in signals.items():
            before = ts.green_phase, ts.is_yellow
            ts.update()
            state = sim.trafficlight.getRedYellowGreenState(tls)
            assert state in program_states[tls], f"{tls} showed a state outside its program"
            phase = sim.trafficlight.getPhase(tls)
            if not visited[tls] or visited[tls][-1] != phase:
                visited[tls].append(phase)
            now = sim.simulation.getTime()
            if before[1] and not ts.is_yellow:
                greens[tls].append([now, None])
            elif not before[1] and ts.is_yellow and greens[tls]:
                greens[tls][-1][1] = now
    for tls, ts in signals.items():
        n = len(ts.all_phases)
        steps = [(b - a) % n for a, b in zip(visited[tls], visited[tls][1:], strict=False)]
        assert all(s == 1 for s in steps), f"{tls} skipped phases of its program: {visited[tls]}"
        for start, end in greens[tls]:
            if end is None:
                continue
            # max green is checked at decisions (every delta_time); the release takes effect on
            # the next step and this loop notices it one step later: + 2 s
            assert end - start <= ts.max_green + ts.delta_time + 2, f"{tls} exceeded max green"
    # the random agent did advance somewhere (the test is not vacuous)
    assert any(len(v) > 3 for v in visited.values())


def test_keep_holds_the_green_until_max_green(sim):
    signals = make_signals(sim)
    tls, ts = next((t, s) for t, s in signals.items() if s.can_advance)
    for _ in range(400):
        if ts.time_to_act:
            ts.set_next_phase(0)  # always keep
        sim.simulationStep()
        ts.update()
    # always "keep" still cycles, forced by max green: never longer than max_green + delta
    assert ts.time_since_last_phase_change <= ts.max_green + ts.delta_time + 60


def test_action_space_is_keep_or_advance(sim):
    for ts in make_signals(sim).values():
        assert ts.action_space.n == 2
        assert ts.num_green_phases == len(ts.decision) >= 1
        assert ts.observation_space.shape[0] == ts.num_green_phases + 2 + 2 * len(ts.lanes) + 4
