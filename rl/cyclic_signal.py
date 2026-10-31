"""Cyclic traffic signal for the RL agents: keep the current green or advance to the next
green of the program, through the program's own transitions.

sumo-rl's TrafficSignal replaces the program with every green state (pedestrian variants
included) plus 3 s yellows between any pair, so an agent jumps between arbitrary greens and
skips the clearance phases. On roosevelt4's joined clusters that gridlocks the short
internal lanes (the first max-pressure version did the same; see sim/controllers/
maxpressure.py). Here the program stays in SUMO, as in the cyclic max-pressure:

- decision greens = program phases with a distinct set of vehicle movements;
- every agent acts every `delta_time` s, in lockstep as in sumo-rl (rewards stay aligned);
- action 0 keeps the green (held with setPhaseDuration), action 1 advances: the program
  runs its own yellow / all-red / pedestrian phases until the next decision green;
- the action is ignored during those transitions and before the minimum green (as sumo-rl
  ignores actions during yellow), and reaching `max_green` advances whatever the action."""

from gymnasium import spaces
from sumo_rl.environment.traffic_signal import TrafficSignal

from sim.controllers.maxpressure import decision_phases

KEEP, ADVANCE = 0, 1
HOLD = 10_000  # remaining duration that keeps a green until the agent releases it


class CyclicTrafficSignal(TrafficSignal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.action_space = spaces.Discrete(2)
        # the min-green flag of the observation is `elapsed >= min_green + yellow_time`:
        # `elapsed` restarts when a green (or a transition) starts, so there is no yellow to add
        self.yellow_time = 0
        self.advanced = False
        self.forced = False
        self._phase = None
        self.green_start = self._now()
        self._sync()

    def _now(self) -> float:
        # the signal's own connection: sumo-rl builds its signals during __init__ through a
        # temporary connection, before the environment's own `sumo` attribute exists
        return float(self.sumo.simulation.getTime())

    def _build_phases(self):
        """Read the program (do not replace it) and find its decision greens."""
        tl = self.sumo.trafficlight
        program = tl.getProgram(self.id)
        logics = tl.getAllProgramLogics(self.id)
        logic = next((lg for lg in logics if lg.programID == program), logics[0])
        states = [p.state for p in logic.phases]
        self.decision = decision_phases(states, tl.getControlledLinks(self.id))
        self.green_order = sorted(self.decision)
        self.green_phases = [logic.phases[i] for i in self.green_order]
        self.num_green_phases = len(self.green_order)
        # short programmed greens (7 s on some joined clusters) stay short
        self.phase_min_green = {
            i: min(self.min_green, logic.phases[i].duration) for i in self.green_order
        }
        self.all_phases = list(logic.phases)

    def _sync(self) -> None:
        """Track the program: entering a decision green holds it until the agent releases it."""
        phase = self.sumo.trafficlight.getPhase(self.id)
        if phase == self._phase:
            return
        self._phase = phase
        self.time_since_last_phase_change = 0
        if phase in self.decision:
            self.green_phase = self.green_order.index(phase)
            self.green_start = self._now()
            self.min_green = self.phase_min_green[phase]
            self.is_yellow = False
            self.sumo.trafficlight.setPhaseDuration(self.id, HOLD)
        else:
            self.is_yellow = True  # program transition: actions are ignored

    @property
    def can_advance(self) -> bool:
        return self.num_green_phases >= 2

    def update(self):
        self.time_since_last_phase_change += 1
        self._sync()

    def set_next_phase(self, new_phase: int):
        """`new_phase` is the action: 0 keep, 1 advance (named as in sumo-rl's interface)."""
        now = self._now()
        self.next_action_time = now + self.delta_time
        self.advanced = self.forced = False
        if self._phase not in self.decision or not self.can_advance:
            return
        elapsed = now - self.green_start
        if elapsed < self.min_green:
            return
        advance = int(new_phase) == ADVANCE
        if not advance and elapsed >= self.max_green:
            advance = self.forced = True
        if advance:
            self.sumo.trafficlight.setPhaseDuration(self.id, 0)  # program goes on by itself
            self.advanced = True

    def next_green(self) -> int:
        return (self.green_phase + 1) % self.num_green_phases if self.num_green_phases else 0
