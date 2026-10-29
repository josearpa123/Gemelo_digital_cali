"""Cyclic max-pressure against a TraCI double that runs a 4-phase program
(north-south green, yellow, east-west green, yellow) like SUMO does."""

from types import SimpleNamespace

from sim.controllers.maxpressure import (
    DECISION,
    MAX_GREEN,
    MIN_GREEN,
    MaxPressureController,
    decision_phases,
    pressure,
    should_advance,
)

NS, NS_Y, EW, EW_Y = "GGrr", "yyrr", "rrGG", "rryy"
DURATIONS = [30, 3, 30, 3]
LINKS = [
    [("n_in", "s_out", "")],
    [("s_in", "n_out", "")],
    [("e_in", "w_out", "")],
    [("w_in", "e_out", "")],
]


class FakeSumo:
    def __init__(self, queues: dict[str, int]):
        self.time = 0.0
        self.queues = queues
        self.phase, self.remaining = 0, DURATIONS[0]
        self.history: list[str] = []
        self.simulation = SimpleNamespace(getTime=lambda: self.time)
        self.lane = SimpleNamespace(
            getLastStepHaltingNumber=lambda lane: self.queues.get(lane, 0),
            getLength=lambda lane: 75.0,
        )
        self.trafficlight = SimpleNamespace(
            getControlledLinks=lambda tls: LINKS,
            getPhase=lambda tls: self.phase,
            setPhaseDuration=self._set_duration,
            setProgramLogic=lambda tls, logic: None,
            setProgram=lambda tls, pid: None,
        )

    def _set_duration(self, tls, seconds):
        self.remaining = seconds

    def tick(self):
        """One simulation second of the program."""
        self.history.append([NS, NS_Y, EW, EW_Y][self.phase])
        self.time += 1
        self.remaining -= 1
        if self.remaining <= 0:
            self.phase = (self.phase + 1) % 4
            self.remaining = DURATIONS[self.phase]


def programs():
    phases = [
        SimpleNamespace(state=s, duration=d)
        for s, d in zip((NS, NS_Y, EW, EW_Y), DURATIONS, strict=True)
    ]
    return {"J": ("0", [SimpleNamespace(programID="0", phases=phases)])}


def run(queues, seconds):
    sumo = FakeSumo(queues)
    ctrl = MaxPressureController()
    ctrl.activate(sumo, programs())
    for _ in range(seconds):
        ctrl.step(sumo)
        sumo.tick()
    return sumo


def test_decision_phases_skip_yellow_and_repeated_movements():
    states = [NS, NS_Y, EW, EW_Y, "GGrr"]
    assert sorted(decision_phases(states, LINKS)) == [0, 2]


def test_pressure_counts_each_incoming_lane_once():
    moves = {("a", "x"), ("a", "y"), ("a", "z")}
    assert pressure(moves, {"a": 6, "x": 3, "y": 0, "z": 0}) == 5


def test_should_advance_keeps_current_on_tie():
    assert not should_advance({0: 3.0, 2: 3.0}, 0, max_green_reached=False)
    assert should_advance({0: 3.0, 2: 4.0}, 0, max_green_reached=False)
    assert should_advance({0: 9.0, 2: 0.0}, 0, max_green_reached=True)


def test_respects_minimum_green():
    sumo = run({"e_in": 20, "w_in": 20}, MIN_GREEN)
    assert set(sumo.history) == {NS}


def test_switches_through_yellow_to_highest_pressure():
    sumo = run({"e_in": 20, "w_in": 20}, MIN_GREEN + 5)
    first_yellow = sumo.history.index(NS_Y)
    assert first_yellow == MIN_GREEN + 1
    assert sumo.history[first_yellow : first_yellow + 3] == [NS_Y] * 3
    assert sumo.history[first_yellow + 3] == EW


def test_holds_green_beyond_program_while_pressure_is_highest():
    sumo = run({"n_in": 20}, DURATIONS[0] + 2 * DECISION)
    assert set(sumo.history) == {NS}


def test_downstream_queue_lowers_pressure():
    # east-west has more vehicles waiting but its exits are full: keep north-south
    queues = {"n_in": 4, "e_in": 10, "w_out": 9, "w_in": 10, "e_out": 9}
    sumo = run(queues, DURATIONS[0] + DECISION)
    assert set(sumo.history) == {NS}


def test_max_green_forces_a_change():
    sumo = run({"n_in": 20, "e_in": 1}, MAX_GREEN + 2)
    assert NS_Y in sumo.history
    assert sumo.history.index(NS_Y) <= MAX_GREEN + 1


def test_deactivate_releases_signals():
    sumo = FakeSumo({})
    ctrl = MaxPressureController()
    ctrl.activate(sumo, programs())
    assert ctrl.signals
    ctrl.deactivate(sumo, programs())
    assert not ctrl.signals
