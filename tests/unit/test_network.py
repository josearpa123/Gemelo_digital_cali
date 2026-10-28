from pathlib import Path

import pytest
import sumolib

from sim.network.build_osm import ZONES, describe

NET = Path("scenarios/roosevelt4/roosevelt4.net.xml")

pytestmark = pytest.mark.skipif(
    not NET.exists(), reason="run python -m sim.network.build_osm first"
)


def test_roosevelt4_has_four_traffic_lights_on_calle_6():
    net = sumolib.net.readNet(str(NET))
    tls = net.getTrafficLights()
    assert len(tls) == 4
    for t in tls:
        streets = {conn[0].getEdge().getName() for conn in t.getConnections()}
        assert "Calle 6" in streets


def test_roosevelt4_is_georeferenced_inside_cali_bbox():
    info = describe(NET)
    assert info["georeferenced"]
    south, west, north, east = ZONES["roosevelt4"]["bbox"]
    for lon, lat in info["tls_lonlat"]:
        assert south <= lat <= north
        assert west <= lon <= east


def test_roosevelt4_has_sidewalks_and_motorcycle_access():
    net = sumolib.net.readNet(str(NET))
    edges = net.getEdges()
    assert any(e.allows("pedestrian") for e in edges)
    assert any(e.allows("motorcycle") for e in edges)
