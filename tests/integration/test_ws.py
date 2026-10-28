import time

import pytest
from fastapi.testclient import TestClient

from api import main

pytestmark = pytest.mark.skipif(
    not (main.NET.exists() and main.ROUTES.exists()), reason="run make dataset first"
)


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        c.post("/api/control", json={"action": "speed", "value": 50})
        yield c


def wait_for(client, predicate, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = client.get("/api/state").json()["snapshot"]
        if snap and predicate(snap):
            return snap
        time.sleep(0.2)
    raise AssertionError("condition not reached")


def test_network_geojson_has_roads_and_signals(client):
    geo = client.get("/api/network").json()
    kinds = {f["properties"]["kind"] for f in geo["features"]}
    assert {"road", "signal", "accident_site"} <= kinds
    lon, lat = next(f for f in geo["features"] if f["properties"]["kind"] == "signal")["geometry"][
        "coordinates"
    ]
    assert 3.40 < lat < 3.45 and -76.56 < lon < -76.52  # Cali


def test_websocket_streams_vehicles_and_four_traffic_lights(client):
    wait_for(client, lambda s: s["t"] > 30)
    with client.websocket_connect("/ws/state") as ws:
        state = ws.receive_json()
    assert len(state["tls"]) == 4
    assert all(set(t["state"]) <= set("GgyYrsuoO") for t in state["tls"])
    assert state["vehicles"], "no vehicles after 30 s"
    v = state["vehicles"][0]
    assert {"id", "lon", "lat", "type"} <= set(v)


def test_accident_closes_a_corridor_lane(client):
    import libsumo

    res = client.post("/api/control", json={"action": "accident", "value": True}).json()
    lane = res["accident_lane"]
    assert lane
    allowed = main.state.executor.submit(libsumo.lane.getAllowed, lane).result()
    assert list(allowed) == ["authority"]
    res = client.post("/api/control", json={"action": "accident", "value": False}).json()
    assert res["accident_lane"] is None
    allowed = main.state.executor.submit(libsumo.lane.getAllowed, lane).result()
    assert "passenger" in allowed


def test_strategy_selector_and_restart(client):
    res = client.post("/api/control", json={"action": "restart", "value": "fixed"}).json()
    assert res["strategy"] == "fixed"
    bad = client.post("/api/control", json={"action": "strategy", "value": "nope"})
    assert bad.status_code == 400
