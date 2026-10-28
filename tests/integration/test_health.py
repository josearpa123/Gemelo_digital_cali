from fastapi.testclient import TestClient

from api.main import app


def test_health_reports_sumo_version():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["sumo"].startswith("Eclipse SUMO sumo 1.28")
