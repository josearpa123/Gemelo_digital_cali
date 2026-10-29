from pathlib import Path

import pytest

# sumo-rl needs traci.start: with LIBSUMO_AS_TRACI, importing libsumo before traci leaves
# traci without start(), so make traci the first one imported (test_sumo_runs imports libsumo)
import traci  # noqa: F401, I001

from sim.network.grid import build_grid


@pytest.fixture(scope="session")
def grid_cfg(tmp_path_factory) -> Path:
    return build_grid(tmp_path_factory.mktemp("grid2x2"), seed=0, end=600)
