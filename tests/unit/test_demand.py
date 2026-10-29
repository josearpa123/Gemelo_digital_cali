"""Demand dataset: valid routes, motorcycle share, disjoint splits, reproducibility, event."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import sumolib

from sim import demand
from sim.events import load_event

NET = Path("scenarios/roosevelt4/roosevelt4.net.xml")

pytestmark = pytest.mark.skipif(
    not NET.exists(), reason="run python -m sim.network.build_osm first"
)


@pytest.fixture(scope="module")
def net_copy(tmp_path_factory) -> Path:
    """Generate into a temp dir so the test never touches the real dataset."""
    out = tmp_path_factory.mktemp("roosevelt4") / NET.name
    out.write_bytes(NET.read_bytes())
    return out


@pytest.fixture(scope="module")
def peak(net_copy) -> Path:
    return demand.generate(net_copy, "peak", 0, end=900)


def test_train_and_eval_seeds_are_disjoint():
    assert not set(demand.TRAIN_SEEDS) & set(demand.EVAL_SEEDS)


def test_routes_are_valid_paths_in_the_network(peak):
    net = sumolib.net.readNet(str(NET))
    vehicles = list(ET.parse(peak).getroot().iter("vehicle"))
    assert vehicles
    for vehicle in vehicles:
        edges = vehicle.find("route").get("edges").split()
        for a, b in zip(edges, edges[1:], strict=False):
            assert net.getEdge(b) in net.getEdge(a).getOutgoing(), f"{vehicle.get('id')}: {a}->{b}"


def test_peak_has_30_to_40_percent_motorcycles(peak):
    counts = demand.count_types(peak)
    share = counts["moto"] / counts["vehicles"]
    assert 0.30 <= share <= 0.40
    assert counts["car"] + counts["moto"] == counts["vehicles"]


def test_peak_volume_matches_flow(peak):
    # duarouter --ignore-errors drops unroutable trips (~5-6 % on roosevelt4)
    expected = demand.FLOWS["peak"] * 900 / 3600
    assert 0.90 * expected <= demand.count_types(peak)["vehicles"] <= expected


def without_header(path: Path) -> str:
    """duarouter writes the generation timestamp in the leading XML comment."""
    return re.sub(r"<!--.*?-->", "", path.read_text(), count=1, flags=re.S)


def test_same_seed_gives_same_file(net_copy, peak):
    first = without_header(peak)
    again = demand.generate(net_copy, "peak", 0, end=900)
    assert without_header(again) == first


def test_event_scenario_has_a_lane_closure_on_the_corridor():
    event = load_event(NET)
    assert event is not None, "scenarios/roosevelt4/roosevelt4.event.json missing"
    net = sumolib.net.readNet(str(NET))
    assert net.getLane(event["lane"]).getEdge().getName() == demand.CORRIDOR
    assert 0 < event["begin"] < 3600 and event["duration"] > 0
