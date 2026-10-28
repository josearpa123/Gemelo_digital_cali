"""Observation: own phase and lanes plus aggregated queues of neighbouring intersections."""

import numpy as np
from gymnasium import spaces
from sumo_rl.environment.observations import ObservationFunction

from rl.neighbors import neighbor_map

MAX_NEIGHBORS = 4


class NeighborObservation(ObservationFunction):
    """[phase one-hot | min-green reached | time in phase | density | queue | neighbour queues]."""

    def _neighbors(self) -> tuple[str, ...]:
        return neighbor_map(self.ts.env._net)[self.ts.id][:MAX_NEIGHBORS]

    def __call__(self) -> np.ndarray:
        ts = self.ts
        phase = [1.0 if ts.green_phase == i else 0.0 for i in range(ts.num_green_phases)]
        elapsed = ts.time_since_last_phase_change
        min_green = [0.0 if elapsed < ts.min_green + ts.yellow_time else 1.0]
        time_in_phase = [min(1.0, elapsed / ts.max_green)]
        neighbor_queues = [0.0] * MAX_NEIGHBORS
        for i, other in enumerate(self._neighbors()):
            queues = ts.env.traffic_signals[other].get_lanes_queue()
            neighbor_queues[i] = float(np.mean(queues)) if queues else 0.0
        obs = phase + min_green + time_in_phase
        obs += ts.get_lanes_density() + ts.get_lanes_queue() + neighbor_queues
        return np.array(obs, dtype=np.float32)

    def observation_space(self) -> spaces.Box:
        size = self.ts.num_green_phases + 2 + 2 * len(self.ts.lanes) + MAX_NEIGHBORS
        return spaces.Box(low=0.0, high=1.0, shape=(size,), dtype=np.float32)
