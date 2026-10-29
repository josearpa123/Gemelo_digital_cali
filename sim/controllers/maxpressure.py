"""Cyclic max-pressure (Le et al. 2015; Levin et al. 2020) on top of SUMO's own program.

The program keeps its phase order and its yellow/clearance phases (the joined clusters of
roosevelt4 need them: jumping between arbitrary greens gridlocks the short median lanes).
Each decision green is held while it has the largest pressure; every DECISION seconds after
the minimum green (MIN_GREEN, or less if the program's green is shorter), if another green
phase has more pressure (or MAX_GREEN is reached) the program advances through its own
transition. Ties keep the current green.

Pressure of a phase = sum over the incoming lanes it serves of (occupancy in - mean occupancy
of its outgoing lanes), with occupancy = halting vehicles / lane capacity."""

from sim.controllers.base import Controller, restore_programs

DECISION = 5
MIN_GREEN = 10
MAX_GREEN = 60
HOLD = 10_000  # remaining duration that keeps a green until we release it
VEHICLE_SPACE = 7.5  # metres per queued vehicle


def is_green(state: str) -> bool:
    return "y" not in state and ("G" in state or "g" in state)


def phase_movements(state: str, links: list) -> frozenset[tuple[str, str]]:
    """(incoming lane, outgoing lane) pairs enabled by a green state."""
    moves = set()
    for index, signal in enumerate(state):
        if signal in "Gg" and index < len(links):
            for link in links[index]:
                moves.add((link[0], link[1]))
    return frozenset(moves)


def decision_phases(states: list[str], links: list) -> dict[int, frozenset]:
    """Green phases with a distinct set of vehicle movements. A repeated set (e.g. the same
    green with pedestrian crossings turning red) is a transition and runs on the program."""
    out: dict[int, frozenset] = {}
    for i, state in enumerate(states):
        if is_green(state):
            moves = phase_movements(state, links)
            if moves and moves not in out.values():
                out[i] = moves
    return out


def pressure(moves, queue: dict[str, float]) -> float:
    """Per incoming lane, not per link: a lane with three turns must not weigh three times."""
    outs: dict[str, list[str]] = {}
    for src, dst in moves:
        outs.setdefault(src, []).append(dst)
    return sum(
        queue.get(src, 0) - sum(queue.get(d, 0) for d in dsts) / len(dsts)
        for src, dsts in outs.items()
    )


def should_advance(pressures: dict[int, float], current: int, max_green_reached: bool) -> bool:
    others = [p for i, p in pressures.items() if i != current]
    if not others:
        return False
    return max_green_reached or max(others) > pressures[current]


class _Signal:
    def __init__(self, tls_id: str, moves: dict[int, frozenset], capacity: dict[str, float]):
        self.id = tls_id
        self.min_green: dict[int, float] = {}
        self.moves = moves
        self.capacity = capacity
        self.phase: int | None = None
        self.green_start = 0.0
        self.next_decision = 0.0


class MaxPressureController(Controller):
    name = "maxpressure"
    label = "Max-pressure"

    def __init__(self, min_green: int = MIN_GREEN, max_green: int = MAX_GREEN):
        self.min_green = min_green
        self.max_green = max_green
        self.signals: dict[str, _Signal] = {}

    def activate(self, sumo, programs: dict) -> None:
        restore_programs(sumo, programs)
        self.signals = {}
        for tls_id, (program_id, logics) in programs.items():
            logic = next((lg for lg in logics if lg.programID == program_id), logics[0])
            links = sumo.trafficlight.getControlledLinks(tls_id)
            moves = decision_phases([p.state for p in logic.phases], links)
            if len(moves) < 2:
                continue
            lanes = {lane for m in moves.values() for pair in m for lane in pair}
            capacity = {lane: max(1.0, sumo.lane.getLength(lane) / VEHICLE_SPACE) for lane in lanes}
            signal = _Signal(tls_id, moves, capacity)
            # short programmed greens (7 s on some joined clusters) stay short
            signal.min_green = {i: min(self.min_green, logic.phases[i].duration) for i in moves}
            self.signals[tls_id] = signal

    def step(self, sumo) -> None:
        now = sumo.simulation.getTime()
        for sig in self.signals.values():
            phase = sumo.trafficlight.getPhase(sig.id)
            if phase != sig.phase:
                sig.phase = phase
                if phase in sig.moves:
                    sig.green_start = now
                    sig.next_decision = now + sig.min_green[phase]
                    sumo.trafficlight.setPhaseDuration(sig.id, HOLD)
                continue
            if phase not in sig.moves or now < sig.next_decision:
                continue
            sig.next_decision = now + DECISION
            queue = {
                lane: sumo.lane.getLastStepHaltingNumber(lane) / cap
                for lane, cap in sig.capacity.items()
            }
            pressures = {i: pressure(m, queue) for i, m in sig.moves.items()}
            if should_advance(pressures, phase, now - sig.green_start >= self.max_green):
                sumo.trafficlight.setPhaseDuration(sig.id, 0)

    def deactivate(self, sumo, programs: dict) -> None:
        self.signals = {}
        super().deactivate(sumo, programs)
