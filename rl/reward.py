"""Reward: r_i = -delta(waiting) - pressure_i ; r_hat_i = r_i + alpha * mean(r_neighbours)."""

from rl.neighbors import neighbor_map


def base_reward(ts, pressure_weight: float) -> float:
    # sumo-rl: _diff_waiting_time_reward = previous - current accumulated waiting (/100 s),
    # get_pressure = vehicles out - vehicles in, i.e. minus the intersection pressure.
    return ts._diff_waiting_time_reward() + pressure_weight * ts.get_pressure()


class NeighborReward:
    """Callable reward for sumo-rl. Base rewards are computed once per step for all agents,
    because the waiting-time difference is stateful and must not be evaluated twice."""

    def __init__(self, alpha: float = 0.0, pressure_weight: float = 0.05):
        self.alpha = alpha
        self.pressure_weight = pressure_weight
        self._step = None
        self._base: dict[str, float] = {}

    def __call__(self, ts) -> float:
        env = ts.env
        if self._step != env.sim_step or id(env) != getattr(self, "_env_id", None):
            self._step, self._env_id = env.sim_step, id(env)
            self._base = {
                tid: base_reward(sig, self.pressure_weight)
                for tid, sig in env.traffic_signals.items()
            }
        own = self._base[ts.id]
        neighbors = neighbor_map(env._net)[ts.id]
        if self.alpha == 0 or not neighbors:
            return own
        return own + self.alpha * sum(self._base[n] for n in neighbors) / len(neighbors)
