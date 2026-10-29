"""What must hold on any machine that runs the project: the image matches the pinned
requirements, SUMO/Python versions, the container user can write the volumes, and the
committed dataset manifest is reproduced bit for bit from the seeds."""

import csv
import os
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pytest

from sim import demand

NET = Path("scenarios/roosevelt4/roosevelt4.net.xml")
REQUIREMENTS = [Path("/tmp/requirements-sim.txt"), Path("/tmp/requirements-train.txt")]


def pinned() -> list[tuple[str, str]]:
    pins = []
    for req in REQUIREMENTS:
        if not req.exists():
            continue
        for line in req.read_text().splitlines():
            m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?==([^\s;#]+)", line.strip())
            if m:
                pins.append((m.group(1), m.group(3)))
    return pins


@pytest.mark.parametrize("name,version", pinned())
def test_installed_versions_match_requirements(name, version):
    """Fails when the image is older than docker/requirements-*.txt: run make build."""
    installed = metadata.version(name)
    assert installed.split("+")[0] == version.split("+")[0], f"{name} {installed} != {version}"


def test_python_and_sumo_versions():
    assert sys.version_info[:2] == (3, 11)
    out = subprocess.run(["sumo", "--version"], capture_output=True, text=True).stdout
    assert re.search(r"sumo 1\.28\.0", out), out.splitlines()[:1]
    assert os.environ.get("SUMO_HOME") and Path(os.environ["SUMO_HOME"]).is_dir()


@pytest.mark.parametrize("path", ["models", "outputs", "scenarios/roosevelt4/demand"])
def test_container_user_can_write_volumes(path):
    """Fails when the host uid/gid differs from the container user: use make (exports UID)."""
    probe = Path(path) / f".write_probe_{os.getpid()}"
    probe.write_text("ok")
    probe.unlink()


def test_code_does_not_depend_on_trained_models_or_outputs(tmp_path, monkeypatch):
    """A fresh clone has empty models/ and outputs/: the panel must still offer fixed and
    max-pressure."""
    from sim.controllers import rl_policy

    assert rl_policy.find_model(tmp_path / "models") is None


def test_dataset_reproduces_committed_manifest(tmp_path):
    """Same seeds -> same vehicles on every machine (catches SUMO/duarouter drift)."""
    net = tmp_path / NET.name
    net.write_bytes(NET.read_bytes())
    manifest = demand.build_dataset(net)
    committed = list(csv.DictReader((NET.parent / "demand" / "manifest.csv").open()))
    generated = list(csv.DictReader(manifest.open()))
    assert generated == committed
