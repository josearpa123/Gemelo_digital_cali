from pathlib import Path

import pytest

from sim.network.grid import build_grid


@pytest.fixture(scope="session")
def grid_cfg(tmp_path_factory) -> Path:
    return build_grid(tmp_path_factory.mktemp("grid2x2"), seed=0, end=600)
