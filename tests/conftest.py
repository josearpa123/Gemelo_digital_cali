import os
import tempfile
from pathlib import Path

import pytest

# automated tests never call a real LLM nor write into the real outputs/traces.db
os.environ["LLM_PROVIDER"] = "fake"
_GROQ_KEY = os.environ.pop("GROQ_API_KEY", None)  # only handed to `live` tests
_TMP = Path(tempfile.mkdtemp(prefix="gemelo_tests_"))
os.environ.setdefault("TRACES_DB", str(_TMP / "traces.db"))
os.environ["LLM_KEY_FILE"] = str(_TMP / "secrets" / "llm_api_key")  # never the real secrets/

# sumo-rl needs traci.start: with LIBSUMO_AS_TRACI, importing libsumo before traci leaves
# traci without start(), so make traci the first one imported (test_sumo_runs imports libsumo)
import traci  # noqa: E402, F401, I001

from sim.network.grid import build_grid  # noqa: E402


@pytest.fixture(scope="session")
def grid_cfg(tmp_path_factory) -> Path:
    return build_grid(tmp_path_factory.mktemp("grid2x2"), seed=0, end=600)


def pytest_addoption(parser):
    parser.addoption("--run-live", action="store_true", help="run tests that call the real LLM")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return
    skip = pytest.mark.skip(reason="real LLM call: run with make test-live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def groq_key(request) -> str:
    if not request.config.getoption("--run-live"):
        pytest.skip("real LLM call: run with make test-live")
    from api.llm import keystore

    key = _GROQ_KEY or keystore.load()  # env file, or the key saved from the panel
    if not key:
        pytest.skip("no Groq key: set GROQ_API_KEY in the env file or save it from the panel")
    return key
